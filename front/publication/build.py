"""Version publiable du prototype (page Artifact de claude.ai).

Lit `front/prototype/index.html` et `front/prototype/data.js` (à régénérer d'abord avec
`make prototype-data`) et écrit `front/publication/dist/` :
  - `index.html` : contenu de la page sans enveloppe `<!doctype>/<html>/<head>/<body>` (ajoutée
    à la publication), sans Font Awesome (feuilles de style externes bloquées hors Google
    Fonts : icônes décoratives masquées, chevrons et bouton de thème dessinés en CSS), avec un
    encadré « Documents de travail » dans la section Méthode ;
  - `data.js` : copie des données, publiée à côté de la page.

Le prototype local (`make prototype`) n'est pas modifié.

Usage :
    python front/publication/build.py [--dossier-seuils URL] [--verification URL]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "front" / "prototype"
DIST = Path(__file__).resolve().parent / "dist"
TITRE = "Baromètre démocratique"
DOSSIER_SEUILS = "https://claude.ai/artifact/TnbzQb6cfDVMz5YY8E6KaJ"
VERIFICATION = "https://claude.ai/artifact/ThcB5kWYainR3xq3fGNhEp"

SHIM = """
    /* Publication : Font Awesome n'est pas chargé. */
    i.fa-solid { display: none; }
    i.chev { display: inline-block; width: .5em; height: .5em; border: solid var(--muted);
      border-width: 0 1.5px 1.5px 0; transform: rotate(-45deg); margin-right: .2em; }
    details[open] i.chev { transform: rotate(45deg); }
    #theme i { display: inline-block; width: .9em; height: .9em; border-radius: 50%;
      border: 1.5px solid currentColor; vertical-align: -.1em;
      background: linear-gradient(90deg, currentColor 50%, transparent 50%); }
"""

DOCUMENTS = """
      <div class="mt-8 rounded-lg border border-rule p-4 text-sm text-ink2 space-y-2">
        <h3 class="font-semibold text-ink">Documents de travail</h3>
        <p>Aucun indicateur n'est encore noté : aucun seuil n'est fixé.
          Le <a class="underline" href="{dossier}">dossier pour la fixation des seuils</a> présente,
          pour chaque indicateur, son historique, ses limites et des propositions de bornes.</p>
        <p>Le <a class="underline" href="{verification}">document de vérification humaine</a> liste
          les chiffres et rapprochements en cours de relecture.</p>
        <p class="text-xs text-muted">Ces deux documents sont accessibles sur invitation.</p>
      </div>
