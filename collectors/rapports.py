"""Collecteur des rapports annuels cités par les relevés manuels (PDF officiels).

Archive une fois chaque PDF cité dans data/seed/usage_force_annuel.csv (rapports annuels de
l'IGPN et du Défenseur des droits, publiés sur vie-publique.fr) : les chiffres sont relevés à
la main dans le seed, ces documents en sont la preuve. Un PDF déjà archivé (même nom de
fichier) n'est pas retéléchargé.

Usage :
    python -m collectors.rapports [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "rapports_annuels"
SEED = Path(__file__).resolve().parent.parent / "data" / "seed" / "usage_force_annuel.csv"


def urls(seed: Path = SEED) -> list[str]:
    with seed.open(encoding="utf-8") as f:
        return sorted({r["source_url"] for r in csv.DictReader(f, delimiter=";")})


def nom(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def collect(
    conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen, seed: Path = SEED
) -> list[str]:
    collectes = []
    for url in urls(seed):
        if is_archived(conn, SOURCE_ID, nom(url)):
            continue
        with opener(url) as response:
            store(
                conn,
                raw_dir,
                source_id=SOURCE_ID,
                external_id=nom(url),
                url=url,
                fetched_at=now_iso(),
                chunks=iter_chunks(response),
                suffix=".pdf",
            )
        print(f"[rapports] {nom(url)}")
        collectes.append(nom(url))
    print(f"[rapports] {len(collectes)} rapport(s) collecté(s)")
    return collectes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.rapports")
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
