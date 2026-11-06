"""Seed des mesures visant des journalistes -> indicateur D5.2 (journalistes inquiétés).

Voir data/seed/README.md (`journalistes_inquietes.csv`). Un fait `mesure_journaliste` par
mesure documentée (garde à vue, interpellation, poursuite, mise en examen, condamnation,
convocation), datée du jour de la mesure. Le nom des journalistes n'est pas relevé (donnée
personnelle sans utilité pour la mesure) : seuls le média, l'autorité et le contexte le sont.
Seules les mesures de `MESURES_COMPTEES` entrent dans la métrique ; les convocations et
auditions sont gardées en contexte.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

SEED = "journalistes_inquietes.csv"
EXTRACTOR = "seed_manuel"
INDICATOR = "D5.journalistes_inquietes"
MESURES_COMPTEES = ("garde_a_vue", "interpellation", "poursuite", "mise_en_examen", "condamnation")
LIBELLES = {
    "garde_a_vue": "Garde à vue",
    "interpellation": "Interpellation",
    "poursuite": "Poursuite",
    "mise_en_examen": "Mise en examen",
    "condamnation": "Condamnation",
    "convocation": "Convocation ou audition",
}


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    seeds = [d for d in latest_documents(conn, "seed_manuel") if d["external_id"] == SEED]
    if not seeds:
        return []
    seed = seeds[0]
    text = (raw_dir / seed["path"]).read_text(encoding="utf-8")
    drafts = []
    for i, row in enumerate(csv.DictReader(io.StringIO(text), delimiter=";"), 1):
        if row["mesure"] not in LIBELLES:
            raise ValueError(f"{SEED} ligne {i} : mesure inconnue {row['mesure']!r}")
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="mesure_journaliste",
                occurred_on=row["date"],
                title=f"{LIBELLES[row['mesure']]} : {row['media']} ({row['contexte']})",
                official_ref=None,
                extraction_method=EXTRACTOR,
                raw_document_ids=(seed["id"],),
                attributes={
                    "mesure": row["mesure"],
                    "comptee": row["mesure"] in MESURES_COMPTEES,
                    "nb_journalistes": int(row["nb_journalistes"]),
                    "media": row["media"],
                    "autorite": row["autorite"],
                    "contexte": row["contexte"],
                    "date_approximative": row["date_approximative"] == "oui",
                    "url": row["source_url"],
                    "extrait": row["extrait"],
                    "a_verifier": row["a_verifier"] == "oui",
                    "note": row["note"] or None,
                },
            )
        )
    return drafts
