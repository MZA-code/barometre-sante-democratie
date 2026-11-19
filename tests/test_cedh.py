import io
import json
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

import pytest

from collectors import cedh as collector
from extract import cedh
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.db import connect, init_db


def doc(itemid, ecli, lang, date, violation="", conclusion="", nom="AFFAIRE X c. FRANCE"):
    return {
        "columns": {
            "itemid": itemid,
            "ecli": ecli,
            "languageisocode": lang,
            "kpdate": f"{date}T00:00:00",
            "violation": violation,
            "conclusion": conclusion,
            "docname": nom,
            "appno": "1/20",
            "doctypebranch": "CHAMBER",
            "importance": "2",
            "rank": "1.0",
        }
    }


DOCS = [
    doc("001-1", "E:1", "ENG", "2025-03-01", "6;6-1", "Violation of Article 6", "CASE OF A"),
    doc("001-2", "E:1", "FRE", "2025-03-01", "", "Violation de l'article 6", "AFFAIRE A c. FRANCE"),
    # Champ `violation` vide : la conclusion suffit ; « Non-violation » ne compte pas.
    doc("001-3", "E:2", "FRE", "2025-06-01", "", "Partiellement irrecevable;Violation de P1-1"),
    doc("001-4", "E:3", "ENG", "2026-01-10", "", "No violation of Art. 8;Non-violation"),
    doc("001-5", "E:4", "ENG", "2026-02-10", "14+8;3", "Violation of Article 3"),
]


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def web_de(docs, rank="1.0"):
    @contextmanager
    def web(url):
        q = parse_qs(urlparse(url).query)
        start, length = int(q["start"][0]), int(q["length"][0])
        page = [{"columns": {**d["columns"], "rank": rank}} for d in docs[start : start + length]]
        yield io.BytesIO(json.dumps({"resultcount": len(docs), "results": page}).encode())

    return web


def test_articles_principaux():
    assert cedh.articles("6;6-1;P1-1;14+8") == ["6", "P1-1", "14"]
    assert cedh.articles("") == []


def test_collecte_pagine_et_ignore_le_rang(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "PAGE", 2)
    raw = tmp_path / "raw"
    assert collector.collect(conn, raw, opener=web_de(DOCS), pause=0) is True
    assert collector.collect(conn, raw, opener=web_de(DOCS, rank="9.9"), pause=0) is False
    assert collector.collect(conn, raw, opener=web_de(DOCS[:-1]), pause=0) is True
    assert collector.collect(conn, raw, opener=web_de(DOCS), pause=0) is True


def test_extraction_et_metrique(conn, tmp_path):
    raw = tmp_path / "raw"
    collector.collect(conn, raw, opener=web_de(DOCS), pause=0)
    drafts = cedh.extract(conn, raw)
    par = {d.official_ref: d for d in drafts}
    assert len(drafts) == 4
    assert par["E:1"].title == "AFFAIRE A c. FRANCE"  # version française préférée
    assert par["E:1"].attributes["articles_violes"] == ["6"]
    assert par["E:2"].fact_type == "arret_cedh_violation"
    assert par["E:3"].fact_type == "arret_cedh_sans_violation"
    assert par["E:4"].attributes["articles_violes"] == ["14", "3"]
    write_facts(conn, drafts)
    ind = load_grid().indicators[cedh.INDICATOR]
    events = metrics.load_events(conn, ind)
    assert sum(1 for e in events if e.fact_type == "arret_cedh_violation") == 3
