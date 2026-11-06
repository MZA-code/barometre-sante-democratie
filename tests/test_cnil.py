# ruff: noqa: E501  (extraits XML de test : lignes longues voulues)
import datetime as dt
import io
import tarfile

import pytest

from extract import cnil
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
INDICATOR = load_grid().indicators[cnil.INDICATOR]


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        (
            "La Commission émet un avis favorable sous réserve des observations.",
            ["favorable_sous_reserves"],
        ),
        (
            "La Commission émet de sérieuses réserves quant à la possibilité d'élargir la liste.",
            ["reserves"],
        ),
        ("La Commission exprime de vives réserves sur la légitimité de ce cadre.", ["reserves"]),
        ("La Commission émet un avis défavorable au projet de décret.", ["defavorable"]),
        # avis défavorable de l'administration dans la procédure créée : pas un avis de la CNIL
        ("de sorte qu'aucun avis défavorable ne soit pris sur le seul fondement d'un fichier.", []),
        # formules d'observation : non comptées (critère strict)
        (
            "La Commission regrette l'absence de précision et demande que le décret soit complété.",
            [],
        ),
        ("sous réserve que les données soient effacées", []),
    ],
)
def test_reserve_formulas_are_strict(texte, attendu):
    assert [k for k, rx in cnil.RESERVE.items() if rx.search(texte)] == attendu


def test_cnil_citations_in_visas():
    visas = (
        "Vu le code de la sécurité intérieure ; Vu la loi n° 78-17 du 6 janvier 1978 relative à "
        "l'informatique, aux fichiers et aux libertés ; Vu l'avis de la Commission nationale de "
        "l'informatique et des libertés en date du 12 mars 2009 ; Vu la délibération n° 2020-001 "
        "du 9 janvier 2020 de la Commission nationale de l'informatique et des libertés ; "
        "Vu l'avis du Conseil d'État du 3 avril 2020"
    )
    got = cnil.cnil_citations(visas)
    assert got["numeros"] == ["2020-001"]
    assert got["dates"] == ["2009-03-12", "2020-01-09"]  # la loi de 1978 n'est pas un avis


def avis(numero, date, reserves=()):
    return cnil.Avis(
        f"CNILTEXT{numero}",
        numero,
        date,
        f"Délibération {numero} portant avis sur un projet de décret",
        list(reserves),
        {1},
    )


def test_match_by_number_then_unique_date():
    a1, a2, a3 = (
        avis("2020-001", "2020-01-09", ["reserves"]),
        avis("2020-002", "2020-01-16"),
        avis("2020-003", "2020-01-16"),
    )
    by_num = {a.numero: a for a in (a1, a2, a3)}
    by_date = {"2020-01-09": [a1], "2020-01-16": [a2, a3]}
    assert cnil.match({"numeros": ["2020-001"], "dates": [], "titre": ""}, by_num, by_date) == (
        [a1],
        "numero",
        None,
    )
    assert cnil.match({"numeros": [], "dates": ["2020-01-09"], "titre": ""}, by_num, by_date) == (
        [a1],
        "date",
        None,
    )
    # deux avis le même jour, titres sans rapport : rapprochement refusé
    assert cnil.match(
        {"numeros": [], "dates": ["2020-01-16"], "titre": "Décret"}, by_num, by_date
    ) == ([], None, None)


def test_same_day_opinions_disambiguated_by_title():
    a = cnil.Avis(
        "C1",
        "2020-033",
        "2020-03-19",
        "Délibération portant avis sur un projet de décret relatif au certificat de décès",
        [],
        {1},
    )
    b = cnil.Avis(
        "C2",
        "2020-034",
        "2020-03-19",
        "Délibération portant avis sur un projet de décret relatif au fichier des véhicules volés",
        [],
        {1},
    )
    decret = {
        "numeros": [],
        "dates": ["2020-03-19"],
        "titre": "Décret n° 2020-446 relatif à l'établissement du certificat de décès",
    }
    lies, methode, score = cnil.match(decret, {}, {"2020-03-19": [a, b]})
    assert lies == [a] and methode == "date_titre" and score >= cnil.SIMILARITE_MIN


def tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


