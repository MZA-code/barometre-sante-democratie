import datetime as dt

import pytest

from extract import procedure, senat
from extract.common import FactDraft, write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.db import connect, init_db

D = dt.date
GRID = load_grid()
INDICATOR = GRID.indicators[procedure.INDICATOR]


def dossier(uid, code_proc="1", acts=()):
    return {
        "uid": uid,
        "procedureParlementaire": {"code": code_proc, "libelle": f"procédure {code_proc}"},
        "actesLegislatifs": {
            "acteLegislatif": [{"codeActe": "AN1", "actesLegislatifs": list(acts)}]
        },
    }


def procacc(date="2024-01-10T00:00:00.000+01:00"):
    return {"@xsi:type": "ProcedureAccelere_Type", "codeActe": "AN1-PROCACC", "dateActe": date}


def prom(code, date="2024-03-01T00:00:00.000+01:00"):
    return {
        "@xsi:type": "Promulgation_Type",
        "codeActe": "PROM-PUB",
        "codeLoi": code,
        "dateActe": date,
    }


def jorf(code, day, title=None, convention=False, raw=(99,)):
    return FactDraft(
        indicator_id="D2.contournement_parlement",
        fact_type="loi_promulguee",
        occurred_on=day,
        title=title or f"LOI n° {code} du ...",
        official_ref=code,
        extraction_method="dila",
        raw_document_ids=raw,
        attributes={"convention_internationale": convention, "url": f"https://jorf/{code}"},
    )


def test_collect_lois_dedups_across_legislatures_and_flags_procedure():
    lois = procedure.collect_lois(
        [
            (1, dossier("DLR5L15N1", acts=[procacc("2019-05-02T00:00:00"), prom("2019-100")])),
            (2, dossier("DLR5L16N1", acts=[prom("2019-100")])),
            (2, dossier("DLR5L16N2", acts=[prom("2023-5")])),
            (2, dossier("DLR5L16N3", acts=[procacc()])),  # pas encore promulguée
        ]
    )
    assert set(lois) == {"2019-100", "2023-5"}
    assert lois["2019-100"].procedure_acceleree and lois["2019-100"].date_engagement == "2019-05-02"
    assert lois["2019-100"].raw_document_ids == {1, 2}
    assert not lois["2023-5"].procedure_acceleree


def senat_loi(
    numero, statut_urgence=None, engagement=None, retrait=None, type_="pjl", date_loi="2020-01-01"
):
    return senat.LoiSenat(
        numero, date_loi, type_, statut_urgence, engagement, retrait, f"sig{numero}", 50
    )


def run(monkeypatch, tmp_path, dossiers, lois_senat, lois_jorf):
    monkeypatch.setattr(
        procedure, "latest_documents", lambda conn, source: [{"id": 1, "path": "x"}]
    )
    monkeypatch.setattr(procedure, "iter_dossiers", lambda path: (d for _, d in dossiers))
    monkeypatch.setattr(procedure.senat, "latest_lois", lambda conn, raw: lois_senat)
    return {d.official_ref: d for d in procedure.extract(None, tmp_path, lois_jorf)}


def test_status_from_an_then_senate_then_unknown(monkeypatch, tmp_path):
    dossiers = [(1, dossier("DLR5L15N41210", acts=[procacc(), prom("2021-191")]))]
    lois_senat = {
        "2021-191": senat_loi("2021-191", engagement="2020-12-21"),
        "85-96": senat_loi("85-96", "oui", date_loi="1985-01-25"),
        "2004-1": senat_loi("2004-1", None, date_loi="2004-01-05"),  # urgence vide
    }
    lois_jorf = [
        jorf("2021-191", "2021-02-22"),
        jorf("85-96", "1985-01-25"),
        jorf("2004-1", "2004-01-05"),
        jorf("99-9", "1999-03-01"),  # aucune source
        jorf("77-1", "1977-06-01"),  # avant le début de l'historique
    ]
    facts = run(monkeypatch, tmp_path, dossiers, lois_senat, lois_jorf)
    assert set(facts) == {"2021-191", "85-96", "2004-1", "99-9"}
    a = facts["2021-191"].attributes
    assert a["statut"] == "acceleree" and a["concordance_an_senat"] is True
    assert a["sources_engagement"] == ["an", "senat"]
    assert facts["2021-191"].raw_document_ids == (1, 50, 99)
    assert a["url_an"].endswith("/dyn/15/dossiers/DLR5L15N41210")
    assert a["url_senat"].endswith("/sig2021-191.html")
    assert facts["85-96"].attributes["statut"] == "acceleree"
    assert facts["85-96"].attributes["sources_engagement"] == ["senat"]
    assert facts["2004-1"].attributes["statut"] == "inconnu"
    assert facts["99-9"].attributes["statut"] == "inconnu"


