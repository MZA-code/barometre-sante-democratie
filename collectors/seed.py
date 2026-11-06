"""Archive les seeds manuels (data/seed/*.csv) comme documents bruts, source `seed_manuel`.

Usage :
    python -m collectors.seed [--db CHEMIN] [--raw-dir DOSSIER] [--seed-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from collectors.http import now_iso
from storage.archive import DEFAULT_RAW_DIR, StoredDocument, store
from storage.db import DEFAULT_DB_PATH, ROOT, connect, init_db

SOURCE_ID = "seed_manuel"
DEFAULT_SEED_DIR = ROOT / "data" / "seed"


def collect(conn: sqlite3.Connection, raw_dir: Path, seed_dir: Path) -> list[StoredDocument]:
    docs = []
    for path in sorted(seed_dir.glob("*.csv")):
        doc = store(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=path.name,
            url=f"data/seed/{path.name}",
            fetched_at=now_iso(),
            chunks=[path.read_bytes()],
            suffix=".csv",
        )
        state = "nouvelle version" if doc.created else "inchangé"
        print(f"[seed_manuel] {path.name} : {state} ({doc.sha256[:12]})")
        docs.append(doc)
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.seed")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, args.seed_dir)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
