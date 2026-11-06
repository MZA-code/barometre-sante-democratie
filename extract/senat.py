"""Base Dosleg du Sénat (dump PostgreSQL archivé) -> procédure suivie par chaque loi.

Seul le bloc `COPY loi (...) FROM stdin;` du dump est lu, ligne par ligne, sans extraire
le fichier. Format COPY de PostgreSQL : champs séparés par des tabulations, `\\N` pour
NULL, échappements `\\t`, `\\n`, `\\\\`.

Colonnes utilisées (commentaires du schéma, constatés le 2026-11-05) :
  - numero      « Numéro de la loi » (« 85-96 », « 2021-191 ») : clé de rapprochement avec
                les faits `loi_promulguee` du JORF ;
  - date_loi    « Date de promulgation » ;
  - typloicod   type de texte (pjl, ppl, cvn = convention, pjlf = loi de finances...) ;
  - urgence     « oui, non ou dro » : déclaration d'urgence, avant la révision de 2008
                (« dro » : urgence de droit, lois de finances et de financement) ;
  - proaccdat   « Date d'engagement de la procédure accélérée » (depuis 2009) ;
  - retproaccdat « Date de retrait de la procédure accélérée ».

Statut d'une loi (`statut_senat`) :
  - « acceleree »  : urgence = oui, ou procédure accélérée engagée et non retirée ;
  - « de_droit »   : urgence = dro (calendrier constitutionnel des lois de finances) ;
  - « ordinaire »  : urgence = non, ou (depuis 2009) aucune procédure engagée ou retrait ;
  - « inconnu »    : urgence vide avant 2009 sans date d'engagement (constaté surtout de
                     1998 à 2008) : rien ne permet de trancher.
"""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path

from extract.common import latest_documents

SOURCE_ID = "senat_dosleg"
COPY_LOI = re.compile(r"COPY loi \((.*)\) FROM stdin;")
# Avant la révision du 23 juillet 2008 (appliquée en 2009), seule la colonne urgence existe.
REFORME_PROCEDURE = "2009-03-01"
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}


@dataclass(frozen=True)
class LoiSenat:
    numero: str
    date_loi: str
    type: str
    urgence: str | None
    engagement: str | None
    retrait: str | None
    signet: str | None
    raw_document_id: int

    @property
    def statut(self) -> str:
        if self.urgence == "dro":
            return "de_droit"
        if self.urgence == "oui" or (self.engagement and not self.retrait):
            return "acceleree"
        if self.urgence == "non" or self.retrait or self.date_loi >= REFORME_PROCEDURE:
            return "ordinaire"
        return "inconnu"

    @property
    def url(self) -> str | None:
        return (
            f"https://www.senat.fr/dossier-legislatif/{self.signet}.html" if self.signet else None
        )


def unescape(value: str) -> str | None:
    if value == "\\N":
        return None
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), value).strip()


def iter_copy_rows(lines, table_pattern: re.Pattern = COPY_LOI):
    """Lignes (dict) du premier bloc COPY correspondant au motif."""
    columns = None
    for line in lines:
        if columns is None:
            match = table_pattern.match(line)
            if match:
                columns = [c.strip() for c in match.group(1).split(",")]
            continue
        if line.startswith("\\."):
            return
        values = line.rstrip("\n").split("\t")
        yield {c: unescape(v) for c, v in zip(columns, values, strict=False)}


def read_lois(zip_path: Path, raw_document_id: int) -> dict[str, LoiSenat]:
    """Lois promulguées (numéro et date connus), par numéro."""
    lois: dict[str, LoiSenat] = {}
    with zipfile.ZipFile(zip_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".sql"))
        with archive.open(name) as raw:
            lines = io.TextIOWrapper(raw, encoding="utf-8")
            for row in iter_copy_rows(lines):
                numero, date_loi = row.get("numero"), row.get("date_loi")
                if not numero or not date_loi:
                    continue
                lois[numero] = LoiSenat(
                    numero=numero,
                    date_loi=date_loi[:10],
                    type=row.get("typloicod") or "",
                    urgence=row.get("urgence"),
                    engagement=(row.get("proaccdat") or "")[:10] or None,
                    retrait=(row.get("retproaccdat") or "")[:10] or None,
                    signet=row.get("signet"),
                    raw_document_id=raw_document_id,
                )
    return lois


def latest_lois(conn: sqlite3.Connection, raw_dir: Path) -> dict[str, LoiSenat]:
    """Lois de la dernière version archivée de la base Dosleg ({} si aucune)."""
    docs = latest_documents(conn, SOURCE_ID)
    if not docs:
        return {}
    doc = docs[-1]
    return read_lois(raw_dir / doc["path"], doc["id"])
