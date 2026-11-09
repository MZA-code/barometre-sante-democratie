import csv
import datetime as dt

import pytest

from extract.common import FactDraft, write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import record_check, store
from storage.db import connect, fingerprint, init_db

D = dt.date
GRID = load_grid()
LEGISLATURES = [
    {"numero": 1, "debut": D(1958, 12, 9), "fin": D(1962, 10, 9)},
    {"numero": 2, "debut": D(1962, 12, 6), "fin": None},
]


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
            fetched_at="1961-01-01T08:00:00Z",
            chunks=[source.encode()],
        )
    yield conn
    conn.close()


def fact(fact_type, day, **attributes):
    return FactDraft(
        "D2.contournement_parlement",
        fact_type,
        day,
        f"{fact_type} {day}",
        day,
        "test",
        (1,),
        attributes,
    )


def engagement(day, texte, censure=False):
    return fact("engagement_49_3", day, texte_uid=texte, censure_adoptee=censure)


def values_on(rows, day, window="glissante_365j"):
    return {r[4]: r[5] for r in rows if r[1] == day and r[2] == window}


def test_data_end_is_eve_of_oldest_last_collection(conn):
    assert metrics.data_end(conn) == D(1960, 12, 31)


def test_data_end_counts_checks_without_new_document(conn, tmp_path):
    for source in metrics.COVERAGE_SOURCES:
        record_check(conn, tmp_path / "raw", source, "1961-03-10T06:30:00Z")
    record_check(conn, tmp_path / "raw", "dila_constit", "1961-02-01T06:30:00Z")
    assert metrics.data_end(conn) == D(1961, 3, 9)


def test_data_end_never_goes_back_with_an_old_check(conn, tmp_path):
    for source in metrics.COVERAGE_SOURCES:
        record_check(conn, tmp_path / "raw", source, "1960-06-01T06:30:00Z")
    assert metrics.data_end(conn) == D(1960, 12, 31)


def test_data_end_needs_all_sources(tmp_path):
    conn = connect(tmp_path / "empty.sqlite")
    init_db(conn)
    assert metrics.data_end(conn) is None
    assert metrics.compute(conn, GRID, LEGISLATURES) == []


def test_rolling_window_counts_and_ratio(conn):
    write_facts(
        conn,
        [
            engagement("1960-01-10", "A"),
            engagement("1960-02-10", "A"),  # même texte, autre lecture
            engagement("1960-03-10", "B", censure=True),  # censure adoptée
            fact("ordonnance_publiee", "1960-04-01", fondement="art38"),
            fact("ordonnance_publiee", "1960-04-02", fondement="art92"),
            fact("loi_promulguee", "1960-05-01"),
            fact("loi_promulguee", "1960-05-02"),
            fact("loi_promulguee", "1960-05-03"),
            fact("loi_promulguee", "1960-05-04", convention_internationale=True),
        ],
    )
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    v = values_on(rows, "1960-12-31")
    assert v["nb_49_3"] == 3
    assert v["nb_textes_49_3"] == 2
    assert v["nb_textes_adoptes_49_3"] == 1
    assert v["nb_ordonnances"] == 2
    assert v["nb_ordonnances_art38"] == 1
    assert v["nb_lois"] == 4
    assert v["nb_lois_hors_conventions"] == 3
    # grille v0 : (textes adoptés via 49.3 + ordonnances art. 38)
    #           / (lois hors conventions + ordonnances art. 38)
    assert v["ratio_contournement"] == pytest.approx((1 + 1) / (3 + 1))


def test_rolling_window_bounds_are_inclusive_365_days(conn):
    write_facts(conn, [fact("loi_promulguee", "1959-12-20")])
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    assert values_on(rows, "1959-12-19")["nb_lois"] == 0
    assert values_on(rows, "1959-12-20")["nb_lois"] == 1
    assert values_on(rows, "1960-12-18")["nb_lois"] == 1  # le fait est à J-364
    assert values_on(rows, "1960-12-19")["nb_lois"] == 0  # le fait est à J-365


