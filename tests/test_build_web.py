import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "front" / "publication"))
import build  # noqa: E402

PAGE = """<!doctype html><html><head>
  <script src="https://cdn.tailwindcss.com/3.4.5"></script>
  <script>
    tailwind.config = { theme: {} };
  </script>
  <style>.a{color:red}</style>
</head><body></body></html>"""


def test_feuille_construite_remplace_le_cdn_apres_les_styles_de_la_page(tmp_path):
    css = tmp_path / "tailwind.css"
    css.write_text(".p-4{padding:1rem}\n")
    out = build.feuille_de_style(PAGE, css)
    assert "cdn.tailwindcss.com" not in out and "tailwind.config" not in out
    assert out.index(".a{color:red}") < out.index(".p-4{padding:1rem}") < out.index("</head>")


def test_sans_feuille_construite_le_cdn_reste(tmp_path):
    assert build.feuille_de_style(PAGE, tmp_path / "absent.css") == PAGE


def test_bloc_cdn_introuvable():
    with pytest.raises(ValueError):
        build.feuille_de_style("<html><head></head></html>", Path("x"))


def test_configuration_identique_a_la_page():
    """tailwind.config.js reprend le thème du bloc tailwind.config de la page."""
    racine = Path(__file__).resolve().parents[1]
    page = (racine / "front" / "prototype" / "index.html").read_text(encoding="utf-8")
    conf = (racine / "front" / "publication" / "tailwind.config.js").read_text(encoding="utf-8")
    bloc = page[page.index("theme: {") : page.index("</script>", page.index("theme: {"))]
    lignes = [ligne.strip() for ligne in bloc.splitlines() if ":" in ligne and "theme" not in ligne]
    assert lignes and all(ligne in conf for ligne in lignes)


def _echappe(classe: str) -> str:
    """Sélecteur CSS d'une classe, échappé comme le fait Tailwind."""
    out = ""
    for c in classe:
        if c == ",":
            out += "\\2c "
        elif c.isalnum() or c in "-_":
            out += c
        else:
            out += "\\" + c
    return out


def test_feuille_construite_a_jour_pour_les_classes_a_valeur_libre():
    """Les classes à valeur libre (`x-[…]`) de la page sont dans tailwind.css : sinon relancer
    `make css` (une classe absente casserait la mise en page de la version web)."""
    racine = Path(__file__).resolve().parents[1]
    css_path = racine / "front" / "publication" / "tailwind.css"
    if not css_path.exists():
        pytest.skip("tailwind.css absent : la version web garde le CDN")
    page = (racine / "front" / "prototype" / "index.html").read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    classes = {
        c
        for attr in re.findall(r"""class(?:Name)?\s*=\s*['"`]([^'"`]*)['"`]""", page)
        for c in attr.split()
        if re.fullmatch(r"[\w:-]+-\[[^\]\s$]+\]", c)
    }
    assert classes
    absentes = sorted(c for c in classes if "." + _echappe(c) not in css)
    assert not absentes, f"relancer make css : {absentes}"


def test_version_web_sans_service_tiers():
    """La page publique ne charge ni Google Fonts ni cdnjs, et l'avis cookies le dit."""
    racine = Path(__file__).resolve().parents[1]
    page = (racine / "front" / "prototype" / "index.html").read_text(encoding="utf-8")
    out = build.polices_locales(page)
    for externe in ("fonts.googleapis", "fonts.gstatic", "cdnjs"):
        assert externe not in out
    assert build.AVIS_LOCAL in out and build.AVIS_TIERS not in out
    for lien in re.findall(r'href="(assets/[^"]+)"', out):
        assert (racine / "front" / "publication" / lien).exists(), lien
