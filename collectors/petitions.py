"""Collecteur des pétitions citoyennes de l'Assemblée nationale (indicateur D2.3).

Deux sources :
  1. le jeu « Pétitions de l'Assemblée nationale » de data.gouv.fr (Licence Ouverte, mis à jour
     chaque lundi) sert seulement à découvrir les pétitions qui approchent des seuils : on en
     retient les identifiants des pétitions de 50 000 signatures ou plus. Constaté le
     2026-11-10 : le jeu n'est pas complet (la pétition « Supprimer CNews de l'audiovisuel
     français », plus de 700 000 signatures, en est absente) ;
  2. la page publique de chaque pétition retenue, ou listée dans config/petitions_suivies.yaml,
     est relue chaque jour sur petitions.assemblee-nationale.fr (autorisé par robots.txt), une
     requête par seconde. On en archive un JSON : titre, nombre de signatures, statut affiché
     (classée par la commission, acceptée, ouverte, expirée), date de classement, commission.
     Jamais le nom de l'auteur ni le texte de la pétition. Une nouvelle version n'est archivée
     que si une valeur change : l'historique des signatures et du statut reste dans l'archive.

Usage :
    python -m collectors.petitions [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import yaml

from collectors.http import Opener, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, record_check, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

ROOT = Path(__file__).resolve().parent.parent
SUIVIES_PATH = ROOT / "config" / "petitions_suivies.yaml"
SOURCE_ID = "petitions_an"
DATAGOUV_CSV = "https://data-pipeline-open.s3.sbg.io.cloud.ovh.net/an_petitions/petitions.csv"
BASE = "https://petitions.assemblee-nationale.fr/initiatives/i-{numero}"
SEUIL_SUIVI = 50_000
PAUSE_S = 1.0
TITRE = re.compile(r'<h2 class="heading2"[^>]*>(.*?)</h2>', re.S)
SIGNATURES = re.compile(r'progress__bar__number">([^<]*)<')
STATUT = re.compile(r'class="[^"]*\binitiative-status\b[^"]*"[^>]*>([^<]*)<')
CLASSEE_LE = re.compile(r"a été classée par la commission\s*:\s*(\d{2})/(\d{2})/(\d{4})")
PUBLIEE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*Identifiant")
COMMISSION = re.compile(r'<a href="/initiatives\?filter%5Barea_id%5D[^"]*">\s*([^<]*?)\s*<')


def url_petition(numero: int) -> str:
    return BASE.format(numero=numero)


def _texte(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def statut_de(libelle: str) -> str:
    bas = libelle.lower()
    if "class" in bas:
        return "classee"
    if "accept" in bas:
        return "examinee"
    if "expir" in bas:
        return "expiree"
    return "ouverte"


def lire_page(page: bytes) -> dict:
    t = page.decode("utf-8", errors="replace")
    titre, sig, st = TITRE.search(t), SIGNATURES.search(t), STATUT.search(t)
    texte = _texte(t)
    classee, commission = CLASSEE_LE.search(texte), COMMISSION.search(t)
    publiee = PUBLIEE.search(texte)
    libelle = _texte(st.group(1)) if st else ""
    nombre = re.sub(r"\D", "", sig.group(1)) if sig else ""
    return {
        "titre": _texte(titre.group(1)) if titre else "",
        "signatures": int(nombre) if nombre else None,
        "statut": statut_de(libelle),
        "libelle_statut": libelle,
        "date_decision": f"{classee.group(3)}-{classee.group(2)}-{classee.group(1)}"
        if classee
        else None,
        "commission": html.unescape(commission.group(1)) if commission else None,
        "date_publication": f"{publiee.group(3)}-{publiee.group(2)}-{publiee.group(1)}"
        if publiee
        else None,
    }


def identifiants_a_suivre(lignes: Iterable[dict], suivies: Iterable[int] = ()) -> list[int]:
    out = set(suivies)
    for r in lignes:
        try:
            if float(r.get("nb_votes") or 0) >= SEUIL_SUIVI:
                out.add(int(r["identifiant"]))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def suivies_configurees(path: Path = SUIVIES_PATH) -> list[int]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return [int(i) for i in (data or {}).get("petitions") or []]


def lignes_datagouv(opener: Opener = urlopen) -> list[dict]:
    with opener(DATAGOUV_CSV) as response:
        texte = response.read().decode("utf-8", errors="replace")
    csv.field_size_limit(1 << 24)
    return list(csv.DictReader(io.StringIO(texte), delimiter=";"))


def collect_pages(
    conn: sqlite3.Connection,
    raw_dir: Path,
    numeros: Iterable[int],
    opener: Opener = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    nouveaux = 0
    for i, numero in enumerate(numeros):
        if i:
            sleep(PAUSE_S)
        url = url_petition(numero)
        try:
            with opener(url) as response:
                infos = lire_page(response.read())
        except Exception as exc:  # page absente ou erreur passagère : on passe à la suivante
            print(f"[petitions] i-{numero} : {exc}")
            continue
        if not infos["titre"] or infos["signatures"] is None:
            print(f"[petitions] i-{numero} : page inattendue (titre ou signatures absents)")
            continue
        data = json.dumps(
            {"identifiant": numero, "url": url, **infos}, ensure_ascii=False, sort_keys=True
        )
        doc = store(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=f"i-{numero}",
            url=url,
            fetched_at=now_iso(),
            chunks=[data.encode()],
            suffix=".json",
        )
        nouveaux += doc.created
    return nouveaux


def collect(conn: sqlite3.Connection, raw_dir: Path, opener: Opener = urlopen) -> int:
    debut = now_iso()
    try:
        lignes = lignes_datagouv(opener)
    except Exception as exc:
        print(f"[petitions] jeu data.gouv indisponible ({exc}) : pétitions déjà suivies seules")
        lignes = []
    deja = [
        int(r[0][2:])
        for r in conn.execute(
            "SELECT DISTINCT external_id FROM raw_documents WHERE source_id = ?", (SOURCE_ID,)
        )
    ]
    numeros = identifiants_a_suivre(lignes, [*suivies_configurees(), *deja])
    n = collect_pages(conn, raw_dir, numeros, opener)
    record_check(conn, raw_dir, SOURCE_ID, debut)
    print(f"[petitions] {len(numeros)} pétition(s) relue(s), {n} changement(s) archivé(s)")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.petitions")
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
