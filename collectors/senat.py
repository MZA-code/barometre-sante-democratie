"""Collecteur open data du Sénat — base des dossiers législatifs (Dosleg).

    https://data.senat.fr/data/dosleg/dosleg.zip

Un dump PostgreSQL (un fichier dosleg.sql, ≈ 127 Mo, ≈ 16 Mo compressé) : documents
déposés au Sénat depuis octobre 1977 et textes adoptés depuis octobre 1958. Licence :
celle de data.senat.fr, qui reprend la Licence Ouverte.

Le fichier est régénéré chaque nuit. Comme pour l'Assemblée, une nouvelle version n'est
archivée que si le contenu du zip a changé (le dump ne contient pas d'horodatage). Le
collecteur est lancé une fois par semaine par ops/quotidien.py : le contenu change presque
chaque nuit, et une collecte quotidienne coûterait ≈ 6 Go par an.

Usage :
    python -m collectors.senat [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, StoredDocument, store_if_content_changed
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "senat_dosleg"
URL = "https://data.senat.fr/data/dosleg/dosleg.zip"
EXTERNAL_ID = "dosleg.zip"


def collect(conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen) -> StoredDocument:
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
        suffix=".zip",
    )
    state = "nouvelle version" if doc.created else "contenu inchangé"
    print(f"[senat_dosleg] {EXTERNAL_ID} : {state} ({doc.sha256[:12]})")
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.senat")
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
