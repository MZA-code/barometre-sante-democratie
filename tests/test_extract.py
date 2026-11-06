import csv
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from extract import dila, parlement, seed
from extract.common import FactDraft, write_facts
from storage.archive import store
from storage.db import connect, init_db

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent
AN_OPEN_DATA_START = "2012-06-20"  # début de la XIVe législature


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    init_db(conn)
    yield conn
    conn.close()


def put(conn, raw_dir, source_id, external_id, content: bytes, suffix=""):
    return store(
        conn,
        raw_dir,
        source_id=source_id,
        external_id=external_id,
        url=f"https://example.org/{external_id}",
        fetched_at="2026-10-26T09:00:00Z",
        chunks=[content],
        suffix=suffix,
    )


def an_zip(*names: str, legacy_export: bool = False) -> bytes:
    """Archive au format de l'open data AN, construite à partir de vrais dossiers."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        dossiers = [json.loads((FIXTURES / "an" / n).read_text("utf-8")) for n in names]
        if legacy_export:  # format de la XIVe législature : un seul fichier
            export = {"export": {"dossiersLegislatifs": {"dossier": dossiers}}}
            archive.writestr("Dossiers_Legislatifs_XIV.json", json.dumps(export))
        else:
            for name, dossier in zip(names, dossiers, strict=True):
                archive.writestr(f"json/dossierParlementaire/{name}", json.dumps(dossier))
            archive.writestr("json/document/IGNORE.json", "{}")
    return buffer.getvalue()


def by_uid(drafts):
    return {d.attributes["acte_uid"]: d for d in drafts}


# --- Engagements 49.3 (open data AN) ---------------------------------------------------


def test_known_case_plf_2023_first_part(conn, tmp_path):
    """Cas connu : 49.3 du 19 octobre 2022 sur la première partie du PLF 2023."""
    raw = tmp_path / "raw"
    put(conn, raw, "an_opendata", "L16", an_zip("DLR5L16N45988.json", "DLR5L16N46497.json"))
    fact = by_uid(parlement.extract_49_3(conn, raw))["L16-VD209592"]

    assert fact.fact_type == "engagement_49_3"
    assert fact.occurred_on == "2022-10-19"
    assert fact.official_ref == "DECLANR5L16B0273-N0"
    assert fact.title.startswith("Engagement de la responsabilité du Gouvernement sur la première")
    attrs = fact.attributes
    assert attrs["texte_uid"] == "DLR5L16N45988"  # dossier du texte, pas le dossier dédié
    assert attrs["texte_titre"] == "Projet de loi de finances pour 2023"
    assert attrs["dossier_dedie_uid"] == "DLR5L16N46497"
    assert attrs["lecture"] == "AN1"
    assert attrs["censure_adoptee"] is False
    assert attrs["url"] == "https://www.assemblee-nationale.fr/dyn/16/dossiers/DLR5L16N45988"


def test_plf_2023_dossier_counts_its_five_engagements(conn, tmp_path):
    raw = tmp_path / "raw"
    put(conn, raw, "an_opendata", "L16", an_zip("DLR5L16N45988.json"))
    drafts = parlement.extract_49_3(conn, raw)
    assert sorted(d.occurred_on for d in drafts) == [
        "2022-10-19",
        "2022-11-02",
        "2022-12-08",
        "2022-12-11",
        "2022-12-15",
    ]
    assert {d.attributes["lecture"] for d in drafts} == {"AN1", "ANNLEC", "ANLDEF"}


def test_known_case_censure_adopted_on_plfss_2025(conn, tmp_path):
    """Cas connu : 49.3 du 2 décembre 2024, motion de censure adoptée le 4 décembre."""
    raw = tmp_path / "raw"
    put(conn, raw, "an_opendata", "L17", an_zip("DLR5L17N50588.json", "DLR5L17N50975.json"))
    fact = by_uid(parlement.extract_49_3(conn, raw))["L17-VD222534"]
    assert fact.occurred_on == "2024-12-02"
    assert fact.attributes["lecture"] == "CMP"
    assert fact.attributes["censure_adoptee"] is True


def test_dedicated_dossier_alone_is_kept_but_flagged(conn, tmp_path):
    raw = tmp_path / "raw"
    put(conn, raw, "an_opendata", "L16", an_zip("DLR5L16N46497.json"))
    fact = by_uid(parlement.extract_49_3(conn, raw))["L16-VD209592"]
    assert fact.attributes["texte_rattache"] is False
    assert fact.attributes["texte_uid"] == "DLR5L16N46497"


def test_legacy_l14_export_format_is_read(conn, tmp_path):
    raw = tmp_path / "raw"
    content = an_zip("DLR5L16N45988.json", legacy_export=True)
    put(conn, raw, "an_opendata", "L14", content)
    assert len(parlement.extract_49_3(conn, raw)) == 5


def test_same_act_in_two_archives_gives_one_fact_citing_both(conn, tmp_path):
    raw = tmp_path / "raw"
    a = put(conn, raw, "an_opendata", "L16", an_zip("DLR5L16N45988.json"))
    b = put(conn, raw, "an_opendata", "L17", an_zip("DLR5L16N45988.json", "DLR5L16N46497.json"))
    fact = by_uid(parlement.extract_49_3(conn, raw))["L16-VD209592"]
    assert fact.raw_document_ids == (a.id, b.id)


def test_only_latest_version_of_an_archive_is_read(conn, tmp_path):
    raw = tmp_path / "raw"
    put(conn, raw, "an_opendata", "L16", an_zip("DLR5L17N50588.json"))
    store(
        conn,
        raw,
        source_id="an_opendata",
        external_id="L16",
        url="u",
        fetched_at="2026-10-27T09:00:00Z",
        chunks=[an_zip("DLR5L16N45988.json")],
    )
    dates = {d.occurred_on[:4] for d in parlement.extract_49_3(conn, raw)}
    assert dates == {"2022"}


def test_art_50_1_declarations_are_not_49_3():
    act = {
        "@xsi:type": "DeclarationGouvernement_Type",
        "typeDeclaration": {"fam_code": "Art.50.1"},
    }
    assert not parlement.is_49_3(act)


# --- Textes DILA (JORF / LEGI) ---------------------------------------------------------


def fixture(name: str) -> bytes:
    return next((FIXTURES / "dila").glob(f"{name}_*.xml")).read_bytes()


def test_parse_real_ordonnance_article_38():
    meta = dila.parse_texte_version(fixture("ord"))
    assert meta["nature"] == "ORDONNANCE"
    assert meta["cid"] == "JORFTEXT000029140226"
    assert meta["num"] == "2014-697"
    assert meta["date_texte"] == "2014-06-26"
    assert meta["constitution_articles"] == ["38"]
    assert dila.ordonnance_fondement(meta["constitution_articles"]) == "art38"


def test_parse_real_loi():
    meta = dila.parse_texte_version(fixture("loi"))
    assert meta["nature"] == "LOI"
    assert meta["cid"].startswith("JORFTEXT")
    assert meta["titre"].lower().startswith("loi")


def test_other_natures_are_ignored():
    data = fixture("loi").replace(b"<NATURE>LOI</NATURE>", b"<NATURE>DECRET</NATURE>")
    assert dila.parse_texte_version(data) is None


@pytest.mark.parametrize(
    ("visas", "articles", "fondement"),
    [
        ("Vu la Constitution, notamment son article 38 ;", ["38"], "art38"),
        ("Vu la Constitution, notamment ses articles 38 et 74-1 ;", ["38", "74-1"], "art38"),
        ("Vu la Constitution, notamment son article 74-1 ; Vu le code civil", ["74-1"], "art74-1"),
        ("Vu la Constitution, et notamment ses articles 34 et 92 ;", ["34", "92"], "art92"),
        ("Vu le code civil, notamment son article 38 ;", [], "inconnu"),
        ("", [], "inconnu"),
    ],
)
def test_constitution_articles_from_visas(visas, articles, fondement):
    assert dila.constitution_articles(visas) == articles
    assert dila.ordonnance_fondement(articles) == fondement


def dila_tar(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_extract_merges_jorf_and_legi_by_cid(conn, tmp_path):
    raw = tmp_path / "raw"
    path = "legi/global/x/JORFTEXT000029140226/texte/version/LEGITEXT000029143290.xml"
    j = put(
        conn,
        raw,
        "dila_jorf",
        "Freemium_jorf_global_20250713-140000.tar.gz",
        dila_tar({path: fixture("ord"), "a/article/x.xml": b"<ARTICLE/>"}),
    )
    renamed = fixture("ord").replace(b"facturation", b"FACTURATION")
    lg = put(
        conn,
        raw,
        "dila_legi",
        "LEGI_20250714-211000.tar.gz",
        dila_tar({f"20250714-211000/{path}": renamed, "x/texte/version/l.xml": fixture("loi")}),
    )
    drafts = {d.attributes["cid"]: d for d in dila.extract(conn, raw, tmp_path / "cache")}

    assert len(drafts) == 2
    ordonnance = drafts["JORFTEXT000029140226"]
    assert ordonnance.fact_type == "ordonnance_publiee"
    assert ordonnance.raw_document_ids == (j.id, lg.id)
    assert "FACTURATION" in ordonnance.title  # LEGI lu en dernier
    assert ordonnance.attributes["fondement"] == "art38"
    assert ordonnance.attributes["url"].endswith("/jorf/id/JORFTEXT000029140226")
    loi = next(d for cid, d in drafts.items() if cid != "JORFTEXT000029140226")
    assert loi.fact_type == "loi_promulguee"
    assert "fondement" not in loi.attributes


def test_scan_cache_is_reused(conn, tmp_path):
    raw = tmp_path / "raw"
    content = dila_tar({"x/texte/version/l.xml": fixture("loi")})
    put(conn, raw, "dila_legi", "Freemium_legi_global_20250713-140000.tar.gz", content)
    first = dila.extract(conn, raw, tmp_path / "cache")
    assert len(list((tmp_path / "cache").glob("*.jsonl"))) == 1
    assert dila.extract(conn, raw, tmp_path / "cache") == first


def test_archive_order_global_first_then_increments():
    docs = [
        {"external_id": "LEGI_20250715-205701.tar.gz"},
        {"external_id": "Freemium_legi_global_20250713-140000.tar.gz"},
        {"external_id": "LEGI_20250713-205013.tar.gz"},
    ]
    ordered = [d["external_id"] for d in sorted(docs, key=dila.archive_order)]
    assert ordered[0].startswith("Freemium") and ordered[1] == "LEGI_20250713-205013.tar.gz"


# --- Seed manuel ------------------------------------------------------------------------


def seed_rows():
    text = (ROOT / "data" / "seed" / "49_3_historique.csv").read_text("utf-8")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def test_seed_matches_official_totals_and_stops_before_an_open_data():
    rows = seed_rows()
    assert len(rows) == 82
    assert all(r["date_engagement"] < AN_OPEN_DATA_START for r in rows)
    assert all(r["source_url"].startswith("https://www.assemblee-nationale.fr/") for r in rows)
    assert len({r["texte_id"] for r in rows}) == 47


@pytest.mark.parametrize(
    ("motion", "adopted"),
    [
        ("25.11.1959 / 27.11.1959 / 277-109", False),
        ("pas de motion", False),
        ("13.02.2003 / 15.02.2003 / 288 requis / 177 obtenus", False),
        ("02.12.2024 / 04.12.2024 / 288 requis / 331 obtenus", True),
        ("x / y / 246-201 et 246-199", False),
    ],
)
def test_seed_censure_parsing(motion, adopted):
    assert seed.censure_adoptee(motion) is adopted


def test_seed_extraction(conn, tmp_path):
    raw = tmp_path / "raw"
    csv_bytes = (ROOT / "data" / "seed" / "49_3_historique.csv").read_bytes()
    doc = put(conn, raw, "seed_manuel", "49_3_historique.csv", csv_bytes, ".csv")
    drafts = seed.extract(conn, raw)
    assert len(drafts) == 82
    assert {d.extraction_method for d in drafts} == {"seed_manuel"}
    assert all(d.raw_document_ids == (doc.id,) for d in drafts)
    first = min(drafts, key=FactDraft.sort_key)
    assert first.occurred_on == "1959-11-25"
    assert first.attributes["texte_uid"] == "seed:LF1960"


# --- Écriture des faits -----------------------------------------------------------------


def draft(date, ref, raw_ids=(1,)):
    return FactDraft("D2", "loi_promulguee", date, f"Loi {ref}", ref, "test", raw_ids)


def test_write_facts_is_order_independent(tmp_path):
    a, b = draft("2020-01-02", "B"), draft("2020-01-01", "A")
    results = []
    for name, order in (("x", [a, b]), ("y", [b, a])):
        c = connect(tmp_path / f"{name}.sqlite")
        init_db(c)
        put(c, tmp_path / name, "dila_legi", "doc", b"x")
        write_facts(c, order)
        results.append([tuple(r) for r in c.execute("SELECT * FROM facts ORDER BY id")])
    assert results[0] == results[1]
    assert results[0][0][5] == "A"


def test_write_facts_refuses_fact_without_source(conn):
    with pytest.raises(ValueError, match="sans document"):
        write_facts(conn, [draft("2020-01-01", "A", raw_ids=())])


@pytest.mark.parametrize(
    ("nature", "titre", "date", "reason"),
    [
        ("ORDONNANCE", "Ordonnance n° 2014-697 du 26 juin 2014 relative à ...", "2014-06-26", None),
        (
            "ORDONNANCE",
            "Ordonnance no  2001-670 du 25 juillet 2001 portant ...",
            "2001-07-25",
            None,
        ),
        ("ORDONNANCE", "‎Ordonnance n°58-1100 du 17 novembre 1958", "1958-11-17", None),
        (
            "ORDONNANCE",
            "Ordonnance du 6 juillet 1998 du premier président de la Cour de cassation",
            "1998-07-06",
            "ordonnance non gouvernementale ou non numérotée",
        ),
        (
            "ORDONNANCE",
            "Rapport au Président de la République relatif à l'ordonnance n° 2025-521",
            "2025-06-12",
            "ordonnance non gouvernementale ou non numérotée",
        ),
        (
            "ORDONNANCE",
            "Ordonnance du 26 février 1958 N0 10-108, relative au classement des hôtels",
            "1958-02-26",
            "ordonnance non gouvernementale ou non numérotée",
        ),
        (
            "LOI",
            "Loi du 8 décembre 1960 relative à certains équipements militaires",
            "1960-12-08",
            None,
        ),
        ("LOI", "Loi n° 2023-23 du 24 janvier 2023", "2999-01-01", "date inconnue"),
    ],
)
def test_exclusion_rules(nature, titre, date, reason):
    text = {"nature": nature, "titre": titre, "date_texte": date}
    assert dila.exclusion_reason(text) == reason


def text(cid, num, titre, nature="LOI", articles=()):
    return {
        "cid": cid,
        "num": num,
        "titre": titre,
        "nature": nature,
        "nor": None,
        "date_texte": "2020-03-23",
        "date_publi": "2020-03-24",
        "constitution_articles": list(articles),
    }


def test_rectificatif_is_merged_into_the_original_text():
    groups = dila.group_by_official_number(
        [
            text("JORFTEXT2", "2020-290", "LOI n° 2020-290 du 23 mars 2020 (rectificatif)"),
            text("JORFTEXT9", "2020-290", "LOI n° 2020-290 du 23 mars 2020 d'urgence"),
            text("JORFTEXT5", "2020-291", "LOI n° 2020-291 de finances rectificative pour 2020"),
            text("JORFTEXT7", None, "Loi du 8 décembre 1960"),
        ]
    )
    assert [[t["cid"] for t in g] for g in groups] == [
        ["JORFTEXT7"],
        ["JORFTEXT9", "JORFTEXT2"],  # l'original d'abord, le rectificatif en doublon
        ["JORFTEXT5"],  # une loi de finances rectificative n'est pas un rectificatif
    ]


def test_merged_ordonnance_keeps_visas_from_any_version():
    group = [
        text("A", "2014-697", "Ordonnance n° 2014-697", "ORDONNANCE"),
        text("B", "2014-697", "Ordonnance n° 2014-697 (rectificatif)", "ORDONNANCE", ["38"]),
    ]
    draft = dila.to_draft(group, {1, 2})
    assert draft.attributes["fondement"] == "art38"
    assert draft.attributes["cid_doublons"] == ["B"]
    assert draft.raw_document_ids == (1, 2)


@pytest.mark.parametrize(
    ("titre", "convention"),
    [
        ("LOI n° 2023-115 du 21 février 2023 autorisant l'approbation de l'accord entre ...", True),
        ("Loi n° 86-1275 du 16 décembre 1986 autorisant la ratification de l'Acte unique", True),
        ("Loi n°59-855 AUTORISANT LE PRESIDENT DE LA REPUBLIQUE A RATIFIER LA CONVENTION", True),
        ("Loi n°61-767 AUTORISANT : 1E - LA RATIFICATION DU TRAITE DE COOPERATION", True),
        ("Loi n°79-549 PORTANT AUTORISATION D'APPROBATION DE L'ACCORD FRANCO-ESPAGNOL", True),
        ("Loi n°60-682 PORTANT APPROBATION DES ACCORDS PARTICULIERS SIGNES LE 22 JUIN 1960", True),
        ("Loi n°71-475 APPROUVANT LA CONVENTION FISCALE ENTRE LE GOUVERNEMENT ...", True),
        (
            "LOI n° 2006-823 autorisant l'approbation de la Charte européenne de l'autonomie "
            "locale (collectivités)",
            True,
        ),
        ("LOI n° 2016-482 autorisant l'accession de la France au protocole sur le statut", True),
        ("LOI n° 2019-1428 du 24 décembre 2019 d'orientation des mobilités", False),
        ("Loi n° 91-1322 du 30 décembre 1991 de finances rectificative pour 1991", False),
        ("Loi n°64-549 RATIFIANT LE DECRET 64-294 DU 4 AVRIL 1964 (DROITS DE DOUANE)", False),
        ("LOI n° 2023-1107 portant transposition de l'accord national interprofessionnel", False),
        ("LOI n° 2015-264 autorisant l'accord local de répartition des sièges", False),
        ("LOI no 99-589 portant approbation d'un avenant à la concession", False),
        (
            "Loi n° 93-944 approuvant une convention conclue entre le ministre de l'économie et le "
            "gouverneur de la Banque de France",
            False,
        ),
        ("Loi n°64-1231 LE GOUVERNEMENT EST AUTORISE A PRENDRE PAR ORDONNANCES (ACCORDS)", False),
    ],
)
def test_convention_internationale(titre, convention):
    assert dila.is_convention_internationale(titre) is convention
