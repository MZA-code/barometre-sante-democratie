"""Pages de pétitions archivées -> faits de l'indicateur D2.3 (pétitions citoyennes).

Une pétition compte dès qu'une version archivée de sa page affiche au moins 500 000
signatures : c'est le seuil à partir duquel la Conférence des présidents peut organiser un
débat en séance (article 148 du règlement de l'Assemblée). Un fait par pétition, selon son
dernier statut affiché :
  - `petition_500k_classee` : « Classée par la commission », daté du jour du classement ;
  - `petition_500k_examinee` : acceptée pour examen (rapport, débat), datée du premier jour où
    le seuil a été constaté ;
  - `petition_500k_en_attente` : ouverte ou expirée sans décision, datée de même.
Le sujet de la pétition n'entre dans aucune règle : seul compte ce que l'Assemblée en a fait.
La date du seuil est celle de la première collecte qui l'a constaté quand la pétition était
suivie avant de l'atteindre ; sinon, la date de publication de la pétition.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from collectors.petitions import SOURCE_ID
from extract.common import FactDraft

INDICATOR = "D2.petitions_classees"
EXTRACTOR = "petitions_an/1"
SEUIL = 500_000
TYPES = {
    "classee": "petition_500k_classee",
    "examinee": "petition_500k_examinee",
}


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    versions: dict[str, list[tuple[int, str, dict]]] = {}
    for row in conn.execute(
        "SELECT id, external_id, fetched_at, path FROM raw_documents WHERE source_id = ?"
        " ORDER BY fetched_at, id",
        (SOURCE_ID,),
    ):
        data = json.loads((raw_dir / row["path"]).read_text(encoding="utf-8"))
        versions.setdefault(row["external_id"], []).append((row["id"], row["fetched_at"], data))
    out = []
    for vs in versions.values():
        seuil = next(((i, q) for i, q, d in vs if (d["signatures"] or 0) >= SEUIL), None)
        if seuil is None:
            continue
        doc_id, _, dernier = vs[-1]
        # Seuil constaté par une collecte (une version antérieure était en dessous) ; sinon,
        # pétition déjà au-dessus à la première collecte : date de publication de la pétition.
        franchi_ici = vs[0][2]["signatures"] is not None and vs[0][2]["signatures"] < SEUIL
        publiee = next((d["date_publication"] for _, _, d in vs if d.get("date_publication")), None)
        date_seuil = seuil[1][:10] if franchi_ici else (publiee or seuil[1][:10])
        fact_type = TYPES.get(dernier["statut"], "petition_500k_en_attente")
        jour = (
            dernier["date_decision"]
            if fact_type.endswith("classee") and dernier["date_decision"]
            else date_seuil
        )
        out.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type=fact_type,
                occurred_on=jour,
                title=dernier["titre"],
                official_ref=dernier["url"],
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted({seuil[0], doc_id})),
                attributes={
                    "identifiant": dernier["identifiant"],
                    "titre": dernier["titre"],
                    "signatures": dernier["signatures"],
                    "statut": dernier["statut"],
                    "date_decision": dernier["date_decision"],
                    "date_seuil": date_seuil,
                    "commission": dernier["commission"],
                    "url": dernier["url"],
                },
            )
        )
    return out
