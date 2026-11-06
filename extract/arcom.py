"""Relevés Arcom des temps de parole hors période électorale -> indicateur D5.1.

Un fait `temps_parole_mois` par mois relevé, daté du dernier jour du mois. Les temps sont lus
dans les lignes d'agrégat calculées par l'Arcom elle-même, colonne par colonne (une colonne =
une chaîne ou radio et un type d'émission : journaux, magazines, autres programmes) :
  - « Total Pouvoir exécutif » : Gouvernement + propos du Président de la République qui
    relèvent du débat politique national (règle de l'Arcom : ses propos relevant de ses
    fonctions de chef de l'État ne sont pas décomptés) ;
  - « Total Partis politiques ».
Les lignes par parti ne sont jamais lues comme critère (règle 5) : seuls les deux totaux
servent. Part de l'exécutif = exécutif / (exécutif + partis), sommés sur toutes les colonnes.

Temps de parole par parti (contexte, hors grille, `extract_partis`) : un fait
`temps_parole_partis_mois` par mois, qui reprend toutes les lignes situées entre « Part Pouvoir
exécutif » et « Total Partis politiques », sous le libellé publié par l'Arcom. Aucun libellé
de parti n'est écrit dans le code ni ne sert de filtre (règle 5) : les lignes sont repérées par
leur position. Contrôle : pour chaque colonne, la somme des lignes doit égaler le total
« Partis politiques » de l'Arcom, à la seconde près ; sinon l'extraction échoue.

Contrôle : pour chaque colonne, les parts publiées par l'Arcom (« Part Pouvoir exécutif »,
« Part Partis politiques ») doivent correspondre aux totaux à 0,1 point près ; sinon
l'extraction échoue.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
import sqlite3
from pathlib import Path

from extract.common import FactDraft, latest_documents

SOURCE_ID = "arcom_temps_parole"
EXTRACTOR = "arcom_temps_parole/1"
INDICATOR = "D5.temps_parole_executif"
INDICATOR_PARTIS = "contexte.temps_parole_partis"
EXTRACTOR_PARTIS = "arcom_temps_parole_partis/1"
NOM = re.compile(r"Export_web_1T2T_01-(\d{2})-(\d{4})_")
EXECUTIF, PARTIS = "Total Pouvoir exécutif", "Total Partis politiques"
PART_EXECUTIF, PART_PARTIS = "Part Pouvoir exécutif", "Part Partis politiques"


def seconds(value: str) -> int:
    """« 01:23:12 » -> 4992 ; « - » ou vide -> 0 (les heures peuvent dépasser 24)."""
    value = value.strip()
    if value in ("", "-"):
        return 0
    h, m, s = (int(x) for x in value.split(":"))
    return h * 3600 + m * 60 + s


def percent(value: str) -> float | None:
    value = value.strip().replace(",", ".").rstrip("%")
    return None if value in ("", "-") else float(value)


def parse(text: str) -> dict:
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    by_label = {r[0].strip(): r[1:] for r in rows if r and r[0].strip()}
    labels = ("Type de service", EXECUTIF, PARTIS, PART_EXECUTIF, PART_PARTIS)
    for label in labels:
        if label not in by_label:
            raise ValueError(f"ligne « {label} » absente")
    services, exe, par, part_exe, part_par = (by_label[label] for label in labels)
    if len({len(by_label[label]) for label in labels}) != 1:
        raise ValueError(
            "nombre de colonnes différent selon les lignes : "
            + ", ".join(f"{label} {len(by_label[label])}" for label in labels)
        )
    totaux: dict[str, list[int]] = {}
    for i, service in enumerate(services):
        e, p = seconds(exe[i]), seconds(par[i])
        for nom, value, published in (
            ("de l'exécutif", e, percent(part_exe[i])),
            ("des partis", p, percent(part_par[i])),
        ):
            if published is not None and (e + p) and abs(100 * value / (e + p) - published) > 0.1:
                raise ValueError(f"colonne {i + 1} : part {nom} incohérente")
        acc = totaux.setdefault(service.strip(), [0, 0])
        acc[0] += e
        acc[1] += p
    exe_total = sum(v[0] for v in totaux.values())
    par_total = sum(v[1] for v in totaux.values())
    return {
        "secondes_executif": exe_total,
        "secondes_partis": par_total,
        "part_executif": round(exe_total / (exe_total + par_total), 6)
        if exe_total + par_total
        else None,
        "par_type_de_service": {
            k: {"secondes_executif": v[0], "secondes_partis": v[1]}
            for k, v in sorted(totaux.items())
        },
    }


def parse_partis(text: str) -> dict:
    """Temps de chaque parti, par chaîne et par type de service, tel que publié."""
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=";") if r and r[0].strip()]
    labels = [r[0].strip() for r in rows]
    for label in ("Type de service", PART_EXECUTIF, PARTIS):
        if label not in labels:
            raise ValueError(f"ligne « {label} » absente")
    chaines = next(r for r in csv.reader(io.StringIO(text), delimiter=";") if r)[1:]
    services = rows[labels.index("Type de service")][1:]
    total = rows[labels.index(PARTIS)][1:]
    lignes = rows[labels.index(PART_EXECUTIF) + 1 : labels.index(PARTIS)]
    width = len(total)
    if len(chaines) != width or len(services) != width:
        raise ValueError("nombre de colonnes différent entre l'en-tête et le total des partis")
    service_de: dict[str, str] = {}
    for chaine, service in zip(chaines, services, strict=True):
        if service_de.setdefault(chaine.strip(), service.strip()) != service.strip():
            raise ValueError(f"chaîne « {chaine.strip()} » rattachée à deux types de service")
    partis: dict[str, dict] = {}
    sommes = [0] * width
    for row in lignes:
        nom = row[0].strip()
        if nom in partis:
            raise ValueError(f"parti « {nom} » présent deux fois")
        valeurs = [seconds(v) for v in row[1 : width + 1]] + [0] * max(0, width + 1 - len(row))
        entry = {"secondes": 0, "par_type_de_service": {}, "par_chaine": {}}
        for i, v in enumerate(valeurs[:width]):
            sommes[i] += v
            if not v:
                continue
            entry["secondes"] += v
            for key, name in (("par_type_de_service", services[i]), ("par_chaine", chaines[i])):
                entry[key][name.strip()] = entry[key].get(name.strip(), 0) + v
        if entry["secondes"]:
            partis[nom] = entry
    for i, (s, t) in enumerate(zip(sommes, total, strict=True)):
        if s != seconds(t):
            raise ValueError(
                f"colonne {i + 1} : somme des partis {s} s, total Arcom {seconds(t)} s"
            )
    return {
        "secondes_partis": sum(sommes),
        "nb_partis": len(partis),
        "type_de_service_par_chaine": dict(sorted(service_de.items())),
        "partis": dict(sorted(partis.items(), key=lambda kv: (-kv[1]["secondes"], kv[0]))),
    }


def _monthly(conn: sqlite3.Connection):
    for doc in latest_documents(conn, SOURCE_ID):
        m = NOM.search(doc["external_id"])
        if m:
            month, year = int(m.group(1)), int(m.group(2))
            last = calendar.monthrange(year, month)[1]
            yield doc, year, month, f"{year}-{month:02d}-{last:02d}"


def extract_partis(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    drafts = []
    for doc, year, month, day in _monthly(conn):
        values = parse_partis((raw_dir / doc["path"]).read_text(encoding="utf-8-sig"))
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR_PARTIS,
                fact_type="temps_parole_partis_mois",
                occurred_on=day,
                title=f"Temps de parole par parti, {month:02d}/{year} (Arcom)",
                official_ref=doc["external_id"],
                extraction_method=EXTRACTOR_PARTIS,
                raw_document_ids=(doc["id"],),
                attributes={**values, "mois": f"{year}-{month:02d}", "url": doc["url"]},
            )
        )
    return drafts


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    drafts = []
    for doc, year, month, day in _monthly(conn):
        values = parse((raw_dir / doc["path"]).read_text(encoding="utf-8-sig"))
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="temps_parole_mois",
                occurred_on=day,
                title=f"Temps de parole politique, {month:02d}/{year} (Arcom)",
                official_ref=doc["external_id"],
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={**values, "mois": f"{year}-{month:02d}", "url": doc["url"]},
            )
        )
    return drafts
