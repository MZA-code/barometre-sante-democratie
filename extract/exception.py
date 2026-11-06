"""Seed des périodes de régime d'exception + archives DILA -> faits (indicateur D3.1).

Les bornes d'une période (déclaration, prorogations, fin) sont écrites dans le corps des
articles, pas dans les titres : elles sont relevées à la main dans `data/seed/
regimes_exception.csv`, chaque ligne citant les textes officiels (identifiants JORFTEXT) et
la phrase qui fixe ses dates (voir data/seed/README.md).

Contrôles automatiques à chaque extraction :
  - chaque texte cité doit exister dans l'archive JORF/LEGI ; le fait cite alors ses
    archives en plus du seed ;
  - chaque texte de l'archive qui déclare, proroge ou lève un régime d'exception doit être
    cité par une période ; sinon il est signalé (nouvelle déclaration à reporter dans le seed).
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from pathlib import Path

from extract import dila
from extract.common import FactDraft, latest_documents

EXTRACTOR = "seed_manuel"
INDICATOR = "D3.regimes_exception"
SOURCE_ID = "seed_manuel"
SEED = "regimes_exception.csv"

# Textes dont l'objet principal est de déclarer, proroger ou lever un régime d'exception :
# la formule suit immédiatement « <nature> n° ... du <date> » (un décret qui « modifie » un
# texte de crise sanitaire n'en est pas un).
REGIME_TEXT = re.compile(
    r"^\W*(?:loi|d[ée]cret|d[ée]cision|ordonnance)(?:\s+n\s*[°o]?\s*[\d-]+)?"
    r"\s+du \d{1,2}(?:er)? \S+ \d{4}\s+"
    r"(?:portant application de la loi n[°o]?\s*55-385"
    r"|prorogeant l'application de la loi n[°o]?\s*55-385"
    r"|relative à l'état d'urgence (?:en|dans|à)"
    r"|d[ée]clarant l'[ée]tat d'urgence"
    r"|prorogeant l'[ée]tat d'urgence"
    r"|autorisant la prorogation de l'[ée]tat d'urgence"
    r"|mettant fin à l'[ée]tat d'urgence"
    r"|mettant fin à l.application de l'article 16"
    r"|portant d[ée]claration de l'[ée]tat d'urgence"
    r"|relative à la dur[ée]e de l'[ée]tat d'urgence"
    r"|d'urgence pour faire face à l'[ée]pid[ée]mie)",
    re.IGNORECASE,
)


def regime_texts(texts: dict[str, dict]) -> dict[str, dict]:
    return {
        cid: t
        for cid, t in texts.items()
        if REGIME_TEXT.search(t["titre"]) and "rectificatif" not in t["titre"].lower()
    }


def read_seed(conn: sqlite3.Connection, raw_dir: Path) -> tuple[int, list[dict]] | None:
    for doc in latest_documents(conn, SOURCE_ID):
        if doc["external_id"] == SEED:
            text = (raw_dir / doc["path"]).read_text(encoding="utf-8")
            return doc["id"], list(csv.DictReader(io.StringIO(text), delimiter=";"))
    return None


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = dila.DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    seed = read_seed(conn, raw_dir)
    if seed is None:
        return []
    seed_id, rows = seed
    texts, sources = dila.merged_texts(conn, raw_dir, cache_dir)

    drafts, cited = [], set()
    for row in rows:
        cids = row["textes"].split()
        cited.update(cids)
        missing = [cid for cid in cids if cid not in texts]
        raw_ids = {seed_id}.union(*(sources[cid] for cid in cids if cid in texts))
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="periode_regime_exception",
                occurred_on=row["debut"],
                title=f"{row['regime']} — {row['territoire']}",
                official_ref=cids[0] if cids else None,
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(raw_ids)),
                attributes={
                    "regime": row["regime"],
                    "territoire": row["territoire"],
                    "metropole": row["metropole"] == "oui",
                    "fin": row["fin"] or None,
                    "textes": cids,
                    "textes_absents_archive": missing,
                    "preuve": row["preuve"],
                    "a_verifier": row["a_verifier"] == "oui",
                    "note": row["note"] or None,
                    "url": dila.LEGIFRANCE_URL.format(cid=cids[0]) if cids else None,
                },
            )
        )
        if missing:
            print(f"[extract] D3 : textes cités absents de l'archive : {', '.join(missing)}")

    for cid, text in sorted(regime_texts(texts).items(), key=lambda kv: kv[1]["date_texte"]):
        if cid not in cited:
            print(
                f"[extract] D3 : texte de régime d'exception non rattaché à une période : "
                f"{text['date_texte']} {text['titre'][:90]} ({cid})"
            )
    return drafts
