"""Décisions de la justice administrative -> contentieux des interdictions de manifester.

Approximation automatique de l'indicateur D4.2 de la grille du comité (« Interdictions de
manifester », défini à partir des arrêtés préfectoraux, collecte semi-manuelle) : on ne voit
ici que les interdictions **contestées devant le juge**, et l'issue de chaque contestation.

Une décision est retenue si son texte :
  - cite l'article L. 211-4 du code de la sécurité intérieure (pouvoir d'interdire une
    manifestation) : la mention « sécurité intérieure » doit figurer près de la citation,
    car un article L. 211-4 existe aussi dans d'autres codes (patrimoine, relations entre le
    public et l'administration, pénitentiaire...) ;
  - ou, dans l'exposé des demandes (les 3 000 premiers caractères), contient une phrase qui
    associe une interdiction, une manifestation (ou un cortège, un défilé) et une autorité
    (arrêté, préfet, maire, décision) : « l'arrêté par lequel le préfet de police a interdit
    la manifestation », « prononçant des interdictions de rassemblements et de
    manifestations »... Limiter la recherche à l'exposé des demandes écarte les décisions
    qui ne font que mentionner une manifestation interdite (droit des étrangers,
    indemnisation...). Mise au point sur mars 2023 (tribunaux) et octobre 2026 (Conseil
    d'État), voir DECISIONS.md.
Seules les métadonnées sont conservées (juridiction, numéro, date, type de recours,
solution, formation) : le texte, même pseudonymisé, n'est ni stocké ni publié (CGU de
l'open data de la justice administrative : interdiction de réidentifier les personnes).

Unité : la décision. Une même interdiction peut donner lieu à plusieurs décisions (requêtes
de plusieurs associations jugées séparément, appel au Conseil d'État) : elles sont comptées
chacune ; ce n'est pas un nombre d'arrêtés.

Lecture des archives mise en cache dans data/cache/ (empreinte de l'archive + version du
format) : environ un million de décisions, relues seulement si le format change.
"""

from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from pathlib import Path

from defusedxml import ElementTree as ET

from extract.common import FactDraft, latest_documents
from storage.db import ROOT

SOURCE_ID = "justice_admin"
EXTRACTOR = "justice_manifestations/2"
SCAN_VERSION = "justice_manif_4"
INDICATOR = "D4.interdictions_manifester_juge"
DEFAULT_CACHE_DIR = ROOT / "data" / "cache"

L2114 = re.compile(r"L\.?\s*211-4\b")
DEMANDES = 3000  # caractères : exposé de la procédure et des demandes
PHRASE = re.compile(r"[^.;]+")
INTERDIT = re.compile(r"\binterdi\w*", re.IGNORECASE)
MANIF = re.compile(
    # « manifestation sportive / nautique… » : épreuves (sanctions antidopage, interdictions de
    # stade, courses), pas l'exercice de la liberté de manifester.
    r"\b(?:contre-)?manifestations?\b"
    r"(?!\s+(?:d['’]intérêt|de\s+(?:son|sa|leur|la\s+vérité)"
    r"|(?:sportive|nautique|aérienne|motorisée|automobile)s?\b))"
    r"|\bcortèges?\b|\bdéfilés?\b",
    re.IGNORECASE,
)
DOPAGE = re.compile(r"\bdopage\b|\bAFLD\b", re.IGNORECASE)
PREFILTRE_MANIF = tuple(m.encode() for m in ("anifestation", "ortège", "éfilé", "assemblement"))
AUTORITE = re.compile(r"\barrêté|\bpréfet|\bmaire\b|\bdécision\b", re.IGNORECASE)
# Appel ou pourvoi de l'administration devant le Conseil d'État (ex. DCE_490870_20240116) :
# la solution se lit alors à l'envers pour la personne qui conteste l'interdiction.
APPEL_ADMINISTRATION = re.compile(
    r"\b(?:le|la)\s+(?:ministre|préfète?|préfecture|commune|maire)\b[^.;]{0,200}?"
    r"\bdemande\s+au\s+(?:juge\s+des\s+référés\s+du\s+)?Conseil\s+d['’][EÉ]tat",
    re.IGNORECASE,
)
REFERE = re.compile(r"juge des référés|L\.\s*521-[12]\b", re.IGNORECASE)
FIELDS = (
    "Identification",
    "Code_Juridiction",
    "Nom_Juridiction",
    "Numero_Dossier",
    "Date_Lecture",
    "Numero_ECLI",
    "Type_Recours",
    "Solution",
    "Formation_Jugement",
)