def test_rolling_window_drops_old_facts(conn):
    write_facts(conn, [fact("loi_promulguee", "1959-01-10"), engagement("1959-02-01", "A")])
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    assert values_on(rows, "1960-01-09")["nb_lois"] == 1
    assert values_on(rows, "1960-01-10")["nb_lois"] == 0
    assert values_on(rows, "1960-01-31")["nb_textes_49_3"] == 1
    assert values_on(rows, "1960-02-01")["nb_textes_49_3"] == 0


def test_rolling_starts_after_one_full_window(conn):
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    days = sorted({r[1] for r in rows if r[2] == "glissante_365j"})
    assert days[0] == "1959-12-08"  # history_start (1958-12-09) + 364 jours
    assert days[-1] == "1960-12-31"


def test_no_ratio_without_laws_or_ordinances(conn):
    write_facts(conn, [engagement("1960-06-01", "A")])
    v = values_on(metrics.compute(conn, GRID, LEGISLATURES), "1960-12-31")
    assert v["nb_49_3"] == 1
    assert "ratio_contournement" not in v


def test_legislature_windows_cover_gaps_and_stop_at_data_end():
    windows = metrics.legislature_windows(LEGISLATURES, D(1958, 12, 9), D(1965, 1, 1))
    assert [(w.id, w.start, w.end) for w in windows] == [
        ("legislature_1", D(1958, 12, 9), D(1962, 12, 5)),
        ("legislature_2", D(1962, 12, 6), D(1965, 1, 1)),
    ]


def test_legislature_metrics(conn):
    write_facts(conn, [engagement("1959-06-01", "A"), fact("loi_promulguee", "1960-06-01")])
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    legislature = {r[4]: r for r in rows if r[2] == "legislature_1"}
    assert legislature["nb_49_3"][1] == "1960-12-31"  # législature en cours à la fin des données
    assert legislature["nb_49_3"][3] == (D(1960, 12, 31) - D(1958, 12, 9)).days + 1
    assert legislature["ratio_contournement"][5] == pytest.approx(1.0)


def test_unknown_metric_in_grid_is_rejected(conn, tmp_path):
    indicator = GRID.indicators["D2.contournement_parlement"]
    bad = type(GRID)(
        GRID.version,
        GRID.status,
        {indicator.id: type(indicator)(**{**indicator.__dict__, "metrics": ("inconnue",)})},
    )
    with pytest.raises(ValueError, match="inconnues"):
        metrics.compute(conn, bad, LEGISLATURES)


def test_write_and_export_are_deterministic(conn, tmp_path):
    write_facts(conn, [engagement("1960-01-10", "A"), fact("loi_promulguee", "1960-05-01")])
    outputs = []
    for run in ("a", "b"):
        metrics.write_metrics(conn, metrics.compute(conn, GRID, LEGISLATURES))
        paths = metrics.export_csv(conn, GRID, tmp_path / run)
        outputs.append(([p.read_bytes() for p in paths], fingerprint(conn)))
    assert outputs[0] == outputs[1]
    with paths[0].open() as f:
        header = next(csv.reader(f))
    assert header[:3] == ["fenetre", "jours", "fin_periode"]
    assert header[3:] == list(GRID.indicators["D2.contournement_parlement"].metrics)


def test_controle_report_lists_metrics_and_facts_with_links(conn, tmp_path):
    from scoring import report

    write_facts(
        conn,
        [
            fact("loi_promulguee", "1960-05-01", url="https://www.legifrance.gouv.fr/jorf/id/X"),
            fact("loi_promulguee", "1958-01-01"),  # hors fenêtre
        ],
    )
    metrics.write_metrics(conn, metrics.compute(conn, GRID, LEGISLATURES))
    indicator = GRID.indicators["D2.contournement_parlement"]
    text = report.controle(conn, indicator, GRID.version, D(1960, 12, 31), "glissante_365j")
    assert "`nb_lois` = 1" in text
    assert "Lois promulguées (1)" in text
    assert "https://www.legifrance.gouv.fr/jorf/id/X" in text
    assert "document brut #1" in text
    assert "seuils de la grille non figés" in text


