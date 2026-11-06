# ruff: noqa: E501  (extraits CSV de test : lignes longues voulues)
import datetime as dt
import io
from contextlib import contextmanager

import pytest

from collectors import arcom as collector
from extract import arcom
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
INDICATOR = load_grid().indicators[arcom.INDICATOR]

CSV = """;TF1;TF1;France Inter
"Type de service";"Chaîne généraliste";"Chaîne généraliste";Radio
"Type d'émission";JTF;MAG;PROG
"Président de la République";;00:00:29;00:10:00
"dont Président de la République - propos qui relèvent du débat politique national";-;00:00:29;-
Gouvernement;00:01:41;00:15:12;01:00:00
"Total Pouvoir exécutif";00:01:41;00:15:41;01:00:00
"Part Pouvoir exécutif";3,01%;23,50%;50,00%
"Parti A";00:50:00;00:51:04;01:00:00
"Total Partis politiques";00:54:10;00:51:04;01:00:00
"Part Partis politiques";96,99%;76,50%;50,00%
"""


def test_parse_uses_arcom_totals_only():
    v = arcom.parse(CSV)
    assert v["secondes_executif"] == 101 + 941 + 3600
    assert v["secondes_partis"] == 3250 + 3064 + 3600
    assert v["par_type_de_service"]["Radio"] == {"secondes_executif": 3600, "secondes_partis": 3600}
    # le Président hors débat politique (10 min à la radio) n'est pas compté, comme à l'Arcom
    assert v["part_executif"] == pytest.approx(4642 / (4642 + 9914), abs=1e-6)


def test_inconsistent_published_share_is_rejected():
    with pytest.raises(ValueError, match="incohérente"):
        arcom.parse(CSV.replace("3,01%", "30,10%"))


def test_inconsistent_parties_share_is_rejected():
    with pytest.raises(ValueError, match="incohérente"):
        arcom.parse(CSV.replace("96,99%", "69,99%"))


def test_missing_share_rows_are_rejected():
    without = "\n".join(row for row in CSV.splitlines() if not row.startswith('"Part Partis'))
    with pytest.raises(ValueError, match="Part Partis politiques"):
        arcom.parse(without)


def test_rows_of_different_lengths_are_rejected_clearly():
    with pytest.raises(ValueError, match="colonnes"):
        arcom.parse(CSV.replace("Radio\n", "Radio;\n"))


def test_seconds():
    assert arcom.seconds("125:13:02") == 125 * 3600 + 13 * 60 + 2
    assert arcom.seconds("-") == 0 and arcom.seconds("") == 0


PAGE = """<html><script type="application/json" data-drupal-selector="drupal-settings-json">
{"tphpe":[{"mois":[{"fichiers":[
 {"file_uri":"/sites/default/files/tphe/files/speaking_time_files/Export_web_1T2T_01-02-2025_28-02-2025%20%281%29.csv"},
 {"file_uri":"/sites/default/files/tphe/files/speaking_time_files/Export_web_Personnalites_avec_seuil_01-02-2025_28-02-2025.csv"}]}]}]}
</script></html>"""


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_collector_keeps_only_1t2t_files_once(conn, tmp_path):
    calls = []

    @contextmanager
    def web(url):
        calls.append(url)
        yield io.BytesIO(PAGE.encode() if "/recherche/source/" in url else CSV.encode())

    got = collector.collect(conn, tmp_path / "raw", [2025], opener=web)
    assert got == ["Export_web_1T2T_01-02-2025_28-02-2025.csv"]  # suffixe « (1) » retiré
    assert collector.collect(conn, tmp_path / "raw", [2025], opener=web) == []


def test_extract_and_rolling_share(conn, tmp_path):
    raw = tmp_path / "raw"
    for name in (
        "Export_web_1T2T_01-01-2025_31-01-2025.csv",
        "Export_web_1T2T_01-02-2025_28-02-2025.csv",
    ):
        store(
            conn,
            raw,
            source_id=arcom.SOURCE_ID,
            external_id=name,
            url="u",
            fetched_at="2026-11-05T00:00:00Z",
            chunks=[CSV.encode()],
            suffix=".csv",
        )
    drafts = arcom.extract(conn, raw)
    assert sorted(d.occurred_on for d in drafts) == ["2025-01-31", "2025-02-28"]
    write_facts(conn, drafts)
    events = metrics.load_events(conn, INDICATOR)
    v = metrics.window_values(
        events, metrics.Window("t", 365, D(2025, 1, 1), D(2025, 12, 31)), INDICATOR.ratios
    )
    assert v["nb_mois_temps_parole"] == 2
    assert v["part_executif"] == pytest.approx(4642 / (4642 + 9914), abs=1e-6)


CSV_PARTIS = """;TF1;TF1;France Inter
"Type de service";"Chaîne généraliste";"Chaîne généraliste";Radio
"Type d'émission";JTF;MAG;PROG
"Président de la République";;00:00:29;00:10:00
"Total Pouvoir exécutif";00:01:41;00:15:41;01:00:00
"Part Pouvoir exécutif";3,01%;23,50%;50,00%
"Parti A";00:50:00;00:51:04;-
"Parti B";00:04:10;-;01:00:00
"Parti C";-;-;-
"Total Partis politiques";00:54:10;00:51:04;01:00:00
"Part Partis politiques";96,99%;76,50%;50,00%
"""


def test_parse_partis_par_chaine_et_service():
    v = arcom.parse_partis(CSV_PARTIS)
    assert v["secondes_partis"] == 3250 + 3064 + 3600
    assert list(v["partis"]) == ["Parti A", "Parti B"]  # trié par temps ; C (aucun temps) omis
    a, b = v["partis"]["Parti A"], v["partis"]["Parti B"]
    assert a["secondes"] == 3000 + 3064
    assert a["par_chaine"] == {"TF1": 6064}
    assert b["par_type_de_service"] == {"Chaîne généraliste": 250, "Radio": 3600}
    assert b["par_chaine"] == {"TF1": 250, "France Inter": 3600}


def test_parse_partis_somme_differente_du_total():
    with pytest.raises(ValueError, match="colonne 1"):
        arcom.parse_partis(CSV_PARTIS.replace('"Parti B";00:04:10', '"Parti B";00:04:11'))


def test_parse_partis_doublon():
    with pytest.raises(ValueError, match="deux fois"):
        arcom.parse_partis(CSV_PARTIS.replace('"Parti C"', '"Parti A"'))


def test_parse_partis_sans_nom_de_parti_dans_le_code():
    """Règle 5 : les partis sont repérés par position, jamais par leur libellé."""
    import inspect

    source = inspect.getsource(arcom)
    for nom in ("Renaissance", "Rassemblement", "insoumise", "Républicains", "Socialiste"):
        assert nom not in source


def test_parse_partis_type_de_service_par_chaine():
    v = arcom.parse_partis(CSV_PARTIS)
    assert v["type_de_service_par_chaine"] == {"France Inter": "Radio", "TF1": "Chaîne généraliste"}
