"""Avis de la CNIL sur les projets de décret et décrets publiés -> indicateur D6.2.

Indicateur de la grille : « Traitements créés malgré réserves » — fichiers et traitements de
données publics créés par décret malgré un avis défavorable ou réservé de la CNIL.

Deux sources, toutes deux archivées depuis la DILA :
  - fonds CNIL : délibérations « portant avis sur un projet de décret » (titre) ;
  - fonds JORF et LEGI : décrets dont les visas citent la CNIL.

Avis réservé (critère strict, constaté le 2026-11-05) : seules comptent les formules par
lesquelles la CNIL qualifie elle-même son avis — « avis défavorable », « avis favorable sous
réserve(s) / assorti de réserves / avec réserves », « émet (de sérieuses / vives...) réserves »,
« exprime des réserves ». Les formules d'observation (« regrette », « demande que »,
« considère que ») ne sont pas comptées : les interpréter serait subjectif. Depuis 2018
(RGPD), la CNIL ne qualifie presque plus ses avis : le compte est structurellement plus
faible, ce que la lecture de l'indicateur doit dire.

Rapprochement avis -> décret publié, trois méthodes par ordre de sûreté (attribut
`rapprochement` de chaque fait) :
  1. « numero » : numéro de délibération cité dans les visas (« délibération n° 2020-001 ») ;
  2. « date » : date de l'avis citée dans les visas (« avis de la CNIL en date du 12 mars
     2009 ») quand un seul avis sur un projet de décret porte cette date ;
  3. « date_titre » : plusieurs avis le même jour (séances plénières) ; on retient celui dont
     le titre partage le plus de mots significatifs avec celui du décret (indice de Jaccard
     >= 0,15 et avance >= 0,08 sur le suivant), sinon rien. Constaté le 2026-11-05 : 366
     décrets dans ce cas, 249 rapprochés ainsi ; contrôle par sondage, à confirmer.
Confiance (attribut `confiance`) : « forte » pour « numero », « date_titre », et « date »
quand les titres partagent des mots (similarité >= 0,10) ; « faible » pour « date » avec des
titres sans rapport apparent. Constaté : un décret peut citer la date d'un avis de la CNIL
qui n'est pas celui de son propre projet (décret de 1991 sur les données fiscales rapproché
de l'avis sur le fichier du terrorisme) ; mais des titres sans mot commun peuvent aussi
désigner le même objet (« réquisitions télématiques » / « mise à disposition de données par
voie électronique »). Seuls les rapprochements de confiance forte sont comptés dans la
métrique notée ; les autres sont comptés à part (à vérifier).
"""

from __future__ import annotations

import json
import re
import sqlite3
import tarfile
from dataclasses import dataclass
from pathlib import Path

from defusedxml import ElementTree as ET

from extract.common import FactDraft, latest_documents

CNIL_SOURCE = "dila_cnil"
JORF_SOURCES = ("dila_jorf", "dila_legi")
EXTRACTOR = "cnil_avis_decrets/2"
SCAN_VERSION = "dila_decrets_cnil_1"
INDICATOR = "D6.traitements_malgre_reserves"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "data" / "cache"

PROJET_DECRET = re.compile(r"avis\s+sur\s+(?:un|le)\s+projet\s+de\s+décret", re.IGNORECASE)
RESERVE = {
    "defavorable": re.compile(
        r"(?:émet|rend|donne)\s+un\s+avis\s+défavorable|avis\s+défavorable\s+(?:au|sur)\s+",
        re.IGNORECASE,
    ),
    "favorable_sous_reserves": re.compile(
        r"avis\s+favorable\s+(?:sous\s+(?:les\s+)?réserves?|assorti\s+(?:de|des)\s+réserves?"
        r"|avec\s+(?:une\s+|des\s+)?réserves?)",
        re.IGNORECASE,
    ),
    "reserves": re.compile(
        r"(?:émet|formule|exprime)\s+(?:de\s+(?:fortes|sérieuses|vives|importantes|nettes)\s+"
        r"|des\s+|une\s+)?réserves?\b",
        re.IGNORECASE,
    ),
}
MOIS = {
    m: i
    for i, m in enumerate(
        [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ],
        1,
    )
}
_DATE = r"(\d{1,2})(?:er)?\s+(" + "|".join(MOIS) + r")\s+(\d{4})"
CNIL_MENTION = re.compile(r"informatique\s+et\s+(?:des\s+)?libertés", re.IGNORECASE)
DELIB_NUM = re.compile(r"délibération\s+n[°o]\s*(\d{2,4}-\d{2,4})", re.IGNORECASE)
AVIS_DATE = re.compile(
    r"(?:avis|délibération)[^;]{0,160}?(?:en\s+date\s+)?du\s+" + _DATE, re.IGNORECASE
)


def iso(day: str, month: str, year: str) -> str:
    return f"{year}-{MOIS[month.lower()]:02d}-{int(day):02d}"


