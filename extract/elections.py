"""Résultats électoraux archivés depuis data.gouv.fr -> participation (contexte).

Donnée de contexte, hors grille : aucune note n'en est tirée. Un fait par scrutin et par
tour (`scrutin_participation`), niveau « France entière », avec inscrits, votants,
abstentions, blancs, nuls, exprimés. Les jeux concernés et la date de chaque tour sont
déclarés dans config/datagouv.yaml (clé `scrutin`).

Seules ces six colonnes sont lues : les colonnes de nuances politiques et de voix ne le
sont jamais (règle 5).

Formats constatés le 2026-11-05 (ministère de l'Intérieur) :
  - 2017 : classeur xlsx, paires libellé / valeur sous « France entière » ;
  - 2022 : texte délimité par « ; », encodage Windows-1252, en-tête + ligne FE ;
  - 2024 : xlsx (1er tour) ou CSV UTF-8 (2nd tour), en-tête + ligne FE.
Les nombres peuvent porter des espaces de milliers ; les pourcentages ne sont pas lus
(recalculés depuis les effectifs).

Contrôles : votants = blancs + nuls + exprimés et inscrits = votants + abstentions ; un
écart fait échouer l'extraction plutôt que de publier un chiffre faux. Au 2nd tour, les
inscrits ne couvrent que les circonscriptions où un second tour a eu lieu : le taux de
référence est celui du 1er tour (attribut `electorat_complet`).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import sqlite3
import zipfile
from pathlib import Path

import yaml
from defusedxml import ElementTree as ET

from extract.common import FactDraft, latest_documents
from storage.db import ROOT

SOURCE_ID = "datagouv"
EXTRACTOR = "datagouv_elections/1"
INDICATOR = "contexte.participation_legislatives"
CONFIG_PATH = ROOT / "config" / "datagouv.yaml"
FIELDS = ("inscrits", "votants", "abstentions", "blancs", "nuls", "exprimes")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def normalize(label: str) -> str:
    """« Exprimés » -> « exprimes » ; seules les six colonnes utiles sont reconnues."""
    text = label.strip().strip('"').lower()
    text = text.translate(str.maketrans("éèêàç", "eeeac"))
    return text if text in FIELDS else ""


def to_int(value: str) -> int:
    digits = re.sub(r"[\s  ]", "", str(value))
    if not re.fullmatch(r"\d+(\.0+)?", digits):
        raise ValueError(f"nombre illisible : {value!r}")
    return int(float(digits))


def xlsx_rows(data: bytes) -> list[list[str]]:
    """Lignes de la première feuille d'un classeur xlsx (bibliothèque standard)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in root.iter(f"{_NS}row"):
        values = []
        for cell in row.findall(f"{_NS}c"):
            v = cell.find(f"{_NS}v")
            kind = cell.get("t")
            if kind == "s" and v is not None:
                values.append(shared[int(v.text)])
            elif kind == "inlineStr":
                values.append("".join(t.text or "" for t in cell.iter(f"{_NS}t")))
            else:
                values.append(v.text if v is not None and v.text else "")
        rows.append(values)
    return rows


def text_rows(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def france_entiere(rows: list[list[str]]) -> dict[str, int]:
    """Effectifs France entière, quel que soit le format (en-tête ou libellé / valeur)."""
    for i, row in enumerate(rows):
        columns = [normalize(c) for c in row]
        if "inscrits" in columns and "votants" in columns:  # ligne d'en-tête
            for data in rows[i + 1 :]:
                if any(c.strip().lower() == "france entière" for c in data[:3]):
                    found = {}
                    for col, name in enumerate(columns):
                        if name and name not in found and col < len(data):
                            found[name] = to_int(data[col])
                    return found
    found = {}  # libellé en première colonne, valeur en deuxième (2017)
    for row in rows:
        if len(row) >= 2 and (name := normalize(row[0])) and name not in found:
            found[name] = to_int(row[1])
    return found


def check(values: dict[str, int], label: str) -> None:
    missing = [f for f in FIELDS if f not in values]
    if missing:
        raise ValueError(f"{label} : colonnes absentes {missing}")
    v = values
    if v["votants"] != v["blancs"] + v["nuls"] + v["exprimes"]:
        raise ValueError(f"{label} : votants ≠ blancs + nuls + exprimés")
    if v["inscrits"] != v["votants"] + v["abstentions"]:
        raise ValueError(f"{label} : inscrits ≠ votants + abstentions")


def parse(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    rows = xlsx_rows(data) if path.suffix == ".xlsx" else text_rows(data)
    values = france_entiere(rows)
    check(values, path.name)
    return values


def load_scrutins(path: Path = CONFIG_PATH) -> dict[str, dict]:
    with path.open(encoding="utf-8") as f:
        jeux = yaml.safe_load(f)["jeux"]
    return {j["id"]: {**j["scrutin"], "nom": j["nom"]} for j in jeux if j.get("scrutin")}


def extract(
    conn: sqlite3.Connection, raw_dir: Path, config_path: Path = CONFIG_PATH
) -> list[FactDraft]:
    scrutins = load_scrutins(config_path)
    by_dataset: dict[str, list[sqlite3.Row]] = {}
    for doc in latest_documents(conn, SOURCE_ID):
        dataset_id, _, resource = doc["external_id"].partition("/")
        if dataset_id in scrutins and resource != "fiche.json":
            by_dataset.setdefault(dataset_id, []).append(doc)

    drafts = []
    for dataset_id, docs in sorted(by_dataset.items()):
        scrutin = scrutins[dataset_id]
        results = {doc["id"]: parse(raw_dir / doc["path"]) for doc in docs}
        distinct = {tuple(sorted(r.items())) for r in results.values()}
        if len(distinct) > 1:  # deux ressources du même tour qui se contredisent
            raise ValueError(f"{scrutin['nom']} : ressources incohérentes")
        values = next(iter(results.values()))
        day = scrutin["date"]
        day = day.isoformat() if isinstance(day, dt.date) else str(day)
        tour = int(scrutin["tour"])
        rang = "1er" if tour == 1 else f"{tour}nd"
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="scrutin_participation",
                occurred_on=day,
                title=f"Élections {scrutin['type']} {day[:4]}, {rang} tour",
                official_ref=f"{scrutin['type']}-{day[:4]}-t{tour}",
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(results)),
                attributes={
                    **values,
                    "scrutin": scrutin["type"],
                    "tour": tour,
                    "participation": round(values["votants"] / values["inscrits"], 6),
                    "electorat_complet": tour == 1,
                    "jeu_datagouv": dataset_id,
                    "url": f"https://www.data.gouv.fr/datasets/{dataset_id}/",
                },
            )
        )
    return drafts
