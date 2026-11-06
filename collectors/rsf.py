"""Collecteur Reporters sans frontières — classement mondial de la liberté de la presse.

Un fichier CSV par édition (constaté le 2026-11-05), lien publié sur rsf.org/fr/classement :
    https://rsf.org/sites/default/files/import_classement/<année>.csv
Éditions disponibles : 2002 à 2026, sauf 2011 (édition « 2011-2012 » publiée en 2012). Les
éditions passées ne sont pas retéléchargées ; l'année en cours et la suivante le sont à chaque
collecte (nouvelle version archivée seulement si le contenu change). Source externe (indicateur
« Externe » de la grille) : RSF en est l'auteur, le baromètre ne fait que la reprendre.

Usage :
    python -m collectors.rsf [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
import urllib.error
from pathlib import Path

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "rsf_classement"
URL = "https://rsf.org/sites/default/files/import_classement/{annee}.csv"
FIRST_YEAR = 2002


def collect(
    conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen, today: dt.date | None = None
) -> list[str]:
    today = today or dt.date.today()
    collected = []
    for annee in range(FIRST_YEAR, today.year + 2):
        name = f"{annee}.csv"
        recent = annee >= today.year
        if not recent and is_archived(conn, SOURCE_ID, name):
            continue
        url = URL.format(annee=annee)
        try:
            with opener(url) as response:
                doc = store(
                    conn,
                    raw_dir,
                    source_id=SOURCE_ID,
                    external_id=name,
                    url=url,
                    fetched_at=now_iso(),
                    chunks=iter_chunks(response),
                    suffix=".csv",
                )
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            continue  # édition inexistante (2011) ou pas encore publiée
        if doc.created:
            print(f"[rsf] {name}")
            collected.append(name)
    print(f"[rsf] {len(collected)} édition(s) collectée(s)")
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.rsf")
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
