"""Archives DILA (fonds JORF et LEGI) -> faits `loi_promulguee` et `ordonnance_publiee`.

LEGI seul n'est pas exhaustif (textes consolidés uniquement) ; JORF couvre ce qui est
publié au Journal officiel. Les deux fonds partagent le format TEXTE_VERSION et les
identifiants JORFTEXT : on fusionne par CID, JORF puis LEGI (LEGI l'emporte en cas de
recouvrement), et le fait cite les archives des deux fonds.

Structure constatée (dumps du 2025-07-13 et incréments, exploration du 2026-10-26) :
  - chaque texte a un fichier .../<CID>/texte/version/<LEGITEXT>.xml (TEXTE_VERSION) ;
    les incréments reprennent les mêmes chemins préfixés par leur horodatage ;
  - identifiant stable d'un texte : META_TEXTE_CHRONICLE/CID (JORFTEXT...), plusieurs
    LEGITEXT pouvant partager un CID ; on dédoublonne par CID, le dernier état lu
    (dump puis incréments, dans l'ordre chronologique) l'emporte ;
  - nature : META_COMMUN/NATURE (LOI, LOI_ORGANIQUE, LOI_CONSTIT, ORDONNANCE...) ;
  - date du fait : DATE_TEXTE (date de signature : promulgation pour une loi) ;
  - fondement d'une ordonnance : articles de la Constitution cités dans les VISAS
    (« Vu la Constitution, notamment son article 38 »).

L'index des textes de chaque archive est mis en cache dans data/cache/, sous un nom
qui contient l'empreinte de l'archive et la version de l'extracteur : le cache est
dérivé, déterministe, et peut être supprimé sans perte.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tarfile
from collections import Counter
from pathlib import Path

from defusedxml import ElementTree as ET

from extract.common import INDICATOR_D2, FactDraft, latest_documents

EXTRACTOR = "dila_textes/4"
# Version du format de cache (lecture brute des archives), distincte de celle de l'extracteur :
# changer une règle de sélection ne demande pas de relire plusieurs Go.
SCAN_VERSION = "dila_textes_2"
UNKNOWN_DATE = "2999-01-01"  # date inconnue dans les fonds DILA
# Ordonnance du Gouvernement : numérotée (« Ordonnance n° 2014-697 », « n0 », « no »).
# Écarte les actes de nature ORDONNANCE qui n'en sont pas : ordonnances du premier
# président de la Cour de cassation, du préfet de police, rapports au Président de la
# République relatifs à une ordonnance (constaté le 2026-10-26, ~15 actes depuis 1958).
# Rectificatif (erratum) publié au JO comme un texte distinct, avec le numéro du texte
# corrigé : « LOI n° 2020-290 du 23 mars 2020 ... (rectificatif) ». À ne pas confondre avec
# une « loi de finances rectificative ».
RECTIFICATIF = re.compile(r"\brectificatif\b", re.IGNORECASE)
# Loi autorisant la ratification ou l'approbation d'un engagement international, repérée
# par son titre (seule information disponible de façon homogène depuis 1958).
#   - formulations sûres : « autorisant la ratification / l'approbation / l'adhésion ... »,
#     « autorisant le Président de la République à ratifier ... » ;
#   - formulations larges : verbe d'approbation suivi d'un objet conventionnel, sauf
#     accords internes (accord interprofessionnel, accord local, concession, conventions
#     entre l'État et une collectivité...).
_APO = r"['’]\s*"
TREATY_STRONG = re.compile(
    r"\bautoris\w*\s*:?\s*(?:1\w*\s*[-–.:]?\s*)?(?:la\s+|l" + _APO + r"|le\s+|les\s+)?"
    r"(?:ratification|approbation|adh[ée]sion|acceptation|d[ée]nonciation|retrait)"
    r"|\bautoris\w*\s+le\s+(?:pr[ée]sident\s+de\s+la\s+r[ée]publique|gouvernement[^;]{0,40}?)"
    r"\s+[àa]\s+(?:ratifier|approuver)"
    r"|\bautorisation\s+(?:de\s+|d" + _APO + r")(?:la\s+|l" + _APO + r")?"
    r"(?:ratification|ratifier|approbation|adh[ée]sion)"
    r"|\bportant\s+(?:approbation|publication)\s+(?:des?|du|de\s+la|de\s+l" + _APO + r")\s*"
    r"(?:accords?|conventions?|trait[ée]s?|protocoles?|avenants?|[ée]changes?\s+de\s+lettres)",
    re.IGNORECASE,
)
TREATY_BROAD = re.compile(
    r"\b(?:autoris\w*|approuv\w*|approbation|ratifi\w*|adh[ée]sion|accession)\b"
    r"[^;]{0,80}?\b(?:conventions?|accords?|trait[ée]s?|protocoles?|avenants?"
    r"|[ée]changes?\s+de\s+lettres|amendements?)\b",
    re.IGNORECASE,
)
DOMESTIC_AGREEMENT = re.compile(
    r"interprofessionnel|accord\s+local|concession|collectivit|par\s+ordonnances"
    r"|gouverneur\s+de\s+la\s+banque|entre\s+l" + _APO + r"[ée]tat\s+et",
    re.IGNORECASE,
)
GOVERNMENT_ORDONNANCE = re.compile(r"^\W*ordonnance\s+n\s*[°o0]\s*\d", re.IGNORECASE)
SOURCE_IDS = ("dila_jorf", "dila_legi")  # ordre de lecture : le dernier l'emporte
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "data" / "cache"

LOI_NATURES = ("LOI", "LOI_ORGANIQUE", "LOI_CONSTIT")
ORDONNANCE_NATURES = ("ORDONNANCE",)
NATURE_MARKERS = tuple(f"<NATURE>{n}</NATURE>".encode() for n in LOI_NATURES + ORDONNANCE_NATURES)
# Décrets et décisions : trop nombreux pour tout indexer ; on ne garde que ceux qui peuvent
# relever des régimes d'exception (D3) ou des dissolutions administratives (D4), repérés
# par un mot-clé dans le texte brut, puis par leur titre ou leurs visas.
OTHER_NATURES = ("DECRET", "DECISION")
OTHER_MARKERS = tuple(f"<NATURE>{n}</NATURE>".encode() for n in OTHER_NATURES)
OTHER_KEYWORDS = (b"dissolution", b"55-385", b"urgence", b"si\xc3\xa8ge", b"article 16")
OTHER_TITLE = re.compile(r"dissolution|55-385|urgence|si[èe]ge|article 16", re.IGNORECASE)
VISAS_MAX = 2000
LEGIFRANCE_URL = "https://www.legifrance.gouv.fr/jorf/id/{cid}"

# « article 38 », « articles 38 et 74-1 », « art. 92 »
CONSTITUTION_ARTICLES = re.compile(
    r"\b(?:articles?|art\.)\s+((?:\d+(?:-\d+)?(?:\s*(?:,|et)\s*)?)+)"
)


def parse_texte_version(data: bytes) -> dict | None:
    """Métadonnées d'un TEXTE_VERSION utile au baromètre, None sinon : lois et
    ordonnances, plus les décrets et décisions dont le titre relève de D3 ou D4."""
    other = any(marker in data for marker in OTHER_MARKERS)
    if other:
        lowered = data.lower()
        if not any(k in lowered for k in OTHER_KEYWORDS):
            return None
    elif not any(marker in data for marker in NATURE_MARKERS):
        return None
    root = ET.fromstring(data)
    nature = root.findtext("META/META_COMMUN/NATURE")
    if nature not in LOI_NATURES + ORDONNANCE_NATURES + OTHER_NATURES:
        return None
    chronicle = root.find("META/META_SPEC/META_TEXTE_CHRONICLE")
    version = root.find("META/META_SPEC/META_TEXTE_VERSION")
    visas = (
        " ".join(" ".join(root.find("VISAS").itertext()).split())
        if root.find("VISAS") is not None
        else ""
    )
    titre = (version.findtext("TITREFULL") or version.findtext("TITRE") or "").strip()
    if nature in OTHER_NATURES and not OTHER_TITLE.search(titre):
        return None
    meta = {
        "cid": chronicle.findtext("CID"),
        "legitext": root.findtext("META/META_COMMUN/ID"),
        "nature": nature,
        "num": chronicle.findtext("NUM") or None,
        "nor": chronicle.findtext("NOR") or None,
        "date_texte": chronicle.findtext("DATE_TEXTE"),
        "date_publi": chronicle.findtext("DATE_PUBLI"),
        "titre": titre,
        "constitution_articles": constitution_articles(visas),
    }
    if nature in OTHER_NATURES:
        meta["visas"] = visas[:VISAS_MAX]
    return meta


def constitution_articles(visas: str) -> list[str]:
    """Articles de la Constitution cités dans les visas (« Vu la Constitution, ... »)."""
    articles: list[str] = []
    for visa in re.split(r"[;]|\bVu\b", visas):
        if "Constitution" not in visa:
            continue
        for match in CONSTITUTION_ARTICLES.finditer(visa.split("Constitution", 1)[1]):
            for article in re.split(r"\s*(?:,|et)\s*", match.group(1)):
                if article and article not in articles:
                    articles.append(article)
    return articles


def ordonnance_fondement(articles: list[str]) -> str:
    """Fondement constitutionnel d'une ordonnance, lu dans ses visas."""
    for article in ("38", "74-1", "47", "47-1", "92"):
        if article in articles:
            return f"art{article}"
    return "inconnu"


