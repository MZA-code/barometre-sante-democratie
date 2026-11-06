import hashlib
import io
import json
import urllib.error
from contextlib import contextmanager

import pytest

from collectors import datagouv
from collectors.datagouv import Config, DatasetSpec
from storage.db import connect, init_db

DS = "aaaa1111"
API = datagouv.API_URL.format(id=DS)
URL_CSV = "https://static.data.gouv.fr/resources/x/20260101-000000/avis.csv"
URL_BIG = "https://static.data.gouv.fr/resources/x/20260101-000000/gros.csv"
URL_XLSX = "https://static.data.gouv.fr/resources/x/20260101-000000/avis.xlsx"


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


class FakeWeb:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    @contextmanager
    def __call__(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        yield io.BytesIO(self.pages[url])


def resource(rid, title, url, fmt, content=b"", size=None, sha1=None):
    return {
        "id": rid,
        "title": title,
        "url": url,
        "format": fmt,
        "filesize": len(content) if size is None else size,
        "checksum": {"type": "sha1", "value": sha1 or hashlib.sha1(content).hexdigest()},
    }


def web(licence="fr-lo", resources=None, files=None):
    fiche = {"id": DS, "license": licence, "resources": resources or []}
    return FakeWeb({API: json.dumps(fiche).encode(), **(files or {})})


def spec(**kw):
    base = dict(id=DS, nom="avis", inclure="^Avis", formats=("csv",), taille_max_mo=1)
    return DatasetSpec(**{**base, **kw})


def config(*specs):
    return Config(frozenset({"fr-lo", "lov2"}), specs)


def standard_web(**kw):
    return web(
        resources=[
            resource("r1", "Avis 2024", URL_CSV, "csv", b"a;b\n1;2\n"),
            resource("r2", "Avis 2024", URL_XLSX, "xlsx", b"xx"),
            resource("r3", "Autre chose", URL_CSV + "?2", "csv", b"zz"),
            resource("r4", "Avis gros", URL_BIG, "csv", size=5_000_000),
        ],
        files={URL_CSV: b"a;b\n1;2\n", URL_XLSX: b"xx"},
        **kw,
    )


def test_filters_format_title_and_size(conn, tmp_path):
    w = standard_web()
    report = datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=w)
    assert report.archived == ["avis/Avis 2024"]
    assert report.skipped == ["avis/Avis gros : 5 Mo > 1 Mo"]
    assert w.calls == [API, URL_CSV]
    rows = conn.execute(
        "SELECT external_id, path FROM raw_documents ORDER BY external_id"
    ).fetchall()
    assert [r["external_id"] for r in rows] == [f"{DS}/fiche.json", f"{DS}/r1"]
    assert rows[1]["path"].endswith(".csv")


def test_already_archived_url_not_downloaded_again(conn, tmp_path):
    datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=standard_web())
    w = standard_web()
    report = datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=w)
    assert w.calls == [API]
    assert report.unchanged == ["avis/Avis 2024"]
    assert report.archived == []


def test_new_publication_url_is_new_version(conn, tmp_path):
    datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=standard_web())
    url2 = URL_CSV.replace("20260101", "20260301")
    w = web(
        resources=[resource("r1", "Avis 2024", url2, "csv", b"a;b\n1;3\n")],
        files={url2: b"a;b\n1;3\n"},
    )
    report = datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=w)
    assert report.archived == ["avis/Avis 2024"]
    n = conn.execute(
        "SELECT COUNT(*) FROM raw_documents WHERE external_id = ?", (f"{DS}/r1",)
    ).fetchone()[0]
    assert n == 2


def test_licence_not_accepted_skips_dataset_but_archives_fiche(conn, tmp_path):
    w = standard_web(licence="notspecified")
    report = datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=w)
    assert w.calls == [API]
    assert report.skipped == ["avis : licence « notspecified » non acceptée"]
    assert conn.execute("SELECT COUNT(*) FROM raw_documents").fetchone()[0] == 1


def test_licence_derogation_allows_with_warning(conn, tmp_path):
    w = standard_web(licence="notspecified")
    s = spec(licence_derogation="même producteur, Licence Ouverte au 1er tour")
    report = datagouv.collect(conn, tmp_path / "raw", config(s), opener=w)
    assert report.archived == ["avis/Avis 2024"]
    assert any("dérogation" in m for m in report.warnings)


def test_sha1_mismatch_is_reported(conn, tmp_path):
    w = web(
        resources=[resource("r1", "Avis", URL_CSV, "csv", b"abc", sha1="0" * 40)],
        files={URL_CSV: b"abc"},
    )
    report = datagouv.collect(conn, tmp_path / "raw", config(spec()), opener=w)
    assert report.archived == ["avis/Avis"]
    assert any("SHA-1" in m for m in report.warnings)


def test_exclure_and_no_match_warning(conn, tmp_path):
    report = datagouv.collect(
        conn, tmp_path / "raw", config(spec(exclure="2024|gros")), opener=standard_web()
    )
    assert report.archived == []
    assert report.warnings == ["avis : aucune ressource ne correspond aux filtres"]


def test_unknown_dataset_name_rejected(conn, tmp_path):
    with pytest.raises(ValueError, match="inconnus"):
        datagouv.collect(conn, tmp_path / "raw", config(spec()), only=["nope"], opener=web())


def test_project_config_is_valid():
    cfg = datagouv.load_config()
    assert cfg.jeux
    for j in cfg.jeux:
        assert j.formats and j.taille_max_mo > 0
