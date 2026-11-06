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
TITRE = "Baromètre de la santé démocratique"
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
        <p>Aucun indicateur n'est encore noté : les seuils de la grille seront fixés par un comité.
          Le <a class="underline" href="{dossier}">dossier pour la fixation des seuils</a> présente,
          pour chaque indicateur, son historique, ses limites et des propositions de bornes.</p>
        <p>Le <a class="underline" href="{verification}">document de vérification humaine</a> liste
          les chiffres et rapprochements en cours de relecture.</p>
        <p class="text-xs text-muted">Ces deux documents sont accessibles sur invitation.</p>
      </div>
"""


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
    return dist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python front/publication/build.py")
    parser.add_argument("--dossier-seuils", default=DOSSIER_SEUILS)
    parser.add_argument("--verification", default=VERIFICATION)
    args = parser.parse_args(argv)
    dist = build(args.dossier_seuils, args.verification)
    print(f"[publication] {dist / 'index.html'} et data.js écrits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
