"""Collecteur des issues GitHub de validation D7 (instantanés archivés).

Chaque fait de presse candidat à D7 a une issue dans le dépôt public du baromètre (ouverte par
ops/issues_d7.py, étiquette `d7`). Le validateur y pose `validé`, `rejeté` ou `doublon` et
corrige au besoin la catégorie (`cat:<clé>`). Ce collecteur archive, pour chaque issue `d7`
modifiée depuis le dernier passage, un instantané JSON :
  - numéro, état, titre, corps, date de mise à jour, étiquettes présentes (triées) ;
  - `historique` : tous les événements `labeled` / `unlabeled` (étiquette, auteur, date) ;
  - `poses` : pour chaque étiquette présente, son dernier `labeled` (auteur et date).
L'historique ne fait que croître : un retour à un état antérieur produit donc un nouveau
document, jamais un document déjà archivé (dont la date de collecte serait plus ancienne).
Les décisions sont lues dans ces instantanés par extract/d7.py, jamais dans l'API.

Accès : jeton GitHub à grain fin limité au dépôt (permission Issues), dans
`config/github.local` (ignoré par git ; modèle `config/github.local.exemple`). Sans ce fichier,
ou si l'API répond par une erreur (quota, panne), le collecteur ne fait rien et sort avec le
code 0 : aucun contrôle de source n'est noté, la tâche horaire ne republie pas.

Usage :
    python -m collectors.github_d7 [--db CHEMIN] [--raw-dir DOSSIER] [--config FICHIER]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from collectors.http import TIMEOUT, USER_AGENT, now_iso
from extract.common import latest_documents
from storage.archive import DEFAULT_RAW_DIR, record_check, store
from storage.db import DEFAULT_DB_PATH, connect, init_db

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "github.local"
SOURCE_ID = "github_d7"
API = "https://api.github.com"
LIEN_SUIVANT = re.compile(r'<([^>]+)>;\s*rel="next"')


class ErreurApi(RuntimeError):
    """L'API GitHub a répondu par une erreur (quota, droits, panne)."""


def lire_config(path: Path = CONFIG_PATH) -> tuple[str, str] | None:
    if not path.exists():
        return None
    valeurs = {}
    for ligne in path.read_text(encoding="utf-8").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            cle, valeur = ligne.split("=", 1)
            valeurs[cle.strip()] = valeur.strip()
    if not valeurs.get("GITHUB_TOKEN") or not valeurs.get("GITHUB_DEPOT"):
        return None
    return valeurs["GITHUB_TOKEN"], valeurs["GITHUB_DEPOT"]


