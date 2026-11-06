"""Collecteur Arcom — relevés mensuels des temps de parole hors période électorale.

Page de liste par année (constaté le 2026-11-05) :
    https://www.arcom.fr/temps-parole/hors-elections/recherche/source/<année>
La liste des fichiers est intégrée à la configuration Drupal de la page (JSON
`drupal-settings-json`, chemin tphpe[].mois[].fichiers[].file_uri). Deux fichiers CSV par
mois ; seul le fichier « Export_web_1T2T_<début>_<fin>.csv » est archivé : il contient, par
chaîne ou radio et par type d'émission, les agrégats calculés par l'Arcom (« Total Pouvoir
exécutif », « Total Partis politiques »). Le fichier des personnalités n'est pas utilisé.

Disponibilité : fichiers publiés depuis janvier 2025 ; un mois paraît environ trois mois après
sa diffusion. Un fichier déjà archivé (même nom) n'est pas retéléchargé. Informations
publiques ; mentions légales de l'Arcom : utilisation libre, à condition de ne pas présenter la
reproduction comme engageant l'Arcom ni comme garantie par elle.

Usage :
    python -m collectors.arcom [--db CHEMIN] [--raw-dir DOSSIER] [--annees 2025 2026]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import urllib.error
from pathlib import Path
from urllib.parse import unquote

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "arcom_temps_parole"
BASE = "https://www.arcom.fr"
LIST_URL = BASE + "/temps-parole/hors-elections/recherche/source/{annee}"
FIRST_YEAR = 2025
SETTINGS = re.compile(
    r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>',
    re.S,
)
FICHIER_1T2T = re.compile(r"Export_web_1T2T_\d{2}-\d{2}-\d{4}_\d{2}-\d{2}-\d{4}")


def list_files(html: str) -> list[str]:
    """Chemins des fichiers « 1T2T » listés dans une page annuelle."""
    match = SETTINGS.search(html)
    if not match:
        return []
    settings = json.loads(match.group(1))
    uris = []
    for bloc in settings.get("tphpe", []):
        for mois in bloc.get("mois", []):
            for fichier in mois.get("fichiers", []):
                uri = fichier.get("file_uri", "")
                if FICHIER_1T2T.search(unquote(uri)):
                    uris.append(uri)
    return sorted(set(uris))


def external_id(uri: str) -> str:
    """Nom stable du fichier : sans suffixe de copie (« (1) ») ajouté par le site."""
    name = unquote(uri.rsplit("/", 1)[-1])
    return FICHIER_1T2T.search(name).group(0) + ".csv"


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    annees: list[int] | None = None,
    opener: Opener = urlopen,
) -> list[str]:
    annees = annees or list(range(FIRST_YEAR, dt.date.today().year + 1))
    collected = []
    for annee in annees:
        try:
            with opener(LIST_URL.format(annee=annee)) as response:
                html = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            print(f"[arcom] {annee} : liste indisponible (HTTP {e.code})")
            continue
        for uri in list_files(html):
            name = external_id(uri)
            if is_archived(conn, SOURCE_ID, name):
                continue
            url = BASE + uri
            with opener(url) as response:
                store(
                    conn,
                    raw_dir,
                    source_id=SOURCE_ID,
                    external_id=name,
                    url=url,
                    fetched_at=now_iso(),
                    chunks=iter_chunks(response),
                    suffix=".csv",
                )
            print(f"[arcom] {name}")
            collected.append(name)
    print(f"[arcom] {len(collected)} fichier(s) collecté(s)")
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.arcom")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--annees", type=int, nargs="+")
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, args.annees)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
