import pytest

from extract import mobilisations
from storage.archive import store
from storage.db import connect, init_db

HEAD = ";".join(
    [
        "date",
        "mouvement",
        "journee",
        "perimetre",
        "compteur",
        "manifestants",
        "compte_par",
        "source_site",
        "source_titre",
        "source_url",
        "controle",
        "releve_via",
        "a_verifier",
        "note",
    ]
)
OK = "chiffre retrouvé dans la source le 2026-11-05"
KO = "non vérifié : source citée inaccessible (HTTP 403)"


def seed(*lines):
    return ("\n".join([HEAD, *lines]) + "\n").encode()


def row(date, journee, compteur, n, controle, site="lnc.nc"):
    return ";".join(
        [
            date,
            "retraites 2023",
            journee,
            "France entière",
            compteur,
            n,
            "CGT" if compteur == "organisateurs" else "ministère de l'Intérieur",
            site,
            "",
            "https://a",
            controle,
            "w",
            "oui",
            "",
        ]
    )


ROWS = [
    row("2023-01-19", "1", "ministere_interieur", "1120000", OK),
    row("2023-01-19", "1", "organisateurs", "2000000", OK),
    row("2023-02-07", "3", "ministere_interieur", "757000", KO, site="Le Point"),
]


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def put(conn, raw, data):
    return store(
        conn,
        raw,
        source_id="seed_manuel",
        external_id=mobilisations.SEED,
        url="data/seed",
        fetched_at="2026-11-05T00:00:00Z",
        chunks=[data],
        suffix=".csv",
    )


def test_one_fact_per_day_with_both_counts(conn, tmp_path):
    doc = put(conn, tmp_path / "raw", seed(*ROWS))
    facts = mobilisations.extract(conn, tmp_path / "raw")
    assert [f.occurred_on for f in facts] == ["2023-01-19", "2023-02-07"]
    a = facts[0].attributes
    assert a["ministere_interieur"]["manifestants"] == 1120000
    assert a["organisateurs"]["manifestants"] == 2000000
    assert a["ministere_interieur"]["verifie_dans_source"] is True
    b = facts[1].attributes
    assert b["organisateurs"] is None and b["ministere_interieur"]["verifie_dans_source"] is False
    assert facts[0].raw_document_ids == (doc.id,)


def test_duplicate_or_unknown_counter_is_rejected(conn, tmp_path):
    put(conn, tmp_path / "raw", seed(ROWS[0], ROWS[0]))
    with pytest.raises(ValueError, match="double"):
        mobilisations.extract(conn, tmp_path / "raw")


def test_project_seed_is_consistent():
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "seed" / mobilisations.SEED
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter=";"))
    assert rows and all(r["source_url"].startswith("http") for r in rows)
    for r in rows:
        assert r["compteur"] in mobilisations.COMPTEURS and int(r["manifestants"]) > 0
