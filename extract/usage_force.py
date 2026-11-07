"""Seed annuel de l'usage de la force (IGPN, Défenseur des droits) -> contexte, hors grille.

Voir data/seed/README.md (`usage_force_annuel.csv`). Un fait `usage_force_annee` par série et
par année : usages déclarés et munitions du LBD et de la grenade de désencerclement (IGPN,
police nationale, toutes circonstances), blessés graves lors d'opérations de maintien de
l'ordre ou de violences urbaines (IGPN), réclamations « déontologie de la sécurité » reçues
par le Défenseur des droits. Chaque valeur porte le document, la page et la ligne citée ; le
PDF est archivé par collectors/rapports.py. Donnée de contexte : aucune note n'en est tirée.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from collectors.rapports import SOURCE_ID as SOURCE_RAPPORTS
from collectors.rapports import nom
from extract.common import FactDraft, latest_documents

SEED = "usage_force_annuel.csv"
EXTRACTOR = "seed_manuel"
INDICATOR = "contexte.usage_force"
COLONNES = (
    "annee",
    "serie",
    "valeur",
    "organisme",
    "document",
    "source_url",
    "page_pdf",
    "citation",
    "controle",
    "note",
)
SERIES = (
    "igpn_lbd_declarations",
    "igpn_lbd_munitions",
    "igpn_gmd_declarations",
    "igpn_gmd_munitions",
    "igpn_blesses_mo_vu",
    "ddd_reclamations_deontologie",
)


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    seeds = [d for d in latest_documents(conn, "seed_manuel") if d["external_id"] == SEED]
    if not seeds:
        return []
    seed = seeds[0]
    pdfs = {d["external_id"]: d["id"] for d in latest_documents(conn, SOURCE_RAPPORTS)}
    reader = csv.DictReader(
        io.StringIO((raw_dir / seed["path"]).read_text(encoding="utf-8")), delimiter=";"
    )
    if tuple(reader.fieldnames or ()) != COLONNES:
        raise ValueError(f"{SEED} : colonnes inattendues {reader.fieldnames}")
    vus = set()
    drafts = []
    for i, row in enumerate(reader, 2):
        if row["serie"] not in SERIES:
            raise ValueError(f"{SEED} ligne {i} : série inconnue {row['serie']!r}")
        if not (row["annee"].isdigit() and row["valeur"].isdigit() and row["page_pdf"].isdigit()):
            raise ValueError(f"{SEED} ligne {i} : année, valeur ou page illisible")
        if (row["serie"], row["annee"]) in vus:
            raise ValueError(f"{SEED} ligne {i} : {row['serie']} {row['annee']} en double")
        vus.add((row["serie"], row["annee"]))
        pdf = pdfs.get(nom(row["source_url"]))
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="usage_force_annee",
                occurred_on=f"{row['annee']}-12-31",
                title=f"{row['serie']} {row['annee']}",
                official_ref=f"{row['source_url']}#page={row['page_pdf']}",
                extraction_method=EXTRACTOR,
                raw_document_ids=(seed["id"],) + ((pdf,) if pdf else ()),
                attributes={
                    "serie": row["serie"],
                    "annee": int(row["annee"]),
                    "valeur": int(row["valeur"]),
                    "organisme": row["organisme"],
                    "document": row["document"],
                    "url": f"{row['source_url']}#page={row['page_pdf']}",
                    "citation": row["citation"],
                    "note": row["note"] or None,
                },
            )
        )
    return drafts
