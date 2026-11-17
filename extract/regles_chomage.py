"""Seed des périodes où l'État a fixé seul les règles de l'assurance chômage -> faits (D3.3).

L'assurance chômage est gérée par les organisations syndicales et patronales (Unédic) : ses
règles viennent d'une convention qu'elles négocient et que l'État agrée par arrêté. À défaut
d'accord agréé, l'État les fixe par décret (article L. 5422-20 et suivants du code du travail).
On relève les périodes où les règles en vigueur viennent d'un décret de l'État et non d'une
convention agréée : du décret qui les fixe à la veille de l'arrêté d'agrément de la convention
suivante. Les décrets d'application qui accompagnent une convention agréée (durées
d'indemnisation, taux) n'ouvrent pas de période.

Relevé à la main dans `data/seed/regles_assurance_chomage.csv` à partir d'un balayage des
titres du Journal officiel (archives DILA JORF, 1990-2026) ; chaque ligne cite les textes qui
ouvrent et ferment la période (identifiants JORFTEXT, liens Légifrance).
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

EXTRACTOR = "seed_manuel"
SOURCE_ID = "seed_manuel"
SEED = "regles_assurance_chomage.csv"
INDICATOR = "D3.regles_chomage_etat"
COLONNES = (
    "debut",
    "fin",
    "texte_debut",
    "cid_debut",
    "texte_fin",
    "cid_fin",
    "a_verifier",
    "note",
)
LEGIFRANCE = "https://www.legifrance.gouv.fr/jorf/id/{}"


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
    out = []
    for i, row in enumerate(reader, 2):
        if not row["cid_debut"].startswith("JORFTEXT") or (
            row["fin"] and not row["cid_fin"].startswith("JORFTEXT")
        ):
            raise ValueError(f"{SEED} ligne {i} : texte officiel manquant")
        if row["fin"] and row["fin"] < row["debut"]:
            raise ValueError(f"{SEED} ligne {i} : fin avant le début")
        out.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="periode_regles_chomage_etat",
                occurred_on=row["debut"],
                title=row["texte_debut"],
                official_ref=row["cid_debut"],
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    "fin": row["fin"] or None,
                    "url": LEGIFRANCE.format(row["cid_debut"]),
                    "texte_fin": row["texte_fin"] or None,
                    "url_fin": LEGIFRANCE.format(row["cid_fin"]) if row["cid_fin"] else None,
                    "a_verifier": row["a_verifier"] == "oui",
                    "note": row["note"] or None,
                },
            )
        )
    return out
