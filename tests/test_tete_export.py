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
