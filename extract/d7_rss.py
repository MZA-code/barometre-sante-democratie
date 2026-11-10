"""Articles RSS archivés -> candidats presse de l'indicateur D7.

Règles (bloc `rss` de D7 dans la grille, figé avant tout comptage) :
  - catégorie : titre + résumé, en minuscules sans accents, contiennent un mot-clé de la
    catégorie, plus un terme d'autorité si la catégorie l'exige, plus un terme de contexte si
    la catégorie en fixe ; la première catégorie qui convient, dans l'ordre de la grille ;
  - lieu : première commune de plus de `population_min_commune` habitants citée avec sa
    majuscule (liste INSEE archivée par collectors/rss.py ; homonymes : la plus peuplée) ;
    un article sans commune reconnue n'est pas candidat (le fait doit être situé) ;
  - même fait : même commune, même catégorie, articles à au plus `jours_regroupement` jours
    du premier article du groupe ;
  - recoupement : au moins deux groupes de propriétaires après fusion des titres identiques
    une fois normalisés (dépêche reprise), comme pour GDELT (collectors/presse_titres.py).
Identifiant stable du candidat : `rss-<code INSEE>-<catégorie>-<AAAAMMJJ du 1er article>`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from collectors.presse_titres import fusionner
from collectors.rss import COMMUNES_ID, SOURCE_ID
from extract.common import latest_documents
from extract.d7_candidats import Article, Candidat, bloc_d7, groupe_de, groupes_presse

__all__ = ["groupes_presse"]


def normaliser(texte: str) -> str:
    sans = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return " ".join(sans.replace("’", "'").split())


def conf_rss() -> dict:
    return bloc_d7()["rss"]


def categorie_texte(texte: str, conf: dict) -> str | None:
    autorite = any(a in texte for a in conf["autorites"])
    for cle, cat in conf["categories"].items():
        if not any(m in texte for m in cat["mots_cles"]):
            continue
        if cat.get("autorite_requise") and not autorite:
            continue
        if cat.get("contexte") and not any(c in texte for c in cat["contexte"]):
            continue
        return cle
    return None


def index_communes(communes: list[dict], population_min: int) -> tuple[re.Pattern, dict]:
    retenues: dict[str, tuple[str, str, str]] = {}
    population: dict[str, int] = {}
    for c in communes:
        pop = c.get("population") or 0
        if pop < population_min or len(c["nom"]) < 4:
            continue
        if pop > population.get(c["nom"], -1):
            retenues[c["nom"]] = (c["code"], c["nom"], c["codeDepartement"])
            population[c["nom"]] = pop
    noms = sorted(retenues, key=len, reverse=True)  # « Saint-Denis » avant « Denis »
    motif = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, noms)) + r")(?![\w-])")
    return motif, retenues


def commune_de(texte: str, index: tuple[re.Pattern, dict]) -> tuple[str, str, str] | None:
    motif, communes = index
    m = motif.search(texte)
    return communes[m.group(1)] if m else None


def items_archives(conn: sqlite3.Connection, raw_dir: Path) -> list[dict]:
    """Articles de tous les jours archivés, une fois chacun (par lien), triés par date."""
    vus: dict[str, dict] = {}
    for doc in latest_documents(conn, SOURCE_ID):
        for a in json.loads((raw_dir / doc["path"]).read_text(encoding="utf-8"))["articles"]:
            vus.setdefault(a["lien"], a)
    return sorted(vus.values(), key=lambda a: (a["date"], a["lien"]))


def communes_archivees(conn: sqlite3.Connection, raw_dir: Path) -> list[dict]:
    docs = latest_documents(conn, COMMUNES_ID)
    return json.loads((raw_dir / docs[0]["path"]).read_text(encoding="utf-8")) if docs else []


def debut_rss(conn: sqlite3.Connection) -> dt.date | None:
    row = conn.execute(
        "SELECT min(substr(external_id, -10)) FROM raw_documents WHERE source_id = ?",
        (SOURCE_ID,),
    ).fetchone()
    return dt.date.fromisoformat(row[0]) if row and row[0] else None


def _domaine(url: str) -> str:
    return url.split("/")[2].lower() if url.count("/") >= 2 else ""


def candidats_rss(
    items: list[dict], conf: dict, index: tuple[re.Pattern, dict], groupes: dict[str, str]
) -> list[Candidat]:
    ecart = dt.timedelta(days=conf["jours_regroupement"])
    par_cle: dict[tuple[str, str], list[dict]] = {}
    for a in sorted(items, key=lambda a: (a["date"], a["lien"])):
        texte = f"{a['titre']} {a.get('resume', '')}"
        cat = categorie_texte(normaliser(texte), conf)
        commune = commune_de(texte, index) if cat else None
        groupe = groupe_de(_domaine(a["lien"]), groupes)
        if cat and commune and groupe:
            par_cle.setdefault((commune[0], cat), []).append(
                {**a, "_commune": commune, "_groupe": groupe}
            )
    out = []
    for (code, cat), articles in par_cle.items():
        paquets: list[list[dict]] = []
        for a in articles:
            debut = dt.datetime.fromisoformat(paquets[-1][0]["date"][:19]) if paquets else None
            if debut and dt.datetime.fromisoformat(a["date"][:19]) - debut <= ecart:
                paquets[-1].append(a)
            else:
                paquets.append([a])
        for paquet in paquets:
            premier = paquet[0]
            _, nom, dep = premier["_commune"]
            arts = tuple(
                sorted(
                    (
                        Article(
                            a["lien"],
                            _domaine(a["lien"]),
                            a["_groupe"],
                            a["date"].replace("-", "").replace(":", "").replace("T", "")[:14],
                        )
                        for a in paquet
                    ),
                    key=lambda x: (x.domaine, x.url),
                )
            )
            cand = Candidat(
                f"rss-{code}-{cat}-{premier['date'][:10].replace('-', '')}",
                premier["date"][:10],
                cat,
                f"{nom} ({dep})",
                arts,
                tuple(sorted({a.groupe for a in arts})),
            )
            if len(cand.groupes) >= 2 and fusionner(cand, {a["lien"]: a["titre"] for a in paquet}):
                out.append(cand)
    return sorted(out, key=lambda c: (c.jour, c.evenement_id))


def candidats_archives(conn: sqlite3.Connection, raw_dir: Path) -> list[Candidat]:
    conf = conf_rss()
    index = index_communes(communes_archivees(conn, raw_dir), conf["population_min_commune"])
    if not index[1]:
        return []
    return candidats_rss(items_archives(conn, raw_dir), conf, index, groupes_presse())
