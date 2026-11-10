"""Tâche horaire D7 : relit les décisions prises sur GitHub et republie le site si besoin.

Lancée par cron toutes les heures (ops/decisions.sh). Elle ne collecte aucune autre source :
  1. si l'exécution quotidienne tourne (verrou data/.quotidien.lock), le tour est sauté ;
  2. flux RSS de la presse (`make collect-rss`) : les flux ne gardent que leurs derniers
     articles, une lecture par jour en perdrait ; un flux en panne n'arrête rien ;
     puis instantanés des issues `d7` modifiées (collectors/github_d7.py) ;
  3. seulement si l'empreinte des décisions (statut, catégorie, lieu, date de chaque issue,
     extract/d7.py:empreinte_decisions) diffère de celle de la dernière publication réussie
     (data/.d7_publiee) : `make rebuild`, `prototype-data`, `deployer` (≈ 15 s). L'empreinte
     n'est notée qu'après une publication réussie : un passage interrompu (erreur d'API après
     quelques instantanés, reconstruction en échec) est rattrapé au tour suivant, et un simple
     commentaire sur une issue ne déclenche rien.
Sans config/github.local, ou si l'API est en erreur, rien n'est republié.

Code de sortie : 0, ou 1 si une étape de reconstruction a échoué.

Usage :
    python -m ops.decisions
"""

from __future__ import annotations

import datetime as dt
import fcntl
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ops.quotidien import LOCK_PATH, ROOT

ETAPES = ("rebuild", "prototype-data", "deployer")
ETAT_PATH = ROOT / "data" / ".d7_publiee"


def empreinte_actuelle() -> str:
    from extract.d7 import empreinte_decisions
    from storage.archive import DEFAULT_RAW_DIR
    from storage.db import DEFAULT_DB_PATH, connect

    conn = connect(DEFAULT_DB_PATH)
    try:
        return empreinte_decisions(conn, DEFAULT_RAW_DIR)
    finally:
        conn.close()


def collecte_github() -> int | None:
    from collectors.github_d7 import Api, collecter, lire_config
    from storage.archive import DEFAULT_RAW_DIR
    from storage.db import DEFAULT_DB_PATH, connect, init_db

    config = lire_config()
    if config is None:
        print("[decisions] config/github.local absent : rien à faire")
        return None
    conn = connect(DEFAULT_DB_PATH)
    try:
        init_db(conn)
        return collecter(conn, DEFAULT_RAW_DIR, Api(*config))
    finally:
        conn.close()


def executer(
    lancer: Callable = subprocess.run,
    collecte: Callable[[], int | None] = collecte_github,
    lock_path: Path = LOCK_PATH,
    empreinte: Callable[[], str] = empreinte_actuelle,
    etat_path: Path = ETAT_PATH,
) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[decisions] exécution quotidienne en cours, tour sauté")
            return 0
        horodatage = dt.datetime.now().isoformat(timespec="seconds")
        proc = lancer(["make", "--no-print-directory", "collect-rss"], cwd=ROOT, check=False)
        if proc.returncode != 0:
            print(f"[decisions] collect-rss : échec (code {proc.returncode}), on continue")
        if collecte() is None:  # pas de config GitHub : D7 pas encore en service
            return 0
        actuelle = empreinte()
        publiee = etat_path.read_text().strip() if etat_path.exists() else None
        if actuelle == publiee:
            print(f"[decisions] {horodatage} : aucune décision nouvelle")
            return 0
        print(f"[decisions] {horodatage} : décisions modifiées, republication")
        for cible in ETAPES:
            proc = lancer(["make", "--no-print-directory", cible], cwd=ROOT, check=False)
            if proc.returncode != 0:
                print(f"[decisions] {cible} : ÉCHEC (code {proc.returncode})")
                return 1
        etat_path.write_text(actuelle)
        print("[decisions] site republié")
        return 0


def main(argv: list[str] | None = None) -> int:
    return executer()


if __name__ == "__main__":
    sys.exit(main())
