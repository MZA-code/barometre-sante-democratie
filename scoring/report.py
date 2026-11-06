"""Rapports de contrôle (Markdown).

  controle    : pour une date, la valeur de chaque métrique et la liste des faits qui la
                composent, avec leurs références officielles et leurs liens ;
  echantillon : N faits tirés au hasard (graine fixe), à vérifier à la main via
                official_ref et l'URL.

Usage :
    python -m scoring.report controle --date AAAA-MM-JJ [--window glissante_365j|legislature_N]
    python -m scoring.report echantillon [--n 20] [--seed 2026]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

from scoring.grid import DEFAULT_GRID_PATH, Indicator, load_grid
from scoring.metrics import format_value, legislature_windows, load_legislatures
from storage.db import DEFAULT_DB_PATH, connect, init_db

FACT_LABELS = {
    "engagement_49_3": "Engagements de responsabilité (49.3)",
    "ordonnance_publiee": "Ordonnances publiées",
    "loi_promulguee": "Lois promulguées",
}


def window_bounds(indicator: Indicator, window_id: str, day: dt.date) -> tuple[dt.date, dt.date]:
    if window_id.startswith("glissante_"):
        days = int(window_id.removeprefix("glissante_").removesuffix("j"))
        return day - dt.timedelta(days=days - 1), day
    for window in legislature_windows(load_legislatures(), indicator.history_start, day):
        if window.id == window_id:
            return window.start, window.end
    raise ValueError(f"Fenêtre inconnue ou postérieure à la date : {window_id}")


def raw_sources(conn: sqlite3.Connection, fact_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT r.id, r.source_id, r.external_id, r.url, r.sha256 FROM fact_sources AS fs"
        " JOIN raw_documents AS r ON r.id = fs.raw_document_id"
        " WHERE fs.fact_id = ? ORDER BY r.id",
        (fact_id,),
    ).fetchall()


def fact_lines(conn: sqlite3.Connection, fact: sqlite3.Row) -> list[str]:
    attrs = json.loads(fact["attributes"])
    details = [f"`{key}`={value}" for key, value in sorted(attrs.items()) if key != "url"]
    lines = [
        f"- **{fact['occurred_on']}** — {fact['title']}",
        f"  - fait #{fact['id']} · réf. officielle : {fact['official_ref'] or '—'}"
        f" · extraction : {fact['extraction_method']}"
        f" · vérifié : {'oui' if fact['verified_by_human'] else 'non'}",
    ]
    if attrs.get("url"):
        lines.append(f"  - lien : {attrs['url']}")
    lines.append(f"  - attributs : {', '.join(details)}")
    for raw in raw_sources(conn, fact["id"]):
        lines.append(
            f"  - document brut #{raw['id']} ({raw['source_id']}) : {raw['url']}"
            f" · sha256 {raw['sha256'][:16]}…"
        )
    return lines


def controle(
    conn: sqlite3.Connection,
    indicator: Indicator,
    grid_version: str,
    day: dt.date,
    window_id: str,
    scale_meaning: str | None = None,
) -> str:
    start, end = window_bounds(indicator, window_id, day)
    period_end = end.isoformat()
    values = conn.execute(
        "SELECT name, value, computed_at FROM metrics WHERE indicator_id = ? AND window_id = ?"
        " AND period_end = ? AND grid_version = ?",
        (indicator.id, window_id, period_end, grid_version),
    ).fetchall()
    out = [
        f"# Contrôle {indicator.id} — {window_id} au {period_end}",
        "",
        f"- Grille : {grid_version} · fenêtre du {start} au {end} inclus",
        f"- État de l'archive : {values[0]['computed_at'] if values else '—'}",
        "",
        "## Métriques",
        "",
    ]
    if not values:
        out.append("Aucune métrique calculée pour cette date (hors période ou base non calculée).")
    by_name = {v["name"]: v["value"] for v in values}
    out += [
        f"- `{name}` = {format_value(name, by_name[name]) if name in by_name else 'non calculée'}"
        for name in indicator.metrics
    ]
    score = conn.execute(
        "SELECT score FROM scores WHERE indicator_id = ? AND window_id = ? AND period_end = ?"
        " AND grid_version = ?",
        (indicator.id, window_id, period_end, grid_version),
    ).fetchone()
    out += [
        "",
        f"Note 0-4 : {score['score'] if score else 'aucune (seuils de la grille non figés)'}",
        f"Échelle : {scale_meaning or 'non définie dans la grille'}",
    ]
    for fact_type in indicator.fact_types:
        facts = conn.execute(
            "SELECT * FROM facts WHERE indicator_id = ? AND fact_type = ?"
            " AND occurred_on BETWEEN ? AND ? ORDER BY occurred_on, id",
            (indicator.id, fact_type, start.isoformat(), end.isoformat()),
        ).fetchall()
        out += ["", f"## {FACT_LABELS.get(fact_type, fact_type)} ({len(facts)})", ""]
        for fact in facts:
            out += fact_lines(conn, fact)
    return "\n".join(out) + "\n"


def echantillon(conn: sqlite3.Connection, n: int, seed: int, since: dt.date) -> str:
    """N faits tirés parmi ceux de la période mesurée (à partir de `since`)."""
    ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM facts WHERE occurred_on >= ? ORDER BY id", (since.isoformat(),)
        )
    ]
    chosen = sorted(random.Random(seed).sample(ids, min(n, len(ids))))
    out = [
        f"# Échantillon de contrôle : {len(chosen)} faits sur {len(ids)} depuis le {since}"
        f" (graine {seed})",
        "",
        "Pour chaque fait : retrouver le texte via la référence officielle et le lien,",
        "vérifier date, nature et titre, puis cocher.",
        "",
    ]
    for fact_id in chosen:
        fact = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        lines = fact_lines(conn, fact)
        out += [lines[0].replace("- ", "- [ ] ", 1), *lines[1:]]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scoring.report")
    parser.add_argument("command", choices=["controle", "echantillon"])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID_PATH)
    parser.add_argument("--date", type=dt.date.fromisoformat)
    parser.add_argument("--window", default="glissante_365j")
    parser.add_argument("--indicator", default="D2.contournement_parlement")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    grid = load_grid(args.grid)
    conn = connect(args.db)
    try:
        init_db(conn)
        if args.command == "controle":
            if args.date is None:
                parser.error("--date est obligatoire pour controle")
            indicator = grid.indicators[args.indicator]
            text = controle(
                conn, indicator, grid.version, args.date, args.window, grid.scale_meaning
            )
        else:
            since = grid.indicators[args.indicator].history_start
            text = echantillon(conn, args.n, args.seed, since)
    finally:
        conn.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Rapport écrit : {args.output}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
