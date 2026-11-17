"""Questions écrites de l'Assemblée nationale -> réponse du Gouvernement dans le délai (D2.5).

Règle (article 135 du règlement de l'Assemblée nationale) : les réponses des ministres sont
publiées au Journal officiel dans les deux mois qui suivent la publication de la question, sans
interruption (depuis la résolution du 28 novembre 2014 ; avant, un mois prolongeable d'un mois au
plus : deux mois au maximum aussi). La série applique donc la même échéance à toute la période.

Un fait par question, daté de son échéance (publication de la question + deux mois) :
  - `question_ecrite_repondue_delai` si une réponse est publiée au plus tard à l'échéance ;
  - `question_ecrite_sans_reponse_delai` sinon (réponse plus tardive ou jamais publiée).
Écartées (le Gouvernement n'avait plus à répondre) :
  - question close avant l'échéance pour une autre raison qu'une réponse (fin de mandat de
    l'auteur, retrait…) ;
  - échéance postérieure à la fin de la législature (question devenue caduque) ;
  - échéance non encore atteinte à la date de collecte (le délai court encore).
Aucune donnée sur l'auteur (ni nom ni groupe) n'est conservée : seulement le ministère
interrogé, les dates et le lien public.
"""

from __future__ import annotations

import calendar
import datetime as dt
import io
import json
import sqlite3
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import yaml

from extract.common import FactDraft, latest_documents
from storage.db import ROOT

SOURCE_ID = "an_questions"
INDICATOR = "D2.questions_ecrites"
EXTRACTOR = "an_questions_ecrites/1"
URL = "https://questions.assemblee-nationale.fr/q{leg}/{leg}-{num}QE.htm"
LEGISLATURES_PATH = ROOT / "config" / "legislatures.yaml"


def jour(texte: str) -> dt.date:
    """Date de l'open data : « AAAA-MM-JJ » ou « JJ/MM/AAAA » (les deux se rencontrent)."""
    s = texte[:10]
    if "/" in s:
        return dt.date(int(s[6:10]), int(s[3:5]), int(s[:2]))
    return dt.date.fromisoformat(s)


def plus_deux_mois(d: dt.date) -> dt.date:
    m = d.month + 2
    a, m = d.year + (m - 1) // 12, (m - 1) % 12 + 1
    return dt.date(a, m, min(d.day, calendar.monthrange(a, m)[1]))


def liste(x) -> list:
    return x if isinstance(x, list) else ([x] if x else [])


def fins_legislatures(path: Path = LEGISLATURES_PATH) -> dict[int, dt.date | None]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        int(leg["numero"]): (dt.date.fromisoformat(str(leg["fin"])) if leg.get("fin") else None)
        for leg in data["legislatures"]
    }


def iter_questions(zip_path: Path) -> Iterator[dict]:
    """Questions d'un zip de l'open data : un JSON par question (législatures 15 et
    suivantes) ou un seul tableau pour toute la législature (14e : 575 Mo décompressé, lu en
    flux, une question à la fois, pour ne pas tout charger en mémoire)."""
    with zipfile.ZipFile(zip_path) as z:
        for nom in sorted(z.namelist()):
            if not nom.endswith(".json"):
                continue
            if z.getinfo(nom).file_size > GROS_FICHIER:
                with z.open(nom) as flux:
                    yield from questions_en_flux(io.TextIOWrapper(flux, encoding="utf-8"))
                continue
            data = json.loads(z.read(nom))
            if "question" in data and isinstance(data["question"], dict):
                yield data["question"]
            else:
                yield from _questions_dans(data)


GROS_FICHIER = 50_000_000


