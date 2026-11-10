"""D7 : faits validés sur GitHub et constats du Défenseur des droits."""

import datetime as dt
import json

import pytest

from extract import d7
from storage.archive import store
from storage.db import connect, init_db

VALIDATEURS = {"MZA-code"}


def inst(numero=1, etiquettes=("d7", "cat:force"), poses=None, titre=None, corps=None):
    return {
        "numero": numero,
        "etat": "open",
        "titre": titre or f"[D7] Force · Lyon, Rhône-Alpes, France · 2026-11-0{numero}",
        "corps": corps if corps is not None else f"liens…\n<!-- d7:gdelt:{1000 + numero} -->",
        "maj": "2026-11-10T10:00:00Z",
        "etiquettes": sorted(etiquettes),
        "historique": [],
        "poses": poses or {},
    }


def pose(par="MZA-code", le="2026-11-10T10:00:00Z"):
    return {"par": par, "le": le}


def test_en_attente():
    assert d7.decision(inst(), VALIDATEURS) == ("en_attente", "force", None)


def test_valide_par_validateur():
    i = inst(etiquettes=("d7", "cat:force", "validé"), poses={"validé": pose()})
    assert d7.decision(i, VALIDATEURS) == ("valide", "force", None)


def test_valide_par_tiers_a_corriger():
    i = inst(etiquettes=("d7", "cat:force", "validé"), poses={"validé": pose("intrus")})
    statut, _, motif = d7.decision(i, VALIDATEURS)
    assert statut == "a_corriger"
    assert motif == "étiquette posée par un compte non validateur"


def test_valide_et_rejete_a_corriger():
    i = inst(
        etiquettes=("d7", "cat:force", "validé", "rejeté"),
        poses={"validé": pose(), "rejeté": pose()},
    )
    assert d7.decision(i, VALIDATEURS)[0] == "a_corriger"


def test_valide_sans_categorie_a_corriger():
    i = inst(etiquettes=("d7", "validé", "cat:force", "cat:reunion"), poses={"validé": pose()})
    assert d7.decision(i, VALIDATEURS) == (
        "a_corriger",
        None,
        "aucune ou plusieurs étiquettes cat:",
    )


def test_categorie_inconnue_a_corriger():
    i = inst(etiquettes=("d7", "validé", "cat:autre"), poses={"validé": pose()})
    assert d7.decision(i, VALIDATEURS)[0] == "a_corriger"


def test_doublon_et_rejet():
    assert (
        d7.decision(
            inst(etiquettes=("d7", "cat:force", "doublon"), poses={"doublon": pose()}), VALIDATEURS
        )[0]
        == "doublon"
    )
    assert (
        d7.decision(
            inst(etiquettes=("d7", "cat:force", "rejeté"), poses={"rejeté": pose()}), VALIDATEURS
        )[0]
        == "rejete"
    )


def test_evenement_de():
    assert d7.evenement_de("x <!-- d7:gdelt:123456 --> y") == "123456"
    assert d7.evenement_de("signalement manuel") is None
    assert (
        d7.evenement_de("<!-- d7:gdelt:rss-67482-force-20261107 -->") == "rss-67482-force-20261107"
    )


def test_lire_titre():
    assert d7.lire_titre(inst()["titre"]) == ("Lyon, Rhône-Alpes, France", "2026-11-01")


def test_issue_manuelle_date_et_lieu():
    corps = "Date : 2025-03-14\nLieu : Brest (29)\nLiens :\n- https://a.fr\n"
    assert d7.lire_corps_manuel(corps) == ("Brest (29)", "2025-03-14")


