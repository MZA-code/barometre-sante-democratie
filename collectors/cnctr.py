"""Collecteur CNCTR — rapports d'activité (PDF) de la Commission nationale de contrôle des
techniques de renseignement.

Liste des rapports : https://www.cnctr.fr/rapports-activité (liens vers cms.cnctr.fr). Les
communiqués de presse ne sont pas archivés. Un rapport déjà archivé (même nom de fichier)
n'est pas retéléchargé. Les chiffres annuels sont relevés à la main dans
data/seed/cnctr_surveillance.csv ; ces PDF archivés en sont la preuve.

Usage :
    python -m collectors.cnctr [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "cnctr_rapports"
LIST_URL = "https://www.cnctr.fr/rapports-activit%C3%A9"
PDF = re.compile(r'href="(https://cms\.cnctr\.fr/uploads/[^"]+\.pdf)"')


def list_reports(html: str) -> list[str]:
    return sorted({u for u in PDF.findall(html) if "communique" not in u.lower()})


def collect(conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen) -> list[str]:
    with opener(LIST_URL) as response:
        html = response.read().decode("utf-8", errors="replace")
    collected = []
    for url in list_reports(html):
        name = url.rsplit("/", 1)[-1]
        if is_archived(conn, SOURCE_ID, name):
            continue
        with opener(url) as response:
            store(
                conn,
                raw_dir,
                source_id=SOURCE_ID,
                external_id=name,
                url=url,
                fetched_at=now_iso(),
                chunks=iter_chunks(response),
                suffix=".pdf",
            )
        print(f"[cnctr] {name}")
        collected.append(name)
    print(f"[cnctr] {len(collected)} rapport(s) collecté(s)")
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.cnctr")
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
