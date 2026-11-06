"""Collecteur open data de l'Assemblée nationale — dossiers législatifs.

Un fichier par législature :
    https://data.assemblee-nationale.fr/static/openData/repository/<N>/loi/
        dossiers_legislatifs/<FICHIER>
Constaté le 2026-10-26 : seules les législatures 14 à 17 (depuis juin 2012) sont
publiées ; les 14e et 15e portent un suffixe en chiffres romains. Les engagements
de responsabilité antérieurs viennent du seed manuel (data/seed/).

L'URL est stable mais le contenu évolue pour la législature en cours : chaque
exécution retélécharge le fichier. Constaté le 2026-11-05 : le serveur régénère le zip
(horodatages internes différents) sans que son contenu change, donc l'empreinte du
fichier change à chaque téléchargement. Une nouvelle version n'est archivée que si le
contenu des fichiers du zip diffère de la dernière version archivée ; le fichier
archivé reste l'original reçu, octet pour octet (règle 1).

Usage :
    python -m collectors.an_opendata [--db CHEMIN] [--raw-dir DOSSIER] [--legislatures 17 16]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import urllib.error
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, StoredDocument, store_if_content_changed
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "an_opendata"
URL_TEMPLATE = (
    "https://data.assemblee-nationale.fr/static/openData/repository/{legislature}"
    "/loi/dossiers_legislatifs/{filename}"
)
FILENAMES = {
    14: "Dossiers_Legislatifs_XIV.json.zip",
    15: "Dossiers_Legislatifs_XV.json.zip",
}
DEFAULT_FILENAME = "Dossiers_Legislatifs.json.zip"
DEFAULT_LEGISLATURES = (17, 16, 15, 14)


def url_for(legislature: int) -> str:
    filename = FILENAMES.get(legislature, DEFAULT_FILENAME)
    return URL_TEMPLATE.format(legislature=legislature, filename=filename)


def external_id(legislature: int) -> str:
    return f"dossiers_legislatifs_L{legislature}.json.zip"


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    legislatures: tuple[int, ...] = DEFAULT_LEGISLATURES,
    opener: Opener = urlopen,
) -> dict[int, StoredDocument | None]:
    """Archive le fichier de chaque législature. None si la source ne le publie pas."""
    results: dict[int, StoredDocument | None] = {}
    for legislature in legislatures:
        url = url_for(legislature)
        try:
            with opener(url) as response:
                data = response.read()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            print(f"[an_opendata] L{legislature} : non publiée (404)")
            results[legislature] = None
            continue
        doc = store_if_content_changed(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=external_id(legislature),
            url=url,
            fetched_at=now_iso(),
            data=data,
            suffix=".zip",
        )
        state = "nouvelle version" if doc.created else "contenu inchangé"
        print(f"[an_opendata] L{legislature} : {state} ({doc.sha256[:12]})")
        results[legislature] = doc
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.an_opendata")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--legislatures", type=int, nargs="+", default=DEFAULT_LEGISLATURES)
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, tuple(args.legislatures))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
