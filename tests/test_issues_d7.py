"""D7 : ouverture des issues candidates sur GitHub."""

import datetime as dt

import pytest

from collectors.github_d7 import ErreurApi
from extract import d7
from extract.d7_candidats import Article, Candidat, categories_d7
from ops import issues_d7 as iss

CATS = categories_d7()
JOUR = dt.date(2026, 11, 10)


def cand(evt, jour, cat="interpellations"):
    articles = (
        Article(
            "https://www.lefigaro.fr/a", "lefigaro.fr", "groupe_figaro_dassault", "20261105120000"
        ),
        Article("https://www.lemonde.fr/b", "lemonde.fr", "groupe_le_monde", "20261105130000"),
    )
    return Candidat(
        evt,
        jour,
        cat,
        "Strasbourg, Alsace, France",
        articles,
        ("groupe_figaro_dassault", "groupe_le_monde"),
    )


def test_titre_lisible_par_l_extraction():
    titre = iss.titre_issue(cand("1", "2026-11-05"), CATS)
    assert titre == "[D7] Interpellations collectives · Strasbourg, Alsace, France · 2026-11-05"
    assert d7.lire_titre(titre) == ("Strasbourg, Alsace, France", "2026-11-05")


def test_corps():
    corps = iss.corps_issue(cand("42", "2026-11-05"), CATS["interpellations"])
    assert d7.evenement_de(corps) == "42"
    assert "Identifiant D7 : 42" in corps
    assert "lefigaro.fr (groupe_figaro_dassault)" in corps
    assert "https://www.lemonde.fr/b" in corps
    assert CATS["interpellations"]["compte"][0] in corps
    assert CATS["interpellations"]["ne_compte_pas"][0] in corps
    assert "`validé`" in corps and "`rejeté`" in corps and "`doublon`" in corps


def test_quota_reprise():
    anciens = [cand(str(i), f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}") for i in range(50)]
    recents = [cand(f"r{i}", f"2026-11-0{i + 7}") for i in range(3)]
    choisis = iss.a_ouvrir(anciens + recents, set(), JOUR)
    assert len(choisis) == 23
    assert [c.evenement_id for c in choisis[:3]] == ["r2", "r1", "r0"]
    jours = [c.jour for c in choisis[3:]]
    assert jours == sorted(jours, reverse=True)


def test_deja_ouverts_exclus():
    assert iss.a_ouvrir([cand("1", "2026-11-09")], {"1"}, JOUR) == []


class FausseApi:
    def __init__(self, issues=(), panne_apres=None):
        self.issues = list(issues)
        self.labels = []
        self.panne_apres = panne_apres
        self.creees = 0

    def lister(self, chemin, params):
        return list(self.labels) if chemin == "labels" else list(self.issues)

    def creer(self, chemin, corps):
        if chemin == "labels":
            self.labels.append({"name": corps["name"]})
            return corps
        if self.panne_apres is not None and self.creees >= self.panne_apres:
            raise ErreurApi("panne")
        self.creees += 1
        issue = {"number": len(self.issues) + 1, "body": corps["body"], "labels": corps["labels"]}
        self.issues.append(issue)
        return issue


def test_etiquettes_creees_une_fois():
    api = FausseApi()
    iss.assurer_etiquettes(api, CATS)
    iss.assurer_etiquettes(api, CATS)
    noms = [x["name"] for x in api.labels]
    assert len(noms) == len(set(noms))
    assert {"d7", "en-attente", "validé", "rejeté", "doublon", "cat:force"} <= set(noms)


def test_pas_de_doublon_si_issue_deja_ouverte():
    api = FausseApi(issues=[{"number": 1, "body": "<!-- d7:gdelt:1 -->", "labels": []}])
    assert iss.publier_candidats(api, [cand("1", "2026-11-09")], set(), JOUR, CATS) == 0


def test_relance_apres_plantage():
    cands = [cand(str(i), "2026-11-09") for i in range(4)]
    api = FausseApi(panne_apres=2)
    with pytest.raises(ErreurApi):
        iss.publier_candidats(api, cands, set(), JOUR, CATS)
    api.panne_apres = None
    assert iss.publier_candidats(api, cands, set(), JOUR, CATS) == 2
    marqueurs = [d7.evenement_de(i["body"]) for i in api.issues]
    assert sorted(marqueurs) == ["0", "1", "2", "3"]


def test_etiquettes_de_l_issue():
    api = FausseApi()
    iss.publier_candidats(api, [cand("1", "2026-11-09", "force")], set(), JOUR, CATS)
    assert api.issues[0]["labels"] == ["d7", "en-attente", "cat:force"]


def test_titres_tous_releves():
    c = cand("1", "2026-11-09")
    assert iss.titres_releves(
        c, {"https://www.lefigaro.fr/a": "X", "https://www.lemonde.fr/b": None}
    )
    assert not iss.titres_releves(c, {"https://www.lefigaro.fr/a": "X"})


def test_candidat_rss_publiable_sans_titres_releves():
    c = cand("rss-67482-force-20261107", "2026-11-07")
    assert iss.titres_releves(c, {})
