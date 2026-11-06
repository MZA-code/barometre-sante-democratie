import io
import zipfile

from collectors import senat as collector
from extract import senat
from storage.db import connect, init_db

COLS = "loicod, typloicod, numero, signet, urgence, date_loi, proaccdat, retproaccdat"


def dump(rows):
    lines = [
        "-- PostgreSQL database dump",
        "COPY autre (a) FROM stdin;",
        "x",
        "\\.",
        f"COPY loi ({COLS}) FROM stdin;",
        *("\t".join(r) for r in rows),
        "\\.",
        "COPY suite (a) FROM stdin;",
        "y",
        "\\.",
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dosleg.sql", "\n".join(lines) + "\n")
    return buf.getvalue()


ROWS = [
    ["a1", "pjl", "85-96", "a84852568", "oui", "1985-01-25 00:00:00", "\\N", "\\N"],
    [
        "a2",
        "pjl",
        "2013-702",
        "pjl12-377",
        "\\N",
        "2013-08-06 00:00:00",
        "2013-04-16 00:00:00",
        "2013-04-19 00:00:00",
    ],
    ["a3", "pjlf", "2008-1", "\\N", "dro", "2008-01-01 00:00:00", "\\N", "\\N"],
    ["a4", "ppl", "2004-1", "s1", "\\N", "2004-01-05 00:00:00", "\\N", "\\N"],
    ["a5", "ppl", "2019-3", "s2", "\\N", "2019-02-01 00:00:00", "\\N", "\\N"],
    ["a6", "ppl", "\\N", "s3", "non", "\\N", "\\N", "\\N"],  # non promulguée
    ["a7", "pjl", "2020-4", "s4", "\\N", "2020-02-01 00:00:00", "2019-10-01 00:00:00", "\\N"],
]


def test_read_lois_statuses(tmp_path):
    path = tmp_path / "dosleg.zip"
    path.write_bytes(dump(ROWS))
    lois = senat.read_lois(path, 7)
    assert set(lois) == {"85-96", "2013-702", "2008-1", "2004-1", "2019-3", "2020-4"}
    statuts = {k: v.statut for k, v in lois.items()}
    assert statuts == {
        "85-96": "acceleree",  # urgence déclarée
        "2013-702": "ordinaire",  # procédure retirée
        "2008-1": "de_droit",  # loi de finances
        "2004-1": "inconnu",  # urgence vide avant 2009
        "2019-3": "ordinaire",  # depuis 2009 : pas d'engagement = procédure ordinaire
        "2020-4": "acceleree",
    }
    assert lois["2013-702"].url == "https://www.senat.fr/dossier-legislatif/pjl12-377.html"
    assert lois["2008-1"].url is None and lois["85-96"].raw_document_id == 7


def test_copy_unescape():
    assert senat.unescape("\\N") is None
    assert senat.unescape("a\\tb\\\\c") == "a\tb\\c"


class Web:
    def __init__(self, data):
        self.data = data

    def __call__(self, url):
        from contextlib import contextmanager

        @contextmanager
        def ctx():
            yield io.BytesIO(self.data)

        return ctx()


def test_collector_skips_identical_content(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    raw = tmp_path / "raw"
    first = collector.collect(conn, raw, opener=Web(dump(ROWS)))
    again = collector.collect(conn, raw, opener=Web(dump(ROWS)))
    changed = collector.collect(conn, raw, opener=Web(dump(ROWS[:2])))
    assert first.created and not again.created and changed.created
    conn.close()
