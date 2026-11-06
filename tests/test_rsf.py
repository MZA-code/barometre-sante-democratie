import datetime as dt
import io
import urllib.error
from contextlib import contextmanager

import pytest

from collectors import rsf as collector
from extract import rsf
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.db import connect, init_db

D = dt.date
INDICATOR = load_grid().indicators[rsf.INDICATOR]
OLD = "﻿Year (N);ISO;Rank N;Score N;Rank N-1\n2005;DNK;1;0,5;1\n2005;FRA;30;6,25;19\n"
NEW = "ISO;Score 2026;Rank;Zone\nFIN;86,22;6;UE\nFRA;76,68;25;UE\nNOR;92,00;1;UE\n"


def test_parse_both_formats_and_encodings():
    assert rsf.parse(OLD.encode("utf-8")) == ({"rang": 30, "score": 6.25}, 2)
    assert rsf.parse(NEW.encode("cp1252")) == ({"rang": 25, "score": 76.68}, 3)


def test_score_period_labels():
    assert "plus bas" in rsf.periode(2012)
    assert "2022" in rsf.periode(2026)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_collect_extract_and_window_rank(conn, tmp_path):
    files = {2025: OLD.replace("2005", "2025"), 2026: NEW}

    @contextmanager
    def web(url):
        year = int(url.rsplit("/", 1)[-1][:4])
        if year not in files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        yield io.BytesIO(files[year].encode())

    raw = tmp_path / "raw"
    got = collector.collect(conn, raw, opener=web, today=D(2026, 11, 5))
    assert got == ["2025.csv", "2026.csv"]
    drafts = rsf.extract(conn, raw)
    assert {d.occurred_on: d.attributes["rang"] for d in drafts} == {
        "2025-01-01": 30,
        "2026-01-01": 25,
    }
    assert all(d.attributes["date_conventionnelle"] for d in drafts)
    write_facts(conn, drafts)
    events = metrics.load_events(conn, INDICATOR)
    v = metrics.window_values(
        events, metrics.Window("t", 365, D(2025, 11, 6), D(2026, 11, 5)), INDICATOR.ratios
    )
    assert v["nb_editions_rsf"] == 1 and v["rang_rsf"] == 25


def test_categories_follow_rsf_bounds():
    assert rsf.categorie(85.0) == (0, "Bonne situation")
    assert rsf.categorie(84.99)[0] == 1
    assert rsf.categorie(70.0)[0] == 1
    assert rsf.categorie(55.0)[0] == 2
    assert rsf.categorie(40.0)[0] == 3
    assert rsf.categorie(39.99) == (4, "Situation très grave")


def test_published_situation_is_checked_against_bounds():
    ok = "ISO;Score;Rank;Situation\nFRA;78,65;21;Situation plutôt bonne\n"
    assert rsf.parse(ok.encode())[0]["rang"] == 21
    bad = "ISO;Score;Rank;Situation\nFRA;78,65;21;Situation problématique\n"
    with pytest.raises(ValueError, match="catégorie publiée"):
        rsf.parse(bad.encode())


def test_window_category_only_from_2022_editions():
    events = [
        metrics.Event(day=D(2021, 1, 1), fact_id=1, fact_type="classement_rsf", rang=34),
        metrics.Event(
            day=D(2022, 1, 1), fact_id=2, fact_type="classement_rsf", rang=26, niveau_categorie=1
        ),
    ]
    days = {
        d: v
        for d, v in metrics.rolling(events, 365, D(2021, 6, 1), D(2022, 6, 1), INDICATOR.ratios)
    }
    assert "categorie_rsf" not in days[D(2021, 6, 1)]
    assert days[D(2022, 6, 1)]["categorie_rsf"] == 1


def test_published_situation_is_checked_only_from_2022():
    # avant 2022, l'échelle et les libellés diffèrent : la colonne n'est pas contrôlée
    old = "ISO;Score;Rank;Situation\nFRA;22,21;34;Situation plutôt bonne\n"
    assert rsf.parse(old.encode(), annee=2019)[0]["rang"] == 34
    with pytest.raises(ValueError, match="catégorie publiée"):
        rsf.parse(old.encode(), annee=2022)
