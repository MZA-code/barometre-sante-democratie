import datetime as dt
import io
import json
import tarfile

import pytest

from extract import constit
from extract.common import write_facts
from scoring import metrics
from scoring.grid import load_grid
from storage.archive import store
from storage.db import connect, init_db

D = dt.date
GRID = load_grid()
INDICATOR = GRID.indicators[constit.INDICATOR]


def fiche(id_, nature, numero, date, titre, solution):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEXTE_JURI_CONSTIT><META><META_COMMUN><ID>{id_}</ID><NATURE>{nature}</NATURE></META_COMMUN>
<META_SPEC><META_JURI><TITRE>{titre}</TITRE><DATE_DEC>{date}</DATE_DEC>
<NUMERO>{numero}</NUMERO><SOLUTION>{solution}</SOLUTION></META_JURI></META_SPEC></META>
<TEXTE><BLOC_TEXTUEL><CONTENU>Texte nominatif non lu.</CONTENU></BLOC_TEXTUEL></TEXTE>
</TEXTE_JURI_CONSTIT>""".encode()


def tarball(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"constit/global/CONS/TEXT/00/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def archive(conn, raw_dir, name, files, fetched_at="2026-11-01T00:00:00Z"):
    return store(
        conn,
        raw_dir,
        source_id=constit.SOURCE_ID,
        external_id=name,
        url=f"https://echanges.dila.gouv.fr/OPENDATA/CONSTIT/{name}",
        fetched_at=fetched_at,
        chunks=[tarball(files)],
        suffix=".tar.gz",
    )


# --- classement des titres (titres réels du fonds CONSTIT) ------------------------------


@pytest.mark.parametrize(
    ("titre", "loi", "organique"),
    [
        ("Loi relative au droit à l'aide à mourir", True, False),
        ("Loi organique relative aux lois de financement de la sécurité sociale", True, True),
        ("Lois organiques complétant les articles L.O. 176 du code électoral", True, True),
        ("Troisième loi de finances rectificative pour 1981", True, False),
        (
            "Dernière loi de finances rectificative pour 1977 et, notamment, son article 6",
            True,
            False,
        ),
        ("Loi autorisant la ratification du traité sur l'Union européenne", True, False),
        ("Résolution modifiant le règlement de l'Assemblée nationale", False, False),
        ("Règlement du Sénat", False, False),
        ("Traité sur l'Union européenne", False, False),
        ("Engagements internationaux relatifs à l'abolition de la peine de mort", False, False),
        ("Révision constitutionnelle relative à l'organisation décentralisée", False, False),
        ("Demande de récusation présentée par des sénateurs", False, False),
    ],
)
def test_classification(titre, loi, organique):
    assert constit.is_loi(titre) is loi
    assert bool(constit.ORGANIQUE.match(titre)) is organique


@pytest.mark.parametrize(
    ("solution", "au_fond", "censure"),
    [
        ("Conformité", True, False),
        ("Conformité - réserve", True, False),
        ("Non conformité partielle", True, True),
        ("Non conformité totale - effet différé - réserve transitoire", True, True),
        ("Irrecevabilité", False, False),
        ("Incompétence pour statuer", False, False),
        ("Non lieu à statuer", False, False),
        ("Rejet", False, False),
    ],
)
def test_solution(solution, au_fond, censure):
    d = constit.Decision("CONSTEXT1", "DC", "1", "2020-01-01", "Loi x", solution)
    assert (d.au_fond, d.censure) == (au_fond, censure)


# --- extraction depuis des archives -----------------------------------------------------


def test_extract_dedup_increments_and_scope(conn, tmp_path):
    raw = tmp_path / "raw"
    g = archive(
        conn,
        raw,
        "Freemium_constit_global_20250713-140000.tar.gz",
        {
            "CONSTEXT0001.xml": fiche(
                "CONSTEXT0001",
                "DC",
                "86-225",
                "1987-01-23",
                "Loi portant diverses mesures d'ordre social",
                "Non conformité partielle",
            ),
            "CONSTEXT0002.xml": fiche(
                "CONSTEXT0002",
                "DC",
                "59-2",
                "1959-06-24",
                "Règlement de l'Assemblée nationale",
                "Conformité",
            ),
            "CONSTEXT0003.xml": fiche(
                "CONSTEXT0003", "AN", "2025-6515", "2025-06-20", "A.N., 4e circ.", "Inéligibilité"
            ),
            "CONSTEXT0004.xml": fiche(
                "CONSTEXT0004", "QPC", "2020-1", "2020-05-01", "M. X [disposition]", "Conformité"
            ),
        },
    )
    inc = archive(
        conn,
        raw,
        "CONSTIT_20260101-000000.tar.gz",
        {
            # réédition de la même décision sous un nouvel identifiant
            "CONSTEXT0009.xml": fiche(
                "CONSTEXT0009",
                "DC",
                "86-225",
                "1987-01-23",
                "Loi portant diverses mesures d'ordre social",
                "Non conformité partielle - réserve",
            ),
            # mise à jour d'une fiche existante
            "CONSTEXT0004.xml": fiche(
                "CONSTEXT0004",
                "QPC",
                "2020-1",
                "2020-05-01",
                "M. X [disposition]",
                "Non conformité totale",
            ),
        },
    )
    drafts = {d.official_ref: d for d in constit.extract(conn, raw)}
    assert set(drafts) == {"86-225 DC", "2020-1 QPC"}

    dc = drafts["86-225 DC"]
    assert dc.fact_type == "decision_dc_loi"
    assert dc.attributes["constext"] == "CONSTEXT0009"
    assert dc.attributes["constext_doublons"] == ["CONSTEXT0001"]
    assert dc.attributes["censure"] and not dc.attributes["organique"]
    assert dc.raw_document_ids == tuple(sorted({g.id, inc.id}))

    qpc = drafts["2020-1 QPC"]
    assert qpc.fact_type == "decision_qpc"
    assert qpc.attributes["solution"] == "Non conformité totale"
    assert "nominatif" not in json.dumps(qpc.attributes)


# --- métriques ---------------------------------------------------------------------------


def draft(day, fact_type="decision_dc_loi", solution="Conformité", organique=False, ref="x"):
    d = constit.Decision("C" + ref, "DC", ref, day, "Loi x", solution)
    return constit.FactDraft(
        indicator_id=constit.INDICATOR,
        fact_type=fact_type,
        occurred_on=day,
        title="Loi x",
        official_ref=ref,
        extraction_method=constit.EXTRACTOR,
        raw_document_ids=(1,),
        attributes={"au_fond": d.au_fond, "censure": d.censure, "organique": organique},
    )


def test_ratio_censure_counts_only_decisions_on_merits(conn, tmp_path):
    archive(conn, tmp_path / "raw", "Freemium_constit_global_20250713-140000.tar.gz", {})
    write_facts(
        conn,
        [
            draft("2024-03-01", solution="Non conformité partielle", ref="1"),
            draft("2024-04-01", solution="Conformité", ref="2"),
            draft("2024-05-01", solution="Non conformité totale", organique=True, ref="3"),
            draft("2024-06-01", solution="Irrecevabilité", ref="4"),
            draft(
                "2024-07-01", fact_type="decision_qpc", solution="Non conformité totale", ref="5"
            ),
        ],
    )
    events = metrics.load_events(conn, INDICATOR)
    window = metrics.Window("test", 366, D(2024, 1, 1), D(2024, 12, 31))
    values = metrics.window_values(events, window, INDICATOR.ratios)
    assert values["nb_lois_deferees"] == 3
    assert values["nb_lois_censurees"] == 2
    assert values["ratio_censure"] == pytest.approx(2 / 3)
    assert values["nb_lois_ordinaires_deferees"] == 2
    assert values["ratio_censure_lois_ordinaires"] == pytest.approx(1 / 2)
    assert (values["nb_qpc"], values["nb_qpc_censures"]) == (1, 1)