class Api:
    """Client minimal de l'API REST GitHub pour un dépôt (bibliothèque standard)."""

    def __init__(self, jeton: str, depot: str) -> None:
        self.jeton, self.depot = jeton, depot

    def _appel(self, methode: str, url: str, corps: dict | None = None) -> tuple[object, dict]:
        data = json.dumps(corps).encode() if corps is not None else None
        requete = urllib.request.Request(
            url,
            data=data,
            method=methode,
            headers={
                "Authorization": f"Bearer {self.jeton}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(requete, timeout=TIMEOUT) as reponse:
                return json.loads(reponse.read() or b"null"), dict(reponse.headers)
        except urllib.error.HTTPError as exc:
            reste = exc.headers.get("x-ratelimit-remaining") if exc.headers else None
            quota = " (quota épuisé)" if reste == "0" else ""
            raise ErreurApi(f"{methode} {url} : HTTP {exc.code}{quota}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ErreurApi(f"{methode} {url} : {exc}") from exc

    def url(self, chemin: str) -> str:
        return f"{API}/repos/{self.depot}/{chemin}"

    def lister(self, chemin: str, params: dict) -> list:
        url = self.url(chemin) + "?" + urllib.parse.urlencode({**params, "per_page": 100})
        out: list = []
        while url:
            corps, entetes = self._appel("GET", url)
            out += corps
            m = LIEN_SUIVANT.search(entetes.get("Link") or entetes.get("link") or "")
            url = m.group(1) if m else None
        return out

    def creer(self, chemin: str, corps: dict) -> dict:
        return self._appel("POST", self.url(chemin), corps)[0]


def instantane(issue: dict, evenements: list[dict]) -> dict:
    historique = sorted(
        (
            {
                "evenement": e["event"],
                "etiquette": e["label"]["name"],
                "par": (e.get("actor") or {}).get("login"),
                "le": e["created_at"],
            }
            for e in evenements
            if e.get("event") in ("labeled", "unlabeled") and e.get("label")
        ),
        key=lambda h: (h["le"], h["etiquette"], h["evenement"]),
    )
    etiquettes = sorted(lab["name"] for lab in issue.get("labels", []))
    poses = {}
    for h in historique:
        if h["evenement"] == "labeled" and h["etiquette"] in etiquettes:
            poses[h["etiquette"]] = {"par": h["par"], "le": h["le"]}
    return {
        "numero": issue["number"],
        "etat": issue["state"],
        "titre": issue["title"],
        "corps": issue.get("body") or "",
        "maj": issue["updated_at"],
        "etiquettes": etiquettes,
        "historique": historique,
        "poses": poses,
    }


def dernier_controle(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT max(checked_at) FROM source_checks WHERE source_id = ?", (SOURCE_ID,)
    ).fetchone()
    return row[0]


def collect(
    conn: sqlite3.Connection, raw_dir: Path, api, maintenant: Callable[[], str] = now_iso
) -> int:
    """Archive les issues `d7` modifiées depuis le dernier contrôle ; nombre de documents
    nouveaux. Le contrôle est daté du début du passage (rien de modifié pendant le passage
    n'est perdu au suivant)."""
    debut = maintenant()
    params = {"labels": "d7", "state": "all"}
    if depuis := dernier_controle(conn):
        params["since"] = depuis
    nouveaux = 0
    for issue in api.lister("issues", params):
        if "pull_request" in issue:
            continue
        inst = instantane(issue, api.lister(f"issues/{issue['number']}/events", {}))
        data = json.dumps(inst, ensure_ascii=False, sort_keys=True, indent=1).encode()
        doc = store(
            conn,
            raw_dir,
            source_id=SOURCE_ID,
            external_id=str(inst["numero"]),
            url=f"{API}/repos/{getattr(api, 'depot', '')}/issues/{inst['numero']}",
            fetched_at=maintenant(),
            chunks=[data],
            suffix=".json",
        )
        nouveaux += doc.created
    record_check(conn, raw_dir, SOURCE_ID, debut)
    return nouveaux


def collecter(conn: sqlite3.Connection, raw_dir: Path, api) -> int:
    """`collect` qui ne lève pas : une erreur d'API est affichée, rien n'est noté."""
    try:
        n = collect(conn, raw_dir, api)
    except ErreurApi as exc:
        print(f"[github_d7] API indisponible, rien de fait : {exc}")
        return 0
    print(f"[github_d7] {n} instantané(s) nouveau(x)")
    return n


def instantanes_docs(conn: sqlite3.Connection, raw_dir: Path) -> list[tuple[int, dict]]:
    """(identifiant du document brut, dernier instantané) de chaque issue, par numéro."""
    out = [
        (d["id"], json.loads((raw_dir / d["path"]).read_text(encoding="utf-8")))
        for d in latest_documents(conn, SOURCE_ID)
    ]
    return sorted(out, key=lambda di: di[1]["numero"])


def instantanes(conn: sqlite3.Connection, raw_dir: Path) -> list[dict]:
    return [inst for _, inst in instantanes_docs(conn, raw_dir)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collectors.github_d7")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args(argv)
    config = lire_config(args.config)
    if config is None:
        print(f"[github_d7] {args.config} absent ou incomplet : rien à faire")
        return 0
    conn = connect(args.db)
    try:
        init_db(conn)
        collecter(conn, args.raw_dir, Api(*config))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
