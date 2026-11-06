"""Seed des déclarations de l'ONU visant la France -> contexte, hors grille.

Voir data/seed/README.md (`onu_declarations.csv`). Un fait `declaration_onu` par déclaration
(communiqué d'experts indépendants, point de presse du Haut-Commissariat, déclaration ou
observations d'un comité des traités), datée du jour de publication. Les extraits sont cités
mot pour mot depuis la page officielle ; aucune qualification n'est ajoutée. Donnée de
contexte : aucune note n'en est tirée.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

SEED = "onu_declarations.csv"
EXTRACTOR = "seed_manuel"
INDICATOR = "contexte.declarations_onu"
COLONNES = (
    "date",
    "organe",
    "type",
    "theme",
    "titre",
    "langue",
    "extrait",
    "extrait_complementaire",
    "source_url",
    "controle",
)
LANGUES = ("fr", "en")


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    seeds = [d for d in latest_documents(conn, "seed_manuel") if d["external_id"] == SEED]
    if not seeds:
        return []
    seed = seeds[0]
    text = (raw_dir / seed["path"]).read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if tuple(reader.fieldnames or ()) != COLONNES:
        raise ValueError(f"{SEED} : colonnes inattendues {reader.fieldnames}")
    drafts = []
    for i, row in enumerate(reader, 1):
        if row["langue"] not in LANGUES:
            raise ValueError(f"{SEED} ligne {i} : langue inconnue {row['langue']!r}")
        if not row["extrait"].strip() or not row["source_url"].startswith("https://"):
            raise ValueError(f"{SEED} ligne {i} : extrait ou source manquant")
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="declaration_onu",
                occurred_on=row["date"],
                title=row["titre"],
                official_ref=row["source_url"],
                extraction_method=EXTRACTOR,
                raw_document_ids=(seed["id"],),
                attributes={
                    "organe": row["organe"],
                    "type": row["type"],
                    "theme": row["theme"],
                    "langue": row["langue"],
                    "extrait": row["extrait"],
                    "extrait_complementaire": row["extrait_complementaire"] or None,
                    "url": row["source_url"],
                    "controle": row["controle"],
                },
            )
        )
    return drafts
