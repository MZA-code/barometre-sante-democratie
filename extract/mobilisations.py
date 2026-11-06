"""Seed manuel des journées de mobilisation nationale -> faits de contexte (hors grille).

Voir data/seed/README.md (`mobilisations_nationales.csv`) pour la source et la méthode.
Un fait `journee_mobilisation` par journée, portant côte à côte le décompte du ministère de
l'Intérieur et celui des organisateurs, chacun avec sa source et l'état de son contrôle.
Donnée de contexte : elle n'entre dans aucun calcul du baromètre.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

EXTRACTOR = "seed_manuel"
SOURCE_ID = "seed_manuel"
SEED = "mobilisations_nationales.csv"
INDICATOR = "contexte.mobilisations"
COMPTEURS = ("ministere_interieur", "organisateurs")


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    docs = [d for d in latest_documents(conn, SOURCE_ID) if d["external_id"] == SEED]
    if not docs:
        return []
    doc = docs[0]
    text = (raw_dir / doc["path"]).read_text(encoding="utf-8")
    days: dict[tuple[str, str], dict] = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if row["compteur"] not in COMPTEURS:
            raise ValueError(f"{SEED} : compteur inconnu {row['compteur']!r}")
        day = days.setdefault(
            (row["date"], row["perimetre"]),
            {"mouvement": row["mouvement"], "journee": int(row["journee"]), "compteurs": {}},
        )
        if row["compteur"] in day["compteurs"]:
            raise ValueError(f"{SEED} : {row['date']} {row['compteur']} en double")
        day["compteurs"][row["compteur"]] = {
            "manifestants": int(row["manifestants"]),
            "compte_par": row["compte_par"],
            "source_site": row["source_site"],
            "source_titre": row["source_titre"] or None,
            "source_url": row["source_url"],
            "verifie_dans_source": row["controle"].startswith("chiffre retrouvé"),
            "controle": row["controle"],
            "a_verifier": row["a_verifier"] == "oui",
            "note": row["note"] or None,
        }
    drafts = []
    for (date, perimetre), day in sorted(days.items()):
        c = day["compteurs"]
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="journee_mobilisation",
                occurred_on=date,
                title=(
                    f"Journée de mobilisation n° {day['journee']} ({day['mouvement']}), {perimetre}"
                ),
                official_ref=None,  # pas de référence officielle : sources de presse citées
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    "mouvement": day["mouvement"],
                    "journee": day["journee"],
                    "perimetre": perimetre,
                    "ministere_interieur": c.get("ministere_interieur"),
                    "organisateurs": c.get("organisateurs"),
                },
            )
        )
    return drafts
