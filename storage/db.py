"""Accès à la base SQLite du baromètre.

Usage en ligne de commande :
    python -m storage.db init [--db CHEMIN]
    python -m storage.db reset-derived [--db CHEMIN]
    python -m storage.db reindex [--db CHEMIN] [--raw-dir DOSSIER]
    python -m storage.db verify-raw [--db CHEMIN] [--raw-dir DOSSIER]
    python -m storage.db fingerprint [--db CHEMIN]
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

import yaml

from storage import archive

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "barometre.sqlite"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SOURCES_PATH = ROOT / "config" / "sources.yaml"

# Ordre de suppression compatible avec les clés étrangères (enfants d'abord).
DERIVED_TABLES = ("score_facts", "scores", "metrics", "fact_sources", "facts")


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Ouvre la base avec les clés étrangères activées."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_sources(path: Path = SOURCES_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def init_db(conn: sqlite3.Connection, sources: list[dict[str, str]] | None = None) -> None:
    """Crée le schéma s'il n'existe pas et enregistre les sources. Idempotent."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    if sources is None:
        sources = load_sources()
    with conn:
        conn.executemany(
            """
            INSERT INTO sources (id, name, url, licence)
            VALUES (:id, :name, :url, :licence)
            ON CONFLICT (id) DO UPDATE SET
              name = excluded.name, url = excluded.url, licence = excluded.licence
            """,
            sources,
        )


def reset_derived(conn: sqlite3.Connection) -> None:
    """Vide toutes les tables dérivées. L'archive brute n'est pas touchée."""
    with conn:
        for table in DERIVED_TABLES:
            conn.execute(f"DELETE FROM {table}")


def fingerprint(conn: sqlite3.Connection) -> dict[str, str]:
    """Empreinte SHA-256 du contenu de chaque table dérivée (lignes triées)."""
    result = {}
    for table in reversed(DERIVED_TABLES):
        digest = hashlib.sha256()
        n_columns = len(conn.execute(f"PRAGMA table_info({table})").fetchall())
        order = ", ".join(str(i) for i in range(1, n_columns + 1))
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            digest.update(repr(tuple(row)).encode())
        result[table] = digest.hexdigest()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m storage.db")
    parser.add_argument(
        "command", choices=["init", "reset-derived", "reindex", "verify-raw", "fingerprint"]
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    raw_dir = args.raw_dir or archive.DEFAULT_RAW_DIR
    conn = connect(args.db)
    try:
        init_db(conn)
        if args.command == "reset-derived":
            reset_derived(conn)
            print(f"Tables dérivées vidées : {', '.join(DERIVED_TABLES)}")
        elif args.command == "reindex":
            added = archive.reindex(conn, raw_dir)
            print(f"Archive brute réindexée : {added} document(s) ajouté(s) à l'index")
        elif args.command == "verify-raw":
            problems = archive.verify(conn, raw_dir)
            for problem in problems:
                print(problem)
            print(f"Archive brute : {len(problems)} anomalie(s)")
            return 1 if problems else 0
        elif args.command == "fingerprint":
            for table, digest in fingerprint(conn).items():
                print(f"{table} {digest}")
        else:
            print(f"Base initialisée : {args.db}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
