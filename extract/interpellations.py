"""Seed des interpellations et gardes à vue lors des journées de mobilisation -> contexte.

Voir data/seed/README.md (`interpellations_mobilisations.csv`). Chiffres annoncés par une
autorité (ministère de l'Intérieur, préfecture de police, parquet), relevés dans des articles en
accès libre, chacun avec la phrase qui le porte. Un fait `interpellations_journee` par journée
et par périmètre (France entière, Paris), avec les mesures connues (interpellations, gardes à
vue). Donnée de contexte : elle n'entre dans aucun calcul du baromètre.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

EXTRACTOR = "seed_manuel"
SOURCE_ID = "seed_manuel"
SEED = "interpellations_mobilisations.csv"
INDICATOR = "contexte.interpellations"
COLONNES = (
    "date",
    "mouvement",
    "journee",
    "perimetre",
    "mesure",
    "nombre",
    "compte_par",
    "source_site",
    "source_titre",
    "source_url",
    "citation",
    "controle",
    "a_verifier",
    "note",
)
MESURES = ("interpellations", "gardes_a_vue")
PERIMETRES = ("France entière", "Paris")


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    docs = [d for d in latest_documents(conn, SOURCE_ID) if d["external_id"] == SEED]
    if not docs:
        return []
    doc = docs[0]
    reader = csv.DictReader(
        io.StringIO((raw_dir / doc["path"]).read_text(encoding="utf-8")), delimiter=";"
    )
    if tuple(reader.fieldnames or ()) != COLONNES:
        raise ValueError(f"{SEED} : colonnes inattendues {reader.fieldnames}")
    jours: dict[tuple[str, str], dict] = {}
    for i, row in enumerate(reader, 2):
        if row["mesure"] not in MESURES or row["perimetre"] not in PERIMETRES:
            raise ValueError(f"{SEED} ligne {i} : mesure ou périmètre inconnu")
        if not row["nombre"].isdigit() or not row["citation"].strip():
            raise ValueError(f"{SEED} ligne {i} : nombre ou citation manquant")
        if not row["source_url"].startswith("http"):
            raise ValueError(f"{SEED} ligne {i} : source manquante")
        jour = jours.setdefault(
            (row["date"], row["perimetre"]),
            {"mouvement": row["mouvement"], "journee": int(row["journee"]), "mesures": {}},
        )
        if row["mesure"] in jour["mesures"]:
            raise ValueError(f"{SEED} ligne {i} : {row['date']} {row['mesure']} en double")
        jour["mesures"][row["mesure"]] = {
            "nombre": int(row["nombre"]),
            "compte_par": row["compte_par"],
            "source_site": row["source_site"],
            "source_url": row["source_url"],
            "citation": row["citation"],
            "a_verifier": row["a_verifier"] == "oui",
            "note": row["note"] or None,
        }
    return [
        FactDraft(
            indicator_id=INDICATOR,
            fact_type="interpellations_journee",
            occurred_on=date,
            title=f"Interpellations, {perimetre}, {j['mouvement']} (journée {j['journee']})",
            official_ref=None,
            extraction_method=EXTRACTOR,
            raw_document_ids=(doc["id"],),
            attributes={"perimetre": perimetre, **j},
        )
        for (date, perimetre), j in sorted(jours.items())
    ]
