# ruff: noqa: E501  (titres réels du Journal officiel : lignes longues voulues)
import pytest

from extract import scrutins as s


@pytest.mark.parametrize(
    ("titre", "attendu"),
    [
        (
            "Décret n° 88-250 portant convocation des électeurs pour l'élection du Président de la République",
            "presidentielle",
        ),
        (
            "Décret n° 2024-226 portant convocation des électeurs pour l'élection des représentants au Parlement européen",
            "europeennes",
        ),
        (
            "Décret n° 2024-527 portant convocation des électeurs pour l'élection des députés à l'Assemblée nationale",
            "legislatives",
        ),
        (
            "Décret portant convocation des électeurs pour l'élection des conseillers municipaux et communautaires",
            "municipales",
        ),
        (
            "Loi n° 2021-191 portant report, de mars à juin 2021, du renouvellement général des conseils départementaux, des conseils régionaux",
            "regionales",
        ),
    ],
)
def test_type_scrutin(titre, attendu):
    assert s.type_scrutin(titre) == attendu


def test_dates_tours_article_and_summary():
    article = (
        "Les électeurs sont convoqués le dimanche 9 juin 2024 en vue de procéder à l'élection."
    )
    assert s.dates_tours(article) == ("2024-06-09", None)
    sm = (
        "Convocation le 24 avril 1988 sur le territoire de la République et les centres de vote à "
        "l'étranger. Si nécessaire, le second tour de scrutin aura lieu le 8 mai 1988."
    )
    assert s.dates_tours(sm) == ("1988-04-24", "1988-05-08")
    # la date de signature citée avant la convocation n'est pas prise
    assert (
        s.dates_tours(
            "Vu le décret du 2 mai 2017 ; Les électeurs sont convoqués le 1er juin 2017."
        )[0]
        == "2017-06-01"
    )


@pytest.mark.parametrize(
    ("titre", "attendu"),
    [
        (
            "LOI n° 2021-191 du 22 février 2021 portant report, de mars à juin 2021, du renouvellement général des conseils départementaux",
            ["calendrier"],
        ),
        (
            "Ordonnance n° 2009-935 du 29 juillet 2009 portant répartition des sièges et délimitation des circonscriptions pour l'élection des députés",
            ["decoupage"],
        ),
        (
            "LOI n° 2018-509 du 25 juin 2018 relative à l'élection des représentants au Parlement européen",
            ["mode_scrutin"],
        ),
        ("Décret n° 2024-527 portant convocation des électeurs pour l'élection des députés", []),
        ("Décret fixant le plafond des dépenses électorales des candidats", []),
    ],
)
def test_categories(titre, attendu):
    assert s.categories(titre) == attendu


def test_calendar_groups_overseas_decrees_and_skips_partial_elections():
    arts = {
        "A": [
            {
                "titre": "Décret portant convocation des électeurs pour l'élection des députés à l'Assemblée nationale",
                "texte": "Les électeurs sont convoqués le dimanche 30 juin 2024.",
                "raw_id": 1,
            }
        ],
        "B": [
            {
                "titre": "Décret portant convocation des électeurs pour l'élection des députés à l'Assemblée nationale dans certaines collectivités d'outre-mer",
                "texte": "Les électeurs sont convoqués le samedi 29 juin 2024.",
                "raw_id": 2,
            }
        ],
        "C": [
            {
                "titre": "Décret portant convocation des électeurs pour l'élection d'un député (élection partielle)",
                "texte": "Les électeurs sont convoqués le dimanche 6 octobre 2024.",
                "raw_id": 3,
            }
        ],
    }
    cal = s.calendrier({}, arts)
    assert [(c["type"], c["t1"], sorted(c["decrets"])) for c in cal] == [
        ("legislatives", "2024-06-30", ["A", "B"])
    ]


@pytest.mark.parametrize(
    ("titre", "partielle"),
    [
        (
            "Décret portant convocation des électeurs pour l'élection de trois députés à l'Assemblée nationale (13e circonscription)",
            True,
        ),
        (
            "Décret portant convocation des électeurs pour l'élection du député de la 6e circonscription du Pas-de-Calais",
            True,
        ),
        (
            "Décret annulant la convocation des électeurs le 13 décembre 2020 pour l'élection du député",
            True,
        ),
        (
            "Décret portant convocation des collèges électoraux pour l'élection des députés à l'Assemblée nationale",
            False,
        ),
    ],
)
def test_partial_elections(titre, partielle):
    assert bool(s.PARTIELLE.search(titre)) is partielle


def test_referendum_and_electoral_colleges_are_convocations():
    assert s.CONVOCATION.search(
        "Décret n° 2005-218 du 9 mars 2005 décidant de soumettre un projet de loi au référendum"
    )
    assert s.CONVOCATION.search(
        "Décret portant convocation des collèges électoraux pour l'élection des députés"
    )
    assert (
        s.type_scrutin("Décret décidant de soumettre un projet de loi au référendum")
        == "referendum"
    )


def test_referendum_date_without_convocation_word():
    texte = "Le projet de loi annexé au présent décret sera soumis au référendum le dimanche 29 mai 2005."
    assert s.dates_tours(texte) == ("2005-05-29", None)


@pytest.mark.parametrize(
    ("titre", "politique"),
    [
        (
            "LOI n° 2021-191 portant report, de mars à juin 2021, du renouvellement général des conseils départementaux, des conseils régionaux",
            True,
        ),
        (
            "LOI organique n° 2020-976 portant report de l'élection de six sénateurs représentant les Français établis hors de France",
            True,
        ),
        (
            "Décret du 24 janvier 1984 portant prorogation du mandat du président du conseil d'administration d'Electricité de France",
            False,
        ),
        (
            "Décret n° 2021-1046 relatif au report exceptionnel des élections des juges des tribunaux de commerce",
            False,
        ),
    ],
)
def test_report_must_concern_a_political_election(titre, politique):
    assert bool(s.POLITIQUE.search(titre)) is politique


