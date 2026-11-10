"""Collecteur GDELT 2.0 — couverture médiatique d'événements situés en France.

Source : fichiers publics de GDELT, une tranche toutes les 15 minutes (constaté le 2026-11-06) :
    https://data.gdeltproject.org/gdeltv2/<AAAAMMJJHHMMSS>.export.CSV.zip    (événements)
    https://data.gdeltproject.org/gdeltv2/<AAAAMMJJHHMMSS>.mentions.CSV.zip  (articles)
L'API de recherche de GDELT (api.gdeltproject.org) n'est pas utilisée : elle limite les
requêtes et ne remonte qu'à trois mois.

Les fichiers bruts pèsent ≈ 18 Mo par jour : ils ne sont pas archivés tels quels. Pour chaque
jour UTC complet, le collecteur archive un extrait filtré et reproductible
(`<AAAA-MM-JJ>.tsv.gz`) : les mentions web (MentionType = 1) d'événements dont le lieu d'action
est en France (ActionGeo_CountryCode = FR, code FIPS), chacune complétée par le code de
l'événement. Un événement est cherché dans les tranches du jour et des deux jours précédents
(une mention cite parfois un événement apparu plus tôt). Les tranches absentes du serveur
(HTTP 404) sont listées en tête du fichier. Aucun texte d'article n'est récupéré : seulement
le domaine et l'adresse de l'article.

La table GDELT « domaine -> pays » (mai 2018) est archivée une fois ; elle sert à l'extraction.

Rattrapage : à chaque exécution, les jours non encore archivés depuis `--depuis` sont traités
du plus récent au plus ancien, `--max-jours` au plus.

Usage :
    python -m collectors.gdelt [--db CHEMIN] [--raw-dir DOSSIER] [--depuis AAAA-MM-JJ]
                               [--max-jours N]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import http.client
import io
import json
import sqlite3
import sys
import time
import urllib.error
import zipfile
from collections.abc import Iterator
from pathlib import Path

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, is_archived, store
from storage.db import DEFAULT_DB_PATH, ROOT, connect, init_db

SOURCE_ID = "gdelt"
BASE = "https://data.gdeltproject.org/gdeltv2/{stamp}.{kind}.CSV.zip"
DOMAINES_URL = (
    "https://data.gdeltproject.org/blog/2018-news-outlets-by-country-may2018-update/"
    "MASTER-GDELTDOMAINSBYCOUNTRY-MAY2018.TXT"
)
DOMAINES_ID = "domaines_par_pays_2018.txt"
# Flux « translingual » de GDELT (presse non anglophone traduite, dont la presse française) :
# mêmes fichiers préfixés `translation.`, archivés sous une source à part pour ne pas changer
# la série de contexte « presse étrangère » (extract/gdelt.py). Utilisé par D7.
SOURCE_ID_TRADUCTION = "gdelt_traduction"
FLUX_TRADUCTION = "translation."
DEPUIS = dt.date(2025, 1, 1)
DEPUIS_TRADUCTION = dt.date(2024, 7, 1)  # reprise D7 : début de la XVIIe législature
CACHE_DIR = ROOT / "data" / "cache" / "gdelt_evenements_fr"
PAUSE_S = 0.2
PAYS = "FR"
COLONNES = (
    "mention_utc",
    "evenement_id",
    "evenement_jour",
    "code_evenement",
    "code_racine",
    "acteur1_type",
    "acteur2_type",
    "lieu",
    "domaine",
    "url",
    "langue_source",
)
csv.field_size_limit(1 << 24)

# Colonnes des fichiers GDELT 2.0 (index à partir de 0).
E_ID, E_JOUR, E_A1_TYPE, E_A2_TYPE, E_CODE, E_RACINE, E_LIEU, E_PAYS = 0, 1, 12, 22, 26, 28, 52, 53
M_ID, M_HEURE, M_TYPE, M_DOMAINE, M_URL, M_TRADUCTION = 0, 2, 3, 4, 5, 14


def stamps(day: dt.date) -> list[str]:
    return [f"{day:%Y%m%d}{h:02d}{m:02d}00" for h in range(24) for m in (0, 15, 30, 45)]


ESSAIS = 4  # tentatives par fichier en cas d'erreur réseau (délai, coupure)
ATTENTE_S = 5.0  # attente avant la 2e tentative, doublée ensuite


def fetch_rows(url: str, opener: Opener, sleep=time.sleep) -> list[list[str]] | None:
    """Lignes d'un fichier GDELT zippé (tabulations) ; None si la tranche n'existe pas.

    Une erreur réseau passagère est retentée ; si elle persiste, l'exception remonte : le jour
    en cours n'est alors pas archivé (jamais d'extrait incomplet dans l'archive immuable).
    """
    for essai in range(ESSAIS):
        try:
            with opener(url) as response:
                data = response.read()
            zipfile.ZipFile(io.BytesIO(data)).testzip()  # zip tronqué -> BadZipFile
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code < 500 or essai == ESSAIS - 1:
                raise
        except (urllib.error.URLError, http.client.HTTPException, zipfile.BadZipFile, OSError):
            if essai == ESSAIS - 1:
                raise
        sleep(ATTENTE_S * 2**essai)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        (name,) = z.namelist()
        text = z.read(name).decode("utf-8", errors="replace")
    return list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))


def evenements_fr(
    day: dt.date, opener: Opener, cache_dir: Path, flux: str = ""
) -> tuple[dict, list[str]]:
    """Événements situés en France apparus ce jour-là (mis en cache, dérivé et jetable)."""
    path = cache_dir / f"{day.isoformat()}.json"
    if path.exists():
        cached = json.loads(path.read_text("utf-8"))
        return cached["evenements"], cached["manquantes"]
    events: dict[str, list[str]] = {}
    manquantes = []
    for stamp in stamps(day):
        rows = fetch_rows(BASE.format(stamp=stamp, kind=f"{flux}export"), opener)
        time.sleep(PAUSE_S)
        if rows is None:
            manquantes.append(f"{stamp}.{flux}export")
            continue
        for r in rows:
            if len(r) > E_PAYS and r[E_PAYS] == PAYS:
                events[r[E_ID]] = [
                    r[E_JOUR],
                    r[E_CODE],
                    r[E_RACINE],
                    r[E_A1_TYPE],
                    r[E_A2_TYPE],
                    r[E_LIEU],
                ]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"evenements": events, "manquantes": manquantes}), "utf-8")
    return events, manquantes


def langue(traduction: str) -> str:
    """« srclc:fra;eng:... » -> « fra » ; vide pour les articles en anglais (non traduits)."""
    for part in traduction.split(";"):
        if part.startswith("srclc:"):
            return part[6:]
    return "eng" if not traduction else ""


def extrait_jour(day: dt.date, opener: Opener, cache_dir: Path, flux: str = "") -> bytes:
    events: dict[str, list[str]] = {}
    manquantes: list[str] = []
    for d in (day - dt.timedelta(days=2), day - dt.timedelta(days=1), day):
        ev, miss = evenements_fr(d, opener, cache_dir, flux)
        events.update(ev)
        if d == day:
            manquantes += miss
    rows = []
    for stamp in stamps(day):
        mentions = fetch_rows(BASE.format(stamp=stamp, kind=f"{flux}mentions"), opener)
        time.sleep(PAUSE_S)
        if mentions is None:
            manquantes.append(f"{stamp}.{flux}mentions")
            continue
        for m in mentions:
            if len(m) <= M_TRADUCTION or m[M_TYPE] != "1" or m[M_ID] not in events:
                continue
            jour, code, racine, a1, a2, lieu = events[m[M_ID]]
            rows.append(
                (
                    m[M_HEURE],
                    m[M_ID],
                    jour,
                    code,
                    racine,
                    a1,
                    a2,
                    lieu,
                    m[M_DOMAINE].lower(),
                    m[M_URL],
                    langue(m[M_TRADUCTION]),
                )
            )
    rows.sort()
    out = io.StringIO()
    out.write(f"# GDELT 2.0, jour UTC {day.isoformat()}, lieu d'action {PAYS}\n")
    out.write(f"# tranches manquantes : {','.join(sorted(manquantes)) or 'aucune'}\n")
    out.write("\t".join(COLONNES) + "\n")
    for r in rows:
        out.write("\t".join(v.replace("\t", " ").replace("\n", " ") for v in r) + "\n")
    # mtime fixé : même contenu -> même empreinte, donc archive idempotente
    return gzip.compress(out.getvalue().encode("utf-8"), mtime=0)


def jours_a_traiter(
    conn: sqlite3.Connection, depuis: dt.date, today: dt.date, source_id: str = SOURCE_ID
) -> Iterator[dt.date]:
    day = today - dt.timedelta(days=1)  # dernier jour UTC complet
    while day >= depuis:
        if not is_archived(conn, source_id, f"{day.isoformat()}.tsv.gz"):
            yield day
        day -= dt.timedelta(days=1)


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    opener: Opener = urlopen,
    today: dt.date | None = None,
    depuis: dt.date = DEPUIS,
    max_jours: int = 7,
    cache_dir: Path = CACHE_DIR,
    traduction: bool = False,
) -> list[str]:
    today = today or dt.datetime.now(dt.UTC).date()
    source_id = SOURCE_ID_TRADUCTION if traduction else SOURCE_ID
    flux = FLUX_TRADUCTION if traduction else ""
    if traduction:
        cache_dir = cache_dir / "traduction"
    if not traduction and not is_archived(conn, SOURCE_ID, DOMAINES_ID):
        with opener(DOMAINES_URL) as response:
            store(
                conn,
                raw_dir,
                source_id=SOURCE_ID,
                external_id=DOMAINES_ID,
                url=DOMAINES_URL,
                fetched_at=now_iso(),
                chunks=[response.read()],
                suffix=".txt",
            )
    collected = []
    for day in jours_a_traiter(conn, depuis, today, source_id):
        if len(collected) >= max_jours:
            break
        start = time.monotonic()
        data = extrait_jour(day, opener, cache_dir, flux)
        name = f"{day.isoformat()}.tsv.gz"
        store(
            conn,
            raw_dir,
            source_id=source_id,
            external_id=name,
            url="https://data.gdeltproject.org/gdeltv2/",
            fetched_at=now_iso(),
            chunks=[data],
            suffix=".tsv.gz",
        )
        collected.append(name)
        print(f"[gdelt] {name} ({len(data) // 1024} Ko, {time.monotonic() - start:.0f} s)")
    # Le cache ne sert qu'aux jours voisins : on garde ceux proches d'hier et du dernier traité.
    if collected:
        last = dt.date.fromisoformat(collected[-1][:10])
        keep = {(ref - dt.timedelta(days=k)).isoformat() for ref in (today, last) for k in range(4)}
        for old in cache_dir.glob("*.json"):
            if old.stem not in keep:
                old.unlink()
    print(f"[gdelt] {len(collected)} jour(s) collecté(s)")
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.gdelt")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--depuis", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--max-jours", type=int, default=7)
    parser.add_argument(
        "--traduction", action="store_true", help="flux traduit (presse non anglophone, D7)"
    )
    args = parser.parse_args(argv)
    depuis = args.depuis or (DEPUIS_TRADUCTION if args.traduction else DEPUIS)
    conn = connect(args.db)
    try:
        init_db(conn)
        collect(
            conn,
            args.raw_dir,
            depuis=depuis,
            max_jours=args.max_jours,
            traduction=args.traduction,
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
