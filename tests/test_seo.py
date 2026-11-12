# ruff: noqa: E501
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "front" / "publication"))
import seo  # noqa: E402


def dim(id_, actuel, valeurs, metrique="nb_dissolutions"):
    return {
        "id": id_,
        "code": id_[:2],
        "label": id_,
        "metrique": metrique,
        "actuel": actuel,
        "debut_historique": "1990-01-01",
        "mensuel": [{"date": "x", "v": v} for v in valeurs],
    }


DATA = {
    "fin_donnees": "2026-11-04",
    "dimensions": [
        dim("D4.dissolutions_administratives", 0, [0, 0, 0, 1]),  # 3 égaux sur 4 : 37,5
        dim("D3.regimes_exception", 5, [0, 1, 2, 5]),  # 3 plus bas + 1/2 égal : 87,5
    ],
    "sources": [{"nom": "S", "url": "https://s.example", "licence": "L"}],
}
PAGE = (
    "<!doctype html><html><head><title>x</title></head><body>"
    '<p id="reponse" class="r"></p><p id="reponse-opinion" class="o"></p><div id="ecart" class="e"></div>'
    '<h2 id="t-indice" class="a"></h2><p id="indice-text" class="b"></p>'
    '<ol id="overview" class="c"></ol></body></html>'
)


def test_position_au_rang_moyen_et_indice():
    assert seo.position(DATA["dimensions"][0]) == 0.375
    assert seo.position(DATA["dimensions"][1]) == 0.875
    i = seo.indice(DATA)
    assert i["valeur"] == 62.5 and i["ecart"] == 12  # round(62,5) = 62 (arrondi au pair)


def test_page_lisible_sans_javascript(tmp_path):
    page = seo.ecrire(tmp_path, PAGE, "window.X = " + json.dumps(DATA) + ";", None)
    assert '<div id="ecart" class="e">+12</div>' in page
    assert (
        '<h2 id="t-indice" class="a">Dans l&#x27;ensemble, les indicateurs suivis sont plus hauts'
        in page
    )
    assert page.count("<li>") == 2 and 'name="description"' in page
    assert '"@type": "Dataset"' in page and "canonical" not in page
    assert not (tmp_path / "sitemap.xml").exists()
    assert "Sitemap" not in (tmp_path / "robots.txt").read_text()
    assert "**+12**" in (tmp_path / "barometre.md").read_text()


def test_domaine_connu(tmp_path):
    page = seo.ecrire(tmp_path, PAGE, json.dumps(DATA), "https://exemple.fr/")
    assert '<link rel="canonical" href="https://exemple.fr/">' in page
    assert "<loc>https://exemple.fr/barometre.md</loc>" in (tmp_path / "sitemap.xml").read_text()
    assert "https://exemple.fr/indicateurs.csv" in (tmp_path / "llms.txt").read_text()


def test_htaccess_utf8_et_redirection_https(tmp_path):
    seo.ecrire(tmp_path, PAGE, json.dumps(DATA), "https://exemple.fr/")
    h = (tmp_path / ".htaccess").read_text()
    assert "AddCharset UTF-8 .md .txt" in h
    assert r"RewriteCond %{HTTP_HOST} !^exemple\.fr$ [NC]" in h
    assert "RewriteRule ^ https://exemple.fr%{REQUEST_URI} [R=301,L]" in h
    assert r"!^/\.well-known/" in h


def test_htaccess_sans_redirection_si_pas_https(tmp_path):
    for url in (None, "http://exemple.fr/"):
        seo.ecrire(tmp_path, PAGE, json.dumps(DATA), url)
        h = (tmp_path / ".htaccess").read_text()
        assert "AddDefaultCharset UTF-8" in h and "Rewrite" not in h


def test_htaccess_entetes_cache_et_page_404(tmp_path):
    seo.ecrire(tmp_path, PAGE, json.dumps(DATA), "https://exemple.fr/")
    h = (tmp_path / ".htaccess").read_text()
    assert "ErrorDocument 404 /404.html" in h
    assert 'Strict-Transport-Security "max-age=31536000"' in h
    assert 'X-Content-Type-Options "nosniff"' in h and "default-src 'self'" in h
    assert 'Cache-Control "public, max-age=31536000, immutable"' in h
    assert 'Cache-Control "no-cache"' in h
    assert "noindex" in (tmp_path / "404.html").read_text()


def test_htaccess_sans_hsts_hors_https(tmp_path):
    seo.ecrire(tmp_path, PAGE, json.dumps(DATA), None)
    assert "Strict-Transport-Security" not in (tmp_path / ".htaccess").read_text()


def test_image_de_partage_seulement_avec_le_domaine(tmp_path):
    page = seo.ecrire(tmp_path, PAGE, json.dumps(DATA), "https://exemple.fr/")
    assert '<meta property="og:image" content="https://exemple.fr/apercu.png">' in page
    assert 'content="summary_large_image"' in page
    page = seo.ecrire(tmp_path, PAGE, json.dumps(DATA), None)
    assert "og:image" not in page and 'twitter:card" content="summary"' in page


