"""D7 : candidats presse dérivés des extraits GDELT."""

import gzip

from extract import d7_candidats as c
from extract.gdelt import lire_jour

CATS = c.categories_d7()
GROUPES = c.groupes_presse()


def row(
    evt="1",
    code="173",
    a1="COP",
    url="https://www.lemonde.fr/a",
    domaine="lemonde.fr",
    jour="20261105",
    lieu="Strasbourg, Alsace, France",
):
    return {
        "mention_utc": "20261105120000",
        "evenement_id": evt,
        "evenement_jour": jour,
        "code_evenement": code,
        "code_racine": code[:2],
        "acteur1_type": a1,
        "acteur2_type": "",
        "lieu": lieu,
        "domaine": domaine,
        "url": url,
        "langue_source": "fra",
    }


def test_categorie_arrestation_par_police():
    assert c.categorie(row(code="173"), CATS) == "interpellations"


def test_categorie_hors_d7():
    assert c.categorie(row(code="040"), CATS) is None


def test_categorie_acteur_non_public():
    assert c.categorie(row(code="173", a1="CVL"), CATS) is None


def test_categorie_par_racine():
    assert c.categorie(row(code="182"), CATS) == "force"


def test_categories_concurrentes():
    # 175 figure dans « reunion » et « force » : la première dans l'ordre de la grille l'emporte.
    assert c.categorie(row(code="175"), CATS) == "reunion"


def test_groupe_sous_domaine():
    assert c.groupe_de("www.ouest-france.fr", GROUPES) == "ouest_france"
    assert c.groupe_de("france3-regions.francetvinfo.fr", GROUPES) == "france_televisions"
    assert c.groupe_de("blog-perso.fr", GROUPES) is None


def test_un_seul_groupe_ne_suffit_pas():
    rows = [
        row(),
        row(url="https://www.courrierinternational.com/b", domaine="courrierinternational.com"),
    ]
    assert c.pre_candidats(rows, CATS, GROUPES) == []


def test_deux_groupes_recoupent():
    rows = [row(), row(url="https://www.lefigaro.fr/b", domaine="lefigaro.fr")]
    (cand,) = c.pre_candidats(rows, CATS, GROUPES)
    assert cand.evenement_id == c.identifiant_gdelt(
        "2026-11-05", "Strasbourg, Alsace, France", "interpellations"
    )
    assert cand.evenement_id.startswith("gdelt-20261105-")
    assert cand.jour == "2026-11-05"
    assert cand.categorie == "interpellations"
    assert cand.lieu == "Strasbourg, Alsace, France"
    assert cand.groupes == ("groupe_figaro_dassault", "groupe_le_monde")
    assert [a.domaine for a in cand.articles] == ["lefigaro.fr", "lemonde.fr"]


def test_domaine_inconnu_ignore():
    rows = [row(), row(url="https://blog-perso.fr/b", domaine="blog-perso.fr")]
    assert c.pre_candidats(rows, CATS, GROUPES) == []


def test_meme_url_comptee_une_fois():
    rows = [row(), row(), row(url="https://www.lefigaro.fr/b", domaine="lefigaro.fr")]
    (cand,) = c.pre_candidats(rows, CATS, GROUPES)
    assert len(cand.articles) == 2


def test_lecture_extrait_archive():
    entete = "\t".join(row().keys())
    texte = "# tranches manquantes : aucune\n" + entete + "\n" + "\t".join(row().values()) + "\n"
    _, rows = lire_jour(gzip.compress(texte.encode()))
    assert c.categorie(rows[0], CATS) == "interpellations"


def test_candidats_depuis_l_archive(tmp_path):
    from collectors import presse_titres as pt
    from storage.archive import store
    from storage.db import connect, init_db

    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    lignes = [row(), row(url="https://www.lefigaro.fr/b", domaine="lefigaro.fr")]
    lignes += [
        row(evt="2", lieu="Lyon, Rhône-Alpes, France"),
        row(
            evt="2",
            url="https://www.lefigaro.fr/c",
            domaine="lefigaro.fr",
            lieu="Lyon, Rhône-Alpes, France",
        ),
    ]
    entete = "\t".join(row().keys())
    texte = entete + "\n" + "".join("\t".join(r.values()) + "\n" for r in lignes)
    store(
        conn,
        tmp_path / "raw",
        source_id="gdelt",
        external_id="2026-11-05.tsv.gz",
        url="u",
        fetched_at="2026-11-06T00:00:00Z",
        chunks=[gzip.compress(texte.encode())],
    )
    web = {
        "https://www.lemonde.fr/a": b"<title>Nasse a Strasbourg</title>",
        "https://www.lefigaro.fr/b": b"<title>Une nasse a Strasbourg - Le Figaro</title>",
        "https://www.lefigaro.fr/c": b"<title>Nasse a Strasbourg - Le Figaro</title>",
    }
    import io
    from contextlib import contextmanager

    @contextmanager
    def opener(url):
        yield io.BytesIO(web[url])

    pt.collect_urls(conn, tmp_path / "raw", list(web), opener=opener, sleep=lambda s: None)
    # L'événement 2 cite deux fois la même dépêche (lemonde.fr/a et lefigaro.fr/c) : écarté.
    lignes2 = [r for r in lignes if r["evenement_id"] == "2"]
    assert {r["url"] for r in lignes2} == {"https://www.lemonde.fr/a", "https://www.lefigaro.fr/c"}
    assert [x.lieu for x in c.candidats(conn, tmp_path / "raw")] == ["Strasbourg, Alsace, France"]


def test_evenements_differents_meme_jour_lieu_categorie_regroupes():
    """GDELT donne souvent un identifiant par article : on regroupe par jour, lieu, catégorie."""
    rows = [row(evt="1"), row(evt="2", url="https://www.lefigaro.fr/b", domaine="lefigaro.fr")]
    (cand,) = c.pre_candidats(rows, CATS, GROUPES)
    assert len(cand.articles) == 2


def test_lieu_vague_ecarte():
    rows = [
        row(lieu="France"),
        row(url="https://www.lefigaro.fr/b", domaine="lefigaro.fr", lieu="France"),
    ]
    assert c.pre_candidats(rows, CATS, GROUPES) == []
