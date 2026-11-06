"""Archive brute immuable (data/raw/).

Chaque document collecté est écrit tel quel sous
    data/raw/<source_id>/<external_id>/<sha256><suffixe>
accompagné d'un fichier de métadonnées
    data/raw/<source_id>/<external_id>/<sha256>.meta.json
(source, identifiant externe, URL, date de collecte, empreinte). Les fichiers sont
passés en lecture seule. L'index `raw_documents` peut être reconstruit à tout moment
depuis ces métadonnées (`reindex`), ce qui rend toute la base reproductible depuis
le seul disque.

Un même document (source, external_id) dont le contenu change est archivé comme une
nouvelle version (nouveau sha256) ; une version déjà connue n'est jamais réécrite.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
META_SUFFIX = ".meta.json"
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class StoredDocument:
    id: int
    sha256: str
    path: Path  # chemin absolu du fichier archivé
    created: bool  # False si cette version était déjà archivée


def safe_dirname(external_id: str) -> str:
    return SAFE_ID.sub("_", external_id)


def store(
    conn: sqlite3.Connection,
    raw_dir: Path,
    *,
    source_id: str,
    external_id: str,
    url: str,
    fetched_at: str,
    chunks: Iterable[bytes],
    suffix: str = "",
) -> StoredDocument:
    """Archive un document lu par morceaux et l'indexe. Idempotent sur le contenu."""
    target_dir = raw_dir / source_id / safe_dirname(external_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(dir=target_dir, prefix=".tmp-")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in chunks:
                digest.update(chunk)
                f.write(chunk)
        sha = digest.hexdigest()

        existing = conn.execute(
            "SELECT id, path FROM raw_documents"
            " WHERE source_id = ? AND external_id = ? AND sha256 = ?",
            (source_id, external_id, sha),
        ).fetchone()
        if existing:
            return StoredDocument(existing["id"], sha, raw_dir / existing["path"], False)

        final = target_dir / f"{sha}{suffix}"
        if not final.exists():
            tmp.replace(final)
            final.chmod(0o444)
        meta = {
            "source_id": source_id,
            "external_id": external_id,
            "url": url,
            "fetched_at": fetched_at,
            "sha256": sha,
            "path": final.relative_to(raw_dir).as_posix(),
        }
        meta_path = target_dir / f"{sha}{META_SUFFIX}"
        if not meta_path.exists():
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
            meta_path.chmod(0o444)
        doc_id = _insert(conn, meta)
        return StoredDocument(doc_id, sha, final, True)
    finally:
        tmp.unlink(missing_ok=True)


def _insert(conn: sqlite3.Connection, meta: dict) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO raw_documents (source_id, external_id, url, fetched_at, sha256, path)"
            " VALUES (:source_id, :external_id, :url, :fetched_at, :sha256, :path)",
            meta,
        )
    return cur.lastrowid


def is_archived(conn: sqlite3.Connection, source_id: str, external_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_documents WHERE source_id = ? AND external_id = ? LIMIT 1",
        (source_id, external_id),
    ).fetchone()
    return row is not None


def content_digest(data: bytes) -> str:
    """Empreinte du contenu d'un zip : noms et contenus des fichiers, ordre et horodatages
    internes ignorés (certains serveurs régénèrent le zip sans changer son contenu). Un
    fichier qui n'est pas un zip valide est pris tel quel."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return hashlib.sha256(data).hexdigest()
    digest = hashlib.sha256()
    with archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            digest.update(info.filename.encode())
            member = hashlib.sha256()
            with archive.open(info) as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    member.update(chunk)
            digest.update(member.digest())
    return digest.hexdigest()


def latest_version(
    conn: sqlite3.Connection, raw_dir: Path, source_id: str, external_id: str
) -> StoredDocument | None:
    row = conn.execute(
        "SELECT id, sha256, path FROM raw_documents WHERE source_id = ? AND external_id = ?"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (source_id, external_id),
    ).fetchone()
    if row is None:
        return None
    return StoredDocument(row["id"], row["sha256"], raw_dir / row["path"], False)


def store_if_content_changed(
    conn: sqlite3.Connection,
    raw_dir: Path,
    *,
    source_id: str,
    external_id: str,
    url: str,
    fetched_at: str,
    data: bytes,
    suffix: str = "",
) -> StoredDocument:
    """Comme `store`, mais n'archive pas un zip dont le contenu est identique à la dernière
    version (created=False). Le fichier archivé reste l'original reçu, octet pour octet."""
    previous = latest_version(conn, raw_dir, source_id, external_id)
    if previous and content_digest(previous.path.read_bytes()) == content_digest(data):
        return previous
    return store(
        conn,
        raw_dir,
        source_id=source_id,
        external_id=external_id,
        url=url,
        fetched_at=fetched_at,
        chunks=[data],
        suffix=suffix,
    )


def archived_urls(conn: sqlite3.Connection, source_id: str, external_id: str) -> set[str]:
    """URL déjà archivées pour un document (toutes versions confondues)."""
    rows = conn.execute(
        "SELECT url FROM raw_documents WHERE source_id = ? AND external_id = ?",
        (source_id, external_id),
    )
    return {row["url"] for row in rows}


def reindex(conn: sqlite3.Connection, raw_dir: Path = DEFAULT_RAW_DIR) -> int:
    """Ajoute à `raw_documents` les documents présents sur disque mais absents de l'index.

    Parcours trié (date de collecte, chemin) pour que les identifiants attribués soient
    les mêmes à chaque reconstruction depuis une base vide. Retourne le nombre ajouté.
    """
    metas = [json.loads(p.read_text("utf-8")) for p in raw_dir.glob(f"*/*/*{META_SUFFIX}")]
    metas.sort(key=lambda m: (m["fetched_at"], m["path"]))
    added = 0
    for meta in metas:
        known = conn.execute(
            "SELECT 1 FROM raw_documents WHERE source_id = ? AND external_id = ? AND sha256 = ?",
            (meta["source_id"], meta["external_id"], meta["sha256"]),
        ).fetchone()
        if not known:
            _insert(conn, meta)
            added += 1
    return added


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(conn: sqlite3.Connection, raw_dir: Path = DEFAULT_RAW_DIR) -> list[str]:
    """Recalcule l'empreinte de chaque document archivé. Retourne les anomalies."""
    problems = []
    for row in conn.execute("SELECT id, path, sha256 FROM raw_documents ORDER BY id"):
        path = raw_dir / row["path"]
        if not path.exists():
            problems.append(f"#{row['id']} manquant : {row['path']}")
        elif sha256_file(path) != row["sha256"]:
            problems.append(f"#{row['id']} empreinte différente : {row['path']}")
    return problems
