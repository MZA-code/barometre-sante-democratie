"""D2.5 : questions écrites sans réponse dans le délai ; D3.3 : règles de l'assurance chômage."""

import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import pytest

from collectors import an_questions as col
from extract import questions_ecrites as qe
from extract import regles_chomage as rc
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
SEED_CHOMAGE = Path(__file__).resolve().parents[1] / "data" / "seed" / rc.SEED


def question(uid="QANR5L17QE1", publiee="2025-01-14", reponse=None, cloture=None, **kw):
    q = {
        "uid": uid,
        "type": "QE",
        "identifiant": {"numero": uid.split("QE")[-1], "legislature": "17"},
        "minInt": {"abrege": "Intérieur"},
        "textesQuestion": {"texteQuestion": {"infoJO": {"dateJO": publiee}, "texte": "M. X…"}},
        "textesReponse": {"texteReponse": {"infoJO": {"dateJO": reponse}}} if reponse else None,
        "cloture": cloture,
    }
    q.update(kw)
    return q


def test_echeance_deux_mois():
    assert qe.plus_deux_mois(D(2025, 1, 14)) == D(2025, 3, 14)
    assert qe.plus_deux_mois(D(2024, 12, 31)) == D(2025, 2, 28)  # fin de mois ramenée
    assert qe.jour("12/04/2022") == D(2022, 4, 12)


def test_statut_dans_le_delai_ou_non():
    collecte = D(2026, 11, 17)
    s = qe.statut(question(reponse="2025-03-14"), None, collecte)
    assert s["echeance"] == D(2025, 3, 14) and s["dans_delai"]
    s = qe.statut(question(reponse="2025-03-18"), None, collecte)
    assert not s["dans_delai"] and s["reponse"] == D(2025, 3, 18)
    assert not qe.statut(question(), None, collecte)["dans_delai"]  # jamais répondue


def test_questions_ecartees():
    collecte = D(2026, 11, 17)
    fin_mandat = {"codeCloture": "FM", "dateCloture": "2025-02-01"}
    assert qe.statut(question(cloture=fin_mandat), None, collecte) is None
    assert qe.statut(question(publiee="2026-10-01"), None, collecte) is None  # délai en cours
    assert qe.statut(question(publiee="2024-05-01"), D(2024, 6, 9), collecte) is None  # caduque
    # close par une réponse : comptée
    rep = {"codeCloture": "REP_PUB", "dateCloture": "2025-02-01"}
    assert qe.statut(question(reponse="2025-02-01", cloture=rep), None, collecte)["dans_delai"]


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def zip_questions(questions, un_seul_fichier=False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if un_seul_fichier:  # format de la XIVe législature
            z.writestr("Q.json", json.dumps({"questionsEcrites": {"question": questions}}))
        else:
            for q in questions:
                z.writestr(f"json/{q['uid']}.json", json.dumps({"question": q}))
    return buf.getvalue()


@pytest.mark.parametrize("un_seul_fichier", [False, True])
def test_extraction(conn, tmp_path, un_seul_fichier):
    data = zip_questions(
        [question("QANR5L17QE1", reponse="2025-02-20"), question("QANR5L17QE2")], un_seul_fichier
    )
    store(
        conn,
        tmp_path / "raw",
        source_id=qe.SOURCE_ID,
        external_id="questions_ecrites_L17.json.zip",
        url="u",
        fetched_at="2026-11-17T03:00:00Z",
        chunks=[data],
        suffix=".zip",
    )
    faits = qe.extract(conn, tmp_path / "raw")
    assert [f.fact_type for f in faits] == [
        "question_ecrite_repondue_delai",
        "question_ecrite_sans_reponse_delai",
    ]
    a = faits[0].attributes
    assert a["delai_jours"] == 37 and a["ministere"] == "Intérieur"
    assert a["url"] == "https://questions.assemblee-nationale.fr/q17/17-1QE.htm"
    assert "texte" not in a and "auteur" not in a  # rien sur l'auteur


def test_telechargement_repris_apres_coupure():
    fichier = bytes(range(256)) * 40
    appels = []

    def lecteur(url, debut):
        appels.append(debut)
        return fichier[debut : debut + 3000], len(fichier)  # coupure tous les 3 000 octets

    assert col.telecharger("u", lecteur) == fichier
    assert appels == [0, 3000, 6000, 9000]
    with pytest.raises(OSError, match="incomplet"):
        col.telecharger("u", lambda url, debut: (b"", len(fichier)), max_reprises=3)


def test_grille():
    g = load_grid()
    q = g.indicators["D2.questions_ecrites"]
    assert q.scored_metric == "ratio_questions_sans_reponse_delai"
    assert "ratio_questions_sans_reponse_delai" in q.ratios
    assert g.indicators["D3.regles_chomage_etat"].scored_metric == "jours_regles_chomage_etat"


def test_seed_chomage(conn, tmp_path):
    store(
        conn,
        tmp_path / "raw",
        source_id="seed_manuel",
        external_id=rc.SEED,
        url="data/seed",
        fetched_at="2026-11-17T00:00:00Z",
        chunks=[SEED_CHOMAGE.read_bytes()],
        suffix=".csv",
    )
    faits = rc.extract(conn, tmp_path / "raw")
    assert len(faits) >= 3
    for f in faits:
        assert f.official_ref.startswith("JORFTEXT") and f.attributes["url_fin"]
        assert f.attributes["fin"] >= f.occurred_on
    periodes = [(f.occurred_on, f.attributes["fin"]) for f in faits]
    assert periodes == sorted(periodes)
    assert all(a[1] < b[0] for a, b in zip(periodes, periodes[1:], strict=False))


def test_metriques_d25_d33(conn, tmp_path):
    from extract.common import FactDraft, write_facts
    from scoring import metrics

    for source in metrics.COVERAGE_SOURCES:
        store(conn, tmp_path / "raw", source_id=source, external_id="x", url="u",
              fetched_at="2026-01-01T08:00:00Z", chunks=[source.encode()])  # fmt: skip

    def fait(ind, typ, jour, **a):
        return FactDraft(ind, typ, jour, f"{typ} {jour} {a}", None, "test", (1,), a)

    write_facts(
        conn,
        [
            fait("D2.questions_ecrites", "question_ecrite_repondue_delai", "2025-03-01", n=1),
            fait("D2.questions_ecrites", "question_ecrite_sans_reponse_delai", "2025-03-02", n=2),
            fait("D2.questions_ecrites", "question_ecrite_sans_reponse_delai", "2025-03-03", n=3),
            fait(
                "D3.regles_chomage_etat",
                "periode_regles_chomage_etat",
                "2025-01-01",
                fin="2025-01-10",
            ),  # fmt: skip
        ],
    )
    rows = metrics.compute(
        conn, load_grid(), [{"numero": 17, "debut": dt.date(2024, 7, 18), "fin": None}]
    )
    v = {(r[0], r[4]): r[5] for r in rows if r[1] == "2025-06-30" and r[2] == "glissante_365j"}
    assert v[("D2.questions_ecrites", "ratio_questions_sans_reponse_delai")] == pytest.approx(2 / 3)
    assert v[("D3.regles_chomage_etat", "jours_regles_chomage_etat")] == 10


def test_lecture_en_flux():
    qs = [question(f"QANR5L14QE{i}", reponse="2025-02-01") for i in range(50)]
    texte = json.dumps({"questionsEcrites": {"question": qs}})
    lues = list(qe.questions_en_flux(io.StringIO(texte), bloc=97))  # morceaux minuscules
    assert [q["uid"] for q in lues] == [q["uid"] for q in qs]