def cnil_citations(visas: str) -> dict:
    """Numéros de délibération et dates d'avis de la CNIL cités dans des visas."""
    numeros, dates = set(), set()
    for visa in re.split(r";|\bVu\b", visas):
        if not CNIL_MENTION.search(visa):
            continue
        numeros.update(DELIB_NUM.findall(visa))
        dates.update(iso(*m.groups()) for m in AVIS_DATE.finditer(visa))
    return {"numeros": sorted(numeros), "dates": sorted(dates)}


def parse_decret(data: bytes) -> dict | None:
    """Décret dont les visas citent la CNIL, None sinon (pré-filtre sur les octets)."""
    if b"<NATURE>DECRET</NATURE>" not in data or b"nformatique et" not in data:
        return None
    root = ET.fromstring(data)
    visas_node = root.find("VISAS")
    if visas_node is None:
        return None
    visas = " ".join(" ".join(visas_node.itertext()).split())
    citations = cnil_citations(visas)
    if not citations["numeros"] and not citations["dates"]:
        return None
    chronicle = root.find("META/META_SPEC/META_TEXTE_CHRONICLE")
    version = root.find("META/META_SPEC/META_TEXTE_VERSION")
    return {
        "cid": chronicle.findtext("CID"),
        "num": chronicle.findtext("NUM") or None,
        "date_texte": chronicle.findtext("DATE_TEXTE"),
        "date_publi": chronicle.findtext("DATE_PUBLI"),
        "titre": (version.findtext("TITREFULL") or version.findtext("TITRE") or "").strip(),
        **citations,
    }


def scan_archive(path: Path) -> list[dict]:
    found = []
    with tarfile.open(path) as tar:
        for member in tar:
            name = member.name.rsplit("/", 1)[-1]
            if member.isfile() and name.endswith(".xml") and "TEXT" in name:
                meta = parse_decret(tar.extractfile(member).read())
                if meta is not None:
                    found.append(meta)
    return found


def cached_scan(raw_dir: Path, doc: sqlite3.Row, cache_dir: Path) -> list[dict]:
    cache = cache_dir / f"{doc['sha256']}.{SCAN_VERSION}.jsonl"
    if cache.exists():
        return [json.loads(line) for line in cache.read_text("utf-8").splitlines()]
    found = scan_archive(raw_dir / doc["path"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in found), "utf-8")
    tmp.replace(cache)
    return found


@dataclass
class Avis:
    id: str
    numero: str
    date: str
    titre: str
    reserves: list[str]
    raw_ids: set[int]


def read_avis(conn: sqlite3.Connection, raw_dir: Path) -> dict[str, Avis]:
    """Avis de la CNIL sur un projet de décret (dernière version de chaque délibération)."""
    docs = sorted(
        latest_documents(conn, CNIL_SOURCE),
        key=lambda d: (not d["external_id"].startswith("Freemium"), d["external_id"]),
    )
    avis: dict[str, Avis] = {}
    for doc in docs:
        with tarfile.open(raw_dir / doc["path"]) as tar:
            for member in tar:
                name = member.name.rsplit("/", 1)[-1]
                if not (member.isfile() and name.startswith("CNILTEXT") and name.endswith(".xml")):
                    continue
                data = tar.extractfile(member).read()
                if b"projet de d" not in data:
                    continue
                root = ET.fromstring(data)
                titre = (root.findtext(".//TITREFULL") or root.findtext(".//TITRE") or "").strip()
                if not PROJET_DECRET.search(titre):
                    continue
                node = root.find(".//CONTENU")
                text = " ".join("".join(node.itertext()).split()) if node is not None else ""
                ident = root.findtext(".//ID")
                previous = avis.get(ident)
                avis[ident] = Avis(
                    id=ident,
                    numero=(root.findtext(".//NUMERO") or "").strip(),
                    date=(root.findtext(".//DATE_TEXTE") or "").strip(),
                    titre=titre,
                    reserves=[k for k, rx in RESERVE.items() if rx.search(text)],
                    raw_ids=(previous.raw_ids if previous else set()) | {doc["id"]},
                )
    return avis


def dedup_avis(avis: dict[str, Avis]) -> dict[str, Avis]:
    """Une délibération publiée sous deux identifiants CNILTEXT (même numéro, même date) ne
    compte qu'une fois : on garde le plus petit identifiant, sources et réserves réunies."""
    by_key: dict[tuple[str, str], Avis] = {}
    out: dict[str, Avis] = {}
    for a in sorted(avis.values(), key=lambda a: a.id):
        if not a.numero:
            out[a.id] = a
            continue
        kept = by_key.get((a.numero, a.date))
        if kept is None:
            by_key[(a.numero, a.date)] = out[a.id] = a
        else:
            kept.raw_ids = kept.raw_ids | a.raw_ids
            kept.reserves = sorted(set(kept.reserves) | set(a.reserves))
    return out


def read_decrets(conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path) -> dict[str, dict]:
    """Décrets citant la CNIL, par identifiant JORF (dernière version lue l'emporte)."""
    decrets: dict[str, dict] = {}
    for source in JORF_SOURCES:
        docs = sorted(
            latest_documents(conn, source),
            key=lambda d: (not d["external_id"].startswith("Freemium"), d["external_id"]),
        )
        for doc in docs:
            for meta in cached_scan(raw_dir, doc, cache_dir):
                if not meta["cid"]:
                    continue
                previous = decrets.get(meta["cid"])
                raw_ids = (previous["raw_ids"] if previous else set()) | {doc["id"]}
                decrets[meta["cid"]] = {**meta, "raw_ids": raw_ids}
    return decrets


