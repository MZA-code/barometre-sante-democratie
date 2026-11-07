"""Documents bruts -> faits de l'indicateur D2 (contournement du Parlement).

Orchestre les extracteurs et extrait lui-même les engagements de responsabilité
(article 49 alinéa 3) depuis les dossiers législatifs de l'Assemblée nationale.

Codage d'un 49.3 dans l'open data de l'Assemblée (exploré le 2026-10-26, L14 à L17) :
  - un acte législatif de type `DeclarationGouvernement_Type` (code d'acte `*-DGVT`)
    dont `typeDeclaration.fam_code == "Art.49.3"` ;
  - les autres déclarations du Gouvernement (`Art.50.1`) sont ignorées ;
  - un même acte (même `uid`) figure à la fois dans le dossier du texte
    (code d'acte préfixé par la lecture : AN1, ANNLEC, ANLDEF, CMP...) et dans un
    dossier dédié « Engagement de la responsabilité gouvernementale »
    (`procedureParlementaire.code == "13"`, code d'acte AN21-DGVT) : on dédoublonne
    par `uid` et on rattache le fait au dossier du texte ;
  - l'issue de la motion de censure déposée en réponse est dans les actes
    `DecisionMotionCensure_Type` imbriqués : `decision.fam_code == "TSORTMOT01"`
    signifie « Motion adoptée » (le texte n'est alors pas adopté).
Contrôle : 6 engagements en L14, 1 en L15, 23 en L16, conformes aux décomptes publics.

Usage :
    python -m extract.parlement [--db CHEMIN] [--raw-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from extract import (
    arcom,
    cnctr,
    cnil,
    constit,
    ddd,
    dila,
    elections,
    exception,
    gdelt,
    interpellations,
    journalistes,
    libertes,
    manifestations,
    mobilisations,
    onu,
    rsf,
    scrutins,
    seed,
)
from extract.common import INDICATOR_D2, FactDraft, latest_documents, write_facts
from storage.archive import DEFAULT_RAW_DIR
from storage.db import DEFAULT_DB_PATH, connect, init_db, reset_derived

EXTRACTOR_49_3 = "an_dossiers_49_3/1"
SOURCE_ID = "an_opendata"
ART_49_3 = "Art.49.3"
PROCEDURE_ENGAGEMENT = "13"  # dossier dédié « Engagement de la responsabilité gouvernementale »
CENSURE_ADOPTEE = "TSORTMOT01"
DOSSIER_URL = "https://www.assemblee-nationale.fr/dyn/{legislature}/dossiers/{uid}"


@dataclass
class Engagement:
    act: dict
    raw_document_ids: set[int] = field(default_factory=set)
    texte: dict | None = None  # dossier du texte concerné
    lecture: str | None = None  # préfixe du code d'acte dans le dossier du texte
    dedie: dict | None = None  # dossier dédié à l'engagement, s'il existe


def iter_dossiers(zip_path: Path) -> Iterator[dict]:
    """Dossiers parlementaires d'une archive AN, quel que soit son format.

    L15 et suivantes : un fichier JSON par dossier (json/dossierParlementaire/*.json).
    L14 : un seul fichier JSON, export.dossiersLegislatifs.dossier[].dossierParlementaire.
    """
    with zipfile.ZipFile(zip_path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".json") or "/document/" in name:
                continue
            data = json.loads(archive.read(name))
            if "dossierParlementaire" in data:
                yield data["dossierParlementaire"]
            elif "export" in data:
                dossiers = data["export"]["dossiersLegislatifs"]["dossier"]
                for item in dossiers if isinstance(dossiers, list) else [dossiers]:
                    yield item["dossierParlementaire"]


def iter_acts(node) -> Iterator[dict]:
    if isinstance(node, dict):
        if "codeActe" in node:
            yield node
        for value in node.values():
            yield from iter_acts(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_acts(value)


def is_49_3(act: dict) -> bool:
    return (
        act.get("@xsi:type") == "DeclarationGouvernement_Type"
        and (act.get("typeDeclaration") or {}).get("fam_code") == ART_49_3
    )


def censure_adoptee(act: dict) -> bool:
    return any(
        sub.get("@xsi:type") == "DecisionMotionCensure_Type"
        and (sub.get("decision") or {}).get("fam_code") == CENSURE_ADOPTEE
        for sub in iter_acts(act.get("actesLegislatifs"))
    )


def collect_engagements(dossiers: Iterator[tuple[int, dict]]) -> dict[str, Engagement]:
    """Regroupe les actes 49.3 par uid à partir de (id du document brut, dossier)."""
    engagements: dict[str, Engagement] = {}
    for raw_id, dossier in dossiers:
        dedicated = dossier["procedureParlementaire"]["code"] == PROCEDURE_ENGAGEMENT
        for act in iter_acts(dossier.get("actesLegislatifs")):
            if not is_49_3(act):
                continue
            eng = engagements.setdefault(act["uid"], Engagement(act=act))
            eng.raw_document_ids.add(raw_id)
            if dedicated:
                eng.dedie = eng.dedie or dossier
            elif eng.texte is None:
                eng.texte = dossier
                eng.lecture = act["codeActe"].removesuffix("-DGVT")
    return engagements


def to_draft(uid: str, eng: Engagement) -> FactDraft:
    act = eng.act
    dossier = eng.texte or eng.dedie
    legislature = dossier["legislature"]
    title = (eng.dedie or dossier)["titreDossier"]["titre"]
    return FactDraft(
        indicator_id=INDICATOR_D2,
        fact_type="engagement_49_3",
        occurred_on=act["dateActe"][:10],
        title=title,
        official_ref=act.get("texteAssocie") or uid,
        extraction_method=EXTRACTOR_49_3,
        raw_document_ids=tuple(sorted(eng.raw_document_ids)),
        attributes={
            "acte_uid": uid,
            "code_acte": act["codeActe"],
            "legislature": int(legislature),
            "lecture": eng.lecture,
            # Clé de regroupement des textes distincts : dossier du texte si connu.
            "texte_uid": dossier["uid"],
            "texte_titre": dossier["titreDossier"]["titre"],
            "texte_rattache": eng.texte is not None,
            "dossier_dedie_uid": eng.dedie["uid"] if eng.dedie else None,
            "censure_adoptee": censure_adoptee(act),
            "url": DOSSIER_URL.format(legislature=legislature, uid=dossier["uid"]),
        },
    )


def extract_49_3(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    def dossiers():
        for doc in latest_documents(conn, SOURCE_ID):
            for dossier in iter_dossiers(raw_dir / doc["path"]):
                yield doc["id"], dossier

    engagements = collect_engagements(dossiers())
    return [to_draft(uid, eng) for uid, eng in sorted(engagements.items())]


def extract_all(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    """Faits de tous les indicateurs construits (D2, D2.2, D3.1, D3.2, D4.1) et du contexte
    (participation électorale)."""
    from extract import procedure  # importe ce module : import différé (cycle)

    textes_dila = dila.extract(conn, raw_dir)
    return (
        extract_49_3(conn, raw_dir)
        + textes_dila
        + procedure.extract(conn, raw_dir, textes_dila)
        + seed.extract(conn, raw_dir)
        + exception.extract(conn, raw_dir)
        + libertes.extract(conn, raw_dir)
        + constit.extract(conn, raw_dir)
        + elections.extract(conn, raw_dir)
        + manifestations.extract(conn, raw_dir)
        + mobilisations.extract(conn, raw_dir)
        + cnil.extract(conn, raw_dir)
        + arcom.extract(conn, raw_dir)
        + arcom.extract_partis(conn, raw_dir)
        + rsf.extract(conn, raw_dir)
        + cnctr.extract(conn, raw_dir)
        + scrutins.extract(conn, raw_dir)
        + journalistes.extract(conn, raw_dir)
        + onu.extract(conn, raw_dir)
        + gdelt.extract(conn, raw_dir)
        + ddd.extract(conn, raw_dir)
        + interpellations.extract(conn, raw_dir)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m extract.parlement")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        init_db(conn)
        # De nouveaux faits invalident métriques et notes : on repart de zéro.
        reset_derived(conn)
        drafts = extract_all(conn, args.raw_dir)
        write_facts(conn, drafts)
        counts = conn.execute(
            "SELECT fact_type, count(*) AS n FROM facts GROUP BY fact_type ORDER BY fact_type"
        ).fetchall()
    finally:
        conn.close()
    for row in counts:
        print(f"[extract] {row['fact_type']} : {row['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
