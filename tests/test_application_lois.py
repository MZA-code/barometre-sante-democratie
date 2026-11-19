import datetime as dt
import io
from contextlib import contextmanager

import pytest

from collectors import application_lois as collector
from extract import application_lois
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.db import connect, init_db

LOIS = (
    "Date de publication de la loi;Titre de la loi;Identifiant Légifrance de la loi\n"
    "2025-01-31;LOI n° 1 du 31 janvier 2025;L1\n"
    "2026-10-01;LOI n° 2 du 1er octobre 2026;L2\n"
)
EN_TETE = (
    "Titre loi;Identifiant loi;N° ordre;Identifiant décret;État;Délai d'application (en jours)\n"
)
MESURES = EN_TETE + (
    "Loi 1;L1;1;D1;appliqué;30\n"  # dans le délai
    "Loi 1;L1;2;D2;appliqué;400\n"  # trop tard
    "Loi 1;L1;3;;en attente d'application;\n"  # toujours en attente
    "Loi 1;L1;4;;sans objet;\n"  # écartée
    "Loi 1;L1;5;D5;appliqué;\n"  # délai inconnu : écartée
    "Loi 2;L2;1;;en attente d'application;\n"  # échéance future : écartée
)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


@contextmanager
def web(url):
    yield io.BytesIO((LOIS if url.endswith("lois_assemblee.csv") else MESURES).encode())


def test_plus_mois_fin_de_mois():
    assert application_lois.plus_mois(dt.date(2025, 8, 31), 6) == dt.date(2026, 2, 28)
    assert application_lois.plus_mois(dt.date(2025, 1, 31), 6) == dt.date(2025, 7, 31)


def test_collecte_mensuelle(conn, tmp_path):
    raw = tmp_path / "raw"
    jour = dt.date.today()
    assert collector.collect(conn, raw, opener=web, today=jour) == ["lois.csv", "mesures.csv"]
    assert collector.collect(conn, raw, opener=web, today=jour + dt.timedelta(days=5)) == []
    assert collector.collect(conn, raw, opener=web, today=jour, forcer=True) == []


def test_extraction_et_ratio(conn, tmp_path):
    raw = tmp_path / "raw"
    collector.collect(conn, raw, opener=web)
    drafts = application_lois.extract(conn, raw)
    assert {d.official_ref: d.fact_type for d in drafts} == {
        "L1#1": "mesure_appliquee_delai",
        "L1#2": "mesure_non_appliquee_delai",
        "L1#3": "mesure_non_appliquee_delai",
    }
    assert {d.occurred_on for d in drafts} == {"2025-07-31"}
    write_facts(conn, drafts)
    ind = load_grid().indicators[application_lois.INDICATOR]
    w = metrics.WindowState()
    for e in metrics.load_events(conn, ind):
        w.add(e)
    v = w.values(ind.ratios)
    assert v["nb_mesures_echues"] == 3
    assert v["ratio_mesures_non_appliquees_delai"] == pytest.approx(2 / 3)
