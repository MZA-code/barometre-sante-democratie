"""Lois du JORF + open data AN + base Dosleg du Sénat -> indicateur D2.2 (procédure accélérée).

La procédure accélérée (article 45 de la Constitution ; « déclaration d'urgence » avant la
révision de 2008) permet au gouvernement de limiter l'examen d'un texte à une lecture par
assemblée avant la commission mixte paritaire.

Un fait `loi_procedure` par loi promulguée au JORF depuis le 3 avril 1978 (ouverture de la
VIe législature ; la base du Sénat couvre les documents déposés depuis octobre 1977). Deux
sources, rapprochées par numéro de loi :
  - l'open data de l'Assemblée (depuis juin 2012) : acte `ProcedureAccelere_Type` dans le
    dossier de la loi (`codeLoi` de l'acte de promulgation) ;
  - la base Dosleg du Sénat (voir extract/senat.py).
Statut :
  - « acceleree » si l'une des sources enregistre l'engagement (urgence ou procédure
    accélérée) et que le Sénat n'enregistre pas de retrait : un engagement enregistré est
    une preuve positive, son absence dans l'autre source peut n'être qu'une lacune de
    saisie (constaté : loi spéciale 2025-1316, engagement au Sénat, absent du dossier AN) ;
  - « ordinaire » si au moins une source connaît la loi sans engagement (ou avec retrait) ;
  - « inconnu » sinon : la loi est comptée à part, jamais devinée.

Constats (2026-11-05) :
  - les 1 020 lois de l'open data AN figurent toutes dans le JORF ; le NOR publié par
    l'Assemblée ne permet pas le rapprochement (629 échecs sur 2016-2026) ;
  - sur 2012-2026, l'Assemblée et le Sénat concordent pour 997 lois sur 1 019 ; les écarts
    portent presque tous sur les lois de finances et de financement (exclues, voir
    ci-dessous) et sur un retrait de procédure (loi 2013-702) ;
  - le Sénat laisse le champ urgence vide pour une partie des lois de 1998 à 2008.

Exclusions du ratio (attributs ; la règle est dans scoring/metrics.py) : lois autorisant un
engagement international (comme D2), lois constitutionnelles (la procédure accélérée ne
s'y applique pas), lois de finances et de financement de la sécurité sociale (calendrier
fixé par les articles 47 et 47-1 de la Constitution, urgence « de droit » au Sénat), y
compris la loi spéciale votée faute de loi de finances (article 45 de la LOLF).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from extract import senat
from extract.common import FactDraft, latest_documents
from extract.parlement import DOSSIER_URL, SOURCE_ID, iter_acts, iter_dossiers

EXTRACTOR = "lois_procedure/2"
INDICATOR = "D2.procedure_acceleree"
HISTORY_START = "1978-04-03"  # VIe législature ; base Dosleg : dépôts depuis octobre 1977
PROC_CONVENTION = "6"  # AN : projet de ratification des traités et conventions
PROC_CONSTITUTIONNELLE = "7"
PROC_FINANCES = {"3", "4", "21"}  # AN : LF de l'année, LFSS, LF rectificative
SENAT_FINANCES = {"pjlf", "pjlr", "pjlg", "pjfs", "pfsr"}
SENAT_CONVENTION = "cvn"
SENAT_CONSTITUTIONNELLE = {"pjlc", "pplc"}
_NUMERO = r"^LOI(?:\s+organique)?\s+n[°o]\.?\s*[\d-]+\s+du\s+.+?\d{4},?\s+"
CONSTITUTIONNELLE = re.compile(r"^LOI\s+constitutionnelle", re.IGNORECASE)
FINANCES = re.compile(
    _NUMERO + r"(?:portant\s+)?(?:de finances|de financement|de règlement"
    r"|règlement définitif|relative aux résultats de la gestion"
    r"|spéciale prévue par l'article 45 de la loi organique)",
    re.IGNORECASE,
)


@dataclass
class LoiAN:
    code: str
    dossiers: dict[str, dict] = field(default_factory=dict)  # uid -> dossier
    raw_document_ids: set[int] = field(default_factory=set)
    procedure_acceleree: bool = False
    date_engagement: str | None = None


def collect_lois(dossiers) -> dict[str, LoiAN]:
    """Lois promulguées de l'open data AN, par numéro (238 dossiers figurent dans deux
    législatures), à partir de (id du document brut, dossier)."""
    lois: dict[str, LoiAN] = {}
    for raw_id, dossier in dossiers:
        acts = list(iter_acts(dossier.get("actesLegislatifs")))
        engagements = sorted(
            (a.get("dateActe") or "")[:10]
            for a in acts
            if a.get("@xsi:type") == "ProcedureAccelere_Type"
        )
        for act in acts:
            if act.get("@xsi:type") != "Promulgation_Type" or not act.get("codeLoi"):
                continue
            loi = lois.setdefault(act["codeLoi"], LoiAN(act["codeLoi"]))
            loi.dossiers[dossier["uid"]] = dossier
            loi.raw_document_ids.add(raw_id)
            if engagements:
                loi.procedure_acceleree = True
                first = engagements[0] or None
                if first and (loi.date_engagement is None or first < loi.date_engagement):
                    loi.date_engagement = first
    return lois


def _legislature(uid: str) -> str:
    match = re.search(r"L(\d+)", uid)
    return match.group(1) if match else ""


def to_draft(jorf: FactDraft, an: LoiAN | None, sen: senat.LoiSenat | None) -> FactDraft:
    an_dossier = an.dossiers[sorted(an.dossiers)[-1]] if an else None  # législature récente
    an_code = an_dossier["procedureParlementaire"]["code"] if an_dossier else None
    sen_type = sen.type if sen else None
    retrait = sen.retrait if sen else None

    statut_senat = sen.statut if sen else None
    sources_engagement = [
        name
        for name, engaged in (
            ("an", an is not None and an.procedure_acceleree),
            ("senat", statut_senat == "acceleree"),
        )
        if engaged
    ]
    connu = an is not None or statut_senat in ("acceleree", "ordinaire")
    if sources_engagement and not retrait:
        statut = "acceleree"
    elif connu or retrait:
        statut = "ordinaire"
    else:
        statut = "inconnu"
    concordance = None
    if an is not None and statut_senat in ("acceleree", "ordinaire"):
        concordance = an.procedure_acceleree == (statut_senat == "acceleree")

    raw_ids = set(jorf.raw_document_ids)
    if an:
        raw_ids |= an.raw_document_ids
    if sen:
        raw_ids.add(sen.raw_document_id)
    uid = sorted(an.dossiers)[-1] if an else None
    return FactDraft(
        indicator_id=INDICATOR,
        fact_type="loi_procedure",
        occurred_on=jorf.occurred_on,
        title=jorf.title,
        official_ref=jorf.official_ref,
        extraction_method=EXTRACTOR,
        raw_document_ids=tuple(sorted(raw_ids)),
        attributes={
            "statut": statut,
            "sources_engagement": sources_engagement,
            "statut_an": None if an is None else an.procedure_acceleree,
            "statut_senat": statut_senat,
            "concordance_an_senat": concordance,
            "date_engagement": (an.date_engagement if an else None)
            or (sen.engagement if sen else None),
            "retrait_senat": retrait,
            "convention_internationale": bool(jorf.attributes.get("convention_internationale"))
            or an_code == PROC_CONVENTION
            or sen_type == SENAT_CONVENTION,
            "constitutionnelle": bool(CONSTITUTIONNELLE.match(jorf.title))
            or an_code == PROC_CONSTITUTIONNELLE
            or sen_type in SENAT_CONSTITUTIONNELLE,
            "finances": bool(FINANCES.match(jorf.title))
            or an_code in PROC_FINANCES
            or sen_type in SENAT_FINANCES
            or statut_senat == "de_droit",
            "url": jorf.attributes.get("url"),
            "url_an": DOSSIER_URL.format(legislature=_legislature(uid), uid=uid) if uid else None,
            "url_senat": sen.url if sen else None,
        },
    )


def extract(conn: sqlite3.Connection, raw_dir: Path, lois_jorf: list[FactDraft]) -> list[FactDraft]:
    """`lois_jorf` : faits `loi_promulguee` déjà extraits des fonds DILA (indicateur D2)."""

    def dossiers():
        for doc in latest_documents(conn, SOURCE_ID):
            for dossier in iter_dossiers(raw_dir / doc["path"]):
                yield doc["id"], dossier

    lois_an = collect_lois(dossiers())
    lois_senat = senat.latest_lois(conn, raw_dir)
    if not lois_an and not lois_senat:  # aucune source de procédure archivée
        return []
    return [
        to_draft(d, lois_an.get(d.official_ref), lois_senat.get(d.official_ref))
        for d in sorted(lois_jorf, key=lambda d: d.official_ref or "")
        if d.fact_type == "loi_promulguee" and d.official_ref and d.occurred_on >= HISTORY_START
    ]
