"""Extraits GDELT archivés -> couverture de la France par la presse étrangère (contexte).

Donnée de contexte, hors grille : aucune note n'en est tirée. Un fait `couverture_etrangere_mois`
par mois (daté du dernier jour du mois), calculé sur les extraits quotidiens de
`collectors/gdelt.py` :
  - article étranger : adresse web distincte dont le domaine est rattaché à un autre pays que la
    France par la table GDELT « domaine -> pays » (mai 2018) ; les domaines absents de la table
    sont comptés à part (`articles_domaine_inconnu`) ;
  - thèmes, d'après le codage automatique CAMEO des événements cités par l'article (un article
    peut relever des deux) :
      * `manifestations` : code racine 14 (« Protest ») ;
      * `force_police` : codes racines 17, 18 ou 19 (coercition, agression, affrontement) avec
        la police (type d'acteur « COP ») parmi les deux acteurs.
Ces thèmes reprennent la classification de GDELT, produite par machine : ils ne qualifient pas
les faits, ils décrivent comment la base les a codés. Un même article d'agence repris par
plusieurs sites compte une fois par site : le nombre de sites distincts est donné à côté.
"""

from __future__ import annotations

import calendar
import csv
import gzip
import io
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from extract.common import FactDraft, latest_documents

SOURCE_ID = "gdelt"
EXTRACTOR = "gdelt_couverture/1"
INDICATOR = "contexte.presse_etrangere"
DOMAINES_ID = "domaines_par_pays_2018.txt"
PAYS_FRANCE = "FR"
RACINE_MANIFESTATION = {"14"}
RACINES_FORCE = {"17", "18", "19"}
POLICE = "COP"
NB_EXEMPLES = 30
THEMES = ("manifestations", "force_police")


def domaines(text: str) -> dict[str, tuple[str, str]]:
    out = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0]:
            out[parts[0].strip().lower()] = (parts[1].strip(), parts[2].strip())
    return out


def lire_jour(data: bytes) -> tuple[list[str], list[dict]]:
    text = gzip.decompress(data).decode("utf-8")
    manquantes: list[str] = []
    lignes = []
    for line in text.splitlines(keepends=True):
        if line.startswith("# tranches manquantes : "):
            valeur = line.split(" : ", 1)[1].strip()
            manquantes = [] if valeur == "aucune" else valeur.split(",")
        elif not line.startswith("#"):
            lignes.append(line)
    return manquantes, list(csv.DictReader(io.StringIO("".join(lignes)), delimiter="\t"))


def themes(row: dict) -> set[str]:
    out = set()
    if row["code_racine"] in RACINE_MANIFESTATION:
        out.add("manifestations")
    if row["code_racine"] in RACINES_FORCE and POLICE in (row["acteur1_type"], row["acteur2_type"]):
        out.add("force_police")
    return out


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    docs = latest_documents(conn, SOURCE_ID)
    table = [d for d in docs if d["external_id"] == DOMAINES_ID]
    if not table:
        return []
    pays_de = domaines((raw_dir / table[0]["path"]).read_text(encoding="utf-8", errors="replace"))
    jours = sorted(
        (d for d in docs if d["external_id"].endswith(".tsv.gz")), key=lambda d: d["external_id"]
    )
    par_mois: dict[str, list] = defaultdict(list)
    for d in jours:
        par_mois[d["external_id"][:7]].append(d)

    drafts = []
    for mois, docs_mois in sorted(par_mois.items()):
        articles: dict[str, dict] = {}  # url -> {domaine, pays, themes, heure}
        inconnus: set[str] = set()
        manquantes = 0
        for doc in docs_mois:
            miss, rows = lire_jour((raw_dir / doc["path"]).read_bytes())
            manquantes += len(miss)
            for r in rows:
                code, nom = pays_de.get(r["domaine"], ("", ""))
                if not code:
                    inconnus.add(r["url"])
                    continue
                if code == PAYS_FRANCE:
                    continue
                a = articles.setdefault(
                    r["url"],
                    {
                        "domaine": r["domaine"],
                        "pays": nom,
                        "themes": set(),
                        "heure": r["mention_utc"],
                    },
                )
                a["themes"] |= themes(r)
                a["heure"] = min(a["heure"], r["mention_utc"])
        par_pays = Counter(a["pays"] for a in articles.values())
        attributs = {
            "mois": mois,
            "jours_couverts": len(docs_mois),
            "jours_dans_le_mois": calendar.monthrange(int(mois[:4]), int(mois[5:]))[1],
            "tranches_manquantes": manquantes,
            "articles_etrangers": len(articles),
            "sites_etrangers": len({a["domaine"] for a in articles.values()}),
            "articles_domaine_inconnu": len(inconnus - set(articles)),
            "par_pays": dict(sorted(par_pays.items(), key=lambda kv: (-kv[1], kv[0]))),
        }
        for theme in THEMES:
            sel = {u: a for u, a in articles.items() if theme in a["themes"]}
            exemples = sorted(sel.items(), key=lambda kv: (kv[1]["heure"], kv[0]), reverse=True)
            attributs[theme] = {
                "articles": len(sel),
                "sites": len({a["domaine"] for a in sel.values()}),
                "par_pays": dict(
                    sorted(
                        Counter(a["pays"] for a in sel.values()).items(),
                        key=lambda kv: (-kv[1], kv[0]),
                    )
                ),
                "exemples": [
                    {"url": u, "domaine": a["domaine"], "pays": a["pays"], "date": a["heure"][:8]}
                    for u, a in exemples[:NB_EXEMPLES]
                ],
            }
        year, month = int(mois[:4]), int(mois[5:])
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="couverture_etrangere_mois",
                occurred_on=f"{mois}-{calendar.monthrange(year, month)[1]:02d}",
                title=f"Presse étrangère sur la France, {month:02d}/{year} (GDELT)",
                official_ref=f"gdelt-{mois}",
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple([table[0]["id"], *(d["id"] for d in docs_mois)]),
                attributes=attributs,
            )
        )
    return drafts