# Mots trop fréquents dans les titres pour distinguer deux avis du même jour.
STOP = set(
    [
        "de",
        "du",
        "des",
        "la",
        "le",
        "les",
        "l",
        "d",
        "un",
        "une",
        "à",
        "au",
        "aux",
        "et",
        "en",
        "pour",
        "par",
        "sur",
        "relatif",
        "relative",
        "portant",
        "projet",
        "décret",
        "conseil",
        "état",
        "etat",
        "avis",
        "délibération",
        "n°",
        "création",
        "traitement",
        "traitements",
        "automatisé",
        "automatisés",
        "données",
        "caractère",
        "personnel",
        "dénommé",
        "intitulé",
        "application",
        "article",
        "articles",
        "code",
        "mise",
        "œuvre",
        "oeuvre",
        "modifiant",
        "ministère",
        "ministre",
    ]
)
SIMILARITE_MIN, AVANCE_MIN = 0.15, 0.08
SIMILARITE_DATE = 0.10  # en deçà, un rapprochement par date seule est de confiance faible


def mots(titre: str) -> set[str]:
    # Mots d'au moins 3 caractères contenant une lettre : les années et numéros (« 2023 »)
    # sont présents dans presque tous les titres d'une même année et ne distinguent rien.
    return {
        w
        for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœ0-9-]{3,}", titre.lower())
        if w not in STOP and re.search(r"[a-zàâçéèêëîïôûùüÿœ]", w)
    }


def similarite(a: str, b: str) -> float:
    ma, mb = mots(a), mots(b)
    return len(ma & mb) / len(ma | mb) if ma | mb else 0.0


def match(decret: dict, by_numero: dict[str, Avis], by_date: dict[str, list[Avis]]) -> tuple:
    """Avis rapprochés d'un décret, méthode de rapprochement et score (date + titre)."""
    found = [by_numero[n] for n in decret["numeros"] if n in by_numero]
    if found:
        return found, "numero", None
    found = [by_date[d][0] for d in decret["dates"] if len(by_date.get(d, [])) == 1]
    if found:
        return found, "date", None
    candidats = [a for d in decret["dates"] for a in by_date.get(d, [])]
    if len(candidats) >= 2:
        notes = sorted(
            ((similarite(decret["titre"], a.titre), a) for a in candidats),
            key=lambda t: (-t[0], t[1].id),
        )
        (s1, best), (s2, _) = notes[0], notes[1]
        if s1 >= SIMILARITE_MIN and s1 - s2 >= AVANCE_MIN:
            return [best], "date_titre", round(s1, 3)
    return [], None, None


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    avis = dedup_avis(read_avis(conn, raw_dir))
    if not avis:
        return []
    by_numero = {a.numero: a for a in avis.values() if a.numero}
    by_date: dict[str, list[Avis]] = {}
    for a in avis.values():
        by_date.setdefault(a.date, []).append(a)
    decrets = read_decrets(conn, raw_dir, cache_dir)

    drafts, publies = [], {}
    for cid in sorted(decrets):
        d = decrets[cid]
        lies, methode, score = match(d, by_numero, by_date)
        if not lies or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["date_publi"] or ""):
            continue
        for a in lies:
            publies.setdefault(a.id, []).append(cid)
        reserves = sorted({r for a in lies for r in a.reserves})
        if methode == "date":
            score = round(max(similarite(d["titre"], a.titre) for a in lies), 3)
        confiance = "faible" if methode == "date" and score < SIMILARITE_DATE else "forte"
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="decret_apres_avis_cnil",
                occurred_on=d["date_publi"],
                title=d["titre"],
                official_ref=d["num"] or cid,
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(d["raw_ids"] | {i for a in lies for i in a.raw_ids})),
                attributes={
                    "cid": cid,
                    "avis": [
                        {"numero": a.numero, "date": a.date, "reserves": a.reserves} for a in lies
                    ],
                    "rapprochement": methode,
                    "score_titre": score,
                    "confiance": confiance,
                    "malgre_reserves": bool(reserves),
                    "formules": reserves,
                    "url": f"https://www.legifrance.gouv.fr/jorf/id/{cid}",
                },
            )
        )
    for a in sorted(avis.values(), key=lambda a: a.id):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.date):
            continue
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="avis_cnil_projet_decret",
                occurred_on=a.date,
                title=a.titre,
                official_ref=a.numero or a.id,
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(a.raw_ids)),
                attributes={
                    "cnil_id": a.id,
                    "reserves": a.reserves,
                    "avis_reserve": bool(a.reserves),
                    "decrets_publies": publies.get(a.id, []),
                    "url": f"https://www.legifrance.gouv.fr/cnil/id/{a.id}",
                },
            )
        )
    return drafts
