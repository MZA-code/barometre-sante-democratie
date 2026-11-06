import csv
import datetime as dt
import io
import tarfile
from pathlib import Path

import pytest

from extract import exception, libertes
from extract.common import FactDraft, write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

ROOT = Path(__file__).resolve().parent.parent
D = dt.date
GRID = load_grid()
LEGISLATURES = [{"numero": 16, "debut": D(2022, 6, 22), "fin": None}]


def decret(titre, visas="", nature="DECRET"):
    return {"nature": nature, "titre": titre, "visas": visas}


# --- D4.1 : dissolutions administratives (titres réels du JORF) ------------------------


@pytest.mark.parametrize(
    ("text", "basis"),
    [
        (
            decret(
                "Décret du 21 juin 2023 portant dissolution d'un groupement de fait",
                "Vu le code de la sécurité intérieure, notamment son article L. 212-1 ;",
            ),
            "L212-1",
        ),
        (
            decret(
                "Décret du 28 avril 2010 portant dissolution d'une association",
                "Vu le code du sport, notamment son article L. 332-18 ;",
            ),
            "L332-18",
        ),
        (
            decret(
                "Décret du 6 août 2002 portant dissolution d'un groupement de fait",
                "Vu la loi du 10 janvier 1936 sur les groupes de combat et milices privées ;",
            ),
            "loi_1936",
        ),
        (
            decret(
                "Décret n°82-670 du 3 août 1982 PORTANT DISSOLUTION DE L'ASSOCIATION DENOMMEE "
                "SERVICE D'ACTION CIVIQUE (SAC)"
            ),
            "titre",
        ),
        (
            decret(
                "Décret du 13 janvier 2020 approuvant la dissolution de l'association reconnue "
                "d'utilité publique dite « L'Hygiène par l'Exemple »"
            ),
            None,
        ),
        (
            decret(
                "Décret du 2 septembre 1986 PORTANT DISSOLUTION DU CONSEIL MUNICIPAL DE QUIERZY"
            ),
            None,
        ),
        (
            decret(
                "Décret n° 2010-1649 du 28 décembre 2010 portant dissolution de l'Institut "
                "national de recherche pédagogique"
            ),
            None,
        ),
        (
            decret(
                "Décret du 10 février 2010 portant attribution à une association cultuelle des "
                "biens d'une association cultuelle ayant décidé sa dissolution"
            ),
            None,
        ),
        (decret("Loi portant dissolution d'une association", nature="LOI"), None),
    ],
)
def test_dissolution_legal_basis(text, basis):
    assert libertes.legal_basis(text) == basis


# --- D3.1 : régimes d'exception --------------------------------------------------------


@pytest.mark.parametrize(
    ("titre", "regime"),
    [
        (
            "Décret n° 2015-1475 du 14 novembre 2015 portant application de la loi n° 55-385 du "
            "3 avril 1955",
            True,
        ),
        (
            "LOI n° 2017-1154 du 11 juillet 2017 prorogeant l'application de la loi n° 55-385 du "
            "3 avril 1955 relative à l'état d'urgence (1)",
            True,
        ),
        ("Décret n° 2020-1257 du 14 octobre 2020 déclarant l'état d'urgence sanitaire", True),
        (
            "Décret n° 2021-1328 du 13 octobre 2021 mettant fin à l'état d'urgence sanitaire à "
            "La Réunion",
            True,
        ),
        (
            "Décision du 29 septembre 1961 mettant fin à l'application de l'article 16 de la "
            "Constitution",
            True,
        ),
        (
            "Décret n° 2020-551 du 12 mai 2020 relatif aux systèmes d'information mentionnés à "
            "l'article 11 de la loi n° 2020-546 du 11 mai 2020 prorogeant l'état d'urgence "
            "sanitaire",
            False,
        ),
        (
            "Décret n° 2015-1478 du 14 novembre 2015 modifiant le décret n° 2015-1476 du "
            "14 novembre 2015 portant application de la loi n° 55-385",
            False,
        ),
        (
            "LOI organique n° 2020-365 du 30 mars 2020 d'urgence pour faire face à l'épidémie de "
            "covid-19",
            False,
        ),
    ],
)
def test_regime_text_detection(titre, regime):
    assert bool(exception.REGIME_TEXT.search(titre)) is regime


def test_seed_is_consistent():
    text = (ROOT / "data" / "seed" / "regimes_exception.csv").read_text("utf-8")
    assert all(line.count(";") == 8 for line in text.splitlines()), "9 colonnes par ligne"
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    assert len(rows) == 20
    for row in rows:
        assert row["debut"] <= row["fin"], row
        assert row["metropole"] in ("oui", "non")
        assert row["a_verifier"] in ("oui", "non")
        assert row["textes"].split() and all(
            c.startswith("JORFTEXT") for c in row["textes"].split()
        )
        assert row["preuve"]
        if row["a_verifier"] == "oui":
            assert row["note"], "une ligne à vérifier dit pourquoi"


