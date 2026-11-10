"""Archives DILA (JORF) -> crédits votés annulés par décret (indicateur D2.4).

Un décret « portant annulation de crédits » (article 14 de la loi organique relative aux lois de
finances) supprime des dépenses votées par le Parlement, sans nouveau vote. Son article 1 donne
le total : « Sont annulés, pour <année>, des crédits d'un montant de X € en autorisations
d'engagement et de Y € en crédits de paiement ». On retient Y, les crédits de paiement :
l'argent qui ne sera pas dépensé dans l'année.

Ne sont pas retenus les décrets « portant ouverture et annulation de crédits » (décrets
d'avance, virements, transferts) : leurs annulations compensent des ouvertures et ne réduisent
pas le budget voté. Les montants sont lus dans le texte publié, sans correction de l'inflation
ni rapport à la taille du budget (à lire avec cette limite).

Les articles sont lus dans les archives JORF déjà collectées (collectors/dila.py, fonds jorf),
mis en cache par archive (data/cache/budget/), comme pour extract/dila.py. Un même décret repris
par plusieurs archives n'est compté qu'une fois (numéro du décret).
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import tarfile
from pathlib import Path

from extract.common import FactDraft, latest_documents

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "data" / "cache"
SOURCE_ID = "dila_jorf"
INDICATOR = "D2.annulations_credits"
EXTRACTOR = "dila_annulations_credits/2"
SCAN_VERSION = "budget2"
TITRE_PUR = re.compile(r"^Décret n°\s*[\d-]+ du .+ portant annulation de crédits\s*$")
TEXTE = re.compile(r"<TEXTE ([^>]*)>")
ATTR = re.compile(r'(\w+)="([^"]*)"')
TITRE = re.compile(r"<TITRE_TXT[^>]*>([^<]*)</TITRE_TXT>")
CONTENU = re.compile(r"<CONTENU>(.*?)</CONTENU>", re.S)
NOMBRE = r"(\d[\d\u00a0\u202f .]*(?:,\d+)?)\s*(?:€|EUR|euros)?"
AE_ET_CP = re.compile(NOMBRE + r"\s*en autorisations d'engagement et en crédits de paiement")
CP = re.compile(r"de\s*" + NOMBRE + r"\s*en crédits de paiement")
AE = re.compile(NOMBRE + r"\s*en autorisations d'engagement")
CP_ANCIEN = re.compile(r"crédits? de paiement de\s*" + NOMBRE)
AP_ANCIEN = re.compile(r"autorisations? de programme de\s*" + NOMBRE)


def _nombre(texte: str) -> float:
    entier, _, decimales = re.sub(r"[^\d,]", "", texte).partition(",")
    return float(f"{entier}.{decimales or 0}")


def montants(phrase: str) -> tuple[float, float] | None:
    """(autorisations d'engagement, crédits de paiement) annulés, en euros, lus dans l'article 1.
    Formulations constatées de 2005 à 2026 (montants avec ou sans centimes, « € », « EUR »,
    « euros » ou rien ; un montant commun aux deux ; autorisations seules ; avant la LOLF,
    « crédit de paiement » et « autorisation de programme »)."""
    phrase = phrase.replace("’", "'")
    if m := AE_ET_CP.search(phrase):
        v = _nombre(m.group(1))
        return v, v
    cp, ae = CP.search(phrase), AE.search(phrase)
    if cp or ae:
        return (_nombre(ae.group(1)) if ae else 0.0, _nombre(cp.group(1)) if cp else 0.0)
    cp, ap = CP_ANCIEN.search(phrase), AP_ANCIEN.search(phrase)
    if cp or ap:
        return (_nombre(ap.group(1)) if ap else 0.0, _nombre(cp.group(1)) if cp else 0.0)
    return None


def lire_article(data: bytes) -> dict | None:
    """Article 1 d'un décret portant annulation de crédits, ou None."""
    if b"annulation de cr" not in data or b"annul" not in data:
        return None
    t = data.decode("utf-8", errors="replace")
    texte, titre = TEXTE.search(t), TITRE.search(t)
    if not texte or not titre:
        return None
    titre_txt = html.unescape(titre.group(1)).strip()
    if not TITRE_PUR.match(titre_txt):
        return None
    contenu = CONTENU.search(t)
    corps = (
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", contenu.group(1))).split())
        if contenu
        else ""
    )
    if not re.match(r"(Sont|Est) annulée?s?\b", corps):  # article 1, pas l'annexe
        return None
    lus = montants(corps)
    if lus is None:
        return None
    attrs = dict(ATTR.findall(texte.group(1)))
    return {
        "cid": attrs.get("cid"),
        "numero": attrs.get("num"),
        "date": attrs.get("date_signature"),
        "titre": titre_txt,
        "montant_ae": lus[0],
        "montant_cp": lus[1],
    }


def scan_archive(tar_path: Path) -> list[dict]:
    out = []
    with tarfile.open(tar_path, "r|gz") as archive:
        for member in archive:
            if not member.isfile() or "/article/" not in member.name:
                continue
            lu = lire_article(archive.extractfile(member).read())
            if lu:
                out.append(lu)
    return out


def cached_scan(raw_dir: Path, doc: sqlite3.Row, cache_dir: Path) -> list[dict]:
    cache = cache_dir / "budget" / f"{doc['sha256']}.{SCAN_VERSION}.jsonl"
    if cache.exists():
        return [json.loads(line) for line in cache.read_text("utf-8").splitlines()]
    trouves = scan_archive(raw_dir / doc["path"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in trouves), "utf-8")
    tmp.replace(cache)
    return trouves


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    decrets: dict[str, dict] = {}
    sources: dict[str, set[int]] = {}
    for doc in latest_documents(conn, SOURCE_ID):
        if not (raw_dir / doc["path"]).exists():
            continue
        for d in cached_scan(raw_dir, doc, cache_dir):
            decrets.setdefault(d["numero"], d)
            sources.setdefault(d["numero"], set()).add(doc["id"])
    return [
        FactDraft(
            indicator_id=INDICATOR,
            fact_type="decret_annulation_credits",
            occurred_on=d["date"],
            title=d["titre"],
            official_ref=numero,
            extraction_method=EXTRACTOR,
            raw_document_ids=tuple(sorted(sources[numero])),
            attributes={
                "montant_cp": d["montant_cp"],
                "montant_ae": d["montant_ae"],
                "montant_cp_md": d["montant_cp"] / 1e9,
                "url": f"https://www.legifrance.gouv.fr/jorf/id/{d['cid']}",
            },
        )
        for numero, d in sorted(decrets.items())
    ]
