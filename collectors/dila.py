"""Collecteur DILA — fonds LEGI, JORF, CONSTIT et CNIL (https://echanges.dila.gouv.fr/OPENDATA/).

Chaque fonds publie :
  - un dump complet  Freemium_<fonds>_global_AAAAMMJJ-HHMMSS.tar.gz (LEGI ~1,1 Go,
    JORF ~1,6 Go au 2025-07-13) ;
  - des incréments   <FONDS>_AAAAMMJJ-HHMMSS.tar.gz.

LEGI ne contient que les textes consolidés par la DILA : il n'est pas exhaustif
(constaté le 2026-10-26, voir DECISIONS.md). JORF contient tout ce qui est publié au
Journal officiel ; les deux fonds partagent les identifiants JORFTEXT. CONSTIT contient
les décisions du Conseil constitutionnel (DC, QPC, etc.), CNIL les délibérations de la
Commission nationale de l'informatique et des libertés.

Stratégie incrémentale : on archive le dump complet le plus récent s'il n'y en a encore
aucun, puis chaque incrément postérieur au dump complet archivé qui ne l'est pas déjà.
Les noms de fichier DILA servent d'identifiant externe : une archive déjà collectée
n'est jamais retéléchargée.

Usage :
    python -m collectors.dila --fund legi|jorf|constit|cnil [--db CHEMIN] [--raw-dir DOSSIER]
                              [--max N]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, record_check, store
from storage.db import DEFAULT_DB_PATH, connect, init_db


@dataclass(frozen=True)
class Fund:
    source_id: str
    base_url: str
    archive_name: re.Pattern

    def parse_listing(self, html: str) -> list[Archive]:
        """Extrait les archives d'une page d'index, triées chronologiquement."""
        found = {
            m.group(0): Archive(self, m.group(2), m.group(0), m.group(1).startswith("Freemium"))
            for m in self.archive_name.finditer(html)
        }
        return sorted(found.values())


FUNDS = {
    "legi": Fund(
        "dila_legi",
        "https://echanges.dila.gouv.fr/OPENDATA/LEGI/",
        re.compile(r"(Freemium_legi_global|LEGI)_(\d{8}-\d{6})\.tar\.gz"),
    ),
    "jorf": Fund(
        "dila_jorf",
        "https://echanges.dila.gouv.fr/OPENDATA/JORF/",
        re.compile(r"(Freemium_jorf_global|JORF)_(\d{8}-\d{6})\.tar\.gz"),
    ),
    "cnil": Fund(
        "dila_cnil",
        "https://echanges.dila.gouv.fr/OPENDATA/CNIL/",
        re.compile(r"(Freemium_cnil_global|CNIL)_(\d{8}-\d{6})\.tar\.gz"),
    ),
    "constit": Fund(
        "dila_constit",
        "https://echanges.dila.gouv.fr/OPENDATA/CONSTIT/",
        re.compile(r"(Freemium_constit_global|CONSTIT)_(\d{8}-\d{6})\.tar\.gz"),
    ),
}


@dataclass(frozen=True)
class Archive:
    fund: Fund
    stamp: str  # AAAAMMJJ-HHMMSS, tri chronologique
    name: str
    is_global: bool

    def __lt__(self, other: Archive) -> bool:
        return (self.stamp, self.name) < (other.stamp, other.name)

    @property
    def url(self) -> str:
        return self.fund.base_url + self.name


def plan(conn: sqlite3.Connection, fund: Fund, archives: list[Archive]) -> list[Archive]:
    """Archives à télécharger, dans l'ordre chronologique."""
    globals_ = [a for a in archives if a.is_global]
    archived_globals = [a for a in globals_ if is_archived(conn, fund.source_id, a.name)]
    if archived_globals:
        base = archived_globals[-1]
        todo = []
    elif globals_:
        base = globals_[-1]
        todo = [base]
    else:
        raise RuntimeError(f"Aucun dump complet dans l'index {fund.base_url}")

    todo += [
        a
        for a in archives
        if not a.is_global
        and a.stamp > base.stamp
        and not is_archived(conn, fund.source_id, a.name)
    ]
    return todo


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    fund: Fund,
    opener: Opener = urlopen,
    max_archives: int | None = None,
) -> list[str]:
    """Télécharge et archive les archives manquantes. Retourne leurs noms."""
    with opener(fund.base_url) as response:
        listing = response.read().decode("utf-8", errors="replace")
    checked_at = now_iso()
    pending = plan(conn, fund, fund.parse_listing(listing))
    todo = pending[:max_archives]

    collected = []
    for archive in todo:
        print(f"[{fund.source_id}] {archive.name}", flush=True)
        with opener(archive.url) as response:
            store(
                conn,
                raw_dir,
                source_id=fund.source_id,
                external_id=archive.name,
                url=archive.url,
                fetched_at=now_iso(),
                chunks=iter_chunks(response),
                suffix=".tar.gz",
            )
        collected.append(archive.name)
    if len(todo) == len(pending):  # rien ne reste à télécharger : la source est à jour
        record_check(conn, raw_dir, fund.source_id, checked_at)
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.dila")
    parser.add_argument("--fund", choices=sorted(FUNDS), required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--max", type=int, default=None, help="nombre maximal d'archives")
    args = parser.parse_args(argv)

    fund = FUNDS[args.fund]
    conn = connect(args.db)
    try:
        init_db(conn)
        collected = collect(conn, args.raw_dir, fund, max_archives=args.max)
    finally:
        conn.close()
    print(f"[{fund.source_id}] {len(collected)} archive(s) collectée(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