def test_indicateur_au_releve_arrete_hors_indice():
    dims = [dict(d) for d in DATA["dimensions"]]
    dims[1]["fin_couverture"] = "2025-12-31"  # la position 0.875 ne compte plus
    data = {**DATA, "dimensions": dims}
    assert seo.indice(data)["valeur"] == 100 * seo.position(dims[0])
    *_, texte, items = seo.vue_statique(data)
    assert "relevé arrêté au 31 décembre 2025" in texte and "hors indice" in items


def test_indicateur_hors_indice_par_raison_explicite():
    """D7 pendant la reprise : `hors_indice` porte la raison, comme sur la page."""
    dims = [dict(d) for d in DATA["dimensions"]]
    dims[1]["hors_indice"] = "reprise depuis juillet 2024 en cours de collecte"
    data = {**DATA, "dimensions": dims}
    assert seo.indice(data)["valeur"] == 100 * seo.position(dims[0])
    *_, texte, items = seo.vue_statique(data)
    assert "reprise depuis juillet 2024 en cours de collecte" in texte
    assert "hors indice" in items


def test_nombre_d_indicateurs_calcule():
    data = {
        **DATA,
        "dimensions": [dict(d) for d in DATA["dimensions"]] * 7 + [DATA["dimensions"][0]],
    }
    assert "15 indicateurs sourcés" in seo.description(data)
    assert "15 indicateurs sourcés" in seo.entete(data, None)
    assert "Quinze indicateurs sourcés" in seo.llms_txt(data, None)
    assert "## Les 15 indicateurs" in seo.resume_md(data, None)
    assert "13 indicateurs" not in seo.appliquer(PAGE, data, None)


def test_donnees_structurees_avec_raison_hors_indice():
    dims = [dict(d) for d in DATA["dimensions"]]
    dims[1]["hors_indice"] = "reprise en cours"
    assert "Hors indice : reprise en cours" in seo.json_ld({**DATA, "dimensions": dims}, None)


REPERES = [
    {"source": "V-Dem", "edition": "R 2026", "annee_donnees": "2025", "valeur": "0.80",
     "echelle": "de 0 à 1", "rang": "9e", "url": "https://v.example",
     "categorie": "démocratie libérale, à la limite de la démocratie électorale",
     "categorie_democratique": True},
    {"source": "FH", "edition": "F 2026", "annee_donnees": "2025", "valeur": "89",
     "echelle": "sur 100", "rang": "", "url": "https://f.example", "categorie": "pays libre",
     "categorie_democratique": True},
]  # fmt: skip


def test_reponse_des_classements_internationaux(tmp_path):
    data = {**DATA, "reperes": REPERES}
    assert seo.reponse(data).startswith("Oui. Les classements internationaux")
    assert "à la limite de sa catégorie inférieure" in seo.reponse(data)
    page = seo.ecrire(tmp_path, PAGE, json.dumps(data), None)
    assert '<p id="reponse" class="r">Oui.' in page
    md = (tmp_path / "barometre.md").read_text()
    assert "## La France est-elle encore une démocratie ?" in md and "https://f.example" in md
    partage = [{**REPERES[0], "categorie_democratique": False}, REPERES[1]]
    assert "ne s'accordent pas : 1 sur 2" in seo.reponse({**DATA, "reperes": partage})
    assert seo.reponse(DATA) == ""


def test_contre_pouvoir_position_donnee_hors_indice():
    dims = [dict(d) for d in DATA["dimensions"]]
    dims[1].update(contre_pouvoir=True, hors_indice="indicateur de contre-pouvoir : …")
    md = seo.resume_md({**DATA, "dimensions": dims}, None)
    assert "88 (contre-pouvoir, hors indice)" in md


OPINION = {
    "question": "Q ?", "source": "CEVIPOF", "edition": "vague 17", "terrain": "janvier 2026",
    "echantillon": "3 166", "url": "https://c.example", "plus_bas": True,
    "serie": [{"date": "2009-12", "bien": 50, "mal": 48}, {"date": "2026-01", "bien": 23, "mal": 76}],
    "autres": {"q55_systeme_democratique_bon": 82},
}  # fmt: skip


def test_reponse_opinion(tmp_path):
    data = {**DATA, "opinion": OPINION}
    r = seo.reponse_opinion(data)
    assert "76\u00a0% des Français pensent que la démocratie fonctionne mal" in r
    assert "le niveau le plus bas depuis 2009" in r and "Mais 82\u00a0%" in r
    page = seo.ecrire(tmp_path, PAGE, json.dumps(data), None)
    assert '<p id="reponse-opinion" class="o">Ils jugent' in page
    md = (tmp_path / "barometre.md").read_text()
    assert "### Ce qu'en pensent les Français" in md and "2026-01 23 %" in md
    assert seo.reponse_opinion(DATA) == ""
