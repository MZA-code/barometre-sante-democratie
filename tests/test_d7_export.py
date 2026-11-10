"""D7 : données exportées pour le site."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "export_data", ROOT / "front/prototype/export_data.py"
)
export_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_data)


def etat(**kw):
    base = {
        "instantanes": 10,
        "reprise_complete": True,
        "reprise_relue_jusqu_au": "2024-07-03",
        "candidats_sans_decision": 0,
        "en_attente": 2,
        "a_corriger": [],
        "validateurs": 1,
    }
    return {**base, **kw}


def test_hors_indice_avant_toute_validation():
    assert export_data.hors_indice_d7(etat(instantanes=0)) == (
        "validation des faits de presse pas encore commencée"
    )


def test_hors_indice_pendant_la_reprise():
    raison = export_data.hors_indice_d7(
        etat(
            reprise_complete=False, candidats_sans_decision=120, reprise_relue_jusqu_au="2025-09-01"
        )
    )
    assert raison == (
        "reprise depuis juillet 2024 en cours de relecture : 120 fait(s) candidat(s) sans "
        "décision (relue jusqu'au 1er septembre 2025)"
    )


def test_dans_l_indice_une_fois_la_reprise_relue():
    assert export_data.hors_indice_d7(etat()) is None


def test_faits_sans_nom():
    lignes = [
        (
            "2025-03-01",
            "fait_presse_valide",
            "github#3",
            json.dumps(
                {
                    "categorie": "force",
                    "lieu": "Lyon",
                    "issue": 3,
                    "valide_par": "MZA-code",
                    "valide_le": "2026-11-10T10:00:00Z",
                }
            ),
        ),
        (
            "2025-04-01",
            "constat_institutionnel",
            "https://juridique.defenseurdesdroits.fr/x",
            json.dumps(
                {
                    "categorie": "reunion",
                    "date_acte": None,
                    "numero": "2025-1",
                    "precision_date": "jour",
                }
            ),
        ),
    ]
    faits = export_data.faits_d7(lignes, "MZA-code/barometre-sante-democratie")
    assert faits[0] == {
        "date": "2025-04-01",
        "voie": "institution",
        "categorie": "reunion",
        "lieu": None,
        "url": "https://juridique.defenseurdesdroits.fr/x",
    }
    assert faits[1] == {
        "date": "2025-03-01",
        "voie": "presse",
        "categorie": "force",
        "lieu": "Lyon",
        "url": "https://github.com/MZA-code/barometre-sante-democratie/issues/3",
    }


def test_hors_indice_tant_que_la_collecte_du_passe_n_est_pas_remontee():
    raison = export_data.hors_indice_d7(
        etat(
            reprise_complete=False,
            candidats_sans_decision=0,
            reprise_relue_jusqu_au=None,
            reprise_collectee_depuis="2026-11-07",
        )
    )
    assert raison == (
        "reprise depuis juillet 2024 en cours de collecte (remontée au 7 novembre 2026)"
    )


def test_export_petitions():
    lignes = [
        (
            "petition_500k_classee",
            json.dumps(
                {
                    "identifiant": 5158,
                    "titre": "Non à la loi Yadan",
                    "signatures": 707957,
                    "statut": "classee",
                    "date_decision": "2026-04-15",
                    "date_seuil": "2026-02-18",
                    "commission": "Commission des lois",
                    "url": "u1",
                }
            ),
        ),
        (
            "petition_500k_examinee",
            json.dumps(
                {
                    "identifiant": 3014,
                    "titre": "Non à la loi Duplomb",
                    "signatures": 2131368,
                    "statut": "examinee",
                    "date_decision": None,
                    "date_seuil": "2025-07-10",
                    "commission": "Commission des affaires économiques",
                    "url": "u2",
                }
            ),
        ),
    ]
    out = export_data.petitions_500k(lignes)
    assert [p["identifiant"] for p in out] == [3014, 5158]  # par signatures décroissantes
    assert out[1] == {
        "identifiant": 5158,
        "titre": "Non à la loi Yadan",
        "signatures": 707957,
        "sort": "classee",
        "date_decision": "2026-04-15",
        "date_seuil": "2026-02-18",
        "commission": "Commission des lois",
        "url": "u1",
    }
