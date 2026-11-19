"""Mesures d'application des lois -> faits (D2.6).

Source : baromètre de l'application des lois de l'Assemblée nationale (collectors/
application_lois.py). Une loi renvoie souvent à des décrets pour s'appliquer ; le Gouvernement
s'est fixé de les publier dans les six mois (circulaire du Premier ministre du 29 février
2008, reprise depuis). Une mesure est datée de son échéance (publication de la loi + six mois)
et classée :
  - `mesure_appliquee_delai` : appliquée, délai d'application de six mois au plus ;
  - `mesure_non_appliquee_delai` : appliquée plus tard, ou toujours en attente.
Écartées : mesures « sans objet », mesures appliquées dont le délai n'est pas renseigné, et
mesures dont l'échéance tombe après la date du relevé (le délai court encore).
"""

from __future__ import annotations

import calendar
import csv
import datetime as dt
import io
import sqlite3
from pathlib import Path

from collectors.application_lois import FICHIERS, SOURCE_ID
from extract.common import FactDraft, latest_documents

INDICATOR = "D2.application_lois"
EXTRACTOR = "an_application_lois@1"
DELAI_MOIS = 6
URL_LOI = "https://www.legifrance.gouv.fr/jorf/id/{id}"


def plus_mois(jour: dt.date, mois: int) -> dt.date:
    annee, m = divmod(jour.month - 1 + mois, 12)
    annee += jour.year
    m += 1
    return dt.date(annee, m, min(jour.day, calendar.monthrange(annee, m)[1]))


def lire(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    docs = {d["external_id"]: d for d in latest_documents(conn, SOURCE_ID)}
    if not all(nom in docs for nom in FICHIERS):
        return []
    d_lois, d_mesures = docs["lois.csv"], docs["mesures.csv"]
    releve = dt.date.fromisoformat(d_mesures["fetched_at"][:10])
    lois = {
        r["Identifiant Légifrance de la loi"]: r
        for r in lire((raw_dir / d_lois["path"]).read_bytes())
    }
    drafts = []
    for m in lire((raw_dir / d_mesures["path"]).read_bytes()):
        loi = lois.get(m["Identifiant loi"])
        etat = m["État"].strip()
        if not loi or etat == "sans objet":
            continue
        publication = dt.date.fromisoformat(loi["Date de publication de la loi"])
        echeance = plus_mois(publication, DELAI_MOIS)
        if echeance > releve:
            continue
        delai = m["Délai d'application (en jours)"].strip()
        if etat == "appliqué":
            if not delai:
                continue
            dans_delai = publication + dt.timedelta(days=int(delai)) <= echeance
        else:
            dans_delai = False
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="mesure_appliquee_delai" if dans_delai else "mesure_non_appliquee_delai",
                occurred_on=echeance.isoformat(),
                title=f"{m['Titre loi'].strip()} — mesure {m['N° ordre']}",
                official_ref=f"{m['Identifiant loi']}#{m['N° ordre']}",
                extraction_method=EXTRACTOR,
                raw_document_ids=(d_lois["id"], d_mesures["id"]),
                attributes={
                    "loi": m["Identifiant loi"],
                    "loi_titre": " ".join(loi["Titre de la loi"].split()),
                    "publication": publication.isoformat(),
                    "etat": etat,
                    "delai_jours": int(delai) if delai else None,
                    "decret": m["Identifiant décret"].strip() or None,
                    "url": URL_LOI.format(id=m["Identifiant loi"]),
                },
            )
        )
    return drafts
