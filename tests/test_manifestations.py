import datetime as dt
import io
import zipfile
from contextlib import contextmanager

import pytest

from collectors import justice_admin
from extract import manifestations as m
from extract.common import FactDraft, write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
GRID = load_grid()
INDICATOR = GRID.indicators[m.INDICATOR]


def decision(texte, ident="DTA_1_20230320.xml", solution="Rejet", date="2023-03-20", juri="TA75"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document><Donnees_Techniques><Identification>{ident}</Identification></Donnees_Techniques>
<Dossier><Code_Juridiction>{juri}</Code_Juridiction>
<Nom_Juridiction>Tribunal Administratif de Paris</Nom_Juridiction>
<Numero_Dossier>2301</Numero_Dossier><Date_Lecture>{date}</Date_Lecture><Numero_ECLI>ECLI:FR:TA:{ident}</Numero_ECLI>
<Type_Recours>Plein contentieux</Type_Recours><Solution>{solution}</Solution></Dossier>
<Audience><Formation_Jugement>Juge des référés</Formation_Jugement></Audience>
<Decision><Texte_Integral><p>{texte}</p></Texte_Integral></Decision></Document>""".encode()


CONCORDE = (
    "Vu la procédure suivante : l'association demande au juge des référés, sur le fondement de "
    "l'article L. 521-2 du code de justice administrative, la suspension de l'arrêté du 18 mars "
    "2023, par lequel le préfet de police a interdit la manifestation déclarée le 17 mars 2023."
)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        (CONCORDE, ["demande_contre_interdiction"]),
        (
            "Aux termes de l'article L. 211-4 du code de la sécurité intérieure : si l'autorité "
            "investie des pouvoirs de police estime que la manifestation projetée est de nature à "
            "troubler l'ordre public, elle l'interdit par un arrêté.",
            ["csi_l211-4", "demande_contre_interdiction"],
        ),
        # même numéro d'article, autre code : écarté
        (
            "au regard des articles L. 211-2 et L. 211-4 du code des relations entre le public et "
            "l'administration, l'arrêté est suffisamment motivé.",
            [],
        ),
        # droit des étrangers : une manifestation est mentionnée, rien n'est contesté
        (
            "M. E a été interpellé lors d'une manifestation sur la voie publique ; le préfet lui a "
            "refusé un titre de séjour.",
            [],
        ),
        ("appel à manifestation d'intérêt : le préfet a interdit tout dépôt hors délai.", []),
        # sanctions antidopage, interdictions de stade, épreuves nautiques : pas des manifestations
        # au sens de la liberté de manifester (DCE_465059_20221227, DTA_2400118_20250630)
        (
            "M. C B demande au Conseil d'Etat d'annuler la décision du 16 mai 2022 de la "
            "commission des sanctions de l'AFLD qui lui a interdit de participer à toute "
            "manifestation sportive organisée par une fédération agréée.",
            [],
        ),
        (
            "d'annuler l'arrêté par lequel le préfet de police lui a interdit de pénétrer dans les "
            "enceintes où se déroulent des manifestations sportives.",
            [],
        ),
        (
            "demande au Conseil d'Etat d'annuler la décision du 28 avril 2025 par laquelle la "
            "commission des sanctions de l'Agence française de lutte contre le dopage (AFLD) lui a "
            "interdit pour une durée de dix-huit mois : - de participer aux manifestations "
            "organisées par une fédération",
            [],
        ),
        (
            "d'annuler la décision par laquelle le directeur de la mer a interdit la manifestation "
            "nautique « Open ».",
            [],
        ),
    ],
)
def test_motifs(texte, attendu):
    assert m.motifs(texte) == attendu


def test_ban_mentioned_only_after_the_claims_is_ignored():
    texte = "Demande d'indemnisation d'un préjudice. " + "x " * 2000 + CONCORDE
    assert m.motifs(texte) == []


@pytest.mark.parametrize(
    ("solution", "issue"),
    [
        ("Satisfaction totale", "favorable_requerant"),
        ("Satisfaction partielle", "favorable_requerant"),
        ("Rejet", "rejet"),
        ("Rejet défaut de doute sérieux", "rejet"),
        ("Non-lieu", "non_lieu"),
        ("Désistement d'office défaut confirm. req.", "autre"),
        ("Rejet PAPC", "rejet"),
        ("R.822-5 Rejet PAPC défaut ministère avocat", "rejet"),
        ("R.822-5-3 Rejet PAPC référé", "rejet"),
        ("TA Melun", "autre"),
    ],
)
def test_issue(solution, issue):
    assert m.issue(solution) == issue


APPEL_MINISTRE = (
    "Vu la procédure suivante : L'association X a demandé au juge des référés du tribunal "
    "administratif de Paris de suspendre l'arrêté par lequel le préfet de police a interdit la "
    "manifestation du 1er mai. Par une ordonnance, le juge a suspendu l'arrêté. Par une requête, "
    "enregistrée le 2 mai 2024 au secrétariat du contentieux du Conseil d'Etat, le ministre de "
    "l'intérieur et des outre-mer demande au juge des référés du Conseil d'Etat d'annuler cette "
    "ordonnance."
)


@pytest.mark.parametrize(
    ("solution", "issue"),
    [
        ("Rejet", "favorable_requerant"),  # appel du ministre rejeté : l'interdiction tombe
        ("R.822-5-3 Rejet PAPC référé", "favorable_requerant"),
        ("Satisfaction totale", "rejet"),  # appel du ministre accueilli : l'interdiction tient
        ("Non-lieu", "non_lieu"),
    ],
)
def test_issue_is_reversed_when_the_administration_appeals(solution, issue):
    assert m.issue(solution, appel_administration=True) == issue


def test_scan_detects_an_appeal_by_the_administration():
    assert m.scan_xml(decision(APPEL_MINISTRE))["appel_administration"] is True
    assert m.scan_xml(decision(CONCORDE))["appel_administration"] is False


def test_scan_keeps_metadata_never_text():
    meta = m.scan_xml(decision(CONCORDE))
    assert meta["refere"] and meta["Solution"] == "Rejet"
    assert "préfet" not in str(meta)  # le texte n'est pas conservé
    assert m.scan_xml(decision("Permis de construire refusé par le maire.")) is None


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def zipped(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_extract_dedups_republished_decisions_and_uses_cache(conn, tmp_path):
    raw, cache = tmp_path / "raw", tmp_path / "cache"
    same = decision(CONCORDE, ident="DTA_1_20230320.xml")
    docs = []
    for name, files in [
        ("TA_202303.zip", {"TA75/a.xml": same, "TA75/b.xml": decision("Autre litige.", ident="x")}),
        ("TA_202304.zip", {"TA75/a.xml": same}),  # republiée dans une autre archive
    ]:
        docs.append(
            store(
                conn,
                raw,
                source_id=m.SOURCE_ID,
                external_id=name,
                url="u",
                fetched_at="2026-11-05T00:00:00Z",
                chunks=[zipped(files)],
                suffix=".zip",
            )
        )
    [draft] = m.extract(conn, raw, cache)
    assert draft.raw_document_ids == (docs[0].id, docs[1].id)
    assert draft.attributes["issue"] == "rejet" and draft.occurred_on == "2023-03-20"
    assert len(list(cache.glob(f"*.{m.SCAN_VERSION}.jsonl"))) == 2
    assert [d.official_ref for d in m.extract(conn, raw, cache)] == [draft.official_ref]


def test_same_file_name_in_two_courts_is_two_decisions(conn, tmp_path):
    # DTA_2301082_20230228.xml existe au TA de Strasbourg (TA67) et au TA de Versailles (TA78)
    raw, cache = tmp_path / "raw", tmp_path / "cache"
    files = {
        f"{juri}/DTA_2301082_20230228.xml": decision(
            CONCORDE, ident="DTA_2301082_20230228.xml", juri=juri
        )
        for juri in ("TA67", "TA78")
    }
    store(
        conn,
        raw,
        source_id=m.SOURCE_ID,
        external_id="TA_202302.zip",
        url="u",
        fetched_at="2026-11-05T00:00:00Z",
        chunks=[zipped(files)],
        suffix=".zip",
    )
    drafts = m.extract(conn, raw, cache)
    assert sorted(d.attributes["juridiction"] for d in drafts) == ["TA67", "TA78"]


def test_ratio_counts_only_decided_cases(conn):
    conn.execute(
        "INSERT INTO raw_documents (source_id, external_id, url, fetched_at, sha256, path)"
        " VALUES ('justice_admin', 'x', 'u', '2026-01-01T00:00:00Z', '" + "0" * 64 + "', 'p')"
    )
    write_facts(
        conn,
        [
            FactDraft(
                m.INDICATOR,
                "decision_interdiction_manifestation",
                "2024-03-01",
                f"d{i}",
                f"ref{i}",
                m.EXTRACTOR,
                (1,),
                {"issue": issue},
            )
            for i, issue in enumerate(
                ["favorable_requerant", "rejet", "rejet", "non_lieu", "autre"]
            )
        ],
    )
    events = metrics.load_events(conn, INDICATOR)
    values = metrics.window_values(
        events, metrics.Window("t", 366, D(2024, 1, 1), D(2024, 12, 31)), INDICATOR.ratios
    )
    assert values["nb_decisions_manifestation"] == 5
    assert values["nb_decisions_manifestation_tranchees"] == 3
    assert values["ratio_interdictions_censurees"] == pytest.approx(1 / 3)


INDEX = """
<a href="/DTA/2026/09/TA_202609.zip">x</a><a href="/DTA/2026/10/TA_202610.zip">x</a>
<a href="/DTA/2026/11/TA_202611.zip">x</a><a href="/DTA/2026/10/TA_202610.zip">doublon</a>
"""


def test_only_completed_months_are_collected_once(conn, tmp_path):
    calls = []

    @contextmanager
    def web(url):
        calls.append(url)
        yield io.BytesIO(INDEX.encode() if url.endswith("/DTA/") else b"zip " + url.encode())

    today = D(2026, 11, 5)
    got = justice_admin.collect(conn, tmp_path / "raw", ("DTA",), opener=web, today=today)
    assert got == ["TA_202609.zip", "TA_202610.zip"]  # novembre 2026 n'est pas terminé
    assert justice_admin.collect(conn, tmp_path / "raw", ("DTA",), opener=web, today=today) == []


def test_decision_without_the_word_manifestation_is_read():
    # TA Paris, 28 mars 2023 : seuls « cortèges, défilés et rassemblements » sont cités.
    texte = (
        "Le syndicat demande au juge des référés de suspendre la décision du préfet de police"
        " d'interdire, chaque jour, tous les cortèges, défilés et rassemblements non déclarés."
    )
    assert m.scan_xml(decision(texte))["motifs"] == ["demande_contre_interdiction"]
