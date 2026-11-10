"""Collecteur des titres d'articles candidats D7 (repérage des dépêches reprises).

Pour chaque article d'un pré-candidat D7 (extract/d7_candidats.py), on lit le début de la
page publique (256 Kio au plus) et on n'archive que son titre (`og:title`, sinon `<title>`)
dans un petit JSON `{"url", "titre"}`. Le texte des articles n'est jamais conservé (droit
d'auteur, articles payants). Une page en échec est archivée avec `"titre": null` et n'est pas
redemandée. Une requête par seconde au plus.

Les titres servent à une seule chose : deux articles de groupes différents au titre
identique (une fois normalisé) sont la même dépêche reprise, et comptent pour une seule source
dans le recoupement (`fusionner`).

Usage :
    python -m collectors.presse_titres [--db CHEMIN] [--raw-dir DOSSIER] [--max N]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from extract.common import latest_documents
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

SOURCE_ID = "presse_titres"
OCTETS_MAX = 256 * 1024
PAUSE_S = 1.0
OG_TITLE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:title[\"'][^>]*content=[\"']([^\"']*)[\"']"
    r"|<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*(?:property|name)=[\"']og:title[\"']",
    re.I,
)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
SUFFIXE = re.compile(r"\s+[-|–—]\s+([^-|–—]+)$")


def titre_de_page(page: bytes) -> str | None:
    text = page.decode("utf-8", errors="replace")
    m = OG_TITLE.search(text)
    brut = (m.group(1) or m.group(2)) if m else None
    if not brut:
        t = TITLE.search(text)
        brut = t.group(1) if t else None
    titre = html.unescape(brut).strip() if brut else ""
    return titre or None


def normaliser_titre(titre: str) -> str:
    m = SUFFIXE.search(titre)
    if m and len(m.group(1).split()) <= 4:  # « - Le Figaro », « | AFP » : nom du média
        titre = titre[: m.start()]
    sans_accents = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).split())


def fusionner(candidat, titres: dict[str, str | None]):
    """Le candidat si ses articles, une fois les dépêches reprises fusionnées, forment au moins
    deux sources couvrant au moins deux groupes ; sinon None."""
    sources: dict[str, set[str]] = {}
    for a in candidat.articles:
        titre = titres.get(a.url)
        cle = normaliser_titre(titre) if titre else f"url:{a.url}"
        sources.setdefault(cle or f"url:{a.url}", set()).add(a.groupe)
    groupes = set().union(*sources.values())
    return candidat if len(sources) >= 2 and len(groupes) >= 2 else None


def external_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def collect_urls(
    conn: sqlite3.Connection,
    raw_dir: Path,
    urls: Iterable[str],
    opener: Opener = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    n = 0
    for url in dict.fromkeys(urls):
        if is_archived(conn, SOURCE_ID, external_id(url)):
            continue
        if n:
            sleep(PAUSE_S)
        try:
            with opener(url) as response:
                titre = titre_de_page(response.read(OCTETS_MAX))
        except Exception as exc:  # page payante, supprimée, refus : on note l'échec
            print(f"[presse_titres] {url} : {exc}")
            titre = None
        data = json.dumps({"url": url, "titre": titre}, ensure_ascii=False, sort_keys=True)
        store(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=external_id(url),
            url=url,
            fetched_at=now_iso(),
            chunks=[data.encode()],
            suffix=".json",
        )
        n += 1
    return n


def titres_archives(conn: sqlite3.Connection, raw_dir: Path) -> dict[str, str | None]:
    out = {}
    for doc in latest_documents(conn, SOURCE_ID):
        data = json.loads((raw_dir / doc["path"]).read_text(encoding="utf-8"))
        out[data["url"]] = data["titre"]
    return out


def collect(conn: sqlite3.Connection, raw_dir: Path, max_urls: int | None = None) -> int:
    from extract.d7_candidats import pre_candidats_archives
    from extract.d7_rss import debut_rss

    fin = debut_rss(conn)  # après le début des flux RSS, GDELT ne sert plus (titres inutiles)
    cands = [c for c in pre_candidats_archives(conn, raw_dir) if fin is None or c.jour < str(fin)]
    urls = [a.url for c in reversed(cands) for a in c.articles]
    urls = [u for u in dict.fromkeys(urls) if not is_archived(conn, SOURCE_ID, external_id(u))]
    n = collect_urls(conn, raw_dir, urls[:max_urls] if max_urls else urls)
    print(f"[presse_titres] {n} titre(s) archivé(s), {max(0, len(urls) - n)} en attente")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.presse_titres")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--max", type=int, default=None)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        collect(conn, args.raw_dir, args.max)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