@pytest.mark.parametrize(
    ("resume", "attendu"),
    [
        ("La Commission constate un double manquement de la part des fonctionnaires.", True),
        ("Le Défenseur conclut à un manquement à la déontologie.", True),
        ("La Commission ne retient pas de manquement à la déontologie.", False),
        ("Il n'y a pas eu de manquement individuel à la déontologie.", False),
        ("Aucun manquement n'a été relevé.", False),
        ("Absence de manquement. La Commission recommande une formation.", False),
        ("Recommandation générale sur le maintien de l'ordre.", False),
        ("Pas de manquement de l'agent A. Le gardien B a commis un manquement.", True),
        # Tournures réelles de l'archive du Défenseur des droits (revue du 2026-11-10)
        ("Le Défenseur des droits n'a pas relevé de manquement à la déontologie.", False),
        ("Il n'a pu relever un quelconque manquement à la déontologie.", False),
        ("Le Défenseur n'est donc pas en mesure de relever un manquement.", False),
        ("Le Défenseur n'a pas constaté de manquement.", False),
        ("Le Défenseur ne peut retenir de manquement à l'encontre des agents.", False),
    ],
)
def test_constat_de_manquement(resume, attendu):
    assert d7.constate_manquement(resume) is attendu


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def archiver_inst(conn, raw, i):
    store(
        conn,
        raw,
        source_id="github_d7",
        external_id=str(i["numero"]),
        url="u",
        fetched_at="2026-11-10T11:00:00Z",
        chunks=[json.dumps(i).encode()],
        suffix=".json",
    )


def test_extract_presse(conn, tmp_path):
    raw = tmp_path / "raw"
    archiver_inst(conn, raw, inst(1, ("d7", "cat:force", "validé"), {"validé": pose()}))
    archiver_inst(conn, raw, inst(2, ("d7", "cat:force", "validé"), {"validé": pose("intrus")}))
    archiver_inst(conn, raw, inst(3, ("d7", "cat:force")))
    (fait,) = [f for f in d7.extract(conn, raw) if f.fact_type == "fait_presse_valide"]
    assert fait.occurred_on == "2026-11-01"
    assert fait.indicator_id == "D7.libertes_en_pratique"
    assert set(fait.attributes) == {"categorie", "lieu", "issue", "valide_par", "valide_le"}
    assert fait.attributes["issue"] == 1 and fait.attributes["categorie"] == "force"


