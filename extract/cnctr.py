"""Seed des chiffres annuels de la CNCTR -> indicateur D6.1 (techniques de renseignement).

Voir data/seed/README.md (`cnctr_surveillance.csv`). Un fait `surveillance_annee` par année,
daté du 31 décembre de l'année comptée, citant le seed et le rapport PDF archivé qui contient
le chiffre (source `cnctr_rapports`). Métrique suivie : le nombre de personnes ayant fait
l'objet d'au moins une technique de renseignement (indicateur calculé par la CNCTR de façon
constante depuis 2016). Les demandes de techniques ne sont relevées que depuis 2023, année
où les rapports donnent un total unique (« techniques domestiques individuelles »).
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

SEED = "cnctr_surveillance.csv"
EXTRACTOR = "seed_manuel"
INDICATOR = "D6.techniques_renseignement"


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    seeds = [d for d in latest_documents(conn, "seed_manuel") if d["external_id"] == SEED]
    if not seeds:
        return []
    seed = seeds[0]
    rapports = {d["external_id"]: d["id"] for d in latest_documents(conn, "cnctr_rapports")}
    text = (raw_dir / seed["path"]).read_text(encoding="utf-8")
    drafts = []
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        annee = int(row["annee"])
        raw_ids = {seed["id"]} | (
            {rapports[row["rapport"]]} if row["rapport"] in rapports else set()
        )
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="surveillance_annee",
                occurred_on=f"{annee}-12-31",
                title=f"Personnes surveillées (techniques de renseignement), {annee}, CNCTR",
                official_ref=f"CNCTR {annee}",
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(raw_ids)),
                attributes={
                    "annee": annee,
                    "personnes_surveillees": int(row["personnes_surveillees"]),
                    "demandes_techniques": int(row["demandes_techniques"])
                    if row["demandes_techniques"]
                    else None,
                    "rapport": row["rapport"],
                    "url": row["rapport_url"],
                    "rapport_archive": row["rapport"] in rapports,
                    "a_verifier": row["a_verifier"] == "oui",
                    "note": row["note"] or None,
                },
            )
        )
    return drafts
