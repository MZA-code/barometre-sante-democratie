"""Collecteur data.gouv.fr — jeux de données listés dans config/datagouv.yaml.

Pour chaque jeu :
1. la fiche du jeu (`/api/1/datasets/<id>/`, JSON) est archivée telle quelle : elle
   documente la licence, le producteur et la liste des ressources à la date de collecte ;
2. la licence déclarée doit figurer dans `licences_acceptees`, sinon le jeu doit porter
   une `licence_derogation` écrite ; à défaut il est ignoré ;
3. chaque ressource dont le titre correspond à `inclure` (et pas à `exclure`), au
   format attendu et sous `taille_max_mo`, est téléchargée et archivée.

Les fichiers de data.gouv.fr sont publiés sous une URL horodatée
(static.data.gouv.fr/resources/<jeu>/<AAAAMMJJ-HHMMSS>/...) : une URL déjà archivée
n'est pas retéléchargée. Une nouvelle publication = nouvelle URL = nouvelle version.
L'empreinte SHA-1 annoncée par data.gouv.fr est contrôlée ; un écart est signalé
(le document reste archivé tel que reçu, règle 1).

Usage :
    python -m collectors.datagouv [--db CHEMIN] [--raw-dir DOSSIER] [--config FICHIER]
                                  [--jeux nom1 nom2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import yaml

from collectors.http import Opener, iter_chunks, now_iso, urlopen
from storage.archive import DEFAULT_RAW_DIR, archived_urls, store
from storage.db import DEFAULT_DB_PATH, ROOT, connect, init_db

SOURCE_ID = "datagouv"
API_URL = "https://www.data.gouv.fr/api/1/datasets/{id}/"
DEFAULT_CONFIG = ROOT / "config" / "datagouv.yaml"


@dataclass(frozen=True)
class DatasetSpec:
    id: str
    nom: str
    inclure: str
    formats: tuple[str, ...]
    taille_max_mo: float
    exclure: str | None = None
    licence_derogation: str | None = None

    def wants(self, resource: dict) -> bool:
        title = resource.get("title") or ""
        if not re.search(self.inclure, title):
            return False
        if self.exclure and re.search(self.exclure, title):
            return False
        return (resource.get("format") or "").lower() in self.formats


@dataclass(frozen=True)
class Config:
    licences_acceptees: frozenset[str]
    jeux: tuple[DatasetSpec, ...]


@dataclass
class Report:
    archived: list[str]
    unchanged: list[str]
    skipped: list[str]
    warnings: list[str]


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    jeux = []
    for j in raw["jeux"]:
        jeux.append(
            DatasetSpec(
                id=j["id"],
                nom=j["nom"],
                inclure=j["inclure"],
                exclure=j.get("exclure"),
                formats=tuple(fmt.lower() for fmt in j["formats"]),
                taille_max_mo=float(j["taille_max_mo"]),
                licence_derogation=j.get("licence_derogation"),
            )
        )
    noms = [j.nom for j in jeux]
    if len(set(noms)) != len(noms):
        raise ValueError("config data.gouv.fr : noms de jeux en double")
    return Config(frozenset(raw["licences_acceptees"]), tuple(jeux))


def metadata_external_id(dataset_id: str) -> str:
    return f"{dataset_id}/fiche.json"


def resource_external_id(dataset_id: str, resource_id: str) -> str:
    return f"{dataset_id}/{resource_id}"


def suffix_for(resource: dict) -> str:
    ext = PurePosixPath(urlparse(resource["url"]).path).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,5}", ext):
        return ext
    fmt = (resource.get("format") or "").lower()
    return f".{fmt}" if re.fullmatch(r"[a-z0-9]{1,5}", fmt) else ""


def _sha1_tee(chunks: Iterable[bytes], digest: hashlib._Hash) -> Iterator[bytes]:
    for chunk in chunks:
        digest.update(chunk)
        yield chunk


def collect_dataset(
    conn: sqlite3.Connection,
    raw_dir: Path,
    spec: DatasetSpec,
    licences: frozenset[str],
    report: Report,
    opener: Opener = urlopen,
) -> None:
    tag = f"[datagouv] {spec.nom}"
    api_url = API_URL.format(id=spec.id)
    with opener(api_url) as response:
        body = response.read()
    store(
        conn,
        raw_dir,
        source_id=SOURCE_ID,
        external_id=metadata_external_id(spec.id),
        url=api_url,
        fetched_at=now_iso(),
        chunks=[body],
        suffix=".json",
    )
    fiche = json.loads(body)

    licence = fiche.get("license")
    if licence not in licences:
        if not spec.licence_derogation:
            report.skipped.append(f"{spec.nom} : licence « {licence} » non acceptée")
            print(f"{tag} : ignoré, licence « {licence} » non acceptée")
            return
        report.warnings.append(f"{spec.nom} : licence « {licence} » admise par dérogation")

    selected = [r for r in fiche.get("resources", []) if spec.wants(r)]
    if not selected:
        report.warnings.append(f"{spec.nom} : aucune ressource ne correspond aux filtres")
        print(f"{tag} : aucune ressource ne correspond aux filtres")
        return

    for res in selected:
        label = f"{spec.nom}/{res.get('title')}"
        ext_id = resource_external_id(spec.id, res["id"])
        size = res.get("filesize")
        if size is not None and size > spec.taille_max_mo * 1_000_000:
            report.skipped.append(f"{label} : {size / 1e6:.0f} Mo > {spec.taille_max_mo:g} Mo")
            print(f"{tag} : {res.get('title')} ignorée ({size / 1e6:.0f} Mo)")
            continue
        if res["url"] in archived_urls(conn, SOURCE_ID, ext_id):
            report.unchanged.append(label)
            print(f"{tag} : {res.get('title')} déjà archivée")
            continue

        sha1 = hashlib.sha1()
        with opener(res["url"]) as response:
            doc = store(
                conn,
                raw_dir,
                source_id=SOURCE_ID,
                external_id=ext_id,
                url=res["url"],
                fetched_at=now_iso(),
                chunks=_sha1_tee(iter_chunks(response), sha1),
                suffix=suffix_for(res),
            )
        announced = res.get("checksum") or {}
        if announced.get("type") == "sha1" and announced.get("value") != sha1.hexdigest():
            report.warnings.append(f"{label} : SHA-1 différent de celui annoncé par data.gouv.fr")
        (report.archived if doc.created else report.unchanged).append(label)
        state = "nouvelle version" if doc.created else "inchangée"
        print(f"{tag} : {res.get('title')} {state} ({doc.sha256[:12]})")


def collect(
    conn: sqlite3.Connection,
    raw_dir: Path,
    config: Config,
    only: Iterable[str] | None = None,
    opener: Opener = urlopen,
) -> Report:
    report = Report([], [], [], [])
    wanted = set(only) if only else None
    if wanted and (unknown := wanted - {j.nom for j in config.jeux}):
        raise ValueError(f"jeux inconnus : {', '.join(sorted(unknown))}")
    for spec in config.jeux:
        if wanted is None or spec.nom in wanted:
            collect_dataset(conn, raw_dir, spec, config.licences_acceptees, report, opener)
    for w in report.warnings:
        print(f"[datagouv] attention : {w}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.datagouv")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--jeux", nargs="+", help="noms de jeux (défaut : tous)")
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        init_db(conn)
        report = collect(conn, args.raw_dir, load_config(args.config), args.jeux)
    finally:
        conn.close()
    print(
        f"[datagouv] {len(report.archived)} archivée(s), {len(report.unchanged)} inchangée(s),"
        f" {len(report.skipped)} ignorée(s), {len(report.warnings)} avertissement(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
