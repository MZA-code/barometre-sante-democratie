"""D2.4 : crédits votés annulés par décret (Journal officiel)."""

import datetime as dt
import io
import tarfile
from pathlib import Path

import pytest

from extract import budget
from extract.common import FactDraft, write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

FIX = Path(__file__).parent / "fixtures" / "budget"
ARTICLE1 = (FIX / "article1_annulation.xml").read_bytes()
RAPPORT = (FIX / "rapport_annulation.xml").read_bytes()


def test_article_1_lu():
    assert budget.lire_article(ARTICLE1) == {
        "cid": "JORFTEXT000054238633",
        "numero": "2026-490",
        "date": "2026-06-11",
        "titre": "Décret n° 2026-490 du 11 juin 2026 portant annulation de crédits",
        "montant_ae": 440278740,
        "montant_cp": 490273528,
    }


def test_rapport_ignore():
    assert budget.lire_article(RAPPORT) is None


def test_decret_d_avance_ignore():
    """Décret « portant ouverture et annulation de crédits » : les annulations y compensent
    des ouvertures (décret d'avance), elles ne réduisent pas le budget voté."""
    avance = ARTICLE1.replace(b"portant annulation de cr", b"portant ouverture et annulation de cr")
    assert budget.lire_article(avance) is None


def test_montants_ecrits_autrement():
    texte = ARTICLE1.replace(
        "d'un montant de 440 278 740 € en autorisations".encode(),
        "d'un montant de 10 000 000 000 € en autorisations".encode(),
    )
    assert budget.lire_article(texte)["montant_ae"] == 10_000_000_000


def tar_avec(*fichiers):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for nom, data in fichiers:
            info = tarfile.TarInfo(nom)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_extraction_depuis_l_archive(conn, tmp_path):
    raw = tmp_path / "raw"
    data = tar_avec(
        ("x/jorf/global/article/JORF/ARTI/1.xml", ARTICLE1),
        ("x/jorf/global/article/JORF/ARTI/2.xml", RAPPORT),
    )
    for nom in ("JORF_20260612-215918.tar.gz", "JORF_20260613-215918.tar.gz"):  # republié
        store(
            conn,
            raw,
            source_id="dila_jorf",
            external_id=nom,
            url="u",
            fetched_at="2026-06-13T00:00:00Z",
            chunks=[data],
            suffix=".tar.gz",
        )
    (fait,) = budget.extract(conn, raw, cache_dir=tmp_path / "cache")
    assert fait.indicator_id == "D2.annulations_credits"
    assert fait.fact_type == "decret_annulation_credits"
    assert fait.occurred_on == "2026-06-11"
    assert fait.official_ref == "2026-490"
    assert fait.attributes["montant_cp_md"] == pytest.approx(0.490273528)
    assert fait.attributes["url"] == "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000054238633"


def test_somme_des_montants_sur_douze_mois(conn, tmp_path):
    for source in metrics.COVERAGE_SOURCES:
        store(
            conn,
            tmp_path / "raw",
            source_id=source,
            external_id="x",
            url="u",
            fetched_at="2026-11-10T08:00:00Z",
            chunks=[source.encode()],
        )

    def decret(jour, md):
        return FactDraft(
            "D2.annulations_credits",
            "decret_annulation_credits",
            jour,
            "d",
            None,
            "test",
            (1,),
            {"montant_cp_md": md},
        )

    write_facts(
        conn, [decret("2026-01-20", 1.5), decret("2026-06-11", 0.49), decret("2025-02-04", 5.0)]
    )
    ind = load_grid().indicators["D2.annulations_credits"]
    assert ind.scored_metric == "montant_annule_cp_md"
    rows = metrics.compute(
        conn, load_grid(), [{"numero": 17, "debut": dt.date(2024, 7, 18), "fin": None}]
    )
    v = {
        r[4]: r[5]
        for r in rows
        if r[0] == "D2.annulations_credits" and r[1] == "2026-11-09" and r[2] == "glissante_365j"
    }
    assert v["nb_decrets_annulation"] == 2.0
    assert v["montant_annule_cp_md"] == pytest.approx(1.99)


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        (
            "Sont annulés, pour 2026, des crédits d'un montant de 440 278 740 € en autorisations d'engagement et de 490 273 528 € en crédits de paiement applicables",
            (440278740, 490273528),
        ),
        (
            "Sont annulés, pour 2026, des crédits d'un montant de 500 000 000 € en autorisations d'engagement et en crédits de paiement applicables",
            (500000000, 500000000),
        ),
        (
            "Sont annulés, pour 2020, des crédits d'un montant de 86 089 520,21 € en autorisations d'engagement et en crédits de paiement applicables",
            (86089520.21, 86089520.21),
        ),
        (
            "Sont annulés, pour 2006, des crédits d'un montant de 1 203 942 en autorisations d'engagement et de 1 204 251 en crédits de paiement applicables",
            (1203942, 1204251),
        ),
        (
            "Sont annulés pour 2007 des crédits d'un montant de 19 304 281 EUR en autorisations d'engagement et de 19 564 281 EUR en crédits de paiement",
            (19304281, 19564281),
        ),
        (
            "Sont annulés, pour 2008, des crédits d'un montant de 2 533 956 euros en autorisations d'engagement et de 7 823 956 euros en crédits de paiement",
            (2533956, 7823956),
        ),
        (
            "Est annulé sur 2005 un crédit de paiement de 746 180 601 EUR applicable aux budgets",
            (0, 746180601),
        ),
        (
            "Sont annulés sur 2005 une autorisation de programme de 7 361 299 EUR et un crédit de paiement de 9 034 931 EUR applicables",
            (7361299, 9034931),
        ),
        (
            "Sont annulés, pour 2025, des crédits d'un montant de 1 951 934,32 € en autorisations d'engagement applicables aux programmes",
            (1951934.32, 0),
        ),
    ],
)
def test_formulations_des_montants(phrase, attendu):
    assert budget.montants(phrase) == pytest.approx(attendu)


def test_annexe_ignoree():
    annexe = ARTICLE1.replace(
        "Sont annulés, pour 2026, des crédits d'un montant de".encode(),
        "ANNEXE TABLEAU AUTORISATIONS d'engagement annulées CRÉDITS de paiement annulés 1 €, de".encode(),
    )
    assert budget.lire_article(annexe) is None
