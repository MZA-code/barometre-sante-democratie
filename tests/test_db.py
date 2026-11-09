import sqlite3

import pytest

from storage.db import DERIVED_TABLES, connect, init_db, load_sources, main, reset_derived

SHA = "a" * 64


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def insert_raw(conn, external_id="doc-1", sha=SHA):
    cur = conn.execute(
        "INSERT INTO raw_documents (source_id, external_id, url, fetched_at, sha256, path)"
        " VALUES ('dila_legi', ?, 'https://example.org/doc', '2026-10-26T09:00:00Z', ?, 'x')",
        (external_id, sha),
    )
    return cur.lastrowid


def insert_fact(conn):
    cur = conn.execute(
        "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, extraction_method)"
        " VALUES ('D2.contournement_parlement', 'loi_promulguee', '2024-01-01', 'Loi', 'test')"
    )
    return cur.lastrowid


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {r["name"] for r in rows}


def test_init_creates_all_tables(conn):
    assert table_names(conn) == {
        "sources",
        "raw_documents",
        "source_checks",
        "facts",
        "fact_sources",
        "metrics",
        "scores",
        "score_facts",
    }


def test_init_is_idempotent_and_seeds_sources(conn):
    init_db(conn)
    ids = {r["id"] for r in conn.execute("SELECT id FROM sources")}
    assert ids == {s["id"] for s in load_sources()}
    assert all(r["licence"] for r in conn.execute("SELECT licence FROM sources"))


def test_raw_documents_are_immutable(conn):
    raw_id = insert_raw(conn)
    with pytest.raises(sqlite3.IntegrityError, match="immuable"):
        conn.execute("UPDATE raw_documents SET url = 'autre' WHERE id = ?", (raw_id,))
    with pytest.raises(sqlite3.IntegrityError, match="immuable"):
        conn.execute("DELETE FROM raw_documents WHERE id = ?", (raw_id,))


def test_raw_documents_reject_duplicate_and_bad_hash(conn):
    insert_raw(conn)
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(conn)
    with pytest.raises(sqlite3.IntegrityError):
        insert_raw(conn, external_id="doc-2", sha="court")


def test_same_document_new_content_is_a_new_version(conn):
    insert_raw(conn, sha="a" * 64)
    insert_raw(conn, sha="b" * 64)
    assert conn.execute("SELECT count(*) FROM raw_documents").fetchone()[0] == 2


def test_raw_documents_require_known_source(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO raw_documents (source_id, external_id, url, fetched_at, sha256, path)"
            " VALUES ('inconnue', 'x', 'u', '2026-10-26', ?, 'p')",
            (SHA,),
        )


def test_fact_sources_require_existing_raw_document(conn):
    fact_id = insert_fact(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fact_sources (fact_id, raw_document_id) VALUES (?, 999)", (fact_id,)
        )


def test_score_must_be_between_0_and_4(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO scores VALUES ('D2', '2024-01-01', 'w', 5, 'v0', '2026-10-26T09:00:00Z')"
        )


def test_reset_derived_keeps_raw_archive(conn):
    raw_id = insert_raw(conn)
    fact_id = insert_fact(conn)
    conn.execute("INSERT INTO fact_sources VALUES (?, ?)", (fact_id, raw_id))
    conn.commit()

    reset_derived(conn)

    for table in DERIVED_TABLES:
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM raw_documents").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] > 0


def test_cli_init_and_reset_on_empty_base(tmp_path):
    db = tmp_path / "cli.sqlite"
    assert main(["init", "--db", str(db)]) == 0
    assert main(["reset-derived", "--db", str(db)]) == 0
    assert db.exists()
