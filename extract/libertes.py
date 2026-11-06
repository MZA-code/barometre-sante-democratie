"""Archives DILA -> faits `dissolution_administrative` (indicateur D4.1).

Une dissolution administrative est un décret qui dissout une association ou un groupement
de fait pour un motif d'ordre public. Repérage constaté dans les données (2026-10-26) :
  - par les visas, depuis le début des années 1990 : loi du 10 janvier 1936 sur les groupes
    de combat et milices privées, article L. 212-1 du code de la sécurité intérieure (depuis
    2012), article L. 332-18 du code du sport (associations de supporters) ;
  - par le titre quand les visas manquent (textes anciens) : « portant dissolution d'une
    association », « de l'association dénommée ... », « du groupement de fait ... ».
Ne sont pas des dissolutions administratives : les dissolutions volontaires approuvées par
décret (associations reconnues d'utilité publique, associations cultuelles), celles de
conseils municipaux, d'établissements ou de services publics.

Couverture : avant 1990, le JORF indexe certaines dissolutions sous des titres opaques
(« ASSOCIATIONS DIVERSES, SIEGE SOCIAL ... », par exemple le 12 juin 1968) ; la série n'est
fiable qu'à partir de 1990 (history_start de l'indicateur dans la grille).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from extract import dila
from extract.common import FactDraft

EXTRACTOR = "dila_dissolutions/1"
INDICATOR = "D4.dissolutions_administratives"

BASIS = (
    ("L212-1", re.compile(r"L\.\s*212-1\b")),
    ("L332-18", re.compile(r"L\.\s*332-18\b")),
    ("loi_1936", re.compile(r"10 janvier 1936")),
)
DISSOLUTION = re.compile(r"\bdissolution\b", re.IGNORECASE)
ADMIN_TITLE = re.compile(
    r"dissolution\s+(?:d['’]une association|de l['’]association|des associations"
    r"|de (?:deux|trois|quatre|cinq|six|plusieurs) associations"
    r"|du groupement de fait|d['’]un groupement de fait|des groupements de fait"
    r"|du mouvement de fait|de la f[ée]d[ée]ration des associations)",
    re.IGNORECASE,
)
NOT_ADMIN = re.compile(
    r"approuvant|attribution|cultuelle|utilit[ée] publique|abrog|rectificatif", re.IGNORECASE
)


def legal_basis(text: dict) -> str | None:
    """Fondement de la dissolution, ou None si le texte n'en est pas une."""
    if text["nature"] != "DECRET" or not DISSOLUTION.search(text["titre"]):
        return None
    if NOT_ADMIN.search(text["titre"]):
        return None
    for name, pattern in BASIS:
        if pattern.search(text.get("visas", "")):
            return name
    if ADMIN_TITLE.search(text["titre"]):
        return "titre"  # visas absents : repérage par le seul titre
    return None


def to_draft(text: dict, raw_ids: set[int], basis: str) -> FactDraft:
    return FactDraft(
        indicator_id=INDICATOR,
        fact_type="dissolution_administrative",
        occurred_on=text["date_texte"],
        title=text["titre"],
        official_ref=text["num"] or text["nor"] or text["cid"],
        extraction_method=EXTRACTOR,
        raw_document_ids=tuple(sorted(raw_ids)),
        attributes={
            "cid": text["cid"],
            "fondement": basis,
            "nor": text["nor"],
            "date_publication": text["date_publi"],
            "url": dila.LEGIFRANCE_URL.format(cid=text["cid"]),
        },
    )


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = dila.DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    texts, sources = dila.merged_texts(conn, raw_dir, cache_dir)
    drafts = []
    for cid in sorted(texts):
        text = texts[cid]
        basis = legal_basis(text)
        if basis and text["date_texte"] and text["date_texte"] != dila.UNKNOWN_DATE:
            drafts.append(to_draft(text, sources[cid], basis))
    return drafts