def put(conn, raw, source, external_id, content, suffix=""):
    return store(
        conn,
        raw,
        source_id=source,
        external_id=external_id,
        url="u",
        fetched_at="2026-10-26T09:00:00Z",
        chunks=[content],
        suffix=suffix,
    )


def test_extract_periods_link_seed_and_archive(tmp_path, capsys):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    raw = tmp_path / "raw"
    seed_csv = (
        "regime;territoire;metropole;debut;fin;textes;preuve;a_verifier;note\n"
        "état d'urgence;métropole;oui;2015-11-14;2017-11-01;JORFTEXT000031473404 JORFTEXT9;"
        "art. 1;non;\n"
    ).encode()
    seed_doc = put(conn, raw, "seed_manuel", "regimes_exception.csv", seed_csv, ".csv")
    xml = (Path(__file__).parent / "fixtures" / "dila").glob("loi_*.xml").__next__().read_bytes()
    xml = xml.replace(b"<NATURE>LOI</NATURE>", b"<NATURE>DECRET</NATURE>")
    xml = xml.replace(b"JORFTEXT000021838381", b"JORFTEXT000031473404")
    titre_start = xml.index(b"<TITREFULL>")
    titre_end = xml.index(b"</TITREFULL>")
    xml = (
        xml[:titre_start]
        + "<TITREFULL>Décret n° 2015-1475 du 14 novembre 2015 portant "
        "application de la loi n° 55-385 du 3 avril 1955".encode()
        + xml[titre_end:]
    )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("x/texte/version/d.xml")
        info.size = len(xml)
        archive.addfile(info, io.BytesIO(xml))
    jorf = put(
        conn, raw, "dila_jorf", "Freemium_jorf_global_20250713-140000.tar.gz", buffer.getvalue()
    )
    drafts = exception.extract(conn, raw, tmp_path / "cache")
    assert len(drafts) == 1
    period = drafts[0]
    assert period.raw_document_ids == (seed_doc.id, jorf.id)
    assert period.attributes["fin"] == "2017-11-01"
    assert period.attributes["metropole"] is True
    assert period.attributes["textes_absents_archive"] == ["JORFTEXT9"]
    assert "JORFTEXT9" in capsys.readouterr().out


# --- Métriques additives ----------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "m.sqlite")
    init_db(conn)
    for source in metrics.COVERAGE_SOURCES:
        put(conn, tmp_path / "raw", source, "x", source.encode())
    yield conn
    conn.close()


def period(start, end, metropole):
    return FactDraft(
        "D3.regimes_exception",
        "periode_regime_exception",
        start,
        f"p {start}",
        None,
        "test",
        (1,),
        {"fin": end, "metropole": metropole},
    )


def dissolution(day):
    return FactDraft(
        "D4.dissolutions_administratives",
        "dissolution_administrative",
        day,
        f"d {day}",
        day,
        "test",
        (1,),
        {},
    )


def at(rows, indicator, day, window="glissante_365j"):
    return {r[4]: r[5] for r in rows if r[0] == indicator and r[1] == day and r[2] == window}


def test_exception_days_count_overlaps_once(conn):
    write_facts(
        conn, [period("2020-01-01", "2020-01-10", True), period("2020-01-05", "2020-01-20", False)]
    )
    v = at(metrics.compute(conn, GRID, LEGISLATURES), "D3.regimes_exception", "2020-06-30")
    assert v["jours_exception"] == 20
    assert v["jours_exception_metropole"] == 10


def test_ongoing_period_runs_to_data_end(conn):
    write_facts(conn, [period("2026-10-20", None, False)])
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    assert at(rows, "D3.regimes_exception", "2026-10-25")["jours_exception"] == 6
    legislature = at(rows, "D3.regimes_exception", "2026-10-25", "legislature_16")
    assert legislature["jours_exception"] == 6


def test_dissolutions_rolling_and_legislature(conn):
    write_facts(
        conn, [dissolution(d) for d in ("2021-03-01", "2021-03-01", "2021-11-30", "2023-01-15")]
    )
    rows = metrics.compute(conn, GRID, LEGISLATURES)
    assert at(rows, "D4.dissolutions_administratives", "2021-12-31")["nb_dissolutions"] == 3
    assert at(rows, "D4.dissolutions_administratives", "2022-03-01")["nb_dissolutions"] == 1
    legislature = at(rows, "D4.dissolutions_administratives", "2026-10-25", "legislature_16")
    assert legislature["nb_dissolutions"] == 1
    days = sorted(
        r[1] for r in rows if r[0] == "D4.dissolutions_administratives" and r[2] == "glissante_365j"
    )
    assert days[0] == "1990-12-31"  # history_start (1990-01-01) + 364 jours
