"""Tête de page : repères internationaux et opinion (fichiers de data/seed lus à l'export)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "export_data", ROOT / "front/prototype/export_data.py"
)
export_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_data)


def test_reperes_internationaux():
    r = export_data.reperes_internationaux()
    assert {x["source"] for x in r} == {"V-Dem", "Freedom House"}
    assert all(isinstance(x["categorie_democratique"], bool) for x in r)
    assert all(x["url"].startswith("https://") for x in r)


def test_opinion_cevipof():
    o = export_data.opinion()
    assert o["serie"][0] == {"date": "2009-12", "bien": 50, "mal": 48, "note": ""}
    assert o["serie"][-1]["date"] == "2026-01" and o["serie"][-1]["bien"] == 23
    assert all(95 <= s["bien"] + s["mal"] <= 100 for s in o["serie"])  # NSP : 0 à 5 %
    assert o["plus_bas"]  # 23 % : plus bas de la série
    assert o["autres"]["q55_systeme_democratique_bon"] == 82
    assert [p["pays"] for p in o["pays"]][0] == "France" and len(o["pays"]) == 5


def test_opinion_plus_bas_faux_si_deja_atteint(tmp_path):
    f = tmp_path / "o.csv"
    f.write_text(
        "indicateur;pays;date;valeur;page;note\n"
        "q22_fonctionne_bien;France;2020-01;30;1;\nq22_fonctionne_mal;France;2020-01;68;1;\n"
        "q22_fonctionne_bien;France;2021-01;30;1;\nq22_fonctionne_mal;France;2021-01;69;1;\n"
    )
    assert not export_data.opinion(f)["plus_bas"]


def test_donnees_telechargeables(tmp_path):
    from storage.db import connect, init_db

    conn = connect(tmp_path / "b.sqlite")
    init_db(conn)
    src = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO raw_documents (source_id, external_id, url, fetched_at, sha256, path)"
        " VALUES (?, 'doc1', 'https://officiel.example/doc1', '2026-01-01', ?, 'x')",
        (src, "a" * 64),
    )
    for ind, titre in (("D4.dissolutions_administratives", "Décret X"), (export_data.D7, "Nom")):
        conn.execute(
            "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, attributes,"
            " extraction_method) VALUES (?, 't', '2025-05-01', ?, '{}', 'm')",
            (ind, titre),
        )
        conn.execute("INSERT INTO fact_sources VALUES (last_insert_rowid(), 1)")
    dims = [
        {"id": "D4.dissolutions_administratives", "metrique": "nb_dissolutions",
         "mensuel": [{"date": "2025-05-31", "v": 1.0}]},
        {"id": export_data.D7, "metrique": "nb", "mensuel": []},
    ]  # fmt: skip
    export_data.ecrire_donnees(conn, dims, tmp_path / "d")
    serie = (tmp_path / "d" / "D4.dissolutions_administratives-serie.csv").read_text()
    assert serie == "fin_de_mois,nb_dissolutions\n2025-05-31,1.0\n"
    faits = (tmp_path / "d" / "D4.dissolutions_administratives-faits.csv").read_text()
    assert "2025-05-01,t,Décret X,,https://officiel.example/doc1," in faits
    assert "a" * 64 in faits and faits.rstrip().endswith(",m,non")
    assert "Nom" not in (tmp_path / "d" / f"{export_data.D7}-faits.csv").read_text()


def test_csv_faits_sans_formule(tmp_path, monkeypatch):
    monkeypatch.setattr(
        export_data,
        "faits_indicateur",
        lambda conn, i: [dict.fromkeys(export_data.COLONNES_FAITS, "=1+1")],
    )
    export_data.ecrire_donnees(None, [{"id": "X", "metrique": "m", "mensuel": []}], tmp_path)
    assert "'=1+1" in (tmp_path / "X-faits.csv").read_text()


def test_fait_presse_d7_marque_verifie(monkeypatch, tmp_path):
    from storage.db import connect, init_db

    conn = connect(tmp_path / "b.sqlite")
    init_db(conn)
    for ftype in ("fait_presse_valide", "constat_institutionnel"):
        conn.execute(
            "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, attributes,"
            " extraction_method) VALUES (?, ?, '2025-05-01', 't', '{}', 'm')",
            (export_data.D7, ftype),
        )
    v = {
        f["type"]: f["verifie_par_un_humain"]
        for f in export_data.faits_indicateur(conn, export_data.D7)
    }
    assert v == {"fait_presse_valide": "oui", "constat_institutionnel": "non"}
