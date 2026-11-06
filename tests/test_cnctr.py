import csv
import datetime as dt
from pathlib import Path

import pytest

from extract import cnctr
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
INDICATOR = load_grid().indicators[cnctr.INDICATOR]
SEED = (
    "annee;personnes_surveillees;demandes_techniques;rapport;rapport_url;controle;a_verifier;note\n"
    "2024;24308;98883;R2024.pdf;https://x/R2024.pdf;ok;oui;\n"
    "2025;25332;100813;R2025.pdf;https://x/R2025.pdf;ok;oui;\n"
)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_facts_cite_seed_and_archived_report(conn, tmp_path):
    raw = tmp_path / "raw"
    seed = store(
        conn,
        raw,
        source_id="seed_manuel",
        external_id=cnctr.SEED,
        url="data/seed",
        fetched_at="2026-11-05T00:00:00Z",
        chunks=[SEED.encode()],
        suffix=".csv",
    )
    pdf = store(
        conn,
        raw,
        source_id="cnctr_rapports",
        external_id="R2025.pdf",
        url="https://x/R2025.pdf",
        fetched_at="2026-11-05T00:00:00Z",
        chunks=[b"%PDF"],
        suffix=".pdf",
    )
    drafts = {d.occurred_on: d for d in cnctr.extract(conn, raw)}
    assert drafts["2025-12-31"].raw_document_ids == (seed.id, pdf.id)
    assert drafts["2024-12-31"].attributes["rapport_archive"] is False  # PDF non archivé ici
    write_facts(conn, list(drafts.values()))
    events = metrics.load_events(conn, INDICATOR)
    v = metrics.window_values(
        events, metrics.Window("t", 365, D(2025, 11, 6), D(2026, 11, 5)), INDICATOR.ratios
    )
    assert v["personnes_surveillees"] == 25332


def test_project_seed_is_complete():
    path = Path(__file__).resolve().parent.parent / "data" / "seed" / cnctr.SEED
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter=";"))
    assert [int(r["annee"]) for r in rows] == list(range(2016, 2026))
    assert all(int(r["personnes_surveillees"]) > 15000 for r in rows)
