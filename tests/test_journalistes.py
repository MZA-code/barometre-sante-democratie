# ruff: noqa: E501  (lignes de seed de test : longues voulues)
import csv
import datetime as dt
from pathlib import Path

import pytest

from extract import journalistes
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
INDICATOR = load_grid().indicators[journalistes.INDICATOR]
COLS = "date;date_approximative;mesure;nb_journalistes;media;autorite;contexte;source_url;extrait;controle;a_verifier;note"


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
        external_id=journalistes.SEED,
        url="data/seed",
        fetched_at="2026-11-05T00:00:00Z",
        chunks=[data],
        suffix=".csv",
    )


def test_counted_measures_and_convocations_apart(conn, tmp_path):
    raw = tmp_path / "raw"
    put(
        conn,
        raw,
        seed(
            "2024-07-28;non;garde_a_vue;2;deux journalistes;police;JO;https://x;extrait;ok;oui;",
            "2024-09-01;oui;condamnation;1;média;justice;manif;https://x;extrait;ok;oui;",
            "2025-04-23;non;convocation;1;pigiste;gendarmerie;tweet;https://x;extrait;ok;oui;",
        ),
    )
    drafts = journalistes.extract(conn, raw)
    assert [d.attributes["comptee"] for d in drafts] == [True, True, False]
    assert "nom" not in str(drafts[0].attributes)
    write_facts(conn, drafts)
    events = metrics.load_events(conn, INDICATOR)
    v = metrics.window_values(events, metrics.Window("t", 730, D(2024, 1, 1), D(2025, 12, 31)), {})
    assert (v["nb_journalistes_mesures"], v["nb_journalistes_convoques"]) == (3, 1)


def test_unknown_measure_is_rejected(conn, tmp_path):
    put(conn, tmp_path / "raw", seed("2024-01-01;non;menace;1;m;a;c;https://x;e;ok;oui;"))
    with pytest.raises(ValueError, match="inconnue"):
        journalistes.extract(conn, tmp_path / "raw")


def test_project_seed_is_valid():
    path = Path(__file__).resolve().parent.parent / "data" / "seed" / journalistes.SEED
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter=";"))
    assert rows and all(r["mesure"] in journalistes.LIBELLES and r["extrait"] for r in rows)
