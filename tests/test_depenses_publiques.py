import io
from contextlib import contextmanager

import pytest

from collectors import eurostat
from extract import depenses_publiques
from storage.db import connect, init_db

ENTETE = (
    "DATAFLOW,LAST UPDATE,freq,unit,sector,cofog99,na_item,geo,"
    "TIME_PERIOD,OBS_VALUE,OBS_FLAG,CONF_STATUS\n"
)
LIGNES = [
    "E,1,A,MIO_EUR,S13,TOTAL,TE,FR,2023,1600000.0,,",
    "E,1,A,PC_GDP,S13,TOTAL,TE,FR,2023,57.0,,",
    "E,1,A,MIO_EUR,S13,GF02,TE,FR,2023,50000.0,,",
    "E,1,A,PC_GDP,S13,GF02,TE,FR,2023,1.8,,",
    "E,1,A,MIO_EUR,S13,TOTAL,TE,FR,2024,1671793.8,p,",
    "E,1,A,MIO_EUR,S13,GF09,TE,FR,2024,148639.6,p,",
    "E,1,A,MIO_EUR,S13,GF09,TE,US,2024,1.0,,",  # pays non suivi : ignoré
    "E,1,A,MIO_EUR,S13,GF09,TE,DE,2024,,,",  # valeur absente : ignorée
]


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def web_de(contenu: str):
    @contextmanager
    def web(url):
        assert url in (eurostat.URL, eurostat.URL_PRISONS)
        yield io.BytesIO((contenu if url == eurostat.URL else "x").encode())

    return web


def test_parse_groupe_par_pays_et_annee():
    out = depenses_publiques.parse((ENTETE + "\n".join(LIGNES)).encode())
    assert set(out) == {("FR", 2023), ("FR", 2024)}
    assert out[("FR", 2023)]["valeurs"]["GF02"] == {"MIO_EUR": 50000.0, "PC_GDP": 1.8}
    assert out[("FR", 2023)]["provisoire"] is False
    assert out[("FR", 2024)]["provisoire"] is True


def test_collecte_archive_seulement_si_le_contenu_change(conn, tmp_path):
    raw = tmp_path / "raw"
    contenu = ENTETE + "\n".join(LIGNES)
    assert eurostat.collect(conn, raw, opener=web_de(contenu)) == [
        "gov_10a_exp.csv",
        "crim_pris_cap.csv",
    ]
    assert eurostat.collect(conn, raw, opener=web_de(contenu)) == []
    assert eurostat.collect(conn, raw, opener=web_de(contenu + "\n")) == ["gov_10a_exp.csv"]
    drafts = depenses_publiques.extract(conn, raw)
    assert [(d.attributes["pays"], d.attributes["annee"]) for d in drafts] == [
        ("FR", 2023),
        ("FR", 2024),
    ]
    assert all(d.indicator_id == "contexte.depenses_publiques" for d in drafts)
    assert drafts[1].attributes["valeurs"]["GF09"] == {"MIO_EUR": 148639.6}


def test_libelles_couvrent_les_fonctions_collectees():
    assert set(depenses_publiques.LIBELLES) == set(eurostat.FONCTIONS)
