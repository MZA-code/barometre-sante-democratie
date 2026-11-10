"""Collecteur des flux RSS de la presse française (repérage des faits candidats à D7).

Flux listés dans config/flux_rss.yaml. Pour chaque flux, on garde de chaque article le titre,
le lien, la date de publication (UTC) et le résumé fourni par le flux, coupé à 300 caractères ;
jamais le texte de l'article (certains flux le contiennent : il est ignoré). Un document brut
par flux et par jour de collecte (`<flux>/<AAAA-MM-JJ>`, JSON trié) : chaque passage du jour
réunit les articles déjà archivés ce jour-là et ceux du flux, et archive la réunion comme
nouvelle version. Les flux ne gardent que leurs derniers articles : la collecte tourne donc
toutes les heures (ops/decisions.py) en plus du passage quotidien. Un flux en panne est
signalé et n'empêche pas les autres.

Liste des communes (geo.api.gouv.fr, données INSEE) : archivée une fois (source
`geo_communes`), elle sert à reconnaître le lieu d'un article (extract/d7_rss.py).

Usage :
    python -m collectors.rss [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import email.utils
import html
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import yaml

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, record_check, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

ROOT = Path(__file__).resolve().parent.parent
FLUX_PATH = ROOT / "config" / "flux_rss.yaml"
SOURCE_ID = "rss_presse"
COMMUNES_ID = "geo_communes"
COMMUNES_URL = (
    "https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,population&format=json"
)
RESUME_MAX = 300
PAUSE_S = 1.0
BALISE = re.compile(r"<[^>]+>")


def flux_configures(path: Path = FLUX_PATH) -> dict[str, str]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["flux"]


def _texte(valeur: str | None) -> str:
    sans_balises = BALISE.sub(" ", html.unescape(valeur or ""))
    return " ".join(html.unescape(sans_balises).split())


def _date_utc(valeur: str | None) -> str | None:
    if not valeur:
        return None
    try:
        d = email.utils.parsedate_to_datetime(valeur.strip())
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(tz=email.utils.datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def lire_flux(data: bytes) -> list[dict]:
    """Articles datés d'un flux RSS 2.0 (titre, lien, date UTC, résumé court). Un flux qui
    déclare un DOCTYPE ou des entités est refusé (expansion d'entités, entités externes)."""
    if b"<!DOCTYPE" in data[:2048].upper() or b"<!ENTITY" in data.upper():
        raise ValueError("flux refusé : DOCTYPE ou entités XML")
    racine = ET.fromstring(data)
    out = []
    for it in racine.iter("item"):
        lien = (it.findtext("link") or "").strip()
        date = _date_utc(it.findtext("pubDate"))
        titre = _texte(it.findtext("title"))
        if not lien or not date or not titre:
            continue
        out.append(
            {
                "titre": titre,
                "lien": lien,
                "date": date,
                "resume": _texte(it.findtext("description"))[:RESUME_MAX],
            }
        )
    return out


def _derniere_version(conn: sqlite3.Connection, raw_dir: Path, external_id: str) -> list[dict]:
    row = conn.execute(
        "SELECT path FROM raw_documents WHERE source_id = ? AND external_id = ?"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (SOURCE_ID, external_id),
    ).fetchone()
    if row is None:
        return []
    return json.loads((raw_dir / row[0]).read_text(encoding="utf-8"))["articles"]


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    flux: dict[str, str],
    opener: Opener = urlopen,
    maintenant: Callable[[], str] = now_iso,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Archive les articles de chaque flux ; nombre de documents nouveaux."""
    debut = maintenant()
    jour = debut[:10]
    nouveaux = 0
    for i, (nom, url) in enumerate(sorted(flux.items())):
        if i:
            sleep(PAUSE_S)
        try:
            with opener(url) as response:
                articles = lire_flux(response.read())
        except Exception as exc:  # flux en panne, XML invalide : on passe au suivant
            print(f"[rss] {nom} : {exc}")
            continue
        external_id = f"{nom}/{jour}"
        reunis = {a["lien"]: a for a in _derniere_version(conn, raw_dir, external_id)}
        for a in articles:
            reunis.setdefault(a["lien"], a)
        data = json.dumps(
            {"flux": nom, "url": url, "articles": sorted(reunis.values(), key=lambda a: a["lien"])},
            ensure_ascii=False,
            sort_keys=True,
        )
        doc = store(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=external_id,
            url=url,
            fetched_at=maintenant(),
            chunks=[data.encode()],
            suffix=".json",
        )
        nouveaux += doc.created
    record_check(conn, raw_dir, SOURCE_ID, debut)
    return nouveaux


def assurer_communes(conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen) -> None:
    if is_archived(conn, COMMUNES_ID, "communes.json"):
        return
    with opener(COMMUNES_URL) as response:
        data = response.read()
    json.loads(data)  # refuse une réponse qui n'est pas du JSON
    store(
        conn,
        raw_dir,
        source_id=COMMUNES_ID,
        external_id="communes.json",
        url=COMMUNES_URL,
        fetched_at=now_iso(),
        chunks=[data],
        suffix=".json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.rss")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        assurer_communes(conn, args.raw_dir)
        n = collect(conn, args.raw_dir, flux_configures())
        print(f"[rss] {n} document(s) nouveau(x)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
