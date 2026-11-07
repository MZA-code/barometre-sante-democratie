# ruff: noqa: E501  (fragments HTML de test : longs voulus)
import io
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

from collectors import ddd as col
from extract import ddd
from storage.archive import is_archived, store
from storage.db import connect, init_db

FIX = Path(__file__).resolve().parent / "fixtures" / "ddd"
NOTICE = (FIX / "notice_60221.html").read_bytes()
LISTE = (FIX / "categorie_3875_p1.html").read_bytes()


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_lecture_d_une_fiche():
    f = ddd.lire_fiche(NOTICE.decode())
    assert f["titre"].startswith("Décision 2026-158 du 7 juillet 2026 - Opérations de maintien")
    assert (f["type"], f["date"], f["numero"]) == ("Décisions", "07/07/2026", "2026-158")
    assert "Manifestation" in f["mots_cles"] and "Usage de la force" in f["mots_cles"]
    assert f["suites"] == ["Recommandation", "Demande de poursuites disciplinaires"]
    assert f["pdf"].endswith("doc_num.php?explnum_id=23301")
    assert f["resume"].startswith("La Défenseure des droits s’est saisie d’office")


def test_liste_et_pagination():
    page = LISTE.decode()
    assert col.fiches(page)[:3] == ["60221", "60064", "59842"]
    assert len(col.fiches(page)) == 10
    assert col.pagination(page) == ("190", "a%2Cb%2Cc%2Cg%2Cl%2Cn%2Co")
    url = col.url_liste(3875, 2, col.pagination(page))
    assert url.endswith("id=3875&page=2&nbr_lignes=190&l_typdoc=a%2Cb%2Cc%2Cg%2Cl%2Cn%2Co")


def test_extraction_un_fait_par_document_propre(conn, tmp_path):
    raw = tmp_path / "raw"
    arret = re.sub(
        r"(record_tdoc.*?<span>)\s*Décisions\s*",
        r"\1 Jurisprudences ",
        NOTICE.decode(),
        count=1,
        flags=re.S,
    )
    assert "Jurisprudences" in arret
    for nid, data in (("60221", NOTICE), ("57320", arret.encode())):
        store(
            conn,
            raw,
            source_id=col.SOURCE_ID,
            external_id=nid,
            url=col.url_fiche(nid),
            fetched_at="2026-11-07T00:00:00Z",
            chunks=[data],
            suffix=".html",
        )
    (f,) = ddd.extract(conn, raw)  # la jurisprudence (arrêt d'une autre juridiction) est écartée
    assert (f.occurred_on, f.fact_type, f.indicator_id) == (
        "2026-07-07",
        "decision_ddd_manifestation",
        "contexte.defenseur_droits",
    )
    assert f.attributes["type"] == "décision" and f.attributes["numero"] == "2026-158"
    assert f.official_ref.endswith("notice_display&id=60221")


class Faux:
    """Site simulé : une page de liste (2 fiches), puis les fiches."""

    def __init__(self):
        self.urls = []

    @contextmanager
    def __call__(self, url):
        self.urls.append(url)
        if "categ_see" in url:
            body = b'<a href="index.php?lvl=notice_display&amp;id=1">a</a><a href="index.php?lvl=notice_display&amp;id=2">b</a>'
        else:
            body = NOTICE
        yield io.BytesIO(body)


def test_collecte_respecte_le_delai_et_n_archive_qu_une_fois(conn, tmp_path):
    faux, attentes = Faux(), []
    raw = tmp_path / "raw"
    assert col.collect(conn, raw, opener=faux, sleep=attentes.append) == ["1", "2"]
    assert is_archived(conn, col.SOURCE_ID, "1") and is_archived(conn, col.SOURCE_ID, "2")
    # 2 listes (une par catégorie) + 2 fiches ; une attente avant chaque requête sauf la première
    assert len(faux.urls) == 4 and len(attentes) == 3 and all(a > 29 for a in attentes)
    faux.urls.clear()
    assert col.collect(conn, raw, opener=faux, sleep=lambda s: None) == []
    assert all("categ_see" in u for u in faux.urls)  # rien de nouveau : listes seulement


def test_page_inattendue_refusee(conn, tmp_path):
    class Vide(Faux):
        @contextmanager
        def __call__(self, url):
            yield io.BytesIO(
                b'<a href="index.php?lvl=notice_display&id=9">x</a>'
                if "categ" in url
                else b"erreur"
            )

    with pytest.raises(ValueError, match="page inattendue"):
        col.collect(conn, tmp_path / "raw", opener=Vide(), sleep=lambda s: None)


def test_fiche_datee_de_l_annee_seulement(conn, tmp_path):
    raw = tmp_path / "raw"
    page = re.sub(
        r"(record_year.*?<span>)07/07/2026", r"\g<1>2010", NOTICE.decode(), count=1, flags=re.S
    )
    assert ">2010<" in page
    store(
        conn,
        raw,
        source_id=col.SOURCE_ID,
        external_id="1",
        url="u",
        fetched_at="2026-11-07T00:00:00Z",
        chunks=[page.encode()],
        suffix=".html",
    )
    (f,) = ddd.extract(conn, raw)
    assert f.occurred_on == "2010-12-31" and f.attributes["precision_date"] == "année"