"""


JOURNAL = ROOT / "docs" / "journal-modifications.md"


def copier_donnees(dist: Path) -> None:
    """Données téléchargeables (front/prototype/donnees/, écrites par export_data.py) et journal
    des modifications de méthode, publiés à côté de la page."""
    shutil.rmtree(dist / "donnees", ignore_errors=True)
    if (SOURCE / "donnees").is_dir():
        shutil.copytree(SOURCE / "donnees", dist / "donnees")
    shutil.copyfile(JOURNAL, dist / "journal.md")


def build(dossier: str, verification: str, dist: Path = DIST) -> Path:
    html = (SOURCE / "index.html").read_text(encoding="utf-8")
    head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    body_match = re.search(r'<body class="([^"]*)">(.*?)</body>', html, re.S)
    body_class, body = body_match.group(1), body_match.group(2)

    # En-tête : titre de produit, sans meta (ajoutées à la publication) ni Font Awesome.
    head = re.sub(r"\s*<meta [^>]*>", "", head)
    head = re.sub(r"\s*<title>.*?</title>", "", head)
    font_awesome = r'\s*<link rel="stylesheet" href="https://cdnjs[^"]*font-awesome[^"]*">'
    head = re.sub(font_awesome, "", head)
    if "font-awesome" in head:
        raise ValueError("Font Awesome encore présent dans l'en-tête")
    head = head.replace("</style>", SHIM + "  </style>", 1)

    marker = '      <ul id="sources"'
    if marker not in body:
        raise ValueError("section Sources introuvable")
    end = body.index("</ul>", body.index(marker)) + len("</ul>")
    body = body[:end] + DOCUMENTS.format(dossier=dossier, verification=verification) + body[end:]

    page = (
        f"<title>{TITRE}</title>\n{head.strip()}\n"
        f'<div class="{body_class}">\n{body.strip()}\n</div>\n'
    )
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(page, encoding="utf-8")
    shutil.copyfile(SOURCE / "data.js", dist / "data.js")
    copier_donnees(dist)
    return dist


WEB = Path(__file__).resolve().parent / "web"


TAILWIND_CSS = Path(__file__).resolve().parent / "tailwind.css"
TAILWIND_CDN = re.compile(
    r'\s*<script src="https://cdn\.tailwindcss\.com[^"]*"></script>'
    r"\s*<script>\s*tailwind\.config = .*?</script>",
    re.S,
)


def feuille_de_style(html: str, css_path: Path = TAILWIND_CSS) -> str:
    """Remplace le CDN Tailwind (compilation dans le navigateur, déconseillée en production) par
    la feuille construite par `make css`, insérée dans la page. Sans elle, le CDN reste.
    Les classes sont celles de front/prototype/index.html : relancer `make css` après les avoir
    modifiées (la configuration est dans tailwind.config.js)."""
    if not TAILWIND_CDN.search(html):
        raise ValueError("bloc Tailwind (CDN + tailwind.config) introuvable dans la page")
    if not css_path.exists():
        print(f"[publication] {css_path.name} absent (make css) : CDN Tailwind conservé")
        return html
    css = css_path.read_text(encoding="utf-8").strip().replace("</", "<\\/")
    # En fin d'en-tête, comme le CDN qui ajoute sa feuille après les styles de la page.
    html = TAILWIND_CDN.sub("", html, count=1)
    return html.replace("</head>", f"  <style>{css}</style>\n</head>", 1)


ASSETS = Path(__file__).resolve().parent / "assets"
POLICES_EXTERNES = re.compile(
    r'\s*<link rel="preconnect" href="https://fonts\.googleapis\.com">'
    r'\s*<link rel="preconnect" href="https://fonts\.gstatic\.com" crossorigin>'
    r'\s*<link href="https://fonts\.googleapis\.com/css2\?family=Source\+Serif\+4[^"]*"'
    r' rel="stylesheet">'
    r'\s*<link rel="stylesheet" href="https://cdnjs\.cloudflare\.com/ajax/libs/font-awesome/'
    r'6\.5\.1/css/all\.min\.css">'
)
POLICES_LOCALES = """
  <link rel="preload" href="assets/polices/source-serif-4-latin.woff2" as="font"
        type="font/woff2" crossorigin>
  <link rel="stylesheet" href="assets/polices/source-serif-4.css">
  <link rel="stylesheet" href="assets/fa/css/fontawesome.min.css">
  <link rel="stylesheet" href="assets/fa/css/solid.min.css">"""
AVIS_TIERS = "Polices et icônes : Google Fonts et cdnjs (Cloudflare), qui voient votre adresse IP."
AVIS_LOCAL = "Polices et icônes sont servies par ce site : aucun service tiers."


def polices_locales(html: str) -> str:
    """Polices (Source Serif 4) et icônes (Font Awesome Solid) servies par le site lui-même :
    aucune requête vers Google Fonts ni cdnjs, donc aucune adresse IP transmise à un tiers."""
    if not POLICES_EXTERNES.search(html):
        raise ValueError("liens Google Fonts / Font Awesome introuvables dans la page")
    if AVIS_TIERS not in html:
        raise ValueError("phrase de l'avis cookies sur les services tiers introuvable")
    html = POLICES_EXTERNES.sub(lambda _: POLICES_LOCALES, html, count=1)
    return html.replace(AVIS_TIERS, AVIS_LOCAL)


def seo_apercu() -> str:
    import seo  # module voisin (référencement)

    return seo.APERCU


def build_web(dist: Path = WEB, site_url: str | None = None) -> Path:
    """Version pour un hébergement web public : la page du prototype telle quelle.

    Document HTML complet (Font Awesome compris) ; aucun lien vers les documents de travail
    privés de claude.ai. Référencement (contenu sans JavaScript, métadonnées, `barometre.md`,
    `indicateurs.csv`, `llms.txt`, `robots.txt`, `sitemap.xml`) : voir `seo.py`.
    """
    html = (SOURCE / "index.html").read_text(encoding="utf-8")
    if not html.lstrip().lower().startswith("<!doctype html>"):
        raise ValueError("la page du prototype n'est plus un document HTML complet")
    if "claude.ai/artifact" in html:
        raise ValueError("lien vers un document claude.ai privé dans la page publique")
    import seo  # module voisin (référencement)

    html = polices_locales(feuille_de_style(html))
    for externe in ("fonts.googleapis", "fonts.gstatic", "cdnjs.cloudflare"):
        if externe in html:
            raise ValueError(f"ressource externe restante dans la page publique : {externe}")
    dist.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(dist / "assets", ignore_errors=True)
    shutil.copytree(ASSETS, dist / "assets")
    shutil.copyfile(Path(__file__).resolve().parent / seo_apercu(), dist / seo_apercu())
    data_js = (SOURCE / "data.js").read_text(encoding="utf-8")
    html = seo.ecrire(dist, html, data_js, site_url)
    (dist / "index.html").write_text(html, encoding="utf-8")
    shutil.copyfile(SOURCE / "data.js", dist / "data.js")
    copier_donnees(dist)
    return dist


def site_url_configure(path: Path = ROOT / "config" / "deploiement.local") -> str | None:
    """Adresse publique du site (`SITE_URL=` dans la configuration locale), si connue."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().upper().startswith("SITE_URL="):
                return line.split("=", 1)[1].strip() or None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python front/publication/build.py")
    parser.add_argument("--dossier-seuils", default=DOSSIER_SEUILS)
    parser.add_argument("--verification", default=VERIFICATION)
    parser.add_argument("--web", action="store_true", help="version pour un hébergement public")
    args = parser.parse_args(argv)
    if args.web:
        dist = build_web(site_url=site_url_configure())
        print(f"[publication] {dist / 'index.html'} et data.js écrits (version web)")
        return 0
    dist = build(args.dossier_seuils, args.verification)
    print(f"[publication] {dist / 'index.html'} et data.js écrits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
