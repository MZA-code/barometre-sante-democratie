"""Exécution quotidienne : collecte de toutes les sources, reconstruction, export.

Chaque étape est une cible du Makefile, lancée séparément : une source en panne
n'empêche ni les autres collectes ni la reconstruction (la fin des données est alors
simplement bornée par la source vérifiée le moins récemment, voir scoring/metrics.py:data_end).
Le dimanche, l'empreinte de toute l'archive brute est recontrôlée (`verify-raw`).

Sorties :
  data/logs/quotidien-AAAA-MM-JJ.log   sortie complète des commandes du jour
  data/logs/quotidien.jsonl            une ligne par exécution (historique)
  data/exports/etat_quotidien.json     état de la dernière exécution
  data/exports/nouveautes.md           faits nouveaux depuis la veille (ops/nouveautes.py)

Avant les collectes, l'exécution attend que le réseau réponde (résolution DNS d'une source,
10 min au plus) : au réveil d'un portable, le minuteur rattrapé (Persistent=true) part
souvent avant le Wi-Fi, et `network-online.target` est sans effet pour un service
utilisateur. Sans réseau au bout du délai, les étapes sont lancées quand même : les
collectes échouent, la reconstruction repart de l'archive locale.

En cas d'échec d'une étape ou d'erreur inattendue, une notification de bureau est envoyée
(`notify-send`) ; son absence ou son échec n'interrompt jamais l'exécution. Si la
reconstruction a réussi, les faits nouveaux sont comparés à ceux de l'exécution précédente ;
une notification d'information les résume s'il y a des faits marquants.

Code de sortie : 0 si toutes les étapes ont réussi, 1 sinon, 2 si une exécution est déjà
en cours.

Usage :
    python -m ops.quotidien [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from ops import nouveautes

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "logs"
STATE_PATH = ROOT / "data" / "exports" / "etat_quotidien.json"
LOCK_PATH = ROOT / "data" / ".quotidien.lock"

# Seule la législature en cours évolue ; les précédentes sont closes.
COLLECTES = (
    ("collect-seed", ()),
    ("collect-an", ("AN_LEGISLATURES=17",)),
    ("collect-legi", ()),
    ("collect-jorf", ()),
    ("collect-constit", ()),
    ("collect-cnil", ()),
    ("collect-justice", ()),  # seulement les mois terminés : un téléchargement par mois
    ("collect-arcom", ()),  # un fichier par mois, publié ≈ 3 mois après la diffusion
    ("collect-rsf", ()),  # une édition par an
    ("collect-cnctr", ()),  # un rapport par an
    ("collect-datagouv", ()),
    # GDELT : hier, puis rattrapage de l'historique (≈ 2 min par jour, 5 jours par passage)
    ("collect-gdelt", ("GDELT_JOURS=5",)),
    # Défenseur des droits : nouvelles fiches seulement (30 s entre deux requêtes, robots.txt)
    ("collect-ddd", ()),
    ("collect-rapports", ()),  # PDF cités par les relevés manuels, archivés une fois
)
# Sources interrogées pour savoir si le réseau répond (une seule suffit).
HOTES_TEST = ("echanges.dila.gouv.fr", "www.data.gouv.fr")
# `deployer` reconstruit la page publique et l'envoie (sans effet sans config/deploiement.local).
RECONSTRUCTION = (("rebuild", ()), ("prototype-data", ()), ("deployer", ()))
CONTROLE_HEBDO = ("verify-raw", ())
COLLECTE_HEBDO = ("collect-senat", ())


def steps(today: dt.date) -> list[tuple[str, tuple[str, ...]]]:
    plan = [*COLLECTES, *RECONSTRUCTION]
    if today.weekday() == 6:  # dimanche : base du Sénat (≈ 16 Mo par version) et contrôle
        plan.insert(len(COLLECTES), COLLECTE_HEBDO)
        plan.append(CONTROLE_HEBDO)
    return plan


def wait_for_network(
    hosts: tuple[str, ...] = HOTES_TEST,
    timeout_s: float = 600,
    interval_s: float = 15,
    resolve=socket.getaddrinfo,
    sleep=time.sleep,
    clock=time.monotonic,
) -> bool:
    """Vrai dès qu'un des hôtes se résout ; faux après `timeout_s` sans réponse."""
    deadline = clock() + timeout_s
    while True:
        for host in hosts:
            try:
                resolve(host, 443)
                return True
            except OSError:
                pass
        if clock() >= deadline:
            return False
        sleep(min(interval_s, max(deadline - clock(), 0)))


