"""Collecteur Eurostat — dépenses publiques par fonction (COFOG) et prisons.

Jeu `gov_10a_exp` (comptes nationaux, classification des fonctions des administrations
publiques, COFOG) : dépenses totales (TE) des administrations publiques (S13), par fonction,
de 1995 à la dernière année publiée, pour la France, l'Allemagne, l'Italie, l'Espagne et la
moyenne de l'Union européenne à 27. Trois unités : millions d'euros courants, part du PIB,
part des dépenses publiques totales.

Jeu `crim_pris_cap` : personnes détenues et capacité officielle des prisons, chaque année
depuis 2008, pour tous les pays couverts (taux d'occupation comparable d'un pays à l'autre).

Un fichier SDMX-CSV par jeu (≈ 500 ko et ≈ 100 ko), téléchargé à chaque collecte ; une
nouvelle version n'est archivée que si son contenu change (Eurostat met ces jeux à jour
quelques fois par an). Données de contexte : aucune note n'en est tirée.

Usage :
    python -m collectors.eurostat [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, store_if_content_changed
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "eurostat_cofog"
EXTERNAL_ID = "gov_10a_exp.csv"
PAYS = ("FR", "DE", "IT", "ES", "EU27_2020")
UNITES = ("MIO_EUR", "PC_GDP", "PC_TOT")
# Divisions COFOG, quelques groupes (intérêts de la dette, police, incendie, tribunaux,
# prisons) et le total.
FONCTIONS = (
    "TOTAL",
    "GF01",
    "GF0107",
    "GF02",
    "GF03",
    "GF0301",
    "GF0302",
    "GF0303",
    "GF0304",
    "GF04",
    "GF05",
    "GF06",
    "GF07",
    "GF08",
    "GF09",
    "GF10",
)
URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/gov_10a_exp/"
    f"A.{'+'.join(UNITES)}.S13.{'+'.join(FONCTIONS)}.TE.{'+'.join(PAYS)}"
    "?format=SDMX-CSV&compressed=false"
)

EXTERNAL_ID_PRISONS = "crim_pris_cap.csv"
URL_PRISONS = (
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/crim_pris_cap/"
    "A.PRIS_ACT_CAP+PRIS_OFF_CAP.NR.?format=SDMX-CSV&compressed=false"
)
JEUX = {EXTERNAL_ID: URL, EXTERNAL_ID_PRISONS: URL_PRISONS}


def collect(conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen) -> list[str]:
    """Jeux archivés dans une nouvelle version."""
    nouveaux = []
    for nom, url in JEUX.items():
        with opener(url) as response:
            data = response.read()
        doc = store_if_content_changed(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=nom,
            url=url,
            fetched_at=now_iso(),
            data=data,
            suffix=".csv",
        )
        print(f"[eurostat] {nom} {'nouvelle version' if doc.created else 'inchangé'}")
        if doc.created:
            nouveaux.append(nom)
    return nouveaux


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.eurostat")
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
