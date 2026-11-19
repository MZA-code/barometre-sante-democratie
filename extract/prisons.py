"""Population carcérale et capacité des prisons -> contexte, hors grille.

Deux sources :
  - Eurostat `crim_pris_cap` (collectors/eurostat.py) : personnes détenues et capacité
    officielle, chaque année depuis 2008, pays de l'Union européenne ; un fait
    `prisons_pays_annee` par pays et par année où les deux nombres sont publiés ;
  - statistique mensuelle du ministère de la Justice (data.gouv.fr, jeu `prisons_mensuel` de
    config/datagouv.yaml) : tableau 6, détenus et capacité opérationnelle au 1er du mois,
    France entière ; un fait `densite_carcerale_mois` par mois.
Le taux d'occupation (détenus / places) n'est pas noté : le baromètre le montre.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from pathlib import Path

from collectors.eurostat import EXTERNAL_ID_PRISONS, SOURCE_ID, URL_PRISONS
from extract.common import FactDraft, latest_documents
from extract.elections import xlsx_rows

INDICATOR = "contexte.prisons"
EXTRACTOR = "prisons@1"
JEU_MENSUEL = "5369a048a3a729239d206322"
UE27 = [
    "AT",
    "BE",
    "BG",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "EL",
    "ES",
    "FI",
    "FR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
]
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


def parse_eurostat(data: bytes) -> dict[tuple[str, int], dict]:
    out: dict[tuple[str, int], dict] = {}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        if row.get("unit") != "NR" or row["geo"] not in UE27 or not row["OBS_VALUE"]:
            continue
        cle = {"PRIS_ACT_CAP": "detenus", "PRIS_OFF_CAP": "capacite"}.get(row["indic_cr"])
        if cle:
            out.setdefault((row["geo"], int(row["TIME_PERIOD"])), {})[cle] = int(
                float(row["OBS_VALUE"])
            )
    return {k: v for k, v in out.items() if len(v) == 2 and v["capacite"]}


def parse_mensuel(data: bytes) -> dict | None:
    """Tableau 6 : date, capacité opérationnelle et détenus, France entière."""
    lignes = xlsx_rows(data, "Tab6")
    date = None
    for ligne in lignes:
        texte = " ".join(c for c in ligne if c)
        if m := re.search(r"au 1er (\w+) (\d{4})", texte):
            date = f"{m.group(2)}-{MOIS[m.group(1).lower()]:02d}-01"
        cellules = [c for c in ligne if c]
        if cellules and cellules[0].strip().lower() == "total france entière" and date:
            return {
                "mois": date,
                "capacite": int(float(cellules[2])),
                "detenus": int(float(cellules[3])),
            }
    return None


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    drafts = []
    for doc in latest_documents(conn, SOURCE_ID):
        if doc["external_id"] != EXTERNAL_ID_PRISONS:
            continue
        for (geo, annee), v in sorted(parse_eurostat((raw_dir / doc["path"]).read_bytes()).items()):
            drafts.append(
                FactDraft(
                    indicator_id=INDICATOR,
                    fact_type="prisons_pays_annee",
                    occurred_on=f"{annee}-12-31",
                    title=f"Prisons, {geo} {annee}",
                    official_ref=f"crim_pris_cap {geo} {annee}",
                    extraction_method=EXTRACTOR,
                    raw_document_ids=(doc["id"],),
                    attributes={"pays": geo, "annee": annee, **v, "url": URL_PRISONS},
                )
            )
    vus = set()
    for doc in latest_documents(conn, "datagouv"):
        if not doc["external_id"].startswith(f"{JEU_MENSUEL}/") or doc["path"].endswith(".json"):
            continue
        mesure = parse_mensuel((raw_dir / doc["path"]).read_bytes())
        if not mesure or mesure["mois"] in vus:
            continue
        vus.add(mesure["mois"])
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="densite_carcerale_mois",
                occurred_on=mesure["mois"],
                title=f"Densité carcérale au {mesure['mois']}",
                official_ref=doc["external_id"],
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={**mesure, "url": doc["url"]},
            )
        )
    return drafts
