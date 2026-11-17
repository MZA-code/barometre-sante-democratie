"""Collecteur open data de l'Assemblée nationale — questions écrites (indicateur D2.5).

Un fichier par législature :
    https://data.assemblee-nationale.fr/static/openData/repository/<N>/questions/
        questions_ecrites/<FICHIER>
Constaté le 2026-11-17 : législatures 14 à 17 publiées (depuis juin 2012). La 14e est un seul
JSON (Questions_ecrites_XIV.json, 134 Mo compressé), les suivantes un JSON par question. Le
serveur coupe les gros téléchargements au bout de quelques Mo : le fichier est relu par
morceaux (en-tête Range), en reprenant là où la connexion s'est arrêtée.

Législature en cours : retéléchargée à chaque passage, archivée seulement si le contenu du zip
change (comme collectors/an_opendata.py). Législatures closes : téléchargées une seule fois.

Usage :
    python -m collectors.an_questions [--db CHEMIN] [--raw-dir DOSSIER] [--legislatures 17 16]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from collectors.http import TIMEOUT, USER_AGENT, now_iso
from storage.archive import (
    DEFAULT_RAW_DIR,
    StoredDocument,
    latest_version,
    record_check,
    store_if_content_changed,
)
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "an_questions"  # source distincte : extract/parlement.py lit tout an_opendata
URL_TEMPLATE = (
    "https://data.assemblee-nationale.fr/static/openData/repository/{legislature}"
    "/questions/questions_ecrites/{filename}"
)
FILENAMES = {14: "Questions_ecrites_XIV.json.zip", 15: "Questions_ecrites_XV.json.zip"}
DEFAULT_FILENAME = "Questions_ecrites.json.zip"
EN_COURS = 17
DEFAULT_LEGISLATURES = (17, 16, 15, 14)
MAX_REPRISES = 200

# Télécharge une plage d'octets à partir d'un décalage : (url, début) -> (octets, taille totale).
Lecteur = Callable[[str, int], tuple[bytes, int | None]]


def url_for(legislature: int) -> str:
    filename = FILENAMES.get(legislature, DEFAULT_FILENAME)
    return URL_TEMPLATE.format(legislature=legislature, filename=filename)


def external_id(legislature: int) -> str:
    return f"questions_ecrites_L{legislature}.json.zip"


def lire_plage(url: str, debut: int) -> tuple[bytes, int | None]:
    """Lit à partir de `debut` jusqu'à la fin ou la coupure ; renvoie ce qui a été reçu."""
    headers = {"User-Agent": USER_AGENT}
    if debut:
        headers["Range"] = f"bytes={debut}-"
    recu = bytearray()
    total = None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=TIMEOUT
        ) as r:
            if debut and r.status != 206:
                raise OSError(f"{url} : reprise refusée (HTTP {r.status})")
            plage = r.headers.get("Content-Range")  # « bytes 100-199/1000 »
            longueur = r.headers.get("Content-Length")
            if plage and "/" in plage:
                total = int(plage.rsplit("/", 1)[1])
            elif longueur:
                total = int(longueur)
            while bloc := r.read(1 << 20):
                recu += bloc
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        if isinstance(e, urllib.error.HTTPError) or "reprise refusée" in str(e):
            raise
    return bytes(recu), total


def telecharger(url: str, lecteur: Lecteur = lire_plage, max_reprises: int = MAX_REPRISES) -> bytes:
    """Fichier complet, en reprenant après chaque coupure ; erreur si la taille annoncée n'est
    pas atteinte en `max_reprises` lectures."""
    data = bytearray()
    total = None
    for _ in range(max_reprises):
        bloc, annonce = lecteur(url, len(data))
        if annonce is not None and total is None:
            total = annonce
        data += bloc
        if total is not None and len(data) >= total:
            return bytes(data[:total])
        if total is None and bloc:
            return bytes(data)  # taille inconnue : une lecture complète suffit
    raise OSError(f"{url} : téléchargement incomplet ({len(data)} octets sur {total})")


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    legislatures: tuple[int, ...] = DEFAULT_LEGISLATURES,
    lecteur: Lecteur = lire_plage,
) -> dict[int, StoredDocument | None]:
    checked_at = now_iso()
    results: dict[int, StoredDocument | None] = {}
    for legislature in legislatures:
        deja = latest_version(conn, raw_dir, SOURCE_ID, external_id(legislature))
        if deja and legislature != EN_COURS:
            print(f"[an_questions] L{legislature} : législature close, déjà archivée")
            results[legislature] = deja
            continue
        url = url_for(legislature)
        try:
            data = telecharger(url, lecteur)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            print(f"[an_questions] L{legislature} : non publiée (404)")
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
        print(f"[an_questions] L{legislature} : {state} ({doc.sha256[:12]})")
        results[legislature] = doc
    record_check(conn, raw_dir, SOURCE_ID, checked_at)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.an_questions")
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
