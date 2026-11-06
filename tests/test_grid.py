import pytest
import yaml

from scoring.grid import DEFAULT_GRID_PATH, GridError, load_grid
from scoring.score import ThresholdsNotFrozen, main, score_value


def write_grid(tmp_path, *, name="grid.v9.yaml", **overrides):
    data = yaml.safe_load(DEFAULT_GRID_PATH.read_text(encoding="utf-8"))
    data["version"] = "v9"
    data["indicators"]["D2.contournement_parlement"].update(overrides)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def d2(path):
    return load_grid(path).indicators["D2.contournement_parlement"]


def test_grid_v0_loads_with_d2_and_null_thresholds():
    grid = load_grid()
    assert grid.version == "v0"
    indicator = grid.indicators["D2.contournement_parlement"]
    assert indicator.fact_types == ("engagement_49_3", "ordonnance_publiee", "loi_promulguee")
    assert indicator.scored_metric == "ratio_contournement"
    assert not indicator.thresholds_frozen


def test_rule_4_no_score_while_thresholds_are_null():
    indicator = load_grid().indicators["D2.contournement_parlement"]
    with pytest.raises(ThresholdsNotFrozen):
        score_value(indicator, 0.5)


def test_score_increasing(tmp_path):
    indicator = d2(write_grid(tmp_path, thresholds=[0.1, 0.2, 0.3, 0.4]))
    assert [score_value(indicator, v) for v in (0.0, 0.1, 0.25, 0.39, 0.4, 1.0)] == [
        0,
        1,
        2,
        3,
        4,
        4,
    ]


def test_score_decreasing(tmp_path):
    path = write_grid(tmp_path, direction="decreasing", thresholds=[0.4, 0.3, 0.2, 0.1])
    indicator = d2(path)
    assert [score_value(indicator, v) for v in (1.0, 0.4, 0.25, 0.1, 0.0)] == [0, 1, 2, 4, 4]


@pytest.mark.parametrize(
    "thresholds",
    [
        [0.1, None, 0.3, 0.4],  # partiellement renseignés
        [0.1, 0.2, 0.3],  # nombre incorrect
        [0.4, 0.3, 0.2, 0.1],  # ordre inverse de la direction
        [0.1, 0.2, 0.2, 0.4],  # pas strictement monotone
    ],
)
def test_invalid_thresholds_are_rejected(tmp_path, thresholds):
    with pytest.raises(GridError):
        load_grid(write_grid(tmp_path, thresholds=thresholds))


def test_version_must_match_filename(tmp_path):
    path = write_grid(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("v9", "v8"), encoding="utf-8")
    with pytest.raises(GridError, match="version"):
        load_grid(path)


def test_filename_must_be_versioned(tmp_path):
    with pytest.raises(GridError):
        load_grid(write_grid(tmp_path, name="grille.yaml"))


def test_scored_metric_must_be_declared(tmp_path):
    with pytest.raises(GridError, match="scored_metric"):
        load_grid(write_grid(tmp_path, scored_metric="inconnue"))


def test_rolling_window_requires_days(tmp_path):
    with pytest.raises(GridError, match="glissante"):
        load_grid(write_grid(tmp_path, windows=[{"type": "rolling"}]))


def test_score_cli_with_v0_produces_no_score(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "t.sqlite")]) == 0
    assert "aucune note produite" in capsys.readouterr().out


def test_ratio_formula_is_read_from_grid():
    ratio = load_grid().indicators["D2.contournement_parlement"].ratios["ratio_contournement"]
    assert ratio.numerator == ("nb_textes_adoptes_49_3", "nb_ordonnances_art38")
    assert ratio.denominator == ("nb_lois_hors_conventions", "nb_ordonnances_art38")


def test_ratio_components_must_be_declared_metrics(tmp_path):
    bad = {"ratio_contournement": {"numerateur": ["inconnue"], "denominateur": ["nb_lois"]}}
    with pytest.raises(GridError, match="inconnue"):
        load_grid(write_grid(tmp_path, ratios=bad))


def test_scale_meaning_is_loaded():
    assert load_grid().scale_meaning.startswith("0 = fonctionnement")
