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
    '<h2 id="t-indice" class="a"></h2><p id="indice-text" class="b"></p>'
    '<ol id="overview" class="c"></ol></body></html>'
)


def test_position_au_rang_moyen_et_indice():
    assert seo.position(DATA["dimensions"][0]) == 0.375
    assert seo.position(DATA["dimensions"][1]) == 0.875
    assert seo.indice(DATA["dimensions"]) == 62


def test_page_lisible_sans_javascript(tmp_path):
    page = seo.ecrire(tmp_path, PAGE, "window.X = " + json.dumps(DATA) + ";", None)
    assert '<h2 id="t-indice" class="a">62 sur 100 : dans l&#x27;ensemble, plus haut' in page
    assert page.count("<li>") == 2 and 'name="description"' in page
    assert '"@type": "Dataset"' in page and "canonical" not in page
    assert not (tmp_path / "sitemap.xml").exists()
    assert "Sitemap" not in (tmp_path / "robots.txt").read_text()
    assert "62 sur 100" in (tmp_path / "barometre.md").read_text()


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
    assert seo.indice(dims) == 62
    dims[1]["fin_couverture"] = "2025-12-31"  # la position 0.875 ne compte plus
    assert seo.indice(dims) == round(100 * seo.position(dims[0]))
    data = {**DATA, "dimensions": dims}
    _, texte, items = seo.vue_statique(data)
    assert "relevé arrêté au 31 décembre 2025" in texte and "hors indice" in items
