"""Faits nouveaux depuis la dernière exécution : résumé écrit et notification de bureau.

La base est reconstruite chaque jour (`make rebuild`) : les identifiants des faits changent,
on compare donc des clés stables (indicateur, type de fait, référence officielle, titre,
date). Un même texte peut porter plusieurs faits le même jour (un décret, deux territoires) :
le titre les distingue ; des faits entièrement identiques sont numérotés (#2, #3…).
La liste des clés de la dernière exécution est gardée dans `data/cache/faits_connus.v2.json` ;
à la première exécution, elle est seulement enregistrée.

Un fait « nouveau » est un fait absent de la liste précédente : publié depuis, ou devenu
visible (décision de justice mise en ligne plusieurs mois après, extracteur modifié). Il est
listé avec sa propre date. Les faits disparus sont signalés aussi : ils trahissent en général
une correction de source ou d'extraction.

Faits marquants (listés un par un et cités dans la notification) : règle par type de fait,
`MARQUANTS` ; les autres types (lois promulguées, ordonnances, avis…) sont seulement comptés.
Si des collectes ont échoué, le résumé le dit en tête : l'absence de fait nouveau ne
signifie alors rien pour ces sources.
Ton : informatif. Le résumé décrit ce qui a été enregistré, il ne qualifie pas.

Sorties :
  data/exports/nouveautes.md               résumé de la dernière exécution
  data/logs/nouveautes-AAAA-MM-JJ.md       copie datée

Usage :
    python -m ops.nouveautes [--db CHEMIN] [--sans-notification]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from storage.db import DEFAULT_DB_PATH, ROOT

# v2 : le titre entre dans la clé (la v1 confondait des faits de même référence et même date).
KNOWN_PATH = ROOT / "data" / "cache" / "faits_connus.v2.json"
SUMMARY_PATH = ROOT / "data" / "exports" / "nouveautes.md"
LOG_DIR = ROOT / "data" / "logs"
MAX_LIGNES = 15  # faits listés par type ; au-delà, seulement le nombre

Fact = dict


def _always(_attrs: dict) -> bool:
    return True


# Type de fait -> (libellé, règle : le fait est-il marquant ?)
MARQUANTS: dict[str, tuple[str, Callable[[dict], bool]]] = {
    "engagement_49_3": ("Engagements de responsabilité (49.3)", _always),
    "dissolution_administrative": ("Dissolutions administratives", _always),
    "report_scrutin": ("Reports de scrutin", _always),
    "texte_electoral": (
        "Règles électorales modifiées moins d'un an avant un scrutin",
        lambda a: bool(a.get("moins_d_un_an")),
    ),
    "periode_regime_exception": ("Régimes d'exception", _always),
    "decision_dc_loi": (
        "Lois censurées par le Conseil constitutionnel",
        lambda a: bool(a.get("au_fond") and a.get("censure")),
    ),
    "decret_apres_avis_cnil": (
        "Décrets publiés malgré des réserves de la CNIL",
        lambda a: bool(a.get("malgre_reserves")) and a.get("confiance") != "faible",
    ),
    "decision_interdiction_manifestation": (
        "Décisions de justice sur des interdictions de manifester",
        _always,
    ),
    "mesure_journaliste": ("Journalistes inquiétés", _always),
    "classement_rsf": ("Classement RSF", _always),
    "surveillance_annee": ("Techniques de renseignement (CNCTR)", _always),
    "temps_parole_mois": ("Temps de parole (Arcom)", _always),
}


def key(fact: Fact) -> str:
    ref = fact["official_ref"] or ""
    return "|".join(
        (fact["indicator_id"], fact["fact_type"], ref, fact["title"], fact["occurred_on"])
    )


def current_facts(conn: sqlite3.Connection) -> dict[str, Fact]:
    rows = conn.execute(
        "SELECT indicator_id, fact_type, occurred_on, title, official_ref, attributes"
        " FROM facts ORDER BY occurred_on, id"
    )
    facts = {}
    for indicator_id, fact_type, occurred_on, title, official_ref, attributes in rows:
        fact = {
            "indicator_id": indicator_id,
            "fact_type": fact_type,
            "occurred_on": occurred_on,
            "title": title,
            "official_ref": official_ref,
            "attributes": json.loads(attributes),
        }
        k, n = key(fact), 1
        while (k if n == 1 else f"{k}#{n}") in facts:
            n += 1
        facts[k if n == 1 else f"{k}#{n}"] = fact
    return facts


def load_known(path: Path) -> dict[str, dict] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_known(path: Path, facts: dict[str, Fact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        k: {"fact_type": f["fact_type"], "occurred_on": f["occurred_on"], "title": f["title"]}
        for k, f in facts.items()
    }
    path.write_text(json.dumps(slim, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def marquant(fact: Fact) -> bool:
    rule = MARQUANTS.get(fact["fact_type"])
    return bool(rule and rule[1](fact["attributes"]))


def summarize(
    day: dt.date,
    new: list[Fact],
    gone: list[dict],
    first_run: bool,
    echecs: list[str] | tuple[str, ...] = (),
) -> str:
    lines = [f"# Faits nouveaux du {day.strftime('%d/%m/%Y')}", ""]
    if echecs:
        lines += [
            f"**Collecte incomplète** : {len(echecs)} collecte(s) en échec"
            f" ({', '.join(echecs)}). Le relevé ci-dessous ne porte que sur les données"
            " déjà archivées ; ce que ces sources ont publié depuis n'y figure pas encore."
            " Détail : make etat.",
            "",
        ]
    if first_run:
        lines += [
            "Première exécution : la liste des faits connus vient d'être enregistrée.",
            "Les faits nouveaux seront signalés à partir de la prochaine exécution.",
        ]
        return "\n".join(lines) + "\n"
    if not new and not gone:
        lines.append(
            "Aucun fait nouveau dans les données disponibles."
            if echecs
            else "Aucun fait nouveau depuis la dernière exécution."
        )
        return "\n".join(lines) + "\n"

    notable = [f for f in new if marquant(f)]
    lines.append(
        f"{len(new)} fait(s) nouveau(x) enregistré(s), dont {len(notable)} marquant(s) ;"
        f" {len(gone)} fait(s) disparu(s)."
    )
    by_type: dict[str, list[Fact]] = defaultdict(list)
    for fact in notable:
        by_type[fact["fact_type"]].append(fact)
    for fact_type, label in ((t, MARQUANTS[t][0]) for t in MARQUANTS if t in by_type):
        facts = sorted(by_type[fact_type], key=lambda f: f["occurred_on"])
        lines += ["", f"## {label} ({len(facts)})", ""]
        for fact in facts[:MAX_LIGNES]:
            url = fact["attributes"].get("url")
            title = f"[{fact['title']}]({url})" if url else fact["title"]
            lines.append(f"- {fact['occurred_on']} — {title}")
        if len(facts) > MAX_LIGNES:
            lines.append(f"- … et {len(facts) - MAX_LIGNES} autre(s)")

    others = Counter(f["fact_type"] for f in new if not marquant(f))
    if others:
        lines += ["", "## Autres faits nouveaux (comptés)", ""]
        lines += [f"- {fact_type} : {n}" for fact_type, n in sorted(others.items())]
    if gone:
        lines += ["", "## Faits disparus", ""]
        lines.append(
            "En général une correction de source ou d'extraction ; à vérifier dans le journal."
        )
        lines.append("")
        for fact_type, n in sorted(Counter(g["fact_type"] for g in gone).items()):
            lines.append(f"- {fact_type} : {n}")
    return "\n".join(lines) + "\n"


def notification(day: dt.date, new: list[Fact]) -> tuple[str, str] | None:
    """Titre et texte de la notification, seulement s'il y a des faits marquants."""
    notable = Counter(f["fact_type"] for f in new if marquant(f))
    if not notable:
        return None
    title = f"Baromètre : faits nouveaux du {day.strftime('%d/%m/%Y')}"
    body = "\n".join(f"{MARQUANTS[t][0]} : {n}" for t, n in notable.most_common())
    return title, body + "\nDétail : data/exports/nouveautes.md"


