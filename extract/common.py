"""Outils communs aux extracteurs : brouillons de faits et écriture déterministe."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

INDICATOR_D2 = "D2.contournement_parlement"


@dataclass(frozen=True)
class FactDraft:
    """Un fait extrait, pas encore numéroté, avec les documents bruts qui le justifient."""

    indicator_id: str
    fact_type: str
    occurred_on: str  # AAAA-MM-JJ
    title: str
    official_ref: str | None
    extraction_method: str
    raw_document_ids: tuple[int, ...]
    attributes: dict = field(default_factory=dict)

    def sort_key(self) -> tuple:
        return (self.occurred_on, self.fact_type, self.official_ref or "", self.title)


def latest_documents(conn: sqlite3.Connection, source_id: str) -> list[sqlite3.Row]:
    """Dernière version archivée de chaque document d'une source, triée par identifiant."""
    return conn.execute(
        """
        SELECT * FROM raw_documents AS r
        WHERE source_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM raw_documents AS newer
            WHERE newer.source_id = r.source_id AND newer.external_id = r.external_id
              AND (newer.fetched_at, newer.id) > (r.fetched_at, r.id)
          )
        ORDER BY external_id
        """,
        (source_id,),
    ).fetchall()


def write_facts(conn: sqlite3.Connection, drafts: list[FactDraft]) -> int:
    """Insère les faits dans un ordre stable (date, type, référence) : mêmes identifiants
    à chaque reconstruction. Chaque fait doit citer au moins un document brut (règle 2)."""
    with conn:
        for draft in sorted(drafts, key=FactDraft.sort_key):
            if not draft.raw_document_ids:
                raise ValueError(f"Fait sans document source : {draft.title}")
            cur = conn.execute(
                "INSERT INTO facts (indicator_id, fact_type, occurred_on, title, official_ref,"
                " attributes, extraction_method) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    draft.indicator_id,
                    draft.fact_type,
                    draft.occurred_on,
                    draft.title,
                    draft.official_ref,
                    json.dumps(draft.attributes, ensure_ascii=False, sort_keys=True),
                    draft.extraction_method,
                ),
            )
            conn.executemany(
                "INSERT INTO fact_sources (fact_id, raw_document_id) VALUES (?, ?)",
                [(cur.lastrowid, raw_id) for raw_id in sorted(set(draft.raw_document_ids))],
            )
    return len(drafts)
