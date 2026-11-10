"""D7 · Libertés en pratique : grille, catégories, groupes de presse, comptage."""

import datetime as dt
from pathlib import Path

import pytest
import yaml

from extract.common import FactDraft, write_facts
from scoring import metrics
from scoring.grid import DEFAULT_GRID_PATH, load_grid, load_raw
from storage.archive import store
from storage.db import connect, init_db

ROOT = Path(__file__).resolve().parents[1]
D7 = "D7.libertes_en_pratique"
CATEGORIES = {
    "interpellations",
    "expression",
    "reunion",
    "surveillance",
    "force",
    "decisions_ignorees",
}


def test_d7_dans_la_grille():
    ind = load_grid().indicators[D7]
    assert ind.fact_types == ("fait_presse_valide", "constat_institutionnel")
    assert ind.scored_metric == "nb_atteintes_pratique"
    assert str(ind.history_start) == "2024-07-01"
    assert not ind.thresholds_frozen


def test_categories_figees():
    cats = load_raw(DEFAULT_GRID_PATH)["indicators"][D7]["categories"]
    assert set(cats) == CATEGORIES
    for c in cats.values():
        assert c["libelle"] and c["compte"] and c["ne_compte_pas"]
        assert isinstance(c["codes_cameo"], list)


def test_domaine_dans_un_seul_groupe():
    data = yaml.safe_load((ROOT / "config" / "medias_groupes.yaml").read_text(encoding="utf-8"))
    assert data["source"]
    domaines = [d for ds in data["groupes"].values() for d in ds]
    assert len(domaines) == len(set(domaines))
    assert "afp.com" in domaines


def test_validateurs():
    data = yaml.safe_load((ROOT / "config" / "validateurs_d7.yaml").read_text(encoding="utf-8"))
    assert data["validateurs"] == ["MZA-code"]


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    for source in metrics.COVERAGE_SOURCES:
        store(
            conn,
            tmp_path / "raw",
            source_id=source,
            external_id="x",
            url="u",
            fetched_at="2026-01-01T08:00:00Z",
            chunks=[source.encode()],
        )
    yield conn
    conn.close()


def fait(fact_type, day):
    return FactDraft(D7, fact_type, day, f"{fact_type} {day}", None, "test", (1,), {})


def test_comptage_d7(conn):
    write_facts(
        conn,
        [
            fait("fait_presse_valide", "2025-03-01"),
            fait("fait_presse_valide", "2025-03-01"),
            fait("constat_institutionnel", "2025-03-01"),
        ],
    )
    rows = metrics.compute(
        conn, load_grid(), [{"numero": 17, "debut": dt.date(2024, 7, 18), "fin": None}]
    )
    valeurs = {
        r[4]: r[5] for r in rows if r[0] == D7 and r[1] == "2025-06-30" and r[2] == "glissante_365j"
    }
    assert valeurs["nb_faits_presse_valides"] == 2
    assert valeurs["nb_constats_institutionnels"] == 1
    assert valeurs["nb_atteintes_pratique"] == 3