def questions_en_flux(texte: io.TextIOBase, bloc: int = 1 << 20) -> Iterator[dict]:
    """Objets du premier tableau `"question": [...]` d'un JSON lu par morceaux."""
    dec = json.JSONDecoder()
    buf = ""
    while '"question"' not in buf or "[" not in buf[buf.index('"question"') :]:
        lu = texte.read(bloc)
        if not lu:
            return
        buf += lu
    pos = buf.index("[", buf.index('"question"')) + 1
    while True:
        while pos < len(buf) and buf[pos] in " \n\r\t,":
            pos += 1
        if pos < len(buf) and buf[pos] == "]":
            return
        try:
            obj, pos = dec.raw_decode(buf, pos)
        except json.JSONDecodeError:
            lu = texte.read(bloc)
            if not lu:
                raise
            buf = buf[pos:] + lu  # on ne garde que la partie non lue
            pos = 0
            continue
        yield obj


def _questions_dans(data) -> Iterator[dict]:
    if isinstance(data, dict):
        if str(data.get("uid", "")).startswith("QANR") and "textesQuestion" in data:
            yield data
            return
        for v in data.values():
            yield from _questions_dans(v)
    elif isinstance(data, list):
        for v in data:
            yield from _questions_dans(v)


def statut(q: dict, fin_legislature: dt.date | None, collecte: dt.date) -> dict | None:
    """Échéance et réponse d'une question, ou None si elle est écartée (voir le module)."""
    if q.get("type") not in (None, "QE"):
        return None
    textes = liste((q.get("textesQuestion") or {}).get("texteQuestion"))
    dates = [jour(t["infoJO"]["dateJO"]) for t in textes if (t.get("infoJO") or {}).get("dateJO")]
    if not dates:
        return None
    publiee = min(dates)
    echeance = plus_deux_mois(publiee)
    if echeance >= collecte or (fin_legislature and echeance > fin_legislature):
        return None
    cloture = q.get("cloture") or {}
    if (
        cloture.get("codeCloture") not in (None, "REP_PUB")
        and cloture.get("dateCloture")
        and jour(cloture["dateCloture"]) <= echeance
    ):
        return None
    reponses = [
        jour(r["infoJO"]["dateJO"])
        for r in liste((q.get("textesReponse") or {}).get("texteReponse"))
        if (r.get("infoJO") or {}).get("dateJO")
    ]
    reponse = min(reponses) if reponses else None
    return {
        "publiee": publiee,
        "echeance": echeance,
        "reponse": reponse,
        "dans_delai": reponse is not None and reponse <= echeance,
    }


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    fins = fins_legislatures()
    out: list[FactDraft] = []
    ecartees: Counter = Counter()
    for doc in latest_documents(conn, SOURCE_ID):
        path = raw_dir / doc["path"]
        if not path.exists():
            continue
        collecte = dt.date.fromisoformat(doc["fetched_at"][:10])
        for q in iter_questions(path):
            ident = q.get("identifiant") or {}
            leg, num = int(ident.get("legislature") or 0), str(ident.get("numero") or "")
            s = statut(q, fins.get(leg), collecte)
            if s is None:
                ecartees[leg] += 1
                continue
            ministere = ((q.get("minInt") or {}).get("abrege") or "").strip() or None
            out.append(
                FactDraft(
                    indicator_id=INDICATOR,
                    fact_type="question_ecrite_repondue_delai"
                    if s["dans_delai"]
                    else "question_ecrite_sans_reponse_delai",
                    occurred_on=str(s["echeance"]),
                    title=f"Question écrite n° {num} ({leg}e législature)",
                    official_ref=q["uid"],
                    extraction_method=EXTRACTOR,
                    raw_document_ids=(doc["id"],),
                    attributes={
                        "legislature": leg,
                        "numero": num,
                        "publiee": str(s["publiee"]),
                        "reponse": str(s["reponse"]) if s["reponse"] else None,
                        "delai_jours": (s["reponse"] - s["publiee"]).days if s["reponse"] else None,
                        "ministere": ministere,
                        "signalee": bool(q.get("signalement")),
                        "url": URL.format(leg=leg, num=num),
                    },
                )
            )
    for leg, n in sorted(ecartees.items()):
        print(f"[extract] questions écrites L{leg} : {n} écartée(s) (close, caduque ou en délai)")
    return out
