"""Collecteur du baromètre de l'application des lois (Assemblée nationale, LexImpact).

Deux fichiers CSV publiés par l'Assemblée nationale (jeu data.gouv.fr « Données du baromètre
de l'application des lois », Licence Ouverte 2.0) : la liste des lois promulguées depuis la
XIIe législature (2002) et la liste des mesures d'application qu'elles prévoient (décret
attendu, date de publication, délai). Les fichiers sont republiés chaque jour sous la même
adresse ; ils ne sont retéléchargés qu'une fois par mois (`RAFRAICHIR_JOURS`), et une nouvelle
version n'est archivée que si le contenu a changé : la mesure porte sur des délais de six mois,
une mise à jour mensuelle suffit.

Usage :
    python -m collectors.application_lois [--db CHEMIN] [--raw-dir DOSSIER] [--forcer]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, record_check, store_if_content_changed
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "an_application_lois"
BASE = "https://barometre.assemblee-nationale.fr/"
FICHIERS = {
    "lois.csv": BASE + "barometre_application_lois_assemblee.csv",
    "mesures.csv": BASE + "barometre_application_mesures_assemblee.csv",
}
RAFRAICHIR_JOURS = 28


def dernier_releve(conn: sqlite3.Connection) -> dt.date | None:
    row = conn.execute(
        "SELECT max(t) FROM (SELECT fetched_at AS t FROM raw_documents WHERE source_id = ?"
        " UNION ALL SELECT checked_at FROM source_checks WHERE source_id = ?)",
        (SOURCE_ID, SOURCE_ID),
    ).fetchone()
    return dt.date.fromisoformat(row[0][:10]) if row and row[0] else None


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    opener: Opener = urlopen,
    today: dt.date | None = None,
    forcer: bool = False,
) -> list[str]:
    today = today or dt.date.today()
    precedent = dernier_releve(conn)
    if not forcer and precedent and (today - precedent).days < RAFRAICHIR_JOURS:
        print(f"[application_lois] relevé du {precedent} : prochain dans moins d'un mois")
        return []
    nouveaux = []
    fetched_at = now_iso()
    for nom, url in FICHIERS.items():
        with opener(url) as response:
            data = response.read()
        doc = store_if_content_changed(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=nom,
            url=url,
            fetched_at=fetched_at,
            data=data,
            suffix=".csv",
        )
        print(f"[application_lois] {nom} {'nouvelle version' if doc.created else 'inchangé'}")
        if doc.created:
            nouveaux.append(nom)
    record_check(conn, raw_dir, SOURCE_ID, fetched_at)
    return nouveaux


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.application_lois")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--forcer", action="store_true", help="ignorer le délai d'un mois")
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, forcer=args.forcer)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
