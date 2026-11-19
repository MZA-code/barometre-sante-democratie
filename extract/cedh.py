"""Arrêts de la Cour européenne des droits de l'homme contre la France -> faits (D3.4).

Un arrêt = un identifiant ECLI (ses versions française et anglaise sont réunies). Il compte
comme constat de violation si au moins une version porte un article violé (champ
`violation` de HUDOC) ou si sa conclusion contient un point commençant par « Violation »
(« Violation de l'article 6-1 », « Violation of P1-1 »...) : le champ `violation` manque sur
une trentaine d'arrêts anciens. « Non-violation » ne compte pas. Les arrêts de satisfaction
équitable, de révision ou de radiation sont des arrêts comme les autres : ils comptent dans
le total, et comme violation seulement si leur conclusion en constate une.

Fait `arret_cedh_violation` ou `arret_cedh_sans_violation`, daté du jour de l'arrêt.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from collectors.cedh import EXTERNAL_ID, SOURCE_ID
from extract.common import FactDraft, latest_documents

INDICATOR = "D3.condamnations_cedh"
EXTRACTOR = "hudoc_cedh@1"
URL_ARRET = "https://hudoc.echr.coe.int/fre?i={itemid}"
VIOLATION = re.compile(r"^Violations? (de|d'|of)\b")

# Articles de la Convention et de ses protocoles, libellés courts.
ARTICLES = {
    "2": "droit à la vie",
    "3": "interdiction de la torture et des traitements inhumains ou dégradants",
    "4": "interdiction de l'esclavage et du travail forcé",
    "5": "droit à la liberté et à la sûreté",
    "6": "droit à un procès équitable",
    "7": "pas de peine sans loi",
    "8": "droit au respect de la vie privée et familiale",
    "9": "liberté de pensée, de conscience et de religion",
    "10": "liberté d'expression",
    "11": "liberté de réunion et d'association",
    "12": "droit au mariage",
    "13": "droit à un recours effectif",
    "14": "interdiction de la discrimination",
    "18": "limitation de l'usage des restrictions aux droits",
    "34": "droit de recours individuel",
    "38": "obligation de coopérer avec la Cour",
    "46": "force obligatoire des arrêts",
    "P1-1": "protection de la propriété",
    "P1-2": "droit à l'instruction",
    "P1-3": "droit à des élections libres",
    "P4-2": "liberté de circulation",
    "P7-4": "droit à ne pas être jugé deux fois",
}


def articles(champ: str) -> list[str]:
    """« 6;6-1;P1-1;14+8 » -> articles principaux : ['6', 'P1-1', '14']."""
    out: list[str] = []
    for token in filter(None, (t.strip() for t in champ.split(";"))):
        token = token.split("+")[0]
        principal = "-".join(token.split("-")[:2]) if token.startswith("P") else token.split("-")[0]
        if principal not in out:
            out.append(principal)
    return out


def constate_violation(colonnes: dict) -> bool:
    if colonnes.get("violation"):
        return True
    return any(VIOLATION.match(p.strip()) for p in (colonnes.get("conclusion") or "").split(";"))


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    docs = [d for d in latest_documents(conn, SOURCE_ID) if d["external_id"] == EXTERNAL_ID]
    if not docs:
        return []
    doc = docs[0]
    data = json.loads((raw_dir / doc["path"]).read_text(encoding="utf-8"))
    par_arret: dict[str, list[dict]] = {}
    for r in data["results"]:
        c = r["columns"]
        if c.get("ecli"):
            par_arret.setdefault(c["ecli"], []).append(c)

    drafts = []
    for ecli, versions in sorted(par_arret.items()):
        # La version française d'abord (titre et conclusion affichés), sinon l'anglaise.
        versions.sort(key=lambda c: (c["languageisocode"] != "FRE", c["itemid"]))
        ref = versions[0]
        violation = any(constate_violation(c) for c in versions)
        violes: list[str] = []
        for c in versions:
            for a in articles(c.get("violation") or ""):
                if a not in violes:
                    violes.append(a)
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="arret_cedh_violation" if violation else "arret_cedh_sans_violation",
                occurred_on=ref["kpdate"][:10],
                title=ref["docname"],
                official_ref=ecli,
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    "requetes": ref.get("appno") or "",
                    "violation": violation,
                    "articles_violes": violes,
                    "conclusion": ref.get("conclusion") or "",
                    "formation": ref.get("doctypebranch") or "",
                    "importance": ref.get("importance") or "",
                    "url": URL_ARRET.format(itemid=ref["itemid"]),
                },
            )
        )
    return drafts