def scan_archive(tar_path: Path) -> list[dict]:
    """Lit une archive LEGI en flux et retourne les textes trouvés, dans l'ordre lu."""
    texts = []
    with tarfile.open(tar_path, "r|gz") as archive:
        for member in archive:
            if not member.isfile() or "/texte/version/" not in member.name:
                continue
            meta = parse_texte_version(archive.extractfile(member).read())
            if meta:
                meta["member"] = member.name
                texts.append(meta)
    return texts


def cached_scan(raw_dir: Path, doc: sqlite3.Row, cache_dir: Path) -> list[dict]:
    cache = cache_dir / f"{doc['sha256']}.{SCAN_VERSION}.jsonl"
    if cache.exists():
        return [json.loads(line) for line in cache.read_text("utf-8").splitlines()]
    texts = scan_archive(raw_dir / doc["path"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in texts), "utf-8")
    tmp.replace(cache)
    return texts


def archive_order(doc: sqlite3.Row) -> tuple[int, str]:
    """Dump complet d'abord, puis incréments par horodatage (contenu dans le nom)."""
    name = doc["external_id"]
    return (0 if name.startswith("Freemium") else 1, name.rsplit("_", 1)[-1])


def exclusion_reason(text: dict) -> str | None:
    """Motif d'exclusion d'un texte, None s'il devient un fait."""
    if not text["date_texte"] or text["date_texte"] == UNKNOWN_DATE:
        return "date inconnue"
    if text["nature"] in ORDONNANCE_NATURES and not GOVERNMENT_ORDONNANCE.match(text["titre"]):
        return "ordonnance non gouvernementale ou non numérotée"
    return None