def notify(title: str, body: str) -> None:
    """Notification de bureau ; ne lève jamais (poste sans session graphique, etc.)."""
    command = [
        "notify-send",
        "--app-name=Baromètre démocratique",
        "--urgency=critical",
        "--icon=dialog-warning",
        title,
        body,
    ]
    try:
        subprocess.run(command, check=False, timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[quotidien] notification impossible : {e}", file=sys.stderr)


def failure_message(day: dt.date, failed: list[str], journal: str) -> tuple[str, str]:
    title = f"Baromètre : collecte du {day.strftime('%d/%m/%Y')} en échec"
    body = (
        f"Étape(s) en échec : {', '.join(failed)}.\n"
        f"Journal : {journal}\n"
        "Détail : make etat (dans le dossier du projet)."
    )
    return title, body


def run_step(target: str, variables: tuple[str, ...], log) -> dict:
    command = ["make", "--no-print-directory", target, *variables]
    log.write(f"\n===== {dt.datetime.now().isoformat(timespec='seconds')} {' '.join(command)}\n")
    log.flush()
    start = time.monotonic()
    proc = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
    return {
        "etape": target,
        "code": proc.returncode,
        "duree_s": round(time.monotonic() - start, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ops.quotidien")
    parser.add_argument(
        "--dry-run", action="store_true", help="affiche les étapes sans rien lancer"
    )
    args = parser.parse_args(argv)

    today = dt.date.today()
    plan = steps(today)
    if args.dry_run:
        for target, variables in plan:
            print("make", target, *variables)
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[quotidien] une exécution est déjà en cours", file=sys.stderr)
            return 2

        started = dt.datetime.now().astimezone()
        if not wait_for_network():
            print(
                "[quotidien] réseau injoignable après 10 min, collectes lancées quand même",
                file=sys.stderr,
                flush=True,
            )
        journal = f"data/logs/quotidien-{today.isoformat()}.log"
        results = []
        try:
            with (LOG_DIR / f"quotidien-{today.isoformat()}.log").open(
                "a", encoding="utf-8"
            ) as log:
                for target, variables in plan:
                    result = run_step(target, variables, log)
                    results.append(result)
                    state = "ok" if result["code"] == 0 else f"ÉCHEC (code {result['code']})"
                    print(f"[quotidien] {target} : {state} en {result['duree_s']} s", flush=True)
        except Exception as e:
            notify(
                f"Baromètre : collecte du {today.strftime('%d/%m/%Y')} interrompue",
                f"Erreur inattendue : {e}\nJournal : {journal}",
            )
            raise

        failed = [r["etape"] for r in results if r["code"] != 0]
        faits = None
        if any(r["etape"] == "rebuild" and r["code"] == 0 for r in results):
            try:
                conn = sqlite3.connect(nouveautes.DEFAULT_DB_PATH)
                try:
                    collect_failed = [f for f in failed if f.startswith("collect-")]
                    faits = nouveautes.run(conn, today, echecs=collect_failed)
                finally:
                    conn.close()
            except Exception as e:  # le résumé ne doit jamais faire échouer la collecte
                print(f"[quotidien] faits nouveaux non calculés : {e}", file=sys.stderr)
        record = {
            "debut": started.isoformat(timespec="seconds"),
            "fin": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "statut": "ok" if not failed else "echec",
            "echecs": failed,
            "etapes": results,
            "journal": journal,
            "faits_nouveaux": faits,
        }
        STATE_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
        with (LOG_DIR / "quotidien.jsonl").open("a", encoding="utf-8") as history:
            history.write(json.dumps(record, ensure_ascii=False) + "\n")
    if failed:
        notify(*failure_message(today, failed, journal))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
