"""D7 : titres des articles candidats et fusion des dépêches reprises."""

import io
import json
from contextlib import contextmanager

import pytest

from collectors import presse_titres as pt
from extract import d7_candidats as c
from storage.db import connect, init_db


def test_titre_og():
    page = (
        b'<html><head><meta property="og:title" content="Strasbourg&nbsp;: des manifestants'
        b' interpell&eacute;s"><title>X</title>'
    )
    assert pt.titre_de_page(page) == "Strasbourg\xa0: des manifestants interpellés"


def test_titre_balise_title():
    assert pt.titre_de_page(b"<html><head><title> Un titre </title></head>") == "Un titre"


def test_sans_titre():
    assert pt.titre_de_page(b"<html><body>rien</body></html>") is None


def test_normaliser_titre():
    a = pt.normaliser_titre("Strasbourg : des manifestants interpellés - Le Figaro")
    b = pt.normaliser_titre("STRASBOURG, des manifestants interpelles")
    assert a == b == "strasbourg des manifestants interpelles"


def article(url, domaine, groupe):
    return c.Article(url, domaine, groupe, "20261105120000")


def candidat(*articles):
    return c.Candidat(
        "1",
        "2026-11-05",
        "interpellations",
        "Strasbourg",
        tuple(articles),
        tuple(sorted({a.groupe for a in articles})),
    )


def test_depeche_reprise_ne_recoupe_pas():
    cand = candidat(
        article("https://a.fr/1", "lemonde.fr", "g1"),
        article("https://b.fr/2", "lefigaro.fr", "g2"),
    )
    titres = {
        "https://a.fr/1": "Strasbourg : 40 interpellations - AFP",
        "https://b.fr/2": "Strasbourg : 40 interpellations",
    }
    assert pt.fusionner(cand, titres) is None


def test_titres_differents_recoupent():
    cand = candidat(
        article("https://a.fr/1", "lemonde.fr", "g1"),
        article("https://b.fr/2", "lefigaro.fr", "g2"),
    )
    titres = {"https://a.fr/1": "Nasse à Strasbourg", "https://b.fr/2": "Quarante interpellations"}
    assert pt.fusionner(cand, titres) == cand


def test_titre_inconnu_reste_une_source():
    cand = candidat(
        article("https://a.fr/1", "lemonde.fr", "g1"),
        article("https://b.fr/2", "lefigaro.fr", "g2"),
    )
    assert pt.fusionner(cand, {"https://a.fr/1": "X", "https://b.fr/2": None}) == cand


class FauxWeb:
    def __init__(self, pages):
        self.pages, self.appels = pages, []

    @contextmanager
    def __call__(self, url):
        self.appels.append(url)
        if self.pages[url] is None:
            raise OSError("refus")
        yield io.BytesIO(self.pages[url])


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_collect_archive_une_fois(conn, tmp_path):
    web = FauxWeb({"https://a.fr/1": b"<title>Un</title>", "https://b.fr/2": None})
    urls = ["https://a.fr/1", "https://b.fr/2"]
    assert pt.collect_urls(conn, tmp_path / "raw", urls, opener=web, sleep=lambda s: None) == 2
    assert pt.collect_urls(conn, tmp_path / "raw", urls, opener=web, sleep=lambda s: None) == 0
    assert web.appels == urls
    assert pt.titres_archives(conn, tmp_path / "raw") == {
        "https://a.fr/1": "Un",
        "https://b.fr/2": None,
    }


def test_document_archive_sans_texte(conn, tmp_path):
    web = FauxWeb({"https://a.fr/1": b"<title>Un</title><p>texte de l'article</p>"})
    pt.collect_urls(conn, tmp_path / "raw", ["https://a.fr/1"], opener=web, sleep=lambda s: None)
    (path,) = conn.execute(
        "SELECT path FROM raw_documents WHERE source_id = 'presse_titres'"
    ).fetchone()
    assert json.loads((tmp_path / "raw" / path).read_text()) == {
        "titre": "Un",
        "url": "https://a.fr/1",
    }
