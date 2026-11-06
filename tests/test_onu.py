# ruff: noqa: E501  (lignes de seed de test : longues voulues)
import csv
import io
from pathlib import Path

import pytest

from extract import onu
from storage.archive import store
from storage.db import connect, init_db

COLS = ";".join(onu.COLONNES)
SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "seed" / onu.SEED


def seed(*rows):
    return (COLS + "\n" + "\n".join(rows) + "\n").encode()


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def put(conn, raw, data):
    store(
        conn,
        raw,
        source_id="seed_manuel",
        external_id=onu.SEED,
        url="data/seed",
        fetched_at="2026-11-06T00:00:00Z",
        chunks=[data],
        suffix=".csv",
    )


def test_une_declaration_par_ligne(conn, tmp_path):
    raw = tmp_path / "raw"
    put(
        conn,
        raw,
        seed(
            "2026-10-28;experts;communiqué;thème;Titre;fr;« extrait »;;https://www.ohchr.org/x;ok"
        ),
    )
    (d,) = onu.extract(conn, raw)
    assert (d.fact_type, d.occurred_on, d.official_ref) == (
        "declaration_onu",
        "2026-10-28",
        "https://www.ohchr.org/x",
    )
    assert d.attributes["extrait"] == "« extrait »"
    assert d.attributes["extrait_complementaire"] is None


def test_langue_inconnue_refusee(conn, tmp_path):
    put(conn, tmp_path / "raw", seed("2026-10-28;o;t;th;T;de;e;;https://x;ok"))
    with pytest.raises(ValueError, match="langue"):
        onu.extract(conn, tmp_path / "raw")


def test_source_obligatoire(conn, tmp_path):
    put(conn, tmp_path / "raw", seed("2026-10-28;o;t;th;T;fr;e;;;ok"))
    with pytest.raises(ValueError, match="source"):
        onu.extract(conn, tmp_path / "raw")


def test_seed_reel_bien_forme():
    rows = list(csv.DictReader(io.StringIO(SEED_FILE.read_text(encoding="utf-8")), delimiter=";"))
    assert rows and all(r["source_url"].startswith("https://www.ohchr.org/") for r in rows)
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
