"""Seed manuel des engagements 49.3 antérieurs à l'open data de l'Assemblée -> faits.

Voir data/seed/README.md pour la source et la méthode de construction.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from pathlib import Path

from extract.common import INDICATOR_D2, FactDraft, latest_documents

EXTRACTOR = "seed_manuel"
SOURCE_ID = "seed_manuel"
SEED_49_3 = "49_3_historique.csv"
# Suffrages d'une motion : « 277-109 » (requis-obtenus) ou « 288 requis / 177 obtenus ».
SUFFRAGES = re.compile(r"(\d+)\s*(?:-|requis\s*/)\s*(\d+)")


def censure_adoptee(motion: str) -> bool:
    """Vrai si l'une des motions a obtenu au moins la majorité requise."""
    return any(int(obtenus) >= int(requis) for requis, obtenus in SUFFRAGES.findall(motion))


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    drafts = []
    for doc in latest_documents(conn, SOURCE_ID):
        if doc["external_id"] != SEED_49_3:
            continue
        text = (raw_dir / doc["path"]).read_text(encoding="utf-8")
        for row in csv.DictReader(io.StringIO(text), delimiter=";"):
            objet = f" ({row['objet']})" if row["objet"] else ""
            drafts.append(
                FactDraft(
                    indicator_id=INDICATOR_D2,
                    fact_type="engagement_49_3",
                    occurred_on=row["date_engagement"],
                    title=f"{row['texte']}{objet}",
                    official_ref=None,  # pas de numéro officiel : date et page source
                    extraction_method=EXTRACTOR,
                    raw_document_ids=(doc["id"],),
                    attributes={
                        "legislature": int(row["legislature"]),
                        "lecture": row["objet"] or None,
                        "texte_uid": f"seed:{row['texte_id']}",
                        "texte_titre": row["texte"],
                        "texte_rattache": True,
                        "censure_adoptee": censure_adoptee(row["motion_censure"]),
                        "date_source": row["date_source"],
                        "motion_censure": row["motion_censure"],
                        "note": row["note"] or None,
                        "url": row["source_url"],
                    },
                )
            )
    return drafts
