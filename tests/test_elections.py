import io
import zipfile

import pytest

from extract import elections
from storage.archive import store
from storage.db import connect, init_db

# Effectifs réels du 1er tour 2024 (contrôlés : 32 057 946 + 582 908 + 267 803 = 32 908 657)
REEL_2024 = {
    "inscrits": 49332709,
    "votants": 32908657,
    "abstentions": 16424052,
    "blancs": 582908,
    "nuls": 267803,
    "exprimes": 32057946,
}


def xlsx(rows):
    """Classeur minimal : chaînes en ligne (inlineStr), nombres en valeur."""

    def cell(v):
        if isinstance(v, int):
            return f"<c><v>{v}</v></c>"
        return f'<c t="inlineStr"><is><t>{v}</t></is></c>'

    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        + "".join("<row>" + "".join(cell(v) for v in r) + "</row>" for r in rows)
        + "</sheetData></worksheet>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def header_format(sep=";"):
    head = [
        "Code localisation",
        "Libellé localisation",
        "Inscrits",
        "Votants",
        "% Votants",
        "Abstentions",
        "Exprimés",
        "Blancs",
        "Nuls",
        "Nuance candidat 1",
        "Voix 1",
    ]
    fe = [
        "FE",
        "France entière",
        "49 332 709",
        "32908657",
        "66,71%",
        "16424052",
        "32057946",
        "582908",
        "267803",
        "XYZ",
        "123",
    ]
    return head, fe


def test_header_format_text_cp1252():
    head, fe = header_format()
    data = (";".join(head) + "\n" + ";".join(fe) + "\n").encode("cp1252")
    assert elections.france_entiere(elections.text_rows(data)) == REEL_2024


def test_header_format_xlsx():
    head, fe = header_format()
    rows = elections.xlsx_rows(xlsx([head, fe]))
    assert elections.france_entiere(rows) == REEL_2024


def test_label_value_format_2017():
    rows = elections.xlsx_rows(
        xlsx(
            [
                ["Résultats - tour 1"],
                ["France entière"],
                [".", "Nombre", "%ins", "%vot", "Nuance", "Sièges", "Voix"],
                ["Inscrits", 47570988, "", "", "EXG", "", 175214],
                ["Abstentions", 24403480, "51.3"],
                ["Votants", 23167508, "48.7"],
                ["Blancs", 357018],
                ["Nuls", 156326],
                ["Exprimés", 22654164],
            ]
        )
    )
    values = elections.france_entiere(rows)
    elections.check(values, "2017")
    assert values["votants"] == 23167508


def test_inconsistent_totals_are_rejected():
    with pytest.raises(ValueError, match="votants"):
        elections.check({**REEL_2024, "nuls": 1}, "faux")
    with pytest.raises(ValueError, match="absentes"):
        elections.check({"inscrits": 1}, "incomplet")


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def test_extract_one_fact_per_round_with_all_sources(conn, tmp_path):
    config = tmp_path / "datagouv.yaml"
    config.write_text(
        "licences_acceptees: [lov2]\njeux:\n"
        "  - {id: ds1, nom: leg_t1, inclure: x, formats: [xlsx], taille_max_mo: 1,\n"
        "     scrutin: {type: legislatives, tour: 1, date: 2024-06-30}}\n"
        "  - {id: autre, nom: cada, inclure: x, formats: [csv], taille_max_mo: 1}\n",
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    head, fe = header_format()
    content = xlsx([head, fe])
    ids = []
    for ext_id, data in [
        ("ds1/r1", content),
        ("ds1/r2", content),
        ("ds1/fiche.json", b"{}"),
        ("autre/r9", b"a;b"),
    ]:
        doc = store(
            conn,
            raw,
            source_id="datagouv",
            external_id=ext_id,
            url="u",
            fetched_at="2026-11-05T00:00:00Z",
            chunks=[data],
            suffix=".xlsx" if ext_id.startswith("ds1/r") else ".csv",
        )
        ids.append(doc.id)
    [draft] = elections.extract(conn, raw, config)
    assert draft.occurred_on == "2024-06-30" and draft.official_ref == "legislatives-2024-t1"
    assert draft.raw_document_ids == (ids[0], ids[1])
    assert draft.attributes["participation"] == pytest.approx(32908657 / 49332709, abs=1e-6)
    assert draft.attributes["electorat_complet"]
    assert "XYZ" not in str(draft.attributes)  # aucune nuance politique lue