AVIS_XML = """<?xml version="1.0" encoding="UTF-8"?><TEXTE_CNIL><META><META_COMMUN><ID>CNILTEXT1</ID>
<NATURE>AVIS</NATURE></META_COMMUN><META_SPEC><META_CNIL><TITRE>Délibération n° 2020-001</TITRE>
<TITREFULL>Délibération n° 2020-001 du 9 janvier 2020 portant avis sur un projet de décret créant un traitement</TITREFULL>
<NUMERO>2020-001</NUMERO><DATE_TEXTE>2020-01-09</DATE_TEXTE></META_CNIL></META_SPEC></META>
<BLOC_TEXTUEL><CONTENU><p>La Commission émet des réserves sur la durée de conservation.</p></CONTENU></BLOC_TEXTUEL></TEXTE_CNIL>"""

DECRET_XML = """<?xml version="1.0" encoding="UTF-8"?><TEXTE_VERSION><META><META_COMMUN><ID>LEGITEXT9</ID>
<NATURE>DECRET</NATURE></META_COMMUN><META_SPEC><META_TEXTE_CHRONICLE><CID>JORFTEXT9</CID><NUM>2020-300</NUM>
<DATE_TEXTE>2020-03-20</DATE_TEXTE><DATE_PUBLI>2020-03-22</DATE_PUBLI></META_TEXTE_CHRONICLE>
<META_TEXTE_VERSION><TITREFULL>Décret n° 2020-300 portant création d'un traitement</TITREFULL></META_TEXTE_VERSION></META_SPEC></META>
<VISAS><CONTENU>Vu la délibération n° 2020-001 du 9 janvier 2020 de la Commission nationale de l'informatique et des libertés ;</CONTENU></VISAS></TEXTE_VERSION>"""


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_extract_and_metrics(conn, tmp_path):
    raw = tmp_path / "raw"
    for source, name, files in [
        (
            "dila_cnil",
            "Freemium_cnil_global_20250713-140000.tar.gz",
            {"cnil/CNILTEXT1.xml": AVIS_XML.encode()},
        ),
        (
            "dila_jorf",
            "Freemium_jorf_global_20250713-140000.tar.gz",
            {"jorf/TEXT/JORFTEXT9.xml": DECRET_XML.encode()},
        ),
    ]:
        store(
            conn,
            raw,
            source_id=source,
            external_id=name,
            url="u",
            fetched_at="2026-11-05T00:00:00Z",
            chunks=[tar(files)],
            suffix=".tar.gz",
        )
    drafts = {d.fact_type: d for d in cnil.extract(conn, raw, tmp_path / "cache")}
    decret = drafts["decret_apres_avis_cnil"]
    assert decret.occurred_on == "2020-03-22" and decret.official_ref == "2020-300"
    assert decret.attributes["malgre_reserves"] and decret.attributes["rapprochement"] == "numero"
    assert decret.attributes["confiance"] == "forte"
    assert drafts["avis_cnil_projet_decret"].attributes["decrets_publies"] == ["JORFTEXT9"]

    from extract.common import write_facts

    write_facts(conn, list(drafts.values()))
    events = metrics.load_events(conn, INDICATOR)
    values = metrics.window_values(
        events, metrics.Window("t", 366, D(2020, 1, 1), D(2020, 12, 31)), {}
    )
    assert values["nb_decrets_malgre_reserves"] == 1 and values["nb_decrets_avis_cnil"] == 1
    assert values["nb_avis_cnil_reserves"] == 1 and values["nb_avis_cnil_projets_decret"] == 1


def test_years_do_not_count_as_shared_words():
    decret = "Décret n° 2023-646 du 20 juillet 2023 portant création d'un traitement dénommé « Aqua-SISE »"
    avis_ = "Délibération n° 2023-034 du 6 avril 2023 portant avis sur un projet de décret dénommé « Fichier du renseignement pénitentiaire »"
    assert cnil.similarite(decret, avis_) == 0.0


def test_same_opinion_published_under_two_ids_is_counted_once():
    # 2022-083 du 21/07/2022 : CNILTEXT000046326824 et CNILTEXT000046328920
    a = cnil.Avis("CNILTEXT2", "2022-083", "2022-07-21", "SIRCID", ["favorable_sous_reserves"], {2})
    b = cnil.Avis("CNILTEXT1", "2022-083", "2022-07-21", "SIRCID", [], {1})
    c = cnil.Avis("CNILTEXT3", "2022-084", "2022-07-21", "Autre", [], {3})
    merged = cnil.dedup_avis({x.id: x for x in (a, b, c)})
    assert sorted(merged) == ["CNILTEXT1", "CNILTEXT3"]
    kept = merged["CNILTEXT1"]
    assert kept.raw_ids == {1, 2} and kept.reserves == ["favorable_sous_reserves"]
