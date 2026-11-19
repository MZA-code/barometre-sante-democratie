"""Collecteur open data de la justice administrative (opendata.justice-administrative.fr).

Une archive zip par juridiction et par mois de lecture, contenant une décision par fichier
XML (métadonnées + texte intégral pseudonymisé) :
    https://opendata.justice-administrative.fr/DCE/AAAA/MM/CE_AAAAMM.zip   (depuis juin 2021)
    https://opendata.justice-administrative.fr/DTA/AAAA/MM/TA_AAAAMM.zip   (depuis juin 2022)
Constaté le 2026-11-05 : ≈ 2,6 Mo par mois pour le Conseil d'État, ≈ 75 Mo pour les
tribunaux administratifs. Les cours administratives d'appel (DCA) ne sont pas collectées :
l'appel d'une ordonnance de référé-liberté va directement au Conseil d'État.

Les mois terminés sont archivés en entier, une fois chacun (le nom du fichier sert
d'identifiant externe, comme pour la DILA). Constaté : les archives passées sont parfois
régénérées (fichiers de mars 2023 datés de septembre 2026) ; elles ne sont pas
retéléchargées.

Mois en cours : son archive grossit chaque jour et l'archiver en entier coûterait ≈ 27 Go par
an. Elle est téléchargée, puis seules les décisions qui passent le pré-filtre de
extract/manifestations.py (≈ 2 % des fichiers) sont archivées, chacune octet pour octet, dans
un zip « <archive>.extrait.zip » ; nouvelle version seulement si son contenu change. Une fois
le mois terminé, l'archive complète prend le relais (les doublons sont écartés à
l'extraction).

Usage :
    python -m collectors.justice_admin [--db CHEMIN] [--raw-dir DOSSIER] [--juridictions DCE DTA]
                                       [--max N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from extract.manifestations import prefiltre
from storage.archive import DEFAULT_RAW_DIR, is_archived, store, store_if_content_changed
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "justice_admin"
BASE_URL = "https://opendata.justice-administrative.fr/"
JURIDICTIONS = ("DCE", "DTA")
EXTRAIT = ".extrait.zip"
ARCHIVE = re.compile(r'href="/?((D[A-Z]{2})/(\d{4})/(\d{2})/([A-Z]+_(\d{6})\.zip))"')


def list_archives(html: str) -> list[tuple[str, str, str]]:
    """(chemin relatif, nom du fichier, AAAAMM) des archives d'une page d'index, triés."""
    found = {m.group(5): (m.group(1), m.group(5), m.group(6)) for m in ARCHIVE.finditer(html)}
    return sorted(found.values(), key=lambda a: (a[2], a[1]))


def completed(month: str, today: dt.date) -> bool:
    return month < today.strftime("%Y%m")


def extrait(archive: Path) -> bytes:
    """Zip des seules décisions qui passent le pré-filtre, copiées octet pour octet, dans
    l'ordre des noms et à date fixe : même contenu -> mêmes octets."""
    out = io.BytesIO()
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(src.namelist()):
            if name.endswith(".xml") and prefiltre(data := src.read(name)):
                dst.writestr(
                    zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED
                )
    return out.getvalue()


def collect_current(
    conn: sqlite3.Connection, raw_dir: Path, path: str, name: str, opener: Opener
) -> bool:
    """Archive l'extrait du mois en cours s'il a changé ; True si une version est ajoutée."""
    url = BASE_URL + path
    with tempfile.TemporaryFile() as tmp:
        with opener(url) as response:
            shutil.copyfileobj(response, tmp)
        tmp.seek(0)
        data = extrait(tmp)
    stored = store_if_content_changed(
        conn,
        raw_dir,
        source_id=SOURCE_ID,
        external_id=name.removesuffix(".zip") + EXTRAIT,
        url=url,
        fetched_at=now_iso(),
        data=data,
    )
    return stored.created


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    juridictions: tuple[str, ...] = JURIDICTIONS,
    opener: Opener = urlopen,
    today: dt.date | None = None,
    max_archives: int | None = None,
) -> list[str]:
    today = today or dt.date.today()
    todo, current = [], []
    for juridiction in juridictions:
        with opener(f"{BASE_URL}{juridiction}/") as response:
            html = response.read().decode("utf-8", errors="replace")
        for path, name, month in list_archives(html):
            if not completed(month, today):
                if month == today.strftime("%Y%m"):
                    current.append((path, name))
            elif not is_archived(conn, SOURCE_ID, name):
                todo.append((path, name))
    collected = []
    for path, name in todo[:max_archives]:
        url = BASE_URL + path
        print(f"[justice_admin] {name}", flush=True)
        with opener(url) as response:
            store(
                conn,
                raw_dir,
                source_id=SOURCE_ID,
                external_id=name,
                url=url,
                fetched_at=now_iso(),
                chunks=iter_chunks(response),
                suffix=".zip",
            )
        collected.append(name)
    print(f"[justice_admin] {len(collected)} archive(s) collectée(s)")
    for path, name in current:
        if collect_current(conn, raw_dir, path, name, opener):
            print(f"[justice_admin] {name} (mois en cours) : nouvel extrait", flush=True)
            collected.append(name.removesuffix(".zip") + EXTRAIT)
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.justice_admin")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--juridictions", nargs="+", default=list(JURIDICTIONS))
    parser.add_argument("--max", type=int, default=None, help="nombre maximal d'archives")
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, tuple(args.juridictions), max_archives=args.max)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