def is_convention_internationale(titre: str) -> bool:
    """Loi autorisant un engagement international (ratification, approbation...)."""
    if TREATY_STRONG.search(titre):
        return True
    return bool(TREATY_BROAD.search(titre)) and not DOMESTIC_AGREEMENT.search(titre)


def fact_type(text: dict) -> str:
    return "loi_promulguee" if text["nature"] in LOI_NATURES else "ordonnance_publiee"


def group_by_official_number(texts: list[dict]) -> list[list[dict]]:
    """Regroupe les textes d'un même acte : même type et même numéro officiel.

    Un même numéro peut apparaître sous plusieurs CID (texte et rectificatif, doublons
    entre fonds). Le premier texte de chaque groupe est la version de référence : non
    rectificatif d'abord, puis plus petit CID. Sans numéro, le CID fait l'identité.
    """
    groups: dict[tuple, list[dict]] = {}
    for text in texts:
        key = (fact_type(text), text["num"]) if text["num"] else ("cid", text["cid"])
        groups.setdefault(key, []).append(text)
    ordered = []
    for key in sorted(groups):
        members = groups[key]
        members.sort(key=lambda t: (bool(RECTIFICATIF.search(t["titre"])), t["cid"]))
        ordered.append(members)
    return ordered


def to_draft(group: list[dict], raw_ids: set[int]) -> FactDraft:
    text = group[0]
    is_loi = text["nature"] in LOI_NATURES
    attributes = {
        "cid": text["cid"],
        "cid_doublons": [t["cid"] for t in group[1:]],
        "nature": text["nature"],
        "nor": text["nor"],
        "date_publication": text["date_publi"],
        "url": LEGIFRANCE_URL.format(cid=text["cid"]),
    }
    if is_loi:
        attributes["convention_internationale"] = is_convention_internationale(text["titre"])
    else:
        # Les visas peuvent manquer dans une version : on réunit ceux de tout le groupe.
        articles = list(dict.fromkeys(a for t in group for a in t["constitution_articles"]))
        attributes["fondement"] = ordonnance_fondement(articles)
        attributes["constitution_articles"] = articles
    return FactDraft(
        indicator_id=INDICATOR_D2,
        fact_type=fact_type(text),
        occurred_on=text["date_texte"],
        title=text["titre"],
        official_ref=text["num"] or text["nor"] or text["cid"],
        extraction_method=EXTRACTOR,
        raw_document_ids=tuple(sorted(raw_ids)),
        attributes=attributes,
    )


def merged_texts(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> tuple[dict[str, dict], dict[str, set[int]]]:
    """Textes des fonds JORF puis LEGI fusionnés par CID, avec les archives qui les citent."""
    texts: dict[str, dict] = {}
    sources: dict[str, set[int]] = {}
    docs = [
        doc
        for source_id in SOURCE_IDS
        for doc in sorted(latest_documents(conn, source_id), key=archive_order)
    ]
    for doc in docs:
        for text in cached_scan(raw_dir, doc, cache_dir):
            texts[text["cid"]] = text  # le dernier état lu l'emporte
            sources.setdefault(text["cid"], set()).add(doc["id"])
    return texts, sources


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    """Lois et ordonnances (indicateur D2)."""
    all_texts, sources = merged_texts(conn, raw_dir, cache_dir)
    texts = {
        cid: t for cid, t in all_texts.items() if t["nature"] in LOI_NATURES + ORDONNANCE_NATURES
    }
    excluded = Counter(exclusion_reason(t) for t in texts.values())
    for reason, count in sorted((r, n) for r, n in excluded.items() if r):
        print(f"[extract] dila : {count} texte(s) écarté(s) — {reason}")
    kept = [texts[cid] for cid in sorted(texts) if exclusion_reason(texts[cid]) is None]
    groups = group_by_official_number(kept)
    merged = len(kept) - len(groups)
    if merged:
        print(f"[extract] dila : {merged} doublon(s) fusionné(s) par numéro officiel")
    return [to_draft(g, set().union(*(sources[t["cid"]] for t in g))) for g in groups]
