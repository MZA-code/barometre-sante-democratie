import io
import urllib.error
from contextlib import contextmanager

import pytest

from collectors import an_opendata, dila
from storage.db import connect, init_db

LISTING = """
<a href="DILA_LEGI_Presentation_20170824.pdf">pdf</a>
<a href="Freemium_legi_global_20250713-140000.tar.gz">global</a>
<a href="LEGI_20250712-211706.tar.gz">LEGI_20250712-211706.tar.gz</a>
<a href="LEGI_20250714-211000.tar.gz">LEGI_20250714-211000.tar.gz</a>
<a href="LEGI_20250715-211000.tar.gz">LEGI_20250715-211000.tar.gz</a>
"""


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


LEGI = dila.FUNDS["legi"]


def dila_web(listing=LISTING):
    pages = {LEGI.base_url: listing.encode()}
    for archive in LEGI.parse_listing(listing):
        pages[archive.url] = f"contenu {archive.name}".encode()
    return FakeWeb(pages)


def test_parse_listing_sorted_and_typed():
    archives = LEGI.parse_listing(LISTING)
    assert [a.name for a in archives] == [
        "LEGI_20250712-211706.tar.gz",
        "Freemium_legi_global_20250713-140000.tar.gz",
        "LEGI_20250714-211000.tar.gz",
        "LEGI_20250715-211000.tar.gz",
    ]
    assert [a.is_global for a in archives] == [False, True, False, False]


def test_dila_first_run_takes_global_then_later_increments(conn, tmp_path):
    collected = dila.collect(conn, tmp_path / "raw", LEGI, opener=dila_web())
    assert collected == [
        "Freemium_legi_global_20250713-140000.tar.gz",
        "LEGI_20250714-211000.tar.gz",
        "LEGI_20250715-211000.tar.gz",
    ]


def test_dila_second_run_downloads_nothing_and_no_duplicate(conn, tmp_path):
    dila.collect(conn, tmp_path / "raw", LEGI, opener=dila_web())
    web = dila_web()
    assert dila.collect(conn, tmp_path / "raw", LEGI, opener=web) == []
    assert web.calls == [LEGI.base_url]
    rows = conn.execute("SELECT sha256 FROM raw_documents").fetchall()
    assert len(rows) == 3 and all(len(r["sha256"]) == 64 for r in rows)


def test_dila_picks_up_new_increment(conn, tmp_path):
    dila.collect(conn, tmp_path / "raw", LEGI, opener=dila_web())
    newer = LISTING + '<a href="LEGI_20250716-211000.tar.gz">x</a>'
    assert dila.collect(conn, tmp_path / "raw", LEGI, opener=dila_web(newer)) == [
        "LEGI_20250716-211000.tar.gz"
    ]


def test_dila_max_limits_downloads(conn, tmp_path):
    assert len(dila.collect(conn, tmp_path / "raw", LEGI, opener=dila_web(), max_archives=1)) == 1


def an_web(content=b"zip L17"):
    return FakeWeb(
        {
            an_opendata.url_for(17): content,
            an_opendata.url_for(16): b"zip L16",
        }
    )


def test_an_collects_each_legislature_and_skips_missing(conn, tmp_path):
    results = an_opendata.collect(conn, tmp_path / "raw", (17, 16, 13), opener=an_web())
    assert results[17].created and results[16].created and results[13] is None


def test_an_unchanged_file_is_not_duplicated_but_new_content_is(conn, tmp_path):
    raw = tmp_path / "raw"
    an_opendata.collect(conn, raw, (17,), opener=an_web())
    again = an_opendata.collect(conn, raw, (17,), opener=an_web())
    assert not again[17].created
    changed = an_opendata.collect(conn, raw, (17,), opener=an_web(b"zip L17 v2"))
    assert changed[17].created
    assert conn.execute("SELECT count(*) FROM raw_documents").fetchone()[0] == 2


def make_zip(files: dict[str, bytes], date_time=(2026, 10, 26, 0, 0, 0)) -> bytes:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, date_time), data)
    return buf.getvalue()


def test_an_repackaged_zip_with_same_content_is_not_archived(conn, tmp_path):
    # Constaté le 2026-11-05 : le serveur régénère le zip (horodatages internes différents)
    # sans que son contenu change. Seul un contenu modifié crée une nouvelle version.
    raw = tmp_path / "raw"
    v1 = make_zip({"a.json": b"{}", "b.json": b"[1]"})
    repack = make_zip({"b.json": b"[1]", "a.json": b"{}"}, date_time=(2026, 11, 5, 3, 0, 0))
    assert v1 != repack
    an_opendata.collect(conn, raw, (17,), opener=an_web(v1))
    again = an_opendata.collect(conn, raw, (17,), opener=an_web(repack))
    assert not again[17].created
    changed = an_opendata.collect(conn, raw, (17,), opener=an_web(make_zip({"a.json": b"{1}"})))
    assert changed[17].created
    assert conn.execute("SELECT count(*) FROM raw_documents").fetchone()[0] == 2


def test_an_old_legislatures_use_roman_suffix():
    assert an_opendata.url_for(15).endswith(
        "/15/loi/dossiers_legislatifs/Dossiers_Legislatifs_XV.json.zip"
    )
    assert an_opendata.url_for(17).endswith(
        "/17/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip"
    )


def test_jorf_fund_parses_its_own_names():
    listing = (
        '<a href="Freemium_jorf_global_20250713-140000.tar.gz">g</a>'
        '<a href="JORF_20250714-002503.tar.gz">i</a>'
        '<a href="LEGI_20250714-211000.tar.gz">x</a>'
    )
    names = [a.name for a in dila.FUNDS["jorf"].parse_listing(listing)]
    assert names == ["Freemium_jorf_global_20250713-140000.tar.gz", "JORF_20250714-002503.tar.gz"]
