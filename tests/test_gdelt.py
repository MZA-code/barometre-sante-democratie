# ruff: noqa: E501  (lignes GDELT de test : longues voulues)
import datetime as dt
import gzip
import io
import urllib.error
import zipfile
from contextlib import contextmanager

import pytest

from collectors import gdelt as collector
from extract import gdelt
from storage.archive import store
from storage.db import connect, init_db

DOMAINES = (
    "exemple.co.uk\tUK\tUnited Kingdom\nexemple.com\tUS\tUnited States\nlemonde.fr\tFR\tFrance\n"
)


def zipped(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("f.CSV", text)
    return buf.getvalue()


def event(eid, racine, a1="", a2="", pays="FR"):
    cols = [""] * 61
    cols[0], cols[1], cols[12], cols[22], cols[26], cols[28], cols[52], cols[53] = (
        eid,
        "20261105",
        a1,
        a2,
        racine + "1",
        racine,
        "Paris, France",
        pays,
    )
    return "\t".join(cols)


def mention(eid, domaine, url, heure="20261105120000", type_="1", trad=""):
    cols = [""] * 16
    cols[0], cols[2], cols[3], cols[4], cols[5], cols[14] = eid, heure, type_, domaine, url, trad
    return "\t".join(cols)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def fake_opener(files):
    @contextmanager
    def opener(url):
        if url not in files:
            raise urllib.error.HTTPError(url, 404, "absent", {}, None)
        yield io.BytesIO(files[url])

    return opener


def test_extrait_jour_filtre_france_et_web(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "PAUSE_S", 0)
    day = dt.date(2026, 11, 5)
    s0 = collector.stamps(day)[0]
    files = {
        collector.BASE.format(stamp=s0, kind="export"): zipped(
            event("1", "14") + "\n" + event("2", "14", pays="UK") + "\n"
        ),
        collector.BASE.format(stamp=s0, kind="mentions"): zipped(
            "\n".join(
                [
                    mention("1", "Exemple.co.uk", "https://exemple.co.uk/a"),
                    mention("2", "exemple.co.uk", "https://exemple.co.uk/b"),  # hors France
                    mention("1", "exemple.com", "https://exemple.com/tv", type_="2"),  # pas web
                    mention("1", "lemonde.fr", "https://lemonde.fr/c", trad="srclc:fra;eng:x"),
                ]
            )
            + "\n"
        ),
    }
    data = collector.extrait_jour(day, fake_opener(files), tmp_path / "cache")
    text = gzip.decompress(data).decode()
    lignes = [line for line in text.splitlines() if not line.startswith("#")]
    assert len(lignes) == 3  # en-tête + 2 mentions d'un événement en France
    assert "exemple.co.uk\thttps://exemple.co.uk/a\teng" in text
    assert "lemonde.fr\thttps://lemonde.fr/c\tfra" in text
    assert f"{collector.stamps(day)[1]}.export" in text  # tranche absente signalée
    assert data == collector.extrait_jour(
        day, fake_opener(files), tmp_path / "cache"
    )  # déterministe


def put(conn, raw, external_id, data, suffix):
    store(
        conn,
        raw,
        source_id="gdelt",
        external_id=external_id,
        url="u",
        fetched_at="2026-11-06T00:00:00Z",
        chunks=[data],
        suffix=suffix,
    )


def jour(rows):
    head = "# GDELT\n# tranches manquantes : aucune\n" + "\t".join(collector.COLONNES) + "\n"
    return gzip.compress((head + "\n".join("\t".join(r) for r in rows) + "\n").encode(), mtime=0)


def row(url, domaine, racine, a1="", a2="", heure="20261105120000"):
    return [heure, "1", "20261105", racine + "1", racine, a1, a2, "Paris", domaine, url, "eng"]


def test_couverture_mensuelle(conn, tmp_path):
    raw = tmp_path / "raw"
    put(conn, raw, gdelt.DOMAINES_ID, DOMAINES.encode(), ".txt")
    put(
        conn,
        raw,
        "2026-11-05.tsv.gz",
        jour(
            [
                row("https://exemple.co.uk/a", "exemple.co.uk", "14"),
                row(
                    "https://exemple.co.uk/a", "exemple.co.uk", "18", a2="COP"
                ),  # même article, 2 thèmes
                row("https://exemple.com/b", "exemple.com", "18", a1="COP"),
                row(
                    "https://exemple.com/c", "exemple.com", "18"
                ),  # agression sans police : hors thème
                row("https://lemonde.fr/d", "lemonde.fr", "14"),  # média français : exclu
                row("https://inconnu.net/e", "inconnu.net", "14"),  # domaine hors table
            ]
        ),
        ".tsv.gz",
    )
    (f,) = gdelt.extract(conn, raw)
    a = f.attributes
    assert (f.occurred_on, a["jours_couverts"], a["jours_dans_le_mois"]) == ("2026-11-30", 1, 30)
    assert (a["articles_etrangers"], a["sites_etrangers"], a["articles_domaine_inconnu"]) == (
        3,
        2,
        1,
    )
    assert a["manifestations"]["articles"] == 1
    assert a["force_police"]["articles"] == 2
    assert a["par_pays"] == {"United States": 2, "United Kingdom": 1}
    assert a["force_police"]["exemples"][0]["url"] in (
        "https://exemple.com/b",
        "https://exemple.co.uk/a",
    )


def test_langue():
    assert collector.langue("srclc:spa;eng:GT-SPA") == "spa"
    assert collector.langue("") == "eng"


def test_erreur_reseau_retentee_puis_reussie():
    calls = []

    @contextmanager
    def flaky(url):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.URLError("handshake operation timed out")
        yield io.BytesIO(zipped(event("1", "14") + "\n"))

    rows = collector.fetch_rows("u", flaky, sleep=lambda s: None)
    assert len(calls) == 3 and rows[0][0] == "1"


def test_erreur_reseau_persistante_remonte():
    @contextmanager
    def down(url):
        raise urllib.error.URLError("timeout")
        yield

    with pytest.raises(urllib.error.URLError):
        collector.fetch_rows("u", down, sleep=lambda s: None)
