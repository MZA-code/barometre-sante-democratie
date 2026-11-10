"""Ouverture des issues GitHub des candidats presse D7 (validation humaine).

Chaque candidat (extract/d7_candidats.py : événement GDELT, catégorie, au moins deux groupes de
presse après fusion des dépêches) reçoit une issue :
  - titre `[D7] <libellé de la catégorie> · <lieu> · <AAAA-MM-JJ>`, relu par extract/d7.py ;
  - corps : lieu, date, catégorie proposée, liste « média (groupe) · date · lien » (jamais le
    titre ni le texte des articles), critères de la catégorie copiés de la grille, consigne de
    validation, marqueur caché `<!-- d7:gdelt:<id> -->` ;
  - étiquettes `d7`, `en-attente`, `cat:<clé>`.
Ouverture par passage : tous les candidats des 7 derniers jours sans issue, puis au plus 20
candidats plus anciens (reprise depuis juillet 2024), du plus récent au plus ancien.
Pas de doublon : avant toute création, les marqueurs sont relus dans les instantanés archivés
ET dans la liste des issues `d7` de l'API (une issue créée juste avant un plantage est vue).
Sans config/github.local ou si l'API est en erreur, rien n'est fait (code 0).

Usage :
    python -m ops.issues_d7 [--db CHEMIN] [--raw-dir DOSSIER] [--config FICHIER] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

from collectors.github_d7 import CONFIG_PATH, Api, ErreurApi, instantanes, lire_config
from collectors.presse_titres import titres_archives
from extract.d7 import evenement_de
from extract.d7_candidats import Candidat, candidats, categories_d7
from storage.archive import DEFAULT_RAW_DIR
from storage.db import DEFAULT_DB_PATH, connect, init_db

QUOTA_REPRISE = 20
JOURS_RECENTS = 7
ETIQUETTES = {
    "d7": ("1f6feb", "Fait candidat à l'indicateur D7 · Libertés en pratique"),
    "en-attente": ("d4c5f9", "D7 : pas encore relu"),
    "validé": ("2da44e", "D7 : fait établi, compté"),
    "rejeté": ("cf222e", "D7 : ne remplit pas les critères, non compté"),
    "doublon": ("8c959f", "D7 : déjà compté dans une autre issue"),
}
COULEUR_CAT = "fbca04"


def titre_issue(c: Candidat, categories: dict) -> str:
    return f"[D7] {categories[c.categorie]['libelle']} · {c.lieu} · {c.jour}"


def corps_issue(c: Candidat, cat: dict) -> str:
    lignes = [
        f"**Lieu :** {c.lieu} · **date de l'événement (GDELT) :** {c.jour} · "
        f"**catégorie proposée :** {cat['libelle']}",
        "",
        "### Articles (au moins deux groupes de presse)",
        "",
    ]
    for a in c.articles:
        jour = f"{a.mention_utc[:4]}-{a.mention_utc[4:6]}-{a.mention_utc[6:8]}"
        lignes.append(f"- {a.domaine} ({a.groupe}) · {jour} · {a.url}")
    lignes += ["", f"### Compte comme « {cat['libelle']} »", ""]
    lignes += [f"- {x}" for x in cat["compte"]]
    lignes += ["", "### Ne compte pas", ""]
    lignes += [f"- {x}" for x in cat["ne_compte_pas"]]
    lignes += [
        "",
        "### Décision",
        "",
        "Lire les articles, puis poser **une** étiquette : `validé` (le fait remplit les "
        "critères ci-dessus), `rejeté` (il ne les remplit pas, ou le codage automatique s'est "
        "trompé) ou `doublon` (déjà compté dans une autre issue : citer son numéro en "
        "commentaire). Si la catégorie est fausse, remplacer l'étiquette `cat:` par la bonne. "
        "Ne pas recopier de nom de personne dans les commentaires.",
        "",
        f"Identifiant D7 : {c.evenement_id} (lu par la collecte, à garder tel quel)",
        f"<!-- d7:gdelt:{c.evenement_id} -->",
    ]
    return "\n".join(lignes)


def a_ouvrir(
    cands: list[Candidat], deja: set[str], aujourd_hui: dt.date, quota_reprise: int = QUOTA_REPRISE
) -> list[Candidat]:
    limite = str(aujourd_hui - dt.timedelta(days=JOURS_RECENTS))
    libres = sorted(
        (c for c in cands if c.evenement_id not in deja),
        key=lambda c: (c.jour, c.evenement_id),
        reverse=True,
    )
    recents = [c for c in libres if c.jour >= limite]
    anciens = [c for c in libres if c.jour < limite]
    return recents + anciens[:quota_reprise]


def assurer_etiquettes(api, categories: dict) -> None:
    existantes = {x["name"] for x in api.lister("labels", {})}
    voulues = dict(ETIQUETTES)
    for cle, cat in categories.items():
        voulues[f"cat:{cle}"] = (COULEUR_CAT, f"D7 : {cat['libelle']}")
    for nom, (couleur, description) in voulues.items():
        if nom not in existantes:
            api.creer("labels", {"name": nom, "color": couleur, "description": description})


def publier_candidats(
    api, cands: list[Candidat], deja: set[str], aujourd_hui: dt.date, categories: dict
) -> int:
    vus = set(deja)
    vus |= {
        e
        for i in api.lister("issues", {"labels": "d7", "state": "all"})
        if (e := evenement_de(i.get("body") or ""))
    }
    n = 0
    for c in a_ouvrir(cands, vus, aujourd_hui):
        api.creer(
            "issues",
            {
                "title": titre_issue(c, categories),
                "body": corps_issue(c, categories[c.categorie]),
                "labels": ["d7", "en-attente", f"cat:{c.categorie}"],
            },
        )
        n += 1
    return n


def titres_releves(c: Candidat, titres: dict) -> bool:
    """Vrai si le titre de chaque article a été relevé (même en échec) : le repérage des
    dépêches reprises a pu se faire."""
    if c.evenement_id.startswith("rss-"):  # titres lus dans le flux, déjà dédoublonnés
        return True
    return all(a.url in titres for a in c.articles)


def publiables(conn: sqlite3.Connection, raw_dir: Path) -> list[Candidat]:
    titres = titres_archives(conn, raw_dir)
    return [c for c in candidats(conn, raw_dir) if titres_releves(c, titres)]


def publier(api, conn: sqlite3.Connection, raw_dir: Path, aujourd_hui: dt.date) -> int:
    categories = categories_d7()
    assurer_etiquettes(api, categories)
    deja = {e for i in instantanes(conn, raw_dir) if (e := evenement_de(i["corps"]))}
    return publier_candidats(api, publiables(conn, raw_dir), deja, aujourd_hui, categories)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ops.issues_d7")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--dry-run", action="store_true", help="compter sans rien créer")
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        init_db(conn)
        if args.dry_run:
            deja = {e for i in instantanes(conn, args.raw_dir) if (e := evenement_de(i["corps"]))}
            choisis = a_ouvrir(publiables(conn, args.raw_dir), deja, dt.date.today())
            print(f"[issues_d7] {len(choisis)} issue(s) seraient ouvertes")
            return 0
        config = lire_config(args.config)
        if config is None:
            print(f"[issues_d7] {args.config} absent ou incomplet : rien à faire")
            return 0
        try:
            n = publier(Api(*config), conn, args.raw_dir, dt.date.today())
        except ErreurApi as exc:
            print(f"[issues_d7] API indisponible, arrêt : {exc}")
            return 0
        print(f"[issues_d7] {n} issue(s) ouverte(s)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
