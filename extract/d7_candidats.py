"""Extraits GDELT archivés -> candidats presse de l'indicateur D7 (libertés en pratique).

Un candidat est un événement GDELT situé en France qui remplit trois conditions :
  - l'acteur 1 est une autorité publique (`acteurs_publics` de la grille : police,
    gouvernement, justice, armée) ;
  - son code CAMEO relève d'une catégorie D7 (`codes_cameo` de la grille ; une entrée à deux
    chiffres vaut pour toute la racine). Si plusieurs catégories conviennent, la première dans
    l'ordre de la grille l'emporte ; le validateur peut la corriger sur GitHub ;
  - au moins deux GROUPES de propriétaires distincts (`config/medias_groupes.yaml`) l'ont
    mentionné. Les domaines absents de la table sont ignorés.
Le codage CAMEO est produit par machine : un candidat n'est qu'une proposition, rien ne compte
avant la validation humaine (extract/d7.py). Aucun texte d'article n'est lu ici.

`candidats()` affine ensuite le recoupement grâce aux titres collectés par
collectors/presse_titres.py : une même dépêche reprise par plusieurs titres compte pour une
seule source.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from collectors.gdelt import SOURCE_ID as GDELT
from collectors.gdelt import SOURCE_ID_TRADUCTION as GDELT_TRADUCTION
from extract.common import latest_documents
from extract.gdelt import lire_jour
from scoring.grid import DEFAULT_GRID_PATH, load_raw

ROOT = Path(__file__).resolve().parent.parent
GROUPES_PATH = ROOT / "config" / "medias_groupes.yaml"
INDICATOR = "D7.libertes_en_pratique"
DEPUIS = dt.date(2024, 7, 1)


@dataclass(frozen=True)
class Article:
    url: str
    domaine: str
    groupe: str
    mention_utc: str


@dataclass(frozen=True)
class Candidat:
    evenement_id: str
    jour: str  # AAAA-MM-JJ, jour de l'événement selon GDELT
    categorie: str
    lieu: str
    articles: tuple[Article, ...]
    groupes: tuple[str, ...]


def bloc_d7(path: Path = DEFAULT_GRID_PATH) -> dict:
    return load_raw(path)["indicators"][INDICATOR]


def categories_d7(path: Path = DEFAULT_GRID_PATH) -> dict:
    """Catégories de la grille, dans leur ordre, avec `acteurs_publics` recopié dans chacune."""
    bloc = bloc_d7(path)
    acteurs = list(bloc["acteurs_publics"])
    return {cle: {**cat, "acteurs_publics": acteurs} for cle, cat in bloc["categories"].items()}


def groupes_presse(path: Path = GROUPES_PATH) -> dict[str, str]:
    """Domaine -> groupe de propriétaires."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {d.lower(): g for g, domaines in data["groupes"].items() for d in domaines}


def categorie(row: dict, categories: dict) -> str | None:
    for cle, cat in categories.items():
        if row["acteur1_type"] not in cat["acteurs_publics"]:
            return None
        for code in cat["codes_cameo"]:
            if row["code_evenement"] == code or (len(code) == 2 and row["code_racine"] == code):
                return cle
    return None


def groupe_de(domaine: str, groupes: dict[str, str]) -> str | None:
    parties = domaine.lower().split(".")
    for i in range(len(parties) - 1):
        groupe = groupes.get(".".join(parties[i:]))
        if groupe:
            return groupe
    return None


def _jour(aaaammjj: str) -> str:
    return f"{aaaammjj[:4]}-{aaaammjj[4:6]}-{aaaammjj[6:8]}"


LIEUX_VAGUES = {"France", ""}


def identifiant_gdelt(jour: str, lieu: str, cat: str) -> str:
    import hashlib

    return f"gdelt-{jour.replace('-', '')}-{hashlib.sha1(lieu.encode()).hexdigest()[:8]}-{cat}"