def test_extract_constats(conn, tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    fiches = {
        "1": {
            "titre": "D1",
            "type": "Décisions",
            "date": "05/03/2025",
            "numero": "2025-1",
            "resume": "Le Défenseur constate un manquement.",
            "mots_cles": ["Usage de la force"],
            "suites": [],
            "pdf": None,
        },
        "2": {
            "titre": "D2",
            "type": "Décisions",
            "date": "2025",
            "numero": None,
            "resume": "La Commission ne retient pas de manquement.",
            "mots_cles": [],
            "suites": [],
            "pdf": None,
        },
        "3": {
            "titre": "J",
            "type": "Jurisprudences",
            "date": "05/03/2025",
            "numero": None,
            "resume": "manquement",
            "mots_cles": [],
            "suites": [],
            "pdf": None,
        },
        "4": {
            "titre": "D4",
            "type": "Décisions",
            "date": "2024",
            "numero": "2024-9",
            "resume": "Un manquement est constaté.",
            "mots_cles": ["Manifestation"],
            "suites": [],
            "pdf": None,
        },
    }
    for k in fiches:
        store(
            conn,
            raw,
            source_id="ddd_juridique",
            external_id=k,
            url="u",
            fetched_at="2026-11-10T11:00:00Z",
            chunks=[k.encode()],
            suffix=".html",
        )
    monkeypatch.setattr(d7, "lire_fiche", lambda page: fiches[page.strip()])
    constats = sorted(
        (f for f in d7.extract(conn, raw) if f.fact_type == "constat_institutionnel"),
        key=lambda f: f.occurred_on,
    )
    assert [(f.occurred_on, f.attributes["categorie"]) for f in constats] == [
        ("2024-12-31", "reunion"),
        ("2025-03-05", "force"),
    ]
    assert constats[1].attributes == {
        "categorie": "force",
        "date_acte": None,
        "numero": "2025-1",
        "precision_date": "jour",
    }


def test_etat_reprise():
    jour = dt.date(2026, 11, 10)
    cands = [("10", "2026-10-01"), ("11", "2026-11-09"), ("12", "2025-01-01")]
    statuts = {"10": "valide", "12": "rejete"}  # 11 récent, en attente : n'empêche pas
    etat = d7.etat_reprise(cands, statuts, jour)
    assert etat == {
        "reprise_complete": True,
        "reprise_relue_jusqu_au": "2025-01-01",
        "candidats_sans_decision": 0,
    }
    statuts.pop("12")
    etat = d7.etat_reprise(cands, statuts, jour)
    assert etat["reprise_complete"] is False
    assert etat["reprise_relue_jusqu_au"] == "2026-10-01"
    assert etat["candidats_sans_decision"] == 1


def test_categorie_changee_par_un_tiers_a_corriger():
    i = inst(
        etiquettes=("d7", "cat:reunion", "validé"),
        poses={"validé": pose(), "cat:reunion": pose("intrus")},
    )
    assert d7.decision(i, VALIDATEURS) == (
        "a_corriger",
        "reunion",
        "étiquette cat: posée par un compte non autorisé",
    )


def test_categorie_posee_par_le_compte_serveur():
    i = inst(
        etiquettes=("d7", "cat:force", "validé"),
        poses={"validé": pose(), "cat:force": pose("robot-barometre")},
    )
    assert d7.decision(i, VALIDATEURS, serveur={"robot-barometre"})[0] == "valide"


def test_marqueur_efface_date_lue_dans_le_titre():
    i = inst(
        etiquettes=("d7", "cat:force", "validé"), poses={"validé": pose()}, corps="corps édité"
    )
    assert d7.lieu_et_date(i) == ("Lyon, Rhône-Alpes, France", "2026-11-01")


def test_evenement_lu_dans_la_ligne_visible():
    assert d7.evenement_de("Événement GDELT : 98765\n(marqueur effacé)") == "98765"


def test_empreinte_ne_depend_que_des_decisions(conn, tmp_path):
    raw = tmp_path / "raw"
    archiver_inst(conn, raw, inst(1, ("d7", "cat:force", "validé"), {"validé": pose()}))
    e1 = d7.empreinte_decisions(conn, raw)
    autre = inst(1, ("d7", "cat:force", "validé"), {"validé": pose()})
    autre["maj"] = "2026-11-10T18:00:00Z"  # simple commentaire : même décision
    store(
        conn,
        raw,
        source_id="github_d7",
        external_id="1",
        url="u",
        fetched_at="2026-11-10T19:00:00Z",
        chunks=[json.dumps(autre).encode()],
        suffix=".json",
    )
    assert d7.empreinte_decisions(conn, raw) == e1
    archiver_inst(conn, raw, inst(2, ("d7", "cat:force", "rejeté"), {"rejeté": pose()}))
    assert d7.empreinte_decisions(conn, raw) != e1


def test_issue_modifiee_apres_validation_a_corriger(conn, tmp_path):
    raw = tmp_path / "raw"
    valide = inst(1, ("d7", "cat:force", "validé"), {"validé": pose()})
    archiver_inst(conn, raw, valide)
    modifie = {
        **valide,
        "titre": "[D7] Force · Ailleurs · 2025-01-01",
        "maj": "2026-11-11T09:00:00Z",
    }
    store(
        conn,
        raw,
        source_id="github_d7",
        external_id="1",
        url="u",
        fetched_at="2026-11-11T10:00:00Z",
        chunks=[json.dumps(modifie).encode()],
        suffix=".json",
    )
    assert [f for f in d7.extract(conn, raw) if f.fact_type == "fait_presse_valide"] == []
    etat = d7.etat_d7(conn, raw, __import__("datetime").date(2026, 11, 11))
    assert etat["a_corriger"] == [(1, "issue modifiée après la validation : revalider")]


def test_revalidation_apres_modification(conn, tmp_path):
    raw = tmp_path / "raw"
    archiver_inst(conn, raw, inst(1, ("d7", "cat:force", "validé"), {"validé": pose()}))
    revalide = inst(1, ("d7", "cat:force", "validé"), {"validé": pose(le="2026-11-11T11:00:00Z")})
    revalide["titre"] = "[D7] Force · Lyon, Rhône-Alpes, France · 2026-11-02"
    store(
        conn,
        raw,
        source_id="github_d7",
        external_id="1",
        url="u",
        fetched_at="2026-11-11T12:00:00Z",
        chunks=[json.dumps(revalide).encode()],
        suffix=".json",
    )
    (fait,) = [f for f in d7.extract(conn, raw) if f.fact_type == "fait_presse_valide"]
    assert fait.occurred_on == "2026-11-02"
