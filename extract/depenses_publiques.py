"""Dépenses publiques par fonction (Eurostat, COFOG) -> contexte, hors grille.

Un fait `depenses_fonction_annee` par pays (ou moyenne de l'UE) et par année, qui porte,
pour chaque fonction relevée par collectors/eurostat.py, le montant en millions d'euros
courants, la part du PIB et la part des dépenses publiques totales telles que publiées par
Eurostat. Les données provisoires (drapeau « p ») sont signalées. Aucune note n'en est tirée :
le baromètre ne juge pas la répartition du budget, il la montre.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from collectors.eurostat import EXTERNAL_ID, FONCTIONS, PAYS, SOURCE_ID, UNITES, URL
from extract.common import FactDraft, latest_documents

INDICATOR = "contexte.depenses_publiques"
EXTRACTOR = "eurostat_cofog@1"

LIBELLES = {
    "TOTAL": "Total des dépenses publiques",
    "GF01": "Services publics généraux",
    "GF0107": "dont intérêts de la dette publique",
    "GF02": "Défense",
    "GF03": "Ordre et sécurité publics",
    "GF0301": "dont police",
    "GF0302": "dont incendie et secours",
    "GF0303": "dont tribunaux",
    "GF0304": "dont prisons",
    "GF04": "Affaires économiques",
    "GF05": "Protection de l'environnement",
    "GF06": "Logement et équipements collectifs",
    "GF07": "Santé",
    "GF08": "Loisirs, culture et culte",
    "GF09": "Enseignement",
    "GF10": "Protection sociale",
}


def parse(data: bytes) -> dict[tuple[str, int], dict]:
    """(pays, année) -> {"valeurs": {fonction: {unité: valeur}}, "provisoire": bool}."""
    out: dict[tuple[str, int], dict] = {}
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    for row in reader:
        if row.get("sector") != "S13" or row.get("na_item") != "TE":
            continue
        geo, fonction, unite = row["geo"], row["cofog99"], row["unit"]
        if geo not in PAYS or fonction not in FONCTIONS or unite not in UNITES:
            continue
        if not row["OBS_VALUE"]:
            continue
        entry = out.setdefault((geo, int(row["TIME_PERIOD"])), {"valeurs": {}, "provisoire": False})
        entry["valeurs"].setdefault(fonction, {})[unite] = float(row["OBS_VALUE"])
        if "p" in (row.get("OBS_FLAG") or ""):
            entry["provisoire"] = True
    return out


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    docs = [d for d in latest_documents(conn, SOURCE_ID) if d["external_id"] == EXTERNAL_ID]
    if not docs:
        return []
    doc = docs[0]
    drafts = []
    for (geo, annee), entry in sorted(parse((raw_dir / doc["path"]).read_bytes()).items()):
        if "TOTAL" not in entry["valeurs"]:
            continue
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="depenses_fonction_annee",
                occurred_on=f"{annee}-12-31",
                title=f"Dépenses publiques par fonction, {geo} {annee}",
                official_ref=f"gov_10a_exp {geo} {annee}",
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    "pays": geo,
                    "annee": annee,
                    "provisoire": entry["provisoire"],
                    "valeurs": entry["valeurs"],
                    "url": URL,
                },
            )
        )
    return drafts