def pre_candidats(rows: list[dict], categories: dict, groupes: dict[str, str]) -> list[Candidat]:
    """Regroupement par (jour de l'événement, lieu, catégorie) : GDELT attribue le plus
    souvent un identifiant d'événement différent à chaque article d'un même fait (constaté le
    2026-11-10 : 74 événements sur 734 cités par deux groupes). Le lieu « France » (pays
    entier) est écarté : il réunirait des faits sans rapport."""
    evenements: dict[str, dict] = {}
    for row in rows:
        cat = categorie(row, categories)
        groupe = groupe_de(row["domaine"], groupes)
        if cat is None or groupe is None or row["lieu"].strip() in LIEUX_VAGUES:
            continue
        cle = identifiant_gdelt(_jour(row["evenement_jour"]), row["lieu"], cat)
        evt = evenements.setdefault(cle, {"row": row, "categorie": cat, "articles": {}})
        evt["articles"].setdefault(
            row["url"], Article(row["url"], row["domaine"].lower(), groupe, row["mention_utc"])
        )
    out = []
    for evt_id, evt in evenements.items():
        articles = tuple(sorted(evt["articles"].values(), key=lambda a: (a.domaine, a.url)))
        groupes_vus = tuple(sorted({a.groupe for a in articles}))
        if len(groupes_vus) < 2:
            continue
        row = evt["row"]
        out.append(
            Candidat(
                evt_id,
                _jour(row["evenement_jour"]),
                evt["categorie"],
                row["lieu"],
                articles,
                groupes_vus,
            )
        )
    return sorted(out, key=lambda c: (c.jour, c.evenement_id))


def documents_jours(conn: sqlite3.Connection, depuis: dt.date = DEPUIS) -> list[sqlite3.Row]:
    """Extraits quotidiens GDELT archivés depuis `depuis` (flux anglophone et flux traduit,
    où se trouve la presse française), par jour croissant."""
    docs = latest_documents(conn, GDELT) + latest_documents(conn, GDELT_TRADUCTION)
    return sorted(
        (
            d
            for d in docs
            if d["external_id"].endswith(".tsv.gz") and d["external_id"][:10] >= str(depuis)
        ),
        key=lambda d: (d["external_id"], d["source_id"]),
    )


def pre_candidats_archives(
    conn: sqlite3.Connection, raw_dir: Path, depuis: dt.date = DEPUIS
) -> list[Candidat]:
    """Pré-candidats de tous les jours archivés. Un événement mentionné sur plusieurs jours
    d'extraits est regroupé : ses mentions sont réunies avant le test des deux groupes."""
    categories, groupes = categories_d7(), groupes_presse()
    rows: list[dict] = []
    for doc in documents_jours(conn, depuis):
        _, lignes = lire_jour((raw_dir / doc["path"]).read_bytes())
        rows += [r for r in lignes if categorie(r, categories)]
    return pre_candidats(rows, categories, groupes)


def candidats_gdelt(
    conn: sqlite3.Connection, raw_dir: Path, depuis: dt.date = DEPUIS
) -> list[Candidat]:
    """Pré-candidats GDELT (reprise du passé) antérieurs au début de la collecte RSS, dont le
    recoupement tient une fois les dépêches reprises fusionnées (titres archivés par
    collectors/presse_titres.py ; un titre inconnu reste une source)."""
    from collectors.presse_titres import fusionner, titres_archives
    from extract.d7_rss import debut_rss

    fin = debut_rss(conn)
    titres = titres_archives(conn, raw_dir)
    return [
        c
        for c in pre_candidats_archives(conn, raw_dir, depuis)
        if (fin is None or c.jour < str(fin)) and fusionner(c, titres)
    ]


def candidats(conn: sqlite3.Connection, raw_dir: Path, depuis: dt.date = DEPUIS) -> list[Candidat]:
    """Tous les candidats presse : GDELT avant le début de la collecte RSS, RSS ensuite."""
    from extract.d7_rss import candidats_archives

    tous = candidats_gdelt(conn, raw_dir, depuis) + candidats_archives(conn, raw_dir)
    return sorted(tous, key=lambda c: (c.jour, c.evenement_id))
