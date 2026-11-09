import json

import pytest

from storage.archive import (
    CHECKS_FILE,
    is_archived,
    last_checks,
    record_check,
    reindex,
    sha256_file,
    store,
    verify,
)
from storage.db import connect, init_db


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def put(conn, raw_dir, content: bytes, external_id="doc.xml", fetched_at="2026-10-26T09:00:00Z"):
    return store(
        conn,
        raw_dir,
        source_id="dila_legi",
        external_id=external_id,
        url=f"https://example.org/{external_id}",
        fetched_at=fetched_at,
        chunks=[content[:3], content[3:]],
        suffix=".xml",
    )


def test_store_writes_file_meta_and_index(conn, tmp_path):
    raw = tmp_path / "raw"
    doc = put(conn, raw, b"<loi>contenu</loi>")

    assert doc.created
    assert doc.path.read_bytes() == b"<loi>contenu</loi>"
    assert sha256_file(doc.path) == doc.sha256
    assert not doc.path.stat().st_mode & 0o222, "le fichier brut doit être en lecture seule"
    meta = json.loads(doc.path.with_name(f"{doc.sha256}.meta.json").read_text())
    assert meta["url"] == "https://example.org/doc.xml"
    row = conn.execute("SELECT * FROM raw_documents WHERE id = ?", (doc.id,)).fetchone()
    assert row["sha256"] == doc.sha256 and row["path"] == meta["path"]
    assert is_archived(conn, "dila_legi", "doc.xml")
    assert list(doc.path.parent.glob(".tmp-*")) == []


def test_store_twice_creates_no_duplicate(conn, tmp_path):
    raw = tmp_path / "raw"
    first = put(conn, raw, b"abcdef")
    second = put(conn, raw, b"abcdef", fetched_at="2026-10-27T09:00:00Z")

    assert not second.created and second.id == first.id
    assert conn.execute("SELECT count(*) FROM raw_documents").fetchone()[0] == 1
    assert len(list(first.path.parent.iterdir())) == 2  # fichier + métadonnées


def test_changed_content_is_archived_as_new_version(conn, tmp_path):
    raw = tmp_path / "raw"
    v1 = put(conn, raw, b"version 1")
    v2 = put(conn, raw, b"version 2")
    assert v2.created and v1.sha256 != v2.sha256
    assert v1.path.read_bytes() == b"version 1"


def test_reindex_rebuilds_index_deterministically(tmp_path):
    raw = tmp_path / "raw"
    conn = connect(tmp_path / "a.sqlite")
    init_db(conn)
    put(conn, raw, b"b", external_id="b", fetched_at="2026-01-02T00:00:00Z")
    put(conn, raw, b"a", external_id="a", fetched_at="2026-01-01T00:00:00Z")

    rows = []
    for name in ("x.sqlite", "y.sqlite"):
        fresh = connect(tmp_path / name)
        init_db(fresh)
        assert reindex(fresh, raw) == 2
        assert reindex(fresh, raw) == 0
        rows.append([tuple(r) for r in fresh.execute("SELECT * FROM raw_documents ORDER BY id")])
    assert rows[0] == rows[1]
    assert [r[2] for r in rows[0]] == ["a", "b"]  # trié par date de collecte


def test_verify_detects_tampering(conn, tmp_path):
    raw = tmp_path / "raw"
    doc = put(conn, raw, b"original")
    assert verify(conn, raw) == []
    doc.path.chmod(0o644)
    doc.path.write_bytes(b"modifie")
    assert len(verify(conn, raw)) == 1


def test_record_check_is_logged_on_disk_and_restored_by_reindex(tmp_path):
    raw = tmp_path / "raw"
    with connect(tmp_path / "a.sqlite") as conn:
        init_db(conn)
        record_check(conn, raw, "dila_legi", "2026-11-09T06:31:00Z")
        record_check(conn, raw, "dila_legi", "2026-11-09T06:31:00Z")  # rejoué : ignoré
        record_check(conn, raw, "dila_legi", "2026-11-10T06:31:00Z")
        assert last_checks(conn) == {"dila_legi": "2026-11-10T06:31:00Z"}
    lines = (raw / "dila_legi" / CHECKS_FILE).read_text("utf-8").splitlines()
    assert len(lines) == 2

    with connect(tmp_path / "fresh.sqlite") as fresh:
        init_db(fresh)
        reindex(fresh, raw)
        rows = fresh.execute("SELECT checked_at FROM source_checks ORDER BY 1").fetchall()
        assert [r[0] for r in rows] == ["2026-11-09T06:31:00Z", "2026-11-10T06:31:00Z"]
