"""Recours contre les actes du Gouvernement jugés par le Conseil d'État -> faits (D3.5).

Le Conseil d'État juge en premier et dernier ressort les recours pour excès de pouvoir contre
les décrets, les ordonnances et les actes réglementaires des ministres (article R. 311-1 du
code de justice administrative). On retient, dans les archives mensuelles du Conseil d'État
(open data de la justice administrative, déjà collectées pour D4.2*), les décisions :
  - de type « Décision » (pas les ordonnances de tri ou de référé), sur un recours pour
    excès de pouvoir ;
  - dont les conclusions, adressées au Conseil d'État, demandent l'annulation d'un décret,
    d'une ordonnance, ou d'un arrêté, d'une circulaire ou d'une instruction d'un ministre
    (repérage dans le texte, après « demande(nt) au Conseil d'État » ; les circulaires
    d'organismes comme l'assurance maladie sont écartées) ;
  - tranchées au fond : « Rejet », « Satisfaction partielle », « Satisfaction totale ».
Fait `recours_acte_gouvernement`, daté de la lecture, avec l'issue (`annule` : satisfaction
totale ou partielle). Les archives du mois en cours (`.extrait.zip`) ne contiennent que les
décisions pré-filtrées pour D4.2* : un mois n'entre ici qu'une fois terminé.
"""

from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from pathlib import Path

from defusedxml import ElementTree as ET

from extract.common import FactDraft, latest_documents
from extract.manifestations import DEFAULT_CACHE_DIR, SOURCE_ID

INDICATOR = "D3.actes_annules_conseil_etat"
EXTRACTOR = "justice_admin_actes@2"
SCAN_VERSION = "ce_actes_2"
URL_DECISION = "https://www.conseil-etat.fr/fr/arianeweb/CE/decision/{date}/{numero}"
CONCLUSIONS = re.compile(r"demand\w* au Conseil d['’]Etat", re.I)
ACTE = re.compile(
    r"annuler pour excès de pouvoir [^.;]{0,80}?"
    r"(?P<acte>le décret|l['’]ordonnance n°"
    r"|(?:la circulaire|l['’]instruction|l['’]arrêté (?:du|de la|des|interministériel))"
    r"[^.;]{0,120}?(?:ministr|garde des sceaux))",
    re.I,
)
TRANCHEES = {"Rejet": False, "Satisfaction partielle": True, "Satisfaction totale": True}
NATURE = {"le décret": "décret", "l'ordonnance n°": "ordonnance", "la circulaire": "circulaire"}


def nature(acte: str) -> str:
    acte = acte.lower().replace("’", "'")
    if acte in NATURE:
        return NATURE[acte]
    if acte.startswith("la circulaire"):
        return "circulaire"
    return "instruction" if acte.startswith("l'instruction") else "arrêté ministériel"


def scan_xml(data: bytes) -> dict | None:
    if "cès de pouvoir".encode() not in data:
        return None
    root = ET.fromstring(data)
    dossier = root.find("Dossier")
    if dossier is None or dossier.findtext("Code_Juridiction", "").strip() != "CE":
        return None
    if dossier.findtext("Type_Recours", "").strip() != "Excès de pouvoir":
        return None
    if dossier.findtext("Type_Decision", "").strip() != "Décision":
        return None
    solution = dossier.findtext("Solution", "").strip()
    if solution not in TRANCHEES:
        return None
    node = root.find(".//Texte_Integral")
    texte = " ".join("".join(node.itertext()).split()) if node is not None else ""
    debut = CONCLUSIONS.search(texte[:6000])
    if not debut:
        return None
    m = ACTE.search(texte[debut.end() : debut.end() + 800])
    if not m:
        return None
    extrait = texte[debut.end() + m.start() : debut.end() + m.end() + 160]
    return {
        "date": dossier.findtext("Date_Lecture", "").strip(),
        "numero": dossier.findtext("Numero_Dossier", "").strip(),
        "ecli": dossier.findtext("Numero_ECLI", "").strip(),
        "fichier": root.findtext(".//Identification", "").strip(),
        "solution": solution,
        "nature": nature(m.group("acte")),
        "conclusions": extrait.split(";")[0].strip(),
        "formation": root.findtext(".//Formation_Jugement", "").strip(),
    }


def cached_scan(raw_dir: Path, doc: sqlite3.Row, cache_dir: Path) -> list[dict]:
    cache = cache_dir / f"{doc['sha256']}.{SCAN_VERSION}.jsonl"
    if cache.exists():
        return [json.loads(line) for line in cache.read_text("utf-8").splitlines()]
    found = []
    with zipfile.ZipFile(raw_dir / doc["path"]) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith(".xml") and (meta := scan_xml(archive.read(name))):
                found.append(meta)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in found), "utf-8")
    tmp.replace(cache)
    return found


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    decisions: dict[str, dict] = {}
    sources: dict[str, set[int]] = {}
    for doc in latest_documents(conn, SOURCE_ID):
        if not re.fullmatch(r"CE_\d{6}\.zip", doc["external_id"]):
            continue
        for meta in cached_scan(raw_dir, doc, cache_dir):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
                decisions[meta["fichier"]] = meta
                sources.setdefault(meta["fichier"], set()).add(doc["id"])
    drafts = []
    for cle in sorted(decisions):
        d = decisions[cle]
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="recours_acte_gouvernement",
                occurred_on=d["date"],
                title=f"Conseil d'État, {d['date']}, n° {d['numero']}",
                official_ref=d["ecli"] or f"CE {d['numero']}",
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(sources[cle])),
                attributes={
                    "annule": TRANCHEES[d["solution"]],
                    "issue": "annule" if TRANCHEES[d["solution"]] else "rejete",
                    "solution": d["solution"],
                    "nature": d["nature"],
                    "conclusions": d["conclusions"],
                    "numero": d["numero"],
                    "formation": d["formation"],
                    "url": URL_DECISION.format(date=d["date"], numero=d["numero"]),
                },
            )
        )
    return drafts
