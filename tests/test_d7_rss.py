# ruff: noqa: E501  (flux RSS de test : lignes longues voulues)
"""D7 : repérage des faits de presse dans les flux RSS."""

import io
import json
from contextlib import contextmanager

import pytest

from collectors import rss
from extract import d7_rss as r
from storage.db import connect, init_db

CONF = r.conf_rss()
GROUPES = r.groupes_presse()
COMMUNES = [
    {"nom": "Strasbourg", "code": "67482", "codeDepartement": "67", "population": 290000},
    {"nom": "Brest", "code": "29019", "codeDepartement": "29", "population": 140000},
    {"nom": "Saint-Denis", "code": "93066", "codeDepartement": "93", "population": 113000},
    {"nom": "Saint-Denis", "code": "97411", "codeDepartement": "974", "population": 150000},
    {"nom": "Vic", "code": "00001", "codeDepartement": "00", "population": 200},
]
INDEX = r.index_communes(COMMUNES, CONF["population_min_commune"])

FLUX = b"""<?xml version="1.0"?><rss><channel>
<item><title>Strasbourg : des manifestants interpell&#233;s au hasard</title>
<link>https://www.lemonde.fr/a</link><pubDate>Sat, 07 Nov 2026 18:00:00 +0100</pubDate>
<description><![CDATA[<p>Quarante personnes ont &eacute;t&eacute; interpell&eacute;es.</p>]]></description></item>
<item><title>Sans date</title><link>https://www.lemonde.fr/b</link></item>
</channel></rss>"""


def test_lire_flux():
    (item,) = rss.lire_flux(FLUX)
    assert item == {
        "titre": "Strasbourg : des manifestants interpellés au hasard",
        "lien": "https://www.lemonde.fr/a",
        "date": "2026-11-07T17:00:00Z",
        "resume": "Quarante personnes ont été interpellées.",
    }


def test_resume_tronque():
    long = (
        b"<rss><channel><item><title>T</title><link>https://x.fr/1</link><pubDate>Sat, 07 Nov 2026 18:00:00 +0000</pubDate><description>"
        + b"a" * 900
        + b"</description></item></channel></rss>"
    )
    assert len(rss.lire_flux(long)[0]["resume"]) == rss.RESUME_MAX


def test_categorie_interpellations_avec_contexte():
    assert (
        r.categorie_texte(r.normaliser("Des manifestants interpellés à Brest"), CONF)
        == "interpellations"
    )
    assert r.categorie_texte(r.normaliser("Un trafiquant interpellé à Brest"), CONF) is None


def test_categorie_force_exige_une_autorite():
    assert (
        r.categorie_texte(r.normaliser("Un lycéen éborgné par un tir de LBD de la police"), CONF)
        == "force"
    )
    assert (
        r.categorie_texte(
            r.normaliser("Une grenade de la Seconde Guerre mondiale découverte"), CONF
        )
        is None
    )


def test_categorie_surveillance():
    texte = r.normaliser("La police saisit les trombinoscopes des élèves d'un lycée")
    assert r.categorie_texte(texte, CONF) == "surveillance"


def test_commune_reconnue_avec_majuscule():
    assert r.commune_de("Brest : la police saisit les trombinoscopes", INDEX) == (
        "29019",
        "Brest",
        "29",
    )
    assert r.commune_de("un brest de rien", INDEX) is None


def test_petite_commune_ignoree():
    assert r.commune_de("Vic sous la neige", INDEX) is None


def test_homonymes_la_plus_peuplee():
    assert r.commune_de("Saint-Denis : rassemblement dispersé", INDEX)[0] == "97411"


def item(lien, titre, date="2026-11-07T17:00:00Z", resume=""):
    return {"titre": titre, "lien": lien, "date": date, "resume": resume}


def test_deux_groupes_meme_commune_meme_categorie():
    items = [
        item("https://www.lemonde.fr/a", "Strasbourg : des manifestants interpellés au hasard"),
        item(
            "https://www.lefigaro.fr/b",
            "À Strasbourg, quarante interpellations lors de la manifestation",
            "2026-11-08T09:00:00Z",
        ),
        item("https://www.lemonde.fr/c", "Brest : des manifestants interpellés"),
    ]
    (c,) = r.candidats_rss(items, CONF, INDEX, GROUPES)
    assert c.evenement_id == "rss-67482-interpellations-20261107"
    assert c.categorie == "interpellations"
    assert c.lieu == "Strasbourg (67)"
    assert c.jour == "2026-11-07"
    assert c.groupes == ("groupe_figaro_dassault", "groupe_le_monde")


def test_trop_eloignes_dans_le_temps():
    items = [
        item("https://www.lemonde.fr/a", "Strasbourg : des manifestants interpellés"),
        item(
            "https://www.lefigaro.fr/b",
            "Strasbourg : des manifestants interpellés en masse",
            "2026-11-12T09:00:00Z",
        ),
    ]
    assert r.candidats_rss(items, CONF, INDEX, GROUPES) == []


def test_depeche_reprise_ne_recoupe_pas():
    titre = "Strasbourg : des manifestants interpellés au hasard"
    items = [
        item("https://www.lemonde.fr/a", titre),
        item("https://www.lefigaro.fr/b", titre + " - AFP"),
    ]
    assert r.candidats_rss(items, CONF, INDEX, GROUPES) == []


class FauxWeb:
    def __init__(self, pages):
        self.pages = pages

    @contextmanager
    def __call__(self, url):
        if isinstance(self.pages[url], Exception):
            raise self.pages[url]
        yield io.BytesIO(self.pages[url])


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_collect_cumule_les_articles_du_jour(conn, tmp_path):
    raw = tmp_path / "raw"
    web = FauxWeb({"u1": FLUX, "u2": OSError("refus")})
    flux = {"lemonde": "u1", "panne": "u2"}
    assert (
        rss.collect(
            conn,
            raw,
            flux,
            opener=web,
            maintenant=lambda: "2026-11-07T18:00:00Z",
            sleep=lambda s: None,
        )
        == 1
    )
    autre = FLUX.replace(b"https://www.lemonde.fr/a", b"https://www.lemonde.fr/z")
    web.pages["u1"] = autre
    assert (
        rss.collect(
            conn,
            raw,
            flux,
            opener=web,
            maintenant=lambda: "2026-11-07T19:00:00Z",
            sleep=lambda s: None,
        )
        == 1
    )
    liens = sorted(i["lien"] for i in r.items_archives(conn, raw))
    assert liens == ["https://www.lemonde.fr/a", "https://www.lemonde.fr/z"]
    (path,) = conn.execute(
        "SELECT path FROM raw_documents WHERE source_id = 'rss_presse' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert json.loads((raw / path).read_text())["flux"] == "lemonde"


def test_debut_rss(conn, tmp_path):
    assert r.debut_rss(conn) is None
    rss.collect(
        conn,
        tmp_path / "raw",
        {"lemonde": "u1"},
        opener=FauxWeb({"u1": FLUX}),
        maintenant=lambda: "2026-11-07T18:00:00Z",
        sleep=lambda s: None,
    )
    assert str(r.debut_rss(conn)) == "2026-11-07"


def test_flux_avec_entites_refuse():
    piege = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel></channel></rss>'
    with pytest.raises(ValueError):
        rss.lire_flux(piege)
