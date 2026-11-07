# ruff: noqa: E501
import csv
import io
from contextlib import contextmanager
from pathlib import Path

import pytest

from collectors import rapports
from extract import usage_force as uf
from storage.archive import is_archived, store
from storage.db import connect, init_db

SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "seed" / uf.SEED
COLS = ";".join(uf.COLONNES)
L = "2024;igpn_lbd_declarations;1585;IGPN;Rapport 2024;https://www.vie-publique.fr/files/rapport/pdf/300479.pdf;87;Usages déclarés du LBD … 1 585;ok;"


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def put(conn, raw, *rows):
    store(
        conn,
        raw,
        source_id="seed_manuel",
        external_id=uf.SEED,
        url="data/seed",
        fetched_at="2026-11-07T00:00:00Z",
        chunks=[(COLS + "\n" + "\n".join(rows) + "\n").encode()],
        suffix=".csv",
    )


def test_un_fait_par_serie_et_annee_relie_au_pdf_archive(conn, tmp_path):
    raw = tmp_path / "raw"
    put(conn, raw, L)
    store(
        conn,
        raw,
        source_id=rapports.SOURCE_ID,
        external_id="300479.pdf",
        url="u",
        fetched_at="2026-11-07T00:00:00Z",
        chunks=[b"%PDF"],
        suffix=".pdf",
    )
    (f,) = uf.extract(conn, raw)
    assert (f.occurred_on, f.attributes["valeur"], f.attributes["serie"]) == (
        "2024-12-31",
        1585,
        "igpn_lbd_declarations",
    )
    assert f.attributes["url"].endswith("300479.pdf#page=87") and len(f.raw_document_ids) == 2


def test_doublon_refuse(conn, tmp_path):
    put(conn, tmp_path / "raw", L, L)
    with pytest.raises(ValueError, match="en double"):
        uf.extract(conn, tmp_path / "raw")


def test_seed_reel():
    rows = list(csv.DictReader(SEED_FILE.open(encoding="utf-8"), delimiter=";"))
    assert tuple(rows[0].keys()) == uf.COLONNES
    assert {r["serie"] for r in rows} == set(uf.SERIES)
    lbd = {int(r["annee"]): int(r["valeur"]) for r in rows if r["serie"] == "igpn_lbd_declarations"}
    assert sorted(lbd) == list(range(2017, 2025))
    for r in rows:  # chaque valeur figure dans la ligne citée (écrite avec espaces de milliers)
        assert (
            f"{int(r['valeur']):,}".replace(",", " ") in r["citation"]
            or r["valeur"] in r["citation"]
        )


def test_collecteur_archive_chaque_pdf_une_fois(conn, tmp_path):
    seed = tmp_path / "s.csv"
    seed.write_text(
        COLS + "\n" + L + "\n" + L.replace("2024;", "2023;", 1) + "\n", encoding="utf-8"
    )

    @contextmanager
    def faux(url):
        yield io.BytesIO(b"%PDF-1.4")

    assert rapports.collect(conn, tmp_path / "raw", opener=faux, seed=seed) == ["300479.pdf"]
    assert is_archived(conn, rapports.SOURCE_ID, "300479.pdf")
    assert rapports.collect(conn, tmp_path / "raw", opener=faux, seed=seed) == []
