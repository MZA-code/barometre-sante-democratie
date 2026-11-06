import datetime as dt
import json
import sqlite3

import pytest

from ops import nouveautes as n

D = dt.date(2026, 11, 6)


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE facts (id INTEGER PRIMARY KEY, indicator_id, fact_type, occurred_on,"
        " title, official_ref, attributes)"
    )
    return conn


def add(conn, fact_type, ref, day, attrs=None, indicator="X"):
    conn.execute(
        "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, official_ref,"
        " attributes) VALUES (?, ?, ?, ?, ?, ?)",
        (indicator, fact_type, day, f"Texte {ref}", ref, json.dumps(attrs or {})),
    )


def paths(tmp_path):
    return {
        "known_path": tmp_path / "connus.json",
        "summary_path": tmp_path / "nouveautes.md",
        "log_dir": tmp_path / "logs",
    }


def test_first_run_only_records_known_facts(conn, tmp_path):
    add(conn, "engagement_49_3", "A", "2026-10-01")
    sent = []
    result = n.run(conn, D, send=lambda *m: sent.append(m), **paths(tmp_path))
    assert result["premiere_execution"] and result["nouveaux"] == 0
    assert sent == []
    assert "Première exécution" in (tmp_path / "nouveautes.md").read_text()


def test_new_notable_facts_are_listed_and_notified(conn, tmp_path):
    add(conn, "loi_promulguee", "L1", "2026-10-01")
    n.run(conn, D, send=None, **paths(tmp_path))
    add(conn, "engagement_49_3", "A", "2026-11-05", {"url": "https://example.org/a"})
    add(conn, "loi_promulguee", "L2", "2026-11-05")
    add(conn, "decision_dc_loi", "DC1", "2026-11-04", {"au_fond": True, "censure": False})
    sent = []
    result = n.run(conn, D, send=lambda *m: sent.append(m), **paths(tmp_path))
    assert (result["nouveaux"], result["marquants"], result["disparus"]) == (3, 1, 0)
    text = (tmp_path / "nouveautes.md").read_text()
    assert "## Engagements de responsabilité (49.3) (1)" in text
    assert "[Texte A](https://example.org/a)" in text
    assert "- loi_promulguee : 1" in text and "- decision_dc_loi : 1" in text
    ((title, body),) = sent
    assert "06/11/2026" in title and "Engagements de responsabilité (49.3) : 1" in body
    assert (tmp_path / "logs" / "nouveautes-2026-11-06.md").exists()


def test_nothing_new_sends_nothing_and_reports_removed_facts(conn, tmp_path):
    add(conn, "loi_promulguee", "L1", "2026-10-01")
    add(conn, "loi_promulguee", "L2", "2026-10-02")
    n.run(conn, D, send=None, **paths(tmp_path))
    conn.execute("DELETE FROM facts WHERE official_ref = 'L2'")
    sent = []
    result = n.run(conn, D, send=lambda *m: sent.append(m), **paths(tmp_path))
    assert (result["nouveaux"], result["disparus"]) == (0, 1)
    assert sent == []
    assert "## Faits disparus" in (tmp_path / "nouveautes.md").read_text()


@pytest.mark.parametrize(
    ("fact_type", "attrs", "attendu"),
    [
        ("decret_apres_avis_cnil", {"malgre_reserves": True, "confiance": "forte"}, True),
        ("decret_apres_avis_cnil", {"malgre_reserves": True, "confiance": "faible"}, False),
        ("texte_electoral", {"moins_d_un_an": False}, False),
        ("decision_dc_loi", {"au_fond": True, "censure": True}, True),
        ("ordonnance_publiee", {}, False),
    ],
)
def test_notable_rules(fact_type, attrs, attendu):
    assert n.marquant({"fact_type": fact_type, "attributes": attrs}) is attendu


def test_long_lists_are_truncated(conn, tmp_path):
    n.run(conn, D, send=None, **paths(tmp_path))
    for i in range(n.MAX_LIGNES + 3):
        add(conn, "decision_interdiction_manifestation", f"N{i}", "2026-10-15")
    n.run(conn, D, send=None, **paths(tmp_path))
    assert "… et 3 autre(s)" in (tmp_path / "nouveautes.md").read_text()


def test_failed_collections_are_stated_before_anything_else(conn, tmp_path):
    add(conn, "loi_promulguee", "L1", "2026-10-01")
    n.run(conn, D, send=None, **paths(tmp_path))
    result = n.run(conn, D, send=None, echecs=["collect-an", "collect-jorf"], **paths(tmp_path))
    text = (tmp_path / "nouveautes.md").read_text()
    assert result["sources_en_echec"] == ["collect-an", "collect-jorf"]
    assert text.index("Collecte incomplète") < text.index("Aucun fait nouveau")
    assert "collect-an, collect-jorf" in text
    assert "Aucun fait nouveau depuis la dernière exécution." not in text


def test_complete_collection_has_no_warning(conn, tmp_path):
    n.run(conn, D, send=None, **paths(tmp_path))
    result = n.run(conn, D, send=None, echecs=[], **paths(tmp_path))
    assert result["sources_en_echec"] == []
    assert "Collecte incomplète" not in (tmp_path / "nouveautes.md").read_text()


def test_facts_sharing_a_reference_and_date_are_kept_apart(conn, tmp_path):
    # un même décret ouvre deux périodes d'état d'urgence (La Réunion, Martinique)
    conn.execute(
        "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, official_ref, attributes)"
        " VALUES ('X', 'periode_regime_exception', '2021-07-14', 'La Réunion', 'J1', '{}'),"
        " ('X', 'periode_regime_exception', '2021-07-14', 'Martinique', 'J1', '{}')"
    )
    assert len(n.current_facts(conn)) == 2
    n.run(conn, D, send=None, **paths(tmp_path))
    conn.execute(
        "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, official_ref, attributes)"
        " VALUES ('X', 'periode_regime_exception', '2021-07-14', 'Guadeloupe', 'J1', '{}')"
    )
    result = n.run(conn, D, send=None, **paths(tmp_path))
    assert (result["nouveaux"], result["disparus"]) == (1, 0)


def test_identical_facts_are_all_counted(conn, tmp_path):
    for _ in range(2):
        conn.execute(
            "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, official_ref,"
            " attributes) VALUES ('X', 'mesure_journaliste', '2025-01-01', 'Garde à vue', NULL,"
            " '{}')"
        )
    n.run(conn, D, send=None, **paths(tmp_path))
    conn.execute(
        "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, official_ref, attributes)"
        " VALUES ('X', 'mesure_journaliste', '2025-01-01', 'Garde à vue', NULL, '{}')"
    )
    assert n.run(conn, D, send=None, **paths(tmp_path))["nouveaux"] == 1
