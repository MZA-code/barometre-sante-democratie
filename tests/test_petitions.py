"""Pétitions citoyennes de l'Assemblée nationale : lecture, collecte, faits."""

import io
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from collectors import petitions as col
from extract import petitions as ext
from storage.archive import store
from storage.db import connect, init_db

FIX = Path(__file__).parent / "fixtures"


def page(numero):
    return (FIX / f"petition_i{numero}.html").read_bytes()


def test_page_classee():
    p = col.lire_page(page(5158))
    assert p["titre"] == "Non à la loi Yadan"
    assert p["signatures"] == 707957
    assert p["statut"] == "classee"
    assert p["libelle_statut"] == "Classée par la commission"
    assert p["date_decision"] == "2026-04-15"
    assert p["commission"].startswith("Commission des lois")


def test_page_examinee():
    p = col.lire_page(page(3014))
    assert p["titre"].startswith("Non à la Loi Duplomb")
    assert p["signatures"] > 2_000_000
    assert p["statut"] == "examinee"
    assert p["date_decision"] is None


def test_aucun_nom_d_auteur():
    p = col.lire_page(page(5158))
    assert set(p) == {
        "titre",
        "signatures",
        "statut",
        "libelle_statut",
        "date_decision",
        "commission",
        "date_publication",
    }
    assert p["date_publication"] == "2026-02-18"


def test_identifiants_a_suivre():
    lignes = [
        {"identifiant": "1", "nb_votes": "60000.0"},
        {"identifiant": "2", "nb_votes": "49999"},
        {"identifiant": "3", "nb_votes": ""},
    ]
    assert col.identifiants_a_suivre(lignes, suivies=[7, 1]) == [1, 7]


class FauxWeb:
    def __init__(self, pages):
        self.pages, self.appels = pages, []

    @contextmanager
    def __call__(self, url):
        self.appels.append(url)
        yield io.BytesIO(self.pages[url])


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_collecte_une_version_par_changement(conn, tmp_path):
    raw = tmp_path / "raw"
    web = FauxWeb({col.url_petition(5158): page(5158)})
    assert col.collect_pages(conn, raw, [5158], opener=web, sleep=lambda s: None) == 1
    assert col.collect_pages(conn, raw, [5158], opener=web, sleep=lambda s: None) == 0
    (path,) = conn.execute(
        "SELECT path FROM raw_documents WHERE source_id = 'petitions_an'"
    ).fetchone()
    data = json.loads((raw / path).read_text())
    assert data["identifiant"] == 5158 and data["signatures"] == 707957


def archiver(conn, raw, numero, quand, **champs):
    data = {
        "identifiant": numero,
        "titre": f"Pétition {numero}",
        "signatures": 0,
        "statut": "ouverte",
        "libelle_statut": "",
        "date_decision": None,
        "commission": "Commission X",
        "url": col.url_petition(numero),
        **champs,
    }
    store(
        conn,
        raw,
        source_id="petitions_an",
        external_id=f"i-{numero}",
        url="u",
        fetched_at=quand,
        chunks=[json.dumps(data, sort_keys=True).encode()],
        suffix=".json",
    )


def test_faits_petitions_500k(conn, tmp_path):
    raw = tmp_path / "raw"
    archiver(conn, raw, 1, "2026-03-01T06:30:00Z", signatures=400_000)
    archiver(
        conn,
        raw,
        1,
        "2026-03-05T06:30:00Z",
        signatures=707_957,
        statut="classee",
        date_decision="2026-04-15",
    )
    # déjà au-dessus du seuil à la première collecte : date de publication de la pétition
    archiver(
        conn,
        raw,
        2,
        "2025-07-20T06:30:00Z",
        signatures=1_000_000,
        statut="ouverte",
        date_publication="2025-07-10",
    )
    archiver(conn, raw, 2, "2025-08-01T06:30:00Z", signatures=2_131_368, statut="examinee")
    archiver(conn, raw, 3, "2026-11-01T06:30:00Z", signatures=480_000, statut="ouverte")
    archiver(conn, raw, 3, "2026-11-05T06:30:00Z", signatures=740_000, statut="ouverte")
    archiver(conn, raw, 4, "2026-11-05T06:30:00Z", signatures=446_160, statut="ouverte")
    faits = {f.attributes["identifiant"]: f for f in ext.extract(conn, raw)}
    assert set(faits) == {1, 2, 3}
    assert (faits[1].fact_type, faits[1].occurred_on) == ("petition_500k_classee", "2026-04-15")
    assert (faits[2].fact_type, faits[2].occurred_on) == ("petition_500k_examinee", "2025-07-10")
    assert (faits[3].fact_type, faits[3].occurred_on) == ("petition_500k_en_attente", "2026-11-05")
    assert faits[3].attributes["signatures"] == 740_000
    assert set(faits[1].attributes) == {
        "identifiant",
        "titre",
        "signatures",
        "statut",
        "date_decision",
        "date_seuil",
        "commission",
        "url",
    }


def test_indicateur_dans_la_grille_et_comptage(conn, tmp_path):
    import datetime as dt

    from extract.common import FactDraft, write_facts
    from scoring import metrics
    from scoring.grid import load_grid

    ind = load_grid().indicators["D2.petitions_classees"]
    assert ind.scored_metric == "nb_petitions_500k_classees"
    assert str(ind.history_start) == "2020-10-01"
    for source in metrics.COVERAGE_SOURCES:
        store(
            conn,
            tmp_path / "raw",
            source_id=source,
            external_id="x",
            url="u",
            fetched_at="2026-11-10T08:00:00Z",
            chunks=[source.encode()],
        )

    def fait(t, jour):
        return FactDraft("D2.petitions_classees", t, jour, t, None, "test", (1,), {})

    write_facts(
        conn,
        [
            fait("petition_500k_classee", "2026-04-15"),
            fait("petition_500k_examinee", "2025-07-10"),
            fait("petition_500k_en_attente", "2026-11-05"),
        ],
    )
    rows = metrics.compute(
        conn, load_grid(), [{"numero": 17, "debut": dt.date(2024, 7, 18), "fin": None}]
    )
    v = {
        r[4]: r[5]
        for r in rows
        if r[0] == "D2.petitions_classees" and r[1] == "2026-11-09" and r[2] == "glissante_365j"
    }
    assert v == {"nb_petitions_500k": 2.0, "nb_petitions_500k_classees": 1.0}
