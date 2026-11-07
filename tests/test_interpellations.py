# ruff: noqa: E501
import csv
from pathlib import Path

import pytest

from extract import interpellations as it
from storage.archive import store
from storage.db import connect, init_db

COLS = ";".join(it.COLONNES)
SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "seed" / it.SEED


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def put(conn, raw, *rows):
    data = (COLS + "\n" + "\n".join(rows) + "\n").encode()
    store(
        conn,
        raw,
        source_id="seed_manuel",
        external_id=it.SEED,
        url="data/seed",
        fetched_at="2026-11-07T00:00:00Z",
        chunks=[data],
        suffix=".csv",
    )


L1 = "2016-05-17;loi Travail 2016;5;France entière;interpellations;87;ministère de l'Intérieur;France 24;T;https://x/a;Au total, 87 personnes ont été interpellées;ok;oui;"
L2 = "2016-05-17;loi Travail 2016;5;France entière;gardes_a_vue;46;ministère de l'Intérieur;France 24;T;https://x/a;et 46 placées en garde à vue;ok;oui;"
L3 = "2016-05-17;loi Travail 2016;5;Paris;interpellations;20;préfecture de police;X;T;https://x/b;20 interpellations;ok;oui;bilan de 18 h"


def test_un_fait_par_journee_et_perimetre(conn, tmp_path):
    put(conn, tmp_path / "raw", L1, L2, L3)
    france, paris = it.extract(conn, tmp_path / "raw")
    assert (
        france.attributes["perimetre"] == "France entière"
        and paris.attributes["perimetre"] == "Paris"
    )
    assert france.attributes["mesures"]["interpellations"]["nombre"] == 87
    assert france.attributes["mesures"]["gardes_a_vue"]["nombre"] == 46
    assert paris.attributes["mesures"]["interpellations"]["note"] == "bilan de 18 h"


def test_doublon_et_mesure_inconnue_refuses(conn, tmp_path):
    put(conn, tmp_path / "raw", L1, L1)
    with pytest.raises(ValueError, match="en double"):
        it.extract(conn, tmp_path / "raw")


def test_seed_reel_coherent():
    rows = list(csv.DictReader(SEED_FILE.open(encoding="utf-8"), delimiter=";"))
    assert tuple(rows[0].keys()) == it.COLONNES
    mob = {
        r["date"]
        for r in csv.DictReader(
            (SEED_FILE.parent / "mobilisations_nationales.csv").open(encoding="utf-8"),
            delimiter=";",
        )
    }
    for r in rows:
        assert r["date"] in mob, r["date"]  # seulement des journées du relevé des mobilisations
        assert r["citation"].strip() and r["source_url"].startswith("http") and r["controle"]