def test_echantillon_is_reproducible(conn):
    from scoring import report

    old = [fact("loi_promulguee", f"1950-01-{d:02d}") for d in range(1, 31)]
    write_facts(conn, old + [fact("loi_promulguee", f"1960-01-{d:02d}") for d in range(1, 31)])
    first = report.echantillon(conn, 20, 2026, D(1958, 12, 9))
    assert first == report.echantillon(conn, 20, 2026, D(1958, 12, 9))
    assert first.count("- [ ] ") == 20
    assert "**1950-" not in first


def _annual_values(fact_type, dates, values, days):
    kwargs = "rang" if fact_type == "classement_rsf" else "personnes"
    events = [
        metrics.Event(day=d, fact_id=i, fact_type=fact_type, **{kwargs: v})
        for i, (d, v) in enumerate(zip(dates, values, strict=True))
    ]
    ratios = GRID.indicators[
        "D5.classement_rsf" if fact_type == "classement_rsf" else "D6.techniques_renseignement"
    ].ratios
    return {day: v for day, v in metrics.rolling(events, 365, days[0], days[-1], ratios)}


def test_annual_series_have_one_value_every_day_of_leap_years():
    # RSF : éditions datées du 1er janvier ; 2024 est bissextile.
    days = [D(2023, 12, 31) + dt.timedelta(days=i) for i in range(370)]
    rsf = _annual_values(
        "classement_rsf", [D(2023, 1, 1), D(2024, 1, 1), D(2025, 1, 1)], [24, 21, 25], days
    )
    assert all(v.get("nb_editions_rsf") == 1 for v in rsf.values())
    assert rsf[D(2024, 12, 31)]["rang_rsf"] == 21
    assert rsf[D(2025, 1, 1)]["rang_rsf"] == 25
    # CNCTR : années datées du 31 décembre ; la fenêtre du 30 décembre 2024 garde 2023.
    days = [D(2024, 12, 25) + dt.timedelta(days=i) for i in range(10)]
    cnctr = _annual_values(
        "surveillance_annee", [D(2023, 12, 31), D(2024, 12, 31)], [24209, 24308], days
    )
    assert cnctr[D(2024, 12, 30)]["personnes_surveillees"] == 24209
    assert cnctr[D(2024, 12, 31)]["personnes_surveillees"] == 24308


def test_annual_window_does_not_reach_back_more_than_a_year():
    # Pas d'édition RSF en 2011 : la fenêtre du 1er janvier 2011 ne reprend pas celle de 2010.
    days = [D(2010, 12, 31), D(2011, 1, 1)]
    rsf = _annual_values("classement_rsf", [D(2010, 1, 1)], [44], days)
    assert rsf[D(2010, 12, 31)]["rang_rsf"] == 44
    assert rsf[D(2011, 1, 1)].get("nb_editions_rsf") == 0


def test_postponed_elections_are_counted_once_per_window():
    ratios = GRID.indicators["D1.scrutins_reportes"].ratios
    events = [
        metrics.Event(
            day=D(2020, 3, 18),
            fact_id=1,
            fact_type="report_scrutin",
            scrutins=("municipales-2020-t2",),
        ),
        metrics.Event(
            day=D(2020, 4, 2),
            fact_id=2,
            fact_type="report_scrutin",
            scrutins=("municipales-2020-t2",),
        ),
        metrics.Event(
            day=D(2020, 8, 4),
            fact_id=3,
            fact_type="report_scrutin",
            scrutins=("senatoriales-fde-2020", "partielles-fde-2020"),
        ),
    ]
    days = dict(metrics.rolling(events, 365, D(2020, 12, 31), D(2021, 3, 20), ratios))
    assert days[D(2020, 12, 31)]["nb_reports_scrutin"] == 3
    assert days[D(2020, 12, 31)]["nb_scrutins_reportes"] == 3
    # 18/03/2020 sort de la fenêtre ; le texte du 02/04/2020 garde les municipales.
    assert days[D(2021, 3, 18)]["nb_reports_scrutin"] == 2
    assert days[D(2021, 3, 18)]["nb_scrutins_reportes"] == 3
