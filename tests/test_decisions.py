"""D7 : tâche horaire (relecture des décisions GitHub, republication si besoin)."""

import fcntl

from ops import decisions


class Lanceur:
    def __init__(self):
        self.cibles = []

    def __call__(self, commande, **kw):
        self.cibles.append(commande[-1])

        class R:
            returncode = 0

        return R()


def test_verrou_pris_saute_le_tour(tmp_path, capsys):
    verrou = tmp_path / "lock"
    with verrou.open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lancer = Lanceur()
        assert decisions.executer(lancer=lancer, collecte=lambda: 3, lock_path=verrou) == 0
    assert lancer.cibles == []
    assert "tour sauté" in capsys.readouterr().out


def lancer_avec(tmp_path, empreinte, lancer=None):
    lancer = lancer or Lanceur()
    code = decisions.executer(
        lancer=lancer,
        collecte=lambda: 0,
        lock_path=tmp_path / "l",
        empreinte=lambda: empreinte,
        etat_path=tmp_path / "publiee",
    )
    return code, lancer


def test_decisions_inchangees_pas_de_rebuild(tmp_path):
    (tmp_path / "publiee").write_text("abc")
    code, lancer = lancer_avec(tmp_path, "abc")
    assert code == 0 and lancer.cibles == ["collect-rss"]


def test_decision_nouvelle_republie_et_note(tmp_path):
    (tmp_path / "publiee").write_text("abc")
    code, lancer = lancer_avec(tmp_path, "def")
    assert lancer.cibles == ["collect-rss", "rebuild", "prototype-data", "deployer"]
    assert (tmp_path / "publiee").read_text() == "def"


def test_republication_ratee_retentee_l_heure_suivante(tmp_path):
    """Collecte réussie mais reconstruction en échec (ou erreur d'API après quelques
    instantanés) : rien n'est noté, le tour suivant republie."""

    def en_panne(commande, **kw):
        class R:
            returncode = 0 if commande[-1] == "collect-rss" else 2

        return R()

    (tmp_path / "publiee").write_text("abc")
    code, _ = lancer_avec(tmp_path, "def", en_panne)
    assert code == 1
    assert (tmp_path / "publiee").read_text() == "abc"
    _, lancer = lancer_avec(tmp_path, "def")
    assert lancer.cibles == ["collect-rss", "rebuild", "prototype-data", "deployer"]


def test_echec_d_une_etape_code_1(tmp_path):
    def lancer(commande, **kw):
        class R:
            returncode = 2 if commande[-1] == "rebuild" else 0

        return R()

    assert (
        decisions.executer(
            lancer=lancer,
            collecte=lambda: 1,
            lock_path=tmp_path / "l",
            empreinte=lambda: "x",
            etat_path=tmp_path / "p",
        )
        == 1
    )


def test_sans_config_github_rien(tmp_path):
    lancer = Lanceur()
    code = decisions.executer(
        lancer=lancer,
        collecte=lambda: None,
        lock_path=tmp_path / "l",
        empreinte=lambda: "neuve",
        etat_path=tmp_path / "p",
    )
    assert code == 0 and lancer.cibles == ["collect-rss"]


def test_flux_rss_en_panne_n_empeche_pas_la_suite(tmp_path):
    def lancer(commande, **kw):
        lancer.cibles.append(commande[-1])

        class R:
            returncode = 2 if commande[-1] == "collect-rss" else 0

        return R()

    lancer.cibles = []
    code = decisions.executer(
        lancer=lancer,
        collecte=lambda: 1,
        lock_path=tmp_path / "l",
        empreinte=lambda: "x",
        etat_path=tmp_path / "p",
    )
    assert code == 0 and lancer.cibles[-1] == "deployer"