def notify(title: str, body: str) -> None:
    command = [
        "notify-send",
        "--app-name=Baromètre démocratique",
        "--urgency=normal",
        "--icon=dialog-information",
        title,
        body,
    ]
    try:
        subprocess.run(command, check=False, timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[nouveautes] notification impossible : {e}", file=sys.stderr)


def run(
    conn: sqlite3.Connection,
    day: dt.date,
    known_path: Path = KNOWN_PATH,
    summary_path: Path = SUMMARY_PATH,
    log_dir: Path = LOG_DIR,
    send: Callable[[str, str], None] | None = notify,
    echecs: list[str] | tuple[str, ...] = (),
) -> dict:
    facts = current_facts(conn)
    known = load_known(known_path)
    first_run = known is None
    known = known or {}
    new = [f for k, f in facts.items() if k not in known] if not first_run else []
    gone = [v for k, v in known.items() if k not in facts]
    text = summarize(day, new, gone, first_run, echecs)
    for path in (summary_path, log_dir / f"nouveautes-{day.isoformat()}.md"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    save_known(known_path, facts)
    message = notification(day, new)
    if message and send:
        send(*message)
    return {
        "premiere_execution": first_run,
        "nouveaux": len(new),
        "marquants": sum(1 for f in new if marquant(f)),
        "disparus": len(gone),
        "sources_en_echec": list(echecs),
        "resume": str(summary_path.relative_to(ROOT))
        if summary_path.is_relative_to(ROOT)
        else str(summary_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ops.nouveautes")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--sans-notification", action="store_true")
    args = parser.parse_args(argv)
    conn = sqlite3.connect(args.db)
    try:
        result = run(conn, dt.date.today(), send=None if args.sans_notification else notify)
    finally:
        conn.close()
    print(
        f"[nouveautes] {result['nouveaux']} nouveau(x), {result['marquants']} marquant(s),"
        f" {result['disparus']} disparu(s) -> {result['resume']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
