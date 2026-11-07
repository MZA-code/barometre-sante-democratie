"""Collecteur Défenseur des droits — documents de la base juridique liés aux manifestations.

Base documentaire publique https://juridique.defenseurdesdroits.fr/ (logiciel PMB). Les
documents sont indexés par mots-clés ; on suit deux catégories :
  - 3875 « Manifestation »,
  - 3894 « Maintien de l'ordre public ».
Les pages de liste (10 documents par page) servent seulement à découvrir les fiches ; chaque
fiche (`notice_display`) est archivée telle quelle, une fois (identifiant de notice). Le tri
retenu par la base place les documents récents en tête : en marche quotidienne, on s'arrête
à la première page qui n'apporte rien de nouveau ; `--complet` parcourt toutes les pages.

Le robots.txt du site demande 30 secondes entre deux requêtes (`Crawl-delay: 30`) : le
délai est respecté pour chaque requête (premier passage ≈ 2 h).

Usage :
    python -m collectors.ddd [--db CHEMIN] [--raw-dir DOSSIER] [--complet] [--max-fiches N]
"""

from __future__ import annotations

import argparse
import html
import re
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "ddd_juridique"
BASE = "https://juridique.defenseurdesdroits.fr/"
CATEGORIES = {3875: "Manifestation", 3894: "Maintien de l'ordre public"}
DELAI_S = 30.0  # Crawl-delay du robots.txt
NOTICE = re.compile(r"lvl=notice_display&(?:amp;)?id=(\d+)")
PAGINATION = re.compile(r"page=\d+&(?:amp;)?nbr_lignes=(\d+)&(?:amp;)?l_typdoc=([^\"&]+)")


def url_liste(categorie: int, page: int = 1, pagination: tuple[str, str] | None = None) -> str:
    url = f"{BASE}index.php?lvl=categ_see&id={categorie}"
    if page > 1 and pagination:
        url += f"&page={page}&nbr_lignes={pagination[0]}&l_typdoc={pagination[1]}"
    return url


def url_fiche(notice: str) -> str:
    return f"{BASE}index.php?lvl=notice_display&id={notice}"


def fiches(page_html: str) -> list[str]:
    """Identifiants de notice d'une page de liste, dans l'ordre, sans doublon."""
    return list(dict.fromkeys(NOTICE.findall(page_html)))


def pagination(page_html: str) -> tuple[str, str] | None:
    m = PAGINATION.search(page_html)
    return (m.group(1), html.unescape(m.group(2))) if m else None


class Poli:
    """Requêtes espacées d'au moins `delai` secondes (consigne du robots.txt)."""

    def __init__(self, opener: Opener, sleep: Callable[[float], None], delai: float = DELAI_S):
        self.opener, self.sleep, self.delai = opener, sleep, delai
        self.derniere: float | None = None

    def get(self, url: str, clock: Callable[[], float] = time.monotonic) -> bytes:
        if self.derniere is not None:
            reste = self.delai - (clock() - self.derniere)
            if reste > 0:
                self.sleep(reste)
        try:
            with self.opener(url) as response:
                return response.read()
        finally:
            self.derniere = clock()


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    opener: Opener = urlopen,
    sleep: Callable[[float], None] = time.sleep,
    complet: bool = False,
    max_fiches: int | None = None,
) -> list[str]:
    poli = Poli(opener, sleep)
    vues: set[str] = set()
    collectees: list[str] = []
    for categorie, nom in CATEGORIES.items():
        page, pag = 1, None
        while True:
            liste = poli.get(url_liste(categorie, page, pag)).decode("utf-8", errors="replace")
            if page == 1:
                pag = pagination(liste)
            ids = [i for i in fiches(liste) if i not in vues]
            vues.update(ids)
            nouvelles = [i for i in ids if not is_archived(conn, SOURCE_ID, i)]
            for notice in nouvelles:
                if max_fiches is not None and len(collectees) >= max_fiches:
                    print(f"[ddd] limite de {max_fiches} fiche(s) atteinte")
                    return collectees
                data = poli.get(url_fiche(notice))
                if b"exempl_titleNot" not in data:
                    raise ValueError(f"[ddd] fiche {notice} : page inattendue (pas de titre)")
                store(
                    conn,
                    raw_dir,
                    source_id=SOURCE_ID,
                    external_id=notice,
                    url=url_fiche(notice),
                    fetched_at=now_iso(),
                    chunks=[data],
                    suffix=".html",
                )
                print(f"[ddd] {nom} : fiche {notice}")
                collectees.append(notice)
            total = int(pag[0]) if pag else len(ids)
            if not ids or page * 10 >= total or (not nouvelles and not complet):
                break
            page += 1
    print(f"[ddd] {len(collectees)} fiche(s) collectée(s)")
    return collectees


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.ddd")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--complet", action="store_true", help="parcourir toutes les pages")
    parser.add_argument("--max-fiches", type=int, default=None)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, complet=args.complet, max_fiches=args.max_fiches)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
