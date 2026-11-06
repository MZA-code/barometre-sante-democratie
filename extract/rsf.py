"""Classement RSF -> indicateur D5.3 (source externe, annuelle).

Un fait `classement_rsf` par édition : rang de la France, nombre de pays classés, score et
période de méthode du score. Le rang est la métrique suivie : les scores ne sont pas
comparables entre périodes (échelle inversée jusqu'en 2012, convertie dans les fichiers à
partir de 2013 ; nouvelle méthodologie depuis 2022).

Date du fait : 1er janvier de l'année d'édition, **date conventionnelle** (la date exacte de
publication de chaque édition n'a pas été relevée). Une fenêtre de 365 jours contient ainsi
une édition ; le rang de la fenêtre est la moyenne des rangs des éditions qu'elle contient.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

SOURCE_ID = "rsf_classement"
EXTRACTOR = "rsf_classement/1"
INDICATOR = "D5.classement_rsf"
PAYS = "FRA"


def periode(annee: int) -> str:
    if annee <= 2012:
        return "2002-2012 (score : plus bas = mieux)"
    if annee <= 2021:
        return "2013-2021 (score converti : plus haut = mieux)"
    return "depuis 2022 (nouvelle méthodologie : plus haut = mieux)"


# Catégories RSF depuis 2022 (score de 0 à 100, plus haut = mieux), d'après la méthodologie
# publiée par RSF (« [85 ; 100 points] : bonne situation », « [70 ; 85 points[ : situation
# plutôt bonne »…), vérifiée le 2026-11-05 sur
# https://rsf.org/fr/m%C3%A9thodologie-d%C3%A9taill%C3%A9e-du-classement-mondial-de-la-libert%C3%A9-de-la-presse-2024
# et contrôlée contre la colonne « Situation » de l'édition 2024. Niveau 0 (bonne) à 4 (très
# grave). Les bornes des éditions antérieures (autre échelle) n'ont pas été vérifiées : pas
# de catégorie avant 2022.
PREMIERE_EDITION_CATEGORIES = 2022
CATEGORIES = (
    (85.0, 0, "Bonne situation"),
    (70.0, 1, "Situation plutôt bonne"),
    (55.0, 2, "Situation problématique"),
    (40.0, 3, "Situation difficile"),
    (0.0, 4, "Situation très grave"),
)


def categorie(score: float) -> tuple[int, str]:
    return next((niveau, label) for borne, niveau, label in CATEGORIES if score >= borne)


def number(value: str) -> float:
    return float(value.strip().replace(",", "."))


def parse(raw: bytes, annee: int | None = None) -> tuple[dict, int]:
    """Ligne de la France et nombre de pays classés."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    if not rows:
        raise ValueError("fichier vide")
    keys = [k.strip() for k in rows[0]]
    rank = next(k for k in rows[0] if k.strip() in ("Rank", "Rank N"))
    score = next(k for k in rows[0] if re.fullmatch(r"Score( N| \d{4})?", k.strip()))
    france = [r for r in rows if (r.get("ISO") or "").strip() == PAYS]
    if len(france) != 1:
        raise ValueError(f"{len(france)} ligne(s) {PAYS} ; colonnes {keys[:6]}")
    values = {"rang": int(france[0][rank]), "score": number(france[0][score])}
    situation = (france[0].get("Situation") or "").strip()
    # Colonne « Situation » présente dans certaines éditions : contrôle des bornes, qui ne
    # valent qu'à partir de 2022 (échelle et libellés antérieurs différents).
    recent = annee is None or annee >= PREMIERE_EDITION_CATEGORIES
    if situation and recent and situation.lower() != categorie(values["score"])[1].lower():
        raise ValueError(f"catégorie publiée « {situation} » != bornes ({values['score']})")
    return values, len(rows)


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    drafts = []
    for doc in latest_documents(conn, SOURCE_ID):
        m = re.fullmatch(r"(\d{4})\.csv", doc["external_id"])
        if not m:
            continue
        annee = int(m.group(1))
        values, nb_pays = parse((raw_dir / doc["path"]).read_bytes(), annee)
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="classement_rsf",
                occurred_on=f"{annee}-01-01",
                title=f"Classement mondial de la liberté de la presse {annee} (RSF) : France",
                official_ref=f"RSF {annee}",
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    **values,
                    "edition": annee,
                    "nb_pays": nb_pays,
                    "rang_relatif": round(values["rang"] / nb_pays, 4),
                    **(
                        dict(
                            zip(
                                ("niveau_categorie", "categorie"),
                                categorie(values["score"]),
                                strict=True,
                            )
                        )
                        if annee >= PREMIERE_EDITION_CATEGORIES
                        else {}
                    ),
                    "periode_score": periode(annee),
                    "date_conventionnelle": True,
                    "url": doc["url"],
                },
            )
        )
    return drafts