def cites_csi_l2114(text: str) -> bool:
    for match in L2114.finditer(text):
        window = text[max(0, match.start() - 600) : match.end() + 150]
        if "sécurité intérieure" in window:
            return True
    return False


def motifs(text: str) -> list[str]:
    found = []
    if cites_csi_l2114(text):
        found.append("csi_l211-4")
    for phrase in PHRASE.finditer(text[:DEMANDES]):
        p = phrase.group(0)
        if DOPAGE.search(p):  # sanctions de l'AFLD : interdiction de compétitions
            continue
        if INTERDIT.search(p) and MANIF.search(p) and AUTORITE.search(p):
            found.append("demande_contre_interdiction")
            break
    return found


def issue(solution: str, appel_administration: bool = False) -> str:
    """Issue pour la personne qui conteste l'interdiction : le juge lui a-t-il donné raison ?

    « favorable_requerant » / « rejet » se lisent toujours de son point de vue : quand
    l'administration fait appel, rejeter son appel donne raison à celui qui contestait.
    """
    s = solution.lower()
    gagne = s.startswith("satisfaction") or "annulation" in s or "suspension" in s
    # « Rejet PAPC », « R.822-5 Rejet PAPC… » (non-admission d'un pourvoi au Conseil d'État)
    perdu = s.startswith("rejet") or re.match(r"r\.\s*822-5[-\d]*\s+rejet", s)
    if appel_administration:
        gagne, perdu = perdu, gagne
    if gagne:
        return "favorable_requerant"
    if perdu:
        return "rejet"
    if "non-lieu" in s or "non lieu" in s:
        return "non_lieu"
    return "autre"


def scan_xml(data: bytes) -> dict | None:
    # Pré-filtre sur les octets : la très grande majorité des décisions n'en parle pas. Une
    # décision peut ne parler que de « cortèges, défilés et rassemblements » (TA Paris,
    # n° 2306532, 28 mars 2023) : ces mots ouvrent aussi la lecture ; la sélection reste celle
    # de motifs().
    if b"211-4" not in data and not (
        b"nterdi" in data and any(mot in data for mot in PREFILTRE_MANIF)
    ):
        return None
    root = ET.fromstring(data)
    node = root.find(".//Texte_Integral")
    text = " ".join("".join(node.itertext()).split()) if node is not None else ""
    found = motifs(text)
    if not found:
        return None
    meta = {name: (root.findtext(f".//{name}") or "").strip() for name in FIELDS}
    meta["motifs"] = found
    meta["appel_administration"] = bool(APPEL_ADMINISTRATION.search(text[:DEMANDES]))
    meta["refere"] = bool(REFERE.search(meta["Formation_Jugement"])) or bool(
        REFERE.search(text[:3000])
    )
    return meta


def scan_archive(path: Path) -> list[dict]:
    found = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith(".xml"):
                meta = scan_xml(archive.read(name))
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


def to_draft(meta: dict, raw_ids: set[int]) -> FactDraft:
    juridiction = meta["Code_Juridiction"] or "?"
    return FactDraft(
        indicator_id=INDICATOR,
        fact_type="decision_interdiction_manifestation",
        occurred_on=meta["Date_Lecture"],
        title=f"{meta['Nom_Juridiction']}, {meta['Date_Lecture']}, n° {meta['Numero_Dossier']}",
        official_ref=meta["Numero_ECLI"] or f"{juridiction} {meta['Numero_Dossier']}",
        extraction_method=EXTRACTOR,
        raw_document_ids=tuple(sorted(raw_ids)),
        attributes={
            "juridiction": juridiction,
            "conseil_etat": juridiction == "CE",
            "numero": meta["Numero_Dossier"],
            "type_recours": meta["Type_Recours"],
            "formation": meta["Formation_Jugement"],
            "refere": meta["refere"],
            "solution": meta["Solution"],
            "appel_administration": meta["appel_administration"],
            "issue": issue(meta["Solution"], meta["appel_administration"]),
            "motifs": meta["motifs"],
            "fichier": meta["Identification"],
        },
    )


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    decisions: dict[str, dict] = {}
    sources: dict[str, set[int]] = {}
    for doc in latest_documents(conn, SOURCE_ID):
        for meta in cached_scan(raw_dir, doc, cache_dir):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["Date_Lecture"]):
                continue
            # Une décision republiée dans deux archives ne compte qu'une fois ; le nom de fichier
            # seul ne suffit pas (DTA_2301082_20230228.xml existe au TA67 et au TA78).
            key = f"{meta['Code_Juridiction']}/{meta['Identification']}"
            decisions[key] = meta
            sources.setdefault(key, set()).add(doc["id"])
    return [to_draft(decisions[k], sources[k]) for k in sorted(decisions)]
