"""D7 : instantanés des issues GitHub de validation."""

import json

import pytest

from collectors import github_d7 as gh
from storage.db import connect, init_db


def issue(
    numero=1, etiquettes=("d7", "en-attente", "cat:force"), etat="open", maj="2026-11-10T10:00:00Z"
):
    return {
        "number": numero,
        "state": etat,
        "title": f"[D7] Force · Lyon · 2026-11-0{numero}",
        "body": f"<!-- d7:gdelt:{numero} -->",
        "updated_at": maj,
        "labels": [{"name": e} for e in etiquettes],
    }


def evt(action, etiquette, par, le):
    return {
        "event": action,
        "label": {"name": etiquette},
        "actor": {"login": par},
        "created_at": le,
    }


class FausseApi:
    def __init__(self, issues, evenements):
        self.issues, self.evenements, self.appels = issues, evenements, []

    def lister(self, chemin, params):
        self.appels.append((chemin, dict(params)))
        if chemin == "issues":
            return list(self.issues)
        return list(self.evenements.get(int(chemin.split("/")[1]), []))


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_instantane_garde_le_dernier_poseur():
    evts = [
        evt("labeled", "validé", "intrus", "2026-11-10T09:00:00Z"),
        evt("unlabeled", "validé", "MZA-code", "2026-11-10T09:30:00Z"),
        evt("labeled", "validé", "MZA-code", "2026-11-10T10:00:00Z"),
        evt("labeled", "rejeté", "MZA-code", "2026-11-10T08:00:00Z"),
        evt("unlabeled", "rejeté", "MZA-code", "2026-11-10T08:10:00Z"),
    ]
    inst = gh.instantane(issue(etiquettes=("d7", "validé", "cat:force")), evts)
    assert inst["etiquettes"] == ["cat:force", "d7", "validé"]
    assert inst["poses"]["validé"] == {"par": "MZA-code", "le": "2026-11-10T10:00:00Z"}
    assert "rejeté" not in inst["poses"]
    assert len(inst["historique"]) == 5


def test_collect_idempotent(conn, tmp_path):
    api = FausseApi([issue()], {1: [evt("labeled", "d7", "bot", "2026-11-10T09:00:00Z")]})
    assert gh.collect(conn, tmp_path / "raw", api, maintenant=lambda: "2026-11-10T11:00:00Z") == 1
    assert gh.collect(conn, tmp_path / "raw", api, maintenant=lambda: "2026-11-10T12:00:00Z") == 0
    assert api.appels[-2] == (
        "issues",
        {"labels": "d7", "state": "all", "since": "2026-11-10T11:00:00Z"},
    )


def test_issue_modifiee_nouvelle_version(conn, tmp_path):
    raw = tmp_path / "raw"
    api = FausseApi([issue()], {})
    gh.collect(conn, raw, api, maintenant=lambda: "2026-11-10T11:00:00Z")
    api.issues = [issue(etiquettes=("d7", "validé", "cat:force"), maj="2026-11-10T11:30:00Z")]
    api.evenements = {1: [evt("labeled", "validé", "MZA-code", "2026-11-10T11:30:00Z")]}
    assert gh.collect(conn, raw, api, maintenant=lambda: "2026-11-10T12:00:00Z") == 1
    (dernier,) = gh.instantanes(conn, raw)
    assert dernier["etiquettes"] == ["cat:force", "d7", "validé"]


def test_retour_a_un_etat_anterieur_reste_le_dernier(conn, tmp_path):
    raw = tmp_path / "raw"
    api = FausseApi([issue()], {})
    gh.collect(conn, raw, api, maintenant=lambda: "2026-11-10T11:00:00Z")
    api.issues = [issue(etiquettes=("d7", "validé", "cat:force"), maj="2026-11-10T11:30:00Z")]
    gh.collect(conn, raw, api, maintenant=lambda: "2026-11-10T12:00:00Z")
    api.issues = [issue(maj="2026-11-10T12:30:00Z")]  # validation retirée
    gh.collect(conn, raw, api, maintenant=lambda: "2026-11-10T13:00:00Z")
    (dernier,) = gh.instantanes(conn, raw)
    assert "validé" not in dernier["etiquettes"]


def test_issue_fermee_conserve_etiquettes(conn, tmp_path):
    api = FausseApi([issue(etiquettes=("d7", "validé", "cat:force"), etat="closed")], {})
    gh.collect(conn, tmp_path / "raw", api, maintenant=lambda: "2026-11-10T11:00:00Z")
    (inst,) = gh.instantanes(conn, tmp_path / "raw")
    assert inst["etat"] == "closed" and "validé" in inst["etiquettes"]


def test_pull_requests_ignorees(conn, tmp_path):
    pr = {**issue(2), "pull_request": {"url": "x"}}
    api = FausseApi([issue(), pr], {})
    assert gh.collect(conn, tmp_path / "raw", api, maintenant=lambda: "2026-11-10T11:00:00Z") == 1


def test_sans_config_sort_0(tmp_path, capsys):
    assert (
        gh.main(
            [
                "--db",
                str(tmp_path / "t.sqlite"),
                "--raw-dir",
                str(tmp_path / "raw"),
                "--config",
                str(tmp_path / "absent"),
            ]
        )
        == 0
    )
    assert "absent" in capsys.readouterr().out


def test_lire_config(tmp_path):
    f = tmp_path / "github.local"
    f.write_text("# commentaire\nGITHUB_TOKEN=abc\nGITHUB_DEPOT=moi/depot\n")
    assert gh.lire_config(f) == ("abc", "moi/depot")


def test_quota_epuise_sort_0_sans_controle(conn, tmp_path, monkeypatch, capsys):
    class ApiEnPanne:
        def lister(self, chemin, params):
            raise gh.ErreurApi("403 : quota épuisé (x-ratelimit-remaining: 0)")

    assert gh.collecter(conn, tmp_path / "raw", ApiEnPanne()) == 0
    assert "quota" in capsys.readouterr().out
    assert conn.execute("SELECT count(*) FROM source_checks").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM raw_documents").fetchone()[0] == 0


def test_instantane_trie_et_stable():
    a = gh.instantane(issue(etiquettes=("en-attente", "d7")), [])
    b = gh.instantane(issue(etiquettes=("d7", "en-attente")), [])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
