"""Collecteur Eurostat — dépenses des administrations publiques par fonction (COFOG).

Jeu `gov_10a_exp` (comptes nationaux, classification des fonctions des administrations
publiques, COFOG) : dépenses totales (TE) des administrations publiques (S13), par fonction,
de 1995 à la dernière année publiée, pour la France, l'Allemagne, l'Italie, l'Espagne et la
moyenne de l'Union européenne à 27. Trois unités : millions d'euros courants, part du PIB,
part des dépenses publiques totales.

Un seul fichier (SDMX-CSV, ≈ 500 ko), téléchargé à chaque collecte ; une nouvelle version
n'est archivée que si son contenu change (Eurostat met le jeu à jour quelques fois par an).
Donnée de contexte : aucune note n'en est tirée.

Usage :
    python -m collectors.eurostat [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, store_if_content_changed
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "eurostat_cofog"
EXTERNAL_ID = "gov_10a_exp.csv"
PAYS = ("FR", "DE", "IT", "ES", "EU27_2020")
UNITES = ("MIO_EUR", "PC_GDP", "PC_TOT")
# Divisions COFOG, quelques groupes (intérêts de la dette, police, incendie, tribunaux,
# prisons) et le total.
FONCTIONS = (
    "TOTAL",
    "GF01",
    "GF0107",
    "GF02",
    "GF03",
    "GF0301",
    "GF0302",
    "GF0303",
    "GF0304",
    "GF04",
    "GF05",
    "GF06",
    "GF07",
    "GF08",
    "GF09",
    "GF10",
)
URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/gov_10a_exp/"
    f"A.{'+'.join(UNITES)}.S13.{'+'.join(FONCTIONS)}.TE.{'+'.join(PAYS)}"
    "?format=SDMX-CSV&compressed=false"
)


def collect(conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen) -> bool:
    with opener(URL) as response:
        data = response.read()
    doc = store_if_content_changed(
        conn,
        raw_dir,
        source_id=SOURCE_ID,
        external_id=EXTERNAL_ID,
        url=URL,
        fetched_at=now_iso(),
        data=data,
        suffix=".csv",
    )
    print(f"[eurostat] {EXTERNAL_ID} {'nouvelle version' if doc.created else 'inchangé'}")
    return doc.created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.eurostat")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
