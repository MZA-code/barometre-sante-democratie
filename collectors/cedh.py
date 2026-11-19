"""Collecteur HUDOC — arrêts de la Cour européenne des droits de l'homme contre la France.

Interroge la base HUDOC (hudoc.echr.coe.int, interface publique de recherche) : arrêts
(collection JUDGMENTS) dont l'État défendeur est la France, en français et en anglais (les
deux langues officielles de la Cour), par pages de 1 000 documents triés par identifiant.
Les pages sont réunies dans un seul fichier JSON archivé (`arrets_fra.json`) : chaque
résultat y est recopié tel que reçu, l'enveloppe est la nôtre. Une nouvelle version n'est
archivée que si l'ensemble des résultats change (le champ de pertinence `rank`, recalculé à
chaque requête, est ignoré pour cette comparaison, pas retiré du fichier).

Usage :
    python -m collectors.cedh [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, latest_version, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "hudoc_cedh"
EXTERNAL_ID = "arrets_fra.json"
BASE = "https://hudoc.echr.coe.int/app/query/results"
QUERY = (
    'contentsitename:ECHR AND (respondent:"FRA") AND (documentcollectionid2:"JUDGMENTS")'
    ' AND (languageisocode:"FRE" OR languageisocode:"ENG")'
)
CHAMPS = (
    "itemid,docname,kpdate,appno,languageisocode,importance,violation,nonviolation,ecli,"
    "doctypebranch,conclusion"
)
PAGE = 1000
PAUSE = 2.0  # secondes entre deux pages


def page_url(start: int) -> str:
    return f"{BASE}?" + urlencode(
        {
            "query": QUERY,
            "select": CHAMPS,
            "sort": "itemid Ascending",
            "start": start,
            "length": PAGE,
        }
    )


def normalise(resultats: list[dict]) -> list[dict]:
    """Résultats sans le champ `rank`, triés par identifiant : base de comparaison."""
    out = [{k: v for k, v in r["columns"].items() if k != "rank"} for r in resultats]
    return sorted(out, key=lambda c: c["itemid"])


def collect(
    conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen, pause: float = PAUSE
) -> bool:
    resultats: list[dict] = []
    total = None
    start = 0
    while total is None or start < total:
        if start:
            time.sleep(pause)
        with opener(page_url(start)) as response:
            page = json.loads(response.read())
        total = page["resultcount"]
        if not page["results"]:
            break
        resultats.extend(page["results"])
        start += PAGE
    if len(resultats) != total:
        raise RuntimeError(f"[cedh] {len(resultats)} résultats reçus sur {total} annoncés")

    previous = latest_version(conn, raw_dir, SOURCE_ID, EXTERNAL_ID)
    if previous:
        ancien = json.loads(previous.path.read_text(encoding="utf-8"))
        if normalise(ancien["results"]) == normalise(resultats):
            print(f"[cedh] {EXTERNAL_ID} inchangé ({total} documents)")
            return False
    data = json.dumps(
        {"query": QUERY, "resultcount": total, "results": resultats}, ensure_ascii=False
    ).encode("utf-8")
    store(
        conn,
        raw_dir,
        source_id=SOURCE_ID,
        external_id=EXTERNAL_ID,
        url=page_url(0),
        fetched_at=now_iso(),
        chunks=[data],
        suffix=".json",
    )
    print(f"[cedh] {EXTERNAL_ID} nouvelle version ({total} documents)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.cedh")
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