def test_new_mode_de_scrutin_phrasings_and_multiple_types():
    assert s.categories(
        "LOI organique n° 2016-506 de modernisation des règles applicables à l'élection présidentielle"
    ) == ["mode_scrutin"]
    assert s.categories(
        "LOI organique n° 2021-335 portant diverses mesures relatives à l'élection du Président de la République"
    ) == ["mode_scrutin"]
    assert s.types_vises(
        "LOI organique n° 2011-410 relative à l'élection des députés et sénateurs"
    ) == ["senatoriales", "legislatives"]


def test_report_titles_without_election_word_are_read():
    titre = (
        "LOI n° 2021-191 du 22 février 2021 portant report, de mars à juin 2021, du renouvellement "
        "général des conseils départementaux, des conseils régionaux et des assemblées de Corse"
    )
    assert s.ELECTORAL.search(titre)
    assert "calendrier" in s.categories(titre) and s.POLITIQUE.search(titre)


@pytest.mark.parametrize(
    "titre",
    [
        "LOI n° 2005-1563 du 15 décembre 2005 prorogeant la durée du mandat des conseillers municipaux et des conseillers généraux renouvelables en 2007",
        "Loi organique portant prolongation du mandat des conseillers municipaux",
        "LOI organique n° 2024-343 portant report du renouvellement général des membres du congrès et des assemblées de province de la Nouvelle-Calédonie",
    ],
)
def test_report_phrasings(titre):
    assert s.REPORT.search(titre) and s.POLITIQUE.search(titre)


def test_application_decrees_are_not_reports():
    assert s.APPLICATION.search(
        "Décret n° 2013-938 portant application de la loi n° 2013-403 du 17 mai 2013 modifiant le calendrier électoral"
    )
    assert not s.APPLICATION.search(
        "LOI n° 2015-29 relative à la délimitation des régions et modifiant le calendrier électoral"
    )


def test_report_texts_are_grouped_by_postponed_election(tmp_path):
    table = s.load_rattachements()
    assert table["2020-267"] == table["2020-643"] == ["municipales-2020-t2"]
    assert s.scrutins_reportes("2021-191", table) == {
        "scrutins_reportes": ["departementales-2021", "regionales-2021"],
        "rattachement": "table",
    }
    assert s.scrutins_reportes("2030-1", table) == {
        "scrutins_reportes": ["texte-2030-1"],
        "rattachement": "a_rattacher",
    }
    assert s.load_rattachements(tmp_path / "absent.yaml") == {}


ARTICLE = """<ARTICLE><CONTEXTE><TEXTE cid="JORFTEXT000041746313" nature="LOI" num="2020-290"
 date_publi="2020-03-24"><TITRE_TXT>LOI n° 2020-290 du 23 mars 2020 d'urgence pour faire face à
 l'épidémie de covid-19</TITRE_TXT></TEXTE></CONTEXTE><BLOC_TEXTUEL><CONTENU>I. - Lorsque, à la
 suite du premier tour organisé le 15 mars 2020 pour l'élection des conseillers municipaux et
 communautaires, un second tour est nécessaire, ce second tour, initialement fixé au 22 mars
 2020, est reporté au plus tard en juin 2020.</CONTENU></BLOC_TEXTUEL></ARTICLE>"""


def test_postponement_in_the_body_of_a_general_law():
    record = s.parse_article(ARTICLE.encode())
    assert record["kind"] == "report_article"
    assert record["num"] == "2020-290"
    assert "est reporté" in record["passages"][0]


@pytest.mark.parametrize(
    ("phrase", "retenue"),
    [
        ("Le mandat des conseillers consulaires et des délégués consulaires est prorogé.", True),
        ("Le renouvellement général des conseillers des Français de l'étranger est reporté.", True),
        # Représentants d'élus dans un comité : pas un mandat électif politique.
        (
            "le mandat des représentants des élus locaux au comité des finances locales est"
            " prorogé jusqu'au second tour du renouvellement des conseils municipaux.",
            False,
        ),
        # Date budgétaire reportée l'année d'un renouvellement.
        (
            "l'année de renouvellement des conseils régionaux, cette date est reportée du 30"
            " avril au 31 mai.",
            False,
        ),
        ("Le mandat des conseillers prud'hommes est prorogé jusqu'à cette date.", False),
    ],
)
def test_body_postponement_must_concern_political_mandates(phrase, retenue):
    assert bool(s.passages_report(phrase)) is retenue


def test_body_detection_skips_texts_already_found_by_title():
    record = {**s.parse_article(ARTICLE.encode()), "raw_id": 1}
    reports = {"JORFTEXT000041746313": [record]}
    assert s.reports_dans_le_corps(reports, {"JORFTEXT000041746313"}, {}) == []
    (draft,) = s.reports_dans_le_corps(reports, set(), s.load_rattachements())
    assert draft.attributes["detection"] == "corps_du_texte"
    assert draft.attributes["scrutins_reportes"] == ["municipales-2020-t2", "consulaires-2020"]


def test_body_reports_are_kept_when_no_other_record_exists(monkeypatch):
    record = {**s.parse_article(ARTICLE.encode()), "raw_id": 1}
    monkeypatch.setattr(s, "read_all", lambda *_: ({}, {}, {"JORFTEXT000041746313": [record]}))
    drafts = s.extract(None, None)
    assert [d.fact_type for d in drafts] == ["report_scrutin"]
