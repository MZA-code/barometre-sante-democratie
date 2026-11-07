"""Défenseur des droits : décisions et rappels à la loi liés aux manifestations -> contexte.

Fiches archivées par collectors/ddd.py (catégories « Manifestation » et « Maintien de l'ordre
public » de la base juridique). Un fait `decision_ddd_manifestation` par document propre au
Défenseur des droits (décision, rappel à la loi, règlement amiable…), daté du jour indiqué
sur la fiche. La veille jurisprudentielle (arrêts d'autres juridictions), les rapports et les
ouvrages sont écartés. Titre, résumé et suites (« Recommandation », « Demande de poursuites
disciplinaires »…) sont repris tels que la base les donne ; aucune qualification n'est
ajoutée. Donnée de contexte : aucune note n'en est tirée.
"""

from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path

from collectors.ddd import BASE, SOURCE_ID
from extract.common import FactDraft, latest_documents

EXTRACTOR = "ddd_fiche/1"
INDICATOR = "contexte.defenseur_droits"
# Types de document produits par le Défenseur des droits lui-même (libellés de la base).
TYPES_RETENUS = {
    "Décisions": "décision",
    "Rappels à la loi": "rappel à la loi",
    "Règlements amiables": "règlement amiable",
    "Décisions des précédentes AAI": "décision d'une autorité antérieure",
}
LIGNE = re.compile(r'<tr class="record_(\w+)">(.*?)</tr>', re.S)
CATEG = re.compile(r"<p>\[([^\]]+)\]\s*<a [^>]*>(.*?)</a></p>", re.S)
PDF = re.compile(r'href="(https://juridique\.defenseurdesdroits\.fr/doc_num\.php\?explnum_id=\d+)"')
DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _texte(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def lire_fiche(page: str) -> dict:
    """Champs d'une fiche PMB (titre, type, date, numéro, mots-clés, résumé, PDF)."""
    champs: dict[str, str] = {}
    mots: dict[str, list[str]] = {}
    for classe, contenu in LIGNE.findall(page):
        valeur = contenu.split('class="labelContent"', 1)[-1]
        if classe == "categories":
            for groupe, lib in CATEG.findall(valeur):
                mots.setdefault(groupe.strip(), []).append(_texte(lib))
        else:
            champs[classe] = _texte(valeur.split(">", 1)[-1])
    pdf = PDF.search(page)
    return {
        "titre": champs.get("tit1", ""),
        "type": champs.get("tdoc", ""),
        "date": champs.get("year", ""),
        "numero": champs.get("code") or None,
        "resume": champs.get("resume") or None,
        "mots_cles": mots.get("Mots-clés", []),
        "suites": mots.get("Documents internes", []),
        "pdf": html.unescape(pdf.group(1)) if pdf else None,
    }


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    drafts = []
    for doc in latest_documents(conn, SOURCE_ID):
        f = lire_fiche((raw_dir / doc["path"]).read_text(encoding="utf-8", errors="replace"))
        if not f["titre"]:
            raise ValueError(f"fiche {doc['external_id']} : titre introuvable")
        if f["type"] not in TYPES_RETENUS:
            continue
        m = DATE.match(f["date"])
        if not m:
            raise ValueError(f"fiche {doc['external_id']} : date illisible {f['date']!r}")
        url = f"{BASE}index.php?lvl=notice_display&id={doc['external_id']}"
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="decision_ddd_manifestation",
                occurred_on=f"{m.group(3)}-{m.group(2)}-{m.group(1)}",
                title=f["titre"],
                official_ref=url,
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    "type": TYPES_RETENUS[f["type"]],
                    "numero": f["numero"],
                    "resume": f["resume"],
                    "mots_cles": f["mots_cles"],
                    "suites": f["suites"],
                    "pdf": f["pdf"],
                    "url": url,
                },
            )
        )
    return drafts
