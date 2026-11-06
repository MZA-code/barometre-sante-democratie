"""Archives DILA CONSTIT -> décisions du Conseil constitutionnel (indicateur D3.2).

Chaque décision est un fichier CONSTEXT*.xml ; on ne lit que ses métadonnées :
NATURE (DC, QPC, AN, ...), NUMERO, DATE_DEC, TITRE, SOLUTION. Le texte de la décision
n'est pas utilisé (il nomme des personnes : règle 5).

Faits produits :
  - `decision_dc_loi` : décision DC portant sur une loi (contrôle avant promulgation :
    lois ordinaires déférées par des parlementaires ou l'exécutif, lois organiques
    transmises d'office). Exclues : règlements des assemblées, traités et engagements
    internationaux, révision constitutionnelle, demandes de récusation.
  - `decision_qpc` : question prioritaire de constitutionnalité (depuis le 1er mars 2010),
    affichée en contexte : elle porte sur des lois déjà en vigueur.

Statut lu dans SOLUTION (valeurs constatées le 2026-11-05) :
  - « Non conformité ... » (partielle ou totale, avec ou sans réserve / effet différé)
    -> censure ;
  - « Conformité ... » -> pas de censure ;
  - autre (Irrecevabilité, Incompétence pour statuer, Rejet, Non lieu à statuer) -> pas
    de décision au fond : le fait est gardé (au_fond = false) mais n'entre pas dans les
    comptes.

Doublons : 33 numéros DC figurent deux fois (rééditions de 2025 ajoutant « réserve » à la
solution ; statut de censure identique dans tous les cas constatés). On garde la fiche
au plus grand identifiant CONSTEXT et on cite toutes les archives qui contiennent l'une
ou l'autre.

Les archives sont lues dans l'ordre (dump complet puis incréments) : la version la plus
récente d'une fiche l'emporte.
"""

from __future__ import annotations

import re
import sqlite3
import tarfile
from dataclasses import dataclass
from pathlib import Path

from defusedxml import ElementTree as ET

from extract.common import FactDraft, latest_documents

SOURCE_ID = "dila_constit"
EXTRACTOR = "dila_constit/1"
INDICATOR = "D3.lois_censurees"
LEGIFRANCE_URL = "https://www.legifrance.gouv.fr/cons/id/{id}"
FIELDS = ("ID", "NATURE", "NUMERO", "DATE_DEC", "TITRE", "SOLUTION")

# Une loi : « Loi ... », « Lois organiques ... », « Troisième loi de finances ... »,
# « Dernière loi de finances ... » (le mot loi parmi les trois premiers mots).
LOI = re.compile(r"^(?:\S+\s+){0,2}lois?\b", re.IGNORECASE)
ORGANIQUE = re.compile(r"^(?:\S+\s+){0,2}lois?\s+organiques?\b", re.IGNORECASE)
NON_LOI = re.compile(
    r"^(?:r[èe]glement|r[ée]solutions?|dispositions du r[èe]glement|trait[ée]|accord"
    r"|protocole|charte|engagements|d[ée]cision|r[ée]vision|demande)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Decision:
    id: str
    nature: str
    numero: str
    date: str
    titre: str
    solution: str

    @property
    def au_fond(self) -> bool:
        return self.solution.startswith(("Conformité", "Non conformité"))

    @property
    def censure(self) -> bool:
        return self.solution.startswith("Non conformité")


def is_loi(titre: str) -> bool:
    return bool(LOI.match(titre)) and not NON_LOI.match(titre)


def parse_meta(xml: bytes) -> Decision | None:
    root = ET.fromstring(xml)
    values = {}
    for name in FIELDS:
        node = root.find(f".//{name}")
        values[name] = " ".join("".join(node.itertext()).split()) if node is not None else ""
    if not values["ID"] or not values["NUMERO"]:
        return None
    return Decision(
        id=values["ID"],
        nature=values["NATURE"],
        numero=values["NUMERO"],
        date=values["DATE_DEC"],
        titre=values["TITRE"],
        solution=values["SOLUTION"],
    )


def read_archives(
    conn: sqlite3.Connection, raw_dir: Path
) -> tuple[dict[str, Decision], dict[str, set[int]]]:
    """Dernière version de chaque fiche (par identifiant CONSTEXT) et archives qui la citent."""
    docs = latest_documents(conn, SOURCE_ID)
    # dump complet d'abord, puis incréments dans l'ordre chronologique du nom
    docs = sorted(
        docs, key=lambda d: (not d["external_id"].startswith("Freemium"), d["external_id"])
    )
    decisions: dict[str, Decision] = {}
    sources: dict[str, set[int]] = {}
    for doc in docs:
        with tarfile.open(raw_dir / doc["path"]) as tar:
            for member in tar:
                name = member.name.rsplit("/", 1)[-1]
                if not (member.isfile() and name.startswith("CONSTEXT") and name.endswith(".xml")):
                    continue
                decision = parse_meta(tar.extractfile(member).read())
                if decision is None:
                    continue
                decisions[decision.id] = decision
                sources.setdefault(decision.id, set()).add(doc["id"])
    return decisions, sources


def deduplicate(
    decisions: dict[str, Decision], sources: dict[str, set[int]]
) -> list[tuple[Decision, list[str], set[int]]]:
    """Une entrée par (nature, numéro) : la fiche au plus grand identifiant."""
    groups: dict[tuple[str, str], list[Decision]] = {}
    for decision in decisions.values():
        groups.setdefault((decision.nature, decision.numero), []).append(decision)
    result = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda d: d.id)
        raw_ids = set().union(*(sources[d.id] for d in group))
        result.append((group[-1], [d.id for d in group], raw_ids))
    return result


def to_draft(decision: Decision, ids: list[str], raw_ids: set[int]) -> FactDraft | None:
    if decision.nature == "DC" and is_loi(decision.titre):
        fact_type = "decision_dc_loi"
        extra = {"organique": bool(ORGANIQUE.match(decision.titre))}
    elif decision.nature == "QPC":
        fact_type = "decision_qpc"
        extra = {}
    else:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", decision.date):
        return None
    return FactDraft(
        indicator_id=INDICATOR,
        fact_type=fact_type,
        occurred_on=decision.date,
        title=decision.titre,
        official_ref=f"{decision.numero} {decision.nature}",
        extraction_method=EXTRACTOR,
        raw_document_ids=tuple(sorted(raw_ids)),
        attributes={
            "constext": decision.id,
            "constext_doublons": ids[:-1],
            "solution": decision.solution,
            "au_fond": decision.au_fond,
            "censure": decision.censure,
            "url": LEGIFRANCE_URL.format(id=decision.id),
            **extra,
        },
    )


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    decisions, sources = read_archives(conn, raw_dir)
    drafts = []
    for decision, ids, raw_ids in deduplicate(decisions, sources):
        draft = to_draft(decision, ids, raw_ids)
        if draft is not None:
            drafts.append(draft)
    return drafts