def test_withdrawal_known_to_senate_overrides_an(monkeypatch, tmp_path):
    # Loi 2013-702 : procédure engagée le 16 avril 2013, retirée le 19 avril.
    dossiers = [(1, dossier("DLR5L14N1", acts=[procacc(), prom("2013-702")]))]
    lois_senat = {"2013-702": senat_loi("2013-702", engagement="2013-04-16", retrait="2013-04-19")}
    facts = run(monkeypatch, tmp_path, dossiers, lois_senat, [jorf("2013-702", "2013-08-07")])
    a = facts["2013-702"].attributes
    assert a["statut"] == "ordinaire" and a["retrait_senat"] == "2013-04-19"
    assert a["concordance_an_senat"] is False


def test_engagement_recorded_by_one_source_is_enough(monkeypatch, tmp_path):
    # Loi spéciale 2025-1316 : engagement enregistré au Sénat, absent du dossier AN.
    dossiers = [(1, dossier("DLR5L17N53386", acts=[prom("2025-1316")]))]
    lois_senat = {"2025-1316": senat_loi("2025-1316", engagement="2025-12-23")}
    title = (
        "LOI n° 2025-1316 du 26 décembre 2025 spéciale prévue par l'article 45 de la loi "
        "organique n° 2001-692 du 1er août 2001 relative aux lois de finances"
    )
    facts = run(
        monkeypatch, tmp_path, dossiers, lois_senat, [jorf("2025-1316", "2025-12-26", title)]
    )
    a = facts["2025-1316"].attributes
    assert a["statut"] == "acceleree" and a["sources_engagement"] == ["senat"]
    assert a["concordance_an_senat"] is False
    assert a["finances"]  # loi spéciale : famille des lois de finances


def test_exclusion_flags(monkeypatch, tmp_path):
    lois_senat = {
        "2017-1837": senat_loi("2017-1837", type_="pjlf"),
        "2008-1": senat_loi("2008-1", "dro", date_loi="2008-01-01"),
        "2018-180": senat_loi("2018-180", type_="cvn"),
    }
    lois_jorf = [
        jorf(
            "2017-1837",
            "2017-12-30",
            title="LOI n° 2017-1837 du 30 décembre 2017 de finances pour 2018 (1)",
        ),
        jorf("2008-1", "2008-01-01"),
        jorf("2018-180", "2018-03-15"),
        jorf("2024-200", "2024-03-08", title="LOI constitutionnelle n° 2024-200 du 8 mars 2024"),
        jorf(
            "96-608",
            "1996-07-05",
            title="LOI no 96-608 du 5 juillet 1996 portant règlement définitif du budget de 1994",
        ),
        jorf(
            "2001-692",
            "2001-08-01",
            title="LOI organique n° 2001-692 du 1er août 2001 relative aux lois de finances",
        ),
    ]
    f = {k: v.attributes for k, v in run(monkeypatch, tmp_path, [], lois_senat, lois_jorf).items()}
    assert f["2017-1837"]["finances"] and f["2008-1"]["finances"] and f["96-608"]["finances"]
    assert not f["2001-692"]["finances"]  # loi organique sur les lois de finances : comptée
    assert f["2018-180"]["convention_internationale"]
    assert f["2024-200"]["constitutionnelle"]


def test_no_facts_without_any_procedure_source(monkeypatch, tmp_path):
    monkeypatch.setattr(procedure, "latest_documents", lambda conn, source: [])
    monkeypatch.setattr(procedure.senat, "latest_lois", lambda conn, raw: {})
    assert procedure.extract(None, tmp_path, [jorf("2024-1", "2024-01-01")]) == []


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def fact(ref, statut="ordinaire", **attrs):
    return FactDraft(
        indicator_id=procedure.INDICATOR,
        fact_type="loi_procedure",
        occurred_on="2024-06-01",
        title=ref,
        official_ref=ref,
        extraction_method=procedure.EXTRACTOR,
        raw_document_ids=(1,),
        attributes={"statut": statut, **attrs},
    )


def test_ratio_excludes_conventions_constitutional_and_finance_laws(conn):
    conn.execute(
        "INSERT INTO raw_documents (source_id, external_id, url, fetched_at, sha256, path)"
        " VALUES ('an_opendata', 'x', 'u', '2026-01-01T00:00:00Z', '" + "0" * 64 + "', 'p')"
    )
    write_facts(
        conn,
        [
            fact("a", "acceleree"),
            fact("b", "acceleree"),
            fact("c"),
            fact("d", "acceleree", convention_internationale=True),
            fact("e", constitutionnelle=True),
            fact("f", "acceleree", finances=True),
            fact("g", "inconnu"),
            fact("h", "inconnu", convention_internationale=True),
        ],
    )
    events = metrics.load_events(conn, INDICATOR)
    window = metrics.Window("t", 366, D(2024, 1, 1), D(2024, 12, 31))
    values = metrics.window_values(events, window, INDICATOR.ratios)
    assert values["nb_lois_statut_connu"] == 3
    assert values["nb_lois_procedure_acceleree"] == 2
    assert values["ratio_procedure_acceleree"] == pytest.approx(2 / 3)
    assert values["nb_lois_statut_inconnu"] == 1
