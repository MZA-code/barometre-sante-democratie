"""Prototype front : exporte les données du baromètre dans front/prototype/data.js.

Prototype jetable (voir front/prototype/README.md). Le fichier produit est un script
(`window.BAROMETRE = {...}`) pour que la page s'ouvre directement depuis le disque.

Usage :
    uv run python front/prototype/export_data.py [--db data/barometre.sqlite]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scoring.grid import load_grid  # noqa: E402
from scoring.metrics import load_legislatures  # noqa: E402
from storage.db import DEFAULT_DB_PATH, connect  # noqa: E402

INDICATOR = "D2.contournement_parlement"
ROLLING = "glissante_365j"
OUT = Path(__file__).with_name("data.js")
DIMENSIONS = (
    "D1.regles_electorales_avant_scrutin",
    "D1.scrutins_reportes",
    "D2.contournement_parlement",
    "D2.procedure_acceleree",
    "D3.regimes_exception",
    "D3.lois_censurees",
    "D4.interdictions_manifester_juge",
    "D4.dissolutions_administratives",
    "D5.temps_parole_executif",
    "D5.journalistes_inquietes",
    "D5.classement_rsf",
    "D6.techniques_renseignement",
    "D6.traitements_malgre_reserves",
)
# Début de la comparaison historique quand il diffère du début de la série : avant la
# réforme du 29 octobre 1974, les lois ordinaires sont rarement déférées (petits effectifs).
COMPARE_FROM = {"D3.lois_censurees": "1975-01-01"}
# Fin de couverture des relevés manuels bornés dans le temps : au-delà, une valeur nulle
# traduirait l'absence de relevé, pas l'absence de cas. La carte affiche la valeur à cette date.
COVERAGE_END = {"D5.journalistes_inquietes": "2025-12-31"}
SERIES = (
    "ratio_contournement",
    "nb_49_3",
    "nb_textes_adoptes_49_3",
    "nb_ordonnances_art38",
    "nb_lois_hors_conventions",
)


def metric_rows(conn, window_id, period_ends=None):
    rows = conn.execute(
        "SELECT period_end, name, value FROM metrics"
        " WHERE indicator_id = ? AND window_id = ? ORDER BY period_end",
        (INDICATOR, window_id),
    )
    table: dict[str, dict] = {}
    for period_end, name, value in rows:
        if period_ends is None or period_end in period_ends:
            table.setdefault(period_end, {"date": period_end})[name] = value
    return list(table.values())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args(argv)

    grid = load_grid()
    indicator = grid.indicators[INDICATOR]
    conn = connect(args.db)

    days = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT period_end FROM metrics WHERE indicator_id = ? AND window_id = ?"
            " ORDER BY period_end",
            (INDICATOR, ROLLING),
        )
    ]
    end = days[-1]
    # Une valeur par fin de mois (et la dernière date) : ~800 points au lieu de ~24 000.
    month_ends = {d for d, nxt in zip(days, days[1:], strict=False) if d[:7] != nxt[:7]}
    month_ends.add(end)
    monthly = [
        {k: r.get(k) for k in ("date", *SERIES)} for r in metric_rows(conn, ROLLING, month_ends)
    ]
    current = metric_rows(conn, ROLLING, {end})[0]

    # Toutes les statistiques historiques portent sur la même série mensuelle que la courbe.
    with_ratio = [m for m in monthly if m.get("ratio_contournement") is not None]
    monthly_ratio = [m["ratio_contournement"] for m in with_ratio]
    peak_month = max(with_ratio, key=lambda m: m["ratio_contournement"])
    peak = (peak_month["date"], peak_month["ratio_contournement"])
    below = sum(1 for v in monthly_ratio if v < current["ratio_contournement"])

    legislatures = []
    by_window = {}
    for row in conn.execute(
        "SELECT window_id, period_end, window_days, name, value FROM metrics"
        " WHERE indicator_id = ? AND window_id LIKE 'legislature_%'",
        (INDICATOR,),
    ):
        entry = by_window.setdefault(row[0], {"fin": row[1], "jours": row[2]})
        entry[row[3]] = row[4]
    for leg in load_legislatures():
        key = f"legislature_{leg['numero']}"
        if key in by_window:
            legislatures.append(
                {"numero": leg["numero"], "debut": str(leg["debut"]), **by_window[key]}
            )

    engagements = []
    for fid, day, title, attrs, method in conn.execute(
        "SELECT id, occurred_on, title, attributes, extraction_method FROM facts"
        " WHERE indicator_id = ? AND fact_type = 'engagement_49_3' ORDER BY occurred_on, id",
        (INDICATOR,),
    ):
        a = json.loads(attrs)
        engagements.append(
            {
                "id": fid,
                "date": day,
                "titre": title,
                "texte": a.get("texte_titre"),
                "lecture": a.get("lecture"),
                "censure": a.get("censure_adoptee", False),
                "legislature": a.get("legislature"),
                "url": a.get("url"),
                "source": "seed manuel (page officielle AN)"
                if method == "seed_manuel"
                else "open data Assemblée nationale",
            }
        )

    start = str(_minus_days(end, 364))
    ordonnances = [
        {"date": d, "titre": t, "url": json.loads(a).get("url")}
        for d, t, a in conn.execute(
            "SELECT occurred_on, title, attributes FROM facts WHERE indicator_id = ?"
            " AND fact_type = 'ordonnance_publiee' AND occurred_on BETWEEN ? AND ?"
            " AND json_extract(attributes, '$.fondement') = 'art38' ORDER BY occurred_on DESC",
            (INDICATOR, start, end),
        )
    ]

    ratio = indicator.ratios["ratio_contournement"]
    dimensions = [dimension(conn, grid, ind_id, month_ends) for ind_id in DIMENSIONS]
    periodes = []
    for day, attrs in conn.execute(
        "SELECT occurred_on, attributes FROM facts"
        " WHERE fact_type = 'periode_regime_exception' ORDER BY occurred_on, id"
    ):
        a = json.loads(attrs)
        periodes.append(
            {
                "debut": day,
                "fin": a.get("fin"),
                "regime": a["regime"],
                "territoire": a["territoire"],
                "metropole": a["metropole"],
                "a_verifier": a["a_verifier"],
                "preuve": a["preuve"],
                "note": a.get("note"),
                "url": a.get("url"),
            }
        )
    dissolutions = [
        {
            "date": d,
            "titre": t,
            "fondement": json.loads(a)["fondement"],
            "url": json.loads(a)["url"],
        }
        for d, t, a in conn.execute(
            "SELECT occurred_on, title, attributes FROM facts"
            " WHERE fact_type = 'dissolution_administrative' ORDER BY occurred_on DESC, id"
        )
    ]
    censures = lois_censurees(conn)
    acceleree = procedure_acceleree(conn, start, end)
    payload = {
        "genere_depuis": {
            "grille": grid.version,
            "statut_grille": grid.status,
            "seuils_figes": indicator.thresholds_frozen,
            "echelle": grid.scale_meaning,
            "etat_archive": conn.execute("SELECT max(fetched_at) FROM raw_documents").fetchone()[0],
        },
        "formule": {"numerateur": list(ratio.numerator), "denominateur": list(ratio.denominator)},
        "fin_donnees": end,
        "debut_fenetre": start,
        "actuel": current,
        "historique": {
            "debut": monthly[0]["date"],
            "min": min(monthly_ratio),
            "max": peak[1],
            "date_max": peak[0],
            "mediane_mensuelle": statistics.median(monthly_ratio),
            "part_mois_inferieurs": below / len(monthly_ratio),
            "nb_mois": len(monthly_ratio),
        },
        "mensuel": monthly,
        "legislatures": legislatures,
        "engagements": engagements,
        "ordonnances_fenetre": ordonnances,
        "dimensions": dimensions,
        "periodes_exception": periodes,
        "dissolutions": dissolutions,
        "censures": censures,
        "procedure_acceleree": acceleree,
        "manifestations": interdictions_manifester(conn),
        "cnil": traitements_cnil(conn),
        "journalistes": [
            {"date": d, **json.loads(a)}
            for d, a in conn.execute(
                "SELECT occurred_on, attributes FROM facts WHERE fact_type = 'mesure_journaliste'"
                " ORDER BY occurred_on DESC"
            )
        ],
        "elections": {
            "scrutins": [
                {"date": d, **{k: json.loads(a)[k] for k in ("type", "national", "t2", "url")}}
                for d, a in conn.execute(
                    "SELECT occurred_on, attributes FROM facts WHERE fact_type = 'scrutin'"
                    " ORDER BY occurred_on"
                )
            ],
            "textes": [
                {"date": d, "titre": t, **json.loads(a)}
                for d, t, a in conn.execute(
                    "SELECT occurred_on, title, attributes FROM facts"
                    " WHERE fact_type = 'texte_electoral' ORDER BY occurred_on"
                )
            ],
            "reports": [
                {"date": d, "titre": t, **json.loads(a)}
                for d, t, a in conn.execute(
                    "SELECT occurred_on, title, attributes FROM facts"
                    " WHERE fact_type = 'report_scrutin' ORDER BY occurred_on DESC"
                )
            ],
        },
        "rsf": [
            {
                k: json.loads(a)[k]
                for k in ("edition", "rang", "nb_pays", "score", "periode_score", "url")
            }
            for (a,) in conn.execute(
                "SELECT attributes FROM facts WHERE fact_type = 'classement_rsf'"
                " ORDER BY occurred_on"
            )
        ],
        "cnctr": [
            {
                k: json.loads(a)[k]
                for k in ("annee", "personnes_surveillees", "demandes_techniques", "url", "note")
            }
            for (a,) in conn.execute(
                "SELECT attributes FROM facts WHERE fact_type = 'surveillance_annee'"
                " ORDER BY occurred_on"
            )
        ],
        "temps_parole": [
            {
                "mois": a["mois"],
                "part": a["part_executif"],
                "h_executif": round(a["secondes_executif"] / 3600, 1),
                "h_partis": round(a["secondes_partis"] / 3600, 1),
                "url": a["url"],
            }
            for a in (
                json.loads(attrs)
                for (attrs,) in conn.execute(
                    "SELECT attributes FROM facts WHERE fact_type = 'temps_parole_mois'"
                    " ORDER BY occurred_on"
                )
            )
        ],
        "temps_parole_partis": temps_parole_partis(conn),
        "presse_etrangere": [
            {
                **(a := json.loads(attrs)),
                "par_pays": sorted(a["par_pays"].items(), key=lambda kv: (-kv[1], kv[0]))[:12],
                **{
                    t: {
                        **a[t],
                        "par_pays": sorted(
                            a[t]["par_pays"].items(), key=lambda kv: (-kv[1], kv[0])
                        )[:8],
                    }
                    for t in ("manifestations", "force_police")
                },
            }
            for (attrs,) in conn.execute(
                "SELECT attributes FROM facts WHERE fact_type = 'couverture_etrangere_mois'"
                " ORDER BY occurred_on"
            )
        ],
        "onu": [
            {"date": d, "titre": t, **json.loads(a)}
            for d, t, a in conn.execute(
                "SELECT occurred_on, title, attributes FROM facts"
                " WHERE fact_type = 'declaration_onu' ORDER BY occurred_on DESC, id"
            )
        ],
        "mobilisations": [
            {"date": d, **json.loads(a)}
            for d, a in conn.execute(
                "SELECT occurred_on, attributes FROM facts"
                " WHERE fact_type = 'journee_mobilisation' ORDER BY occurred_on"
            )
        ],
        "participation": [
            {"date": d, "ref": ref, "titre": t, **json.loads(a)}
            for d, ref, t, a in conn.execute(
                "SELECT occurred_on, official_ref, title, attributes FROM facts"
                " WHERE fact_type = 'scrutin_participation' ORDER BY occurred_on"
            )
        ],
        "sources": [
            {"nom": r[0], "url": r[1], "licence": r[2]}
            for r in conn.execute("SELECT name, url, licence FROM sources ORDER BY id")
        ],
    }
    conn.close()
    OUT.write_text(
        "// Généré par export_data.py — ne pas modifier à la main.\n"
        f"window.BAROMETRE = {json.dumps(payload, ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    print(f"{OUT} : {len(monthly)} mois, {len(engagements)} engagements, fin {end}")
    return 0


def temps_parole_partis(conn) -> dict:
    """Contexte D5.1 : temps de chaque parti par mois et par chaîne, libellés de l'Arcom.

    Format compact : par mois, une liste [parti, secondes, {chaîne: secondes}] ; le type de
    service de chaque chaîne est donné une fois (`services`).
    """
    services: dict[str, str] = {}
    mois = []
    for (attrs,) in conn.execute(
        "SELECT attributes FROM facts WHERE fact_type = 'temps_parole_partis_mois'"
        " ORDER BY occurred_on"
    ):
        a = json.loads(attrs)
        partis = []
        for nom, v in sorted(a["partis"].items(), key=lambda kv: (-kv[1]["secondes"], kv[0])):
            partis.append([nom, v["secondes"], v["par_chaine"]])
        mois.append({"mois": a["mois"], "url": a["url"], "partis": partis})
        services.update(a["type_de_service_par_chaine"])
    return {"mois": mois, "services": dict(sorted(services.items()))}


def dimension(conn, grid, ind_id: str, month_ends: set[str]) -> dict:
    """Valeur actuelle de la métrique notée d'un indicateur et sa place dans son historique."""
    ind = grid.indicators[ind_id]
    name = ind.scored_metric
    series = [
        (d, v)
        for d, v in conn.execute(
            "SELECT period_end, value FROM metrics WHERE indicator_id = ? AND window_id = ?"
            " AND name = ? ORDER BY period_end",
            (ind_id, ROLLING, name),
        )
    ]
    since = COMPARE_FROM.get(ind_id, str(ind.history_start))
    until = COVERAGE_END.get(ind_id)
    if until:
        series = [(d, v) for d, v in series if d <= until]
        month_ends = month_ends | {series[-1][0]}
    monthly = [(d, v) for d, v in series if d in month_ends and d >= since]
    values = [v for _, v in monthly]
    current_day, current = series[-1]
    peak = max(monthly, key=lambda dv: dv[1])
    return {
        "id": ind_id,
        "code": ind_id.split(".")[0],
        "label": ind.label,
        "metrique": name,
        "actuel": current,
        "date": current_day,
        "debut_historique": since,
        "fin_couverture": until,
        "mensuel": [{"date": d, "v": v} for d, v in monthly],
        "mediane": statistics.median(values),
        "max": peak[1],
        "date_max": peak[0],
        "part_mois_inferieurs": sum(1 for v in values if v < current) / len(values),
        "part_mois_nuls": sum(1 for v in values if v == 0) / len(values),
    }


def procedure_acceleree(conn, start: str, end: str) -> dict:
    """D2.2 : valeurs par législature et lois de la fenêtre glissante."""
    per_leg: dict[int, dict] = {}
    for window_id, period_end, window_days, name, value in conn.execute(
        "SELECT window_id, period_end, window_days, name, value FROM metrics"
        " WHERE indicator_id = 'D2.procedure_acceleree' AND window_id LIKE 'legislature_%'"
    ):
        num = int(window_id.split("_")[1])
        debut = str(_minus_days(period_end, window_days - 1))
        row = per_leg.setdefault(num, {"legislature": num, "fin": period_end, "debut": debut})
        row[name] = value
    lois = []
    for day, ref, titre, attrs in conn.execute(
        "SELECT occurred_on, official_ref, title, attributes FROM facts"
        " WHERE fact_type = 'loi_procedure' AND occurred_on BETWEEN ? AND ?"
        " ORDER BY occurred_on DESC, id DESC",
        (start, end),
    ):
        a = json.loads(attrs)
        if a["convention_internationale"] or a["constitutionnelle"] or a["finances"]:
            continue
        if a["statut"] == "inconnu":
            continue
        lois.append(
            {
                "date": day,
                "ref": ref,
                "titre": titre,
                "acceleree": a["statut"] == "acceleree",
                "date_engagement": a["date_engagement"],
                "url": a["url_an"] or a["url_senat"] or a["url"],
            }
        )
    comparees = discordances = 0
    for (attrs,) in conn.execute("SELECT attributes FROM facts WHERE fact_type = 'loi_procedure'"):
        a = json.loads(attrs)
        if a["convention_internationale"] or a["constitutionnelle"] or a["finances"]:
            continue
        if a["concordance_an_senat"] is not None:
            comparees += 1
            discordances += not a["concordance_an_senat"]
    return {
        "legislatures": [per_leg[k] for k in sorted(per_leg)],
        "lois_fenetre": lois,
        "comparees_an_senat": comparees,
        "discordances_an_senat": discordances,
    }


def traitements_cnil(conn) -> dict:
    """D6.2 : décrets publiés après un avis de la CNIL sur leur projet, par année."""
    annees: dict[str, dict] = {}
    reserves = []
    for day, ref, titre, attrs in conn.execute(
        "SELECT occurred_on, official_ref, title, attributes FROM facts"
        " WHERE fact_type = 'decret_apres_avis_cnil' ORDER BY occurred_on DESC, id"
    ):
        a = json.loads(attrs)
        row = annees.setdefault(
            day[:4], {"annee": day[:4], "reserves": 0, "autres": 0, "a_verifier": 0}
        )
        if a["confiance"] == "faible":
            row["a_verifier"] += a["malgre_reserves"]
        else:
            row["reserves" if a["malgre_reserves"] else "autres"] += 1
        if a["malgre_reserves"]:
            reserves.append(
                {
                    "date": day,
                    "ref": ref,
                    "titre": titre,
                    "formules": a["formules"],
                    "avis": a["avis"],
                    "confiance": a["confiance"],
                    "url": a["url"],
                }
            )
    avis = conn.execute(
        "SELECT count(*), sum(json_extract(attributes, '$.avis_reserve'))"
        " FROM facts WHERE fact_type = 'avis_cnil_projet_decret'"
    ).fetchone()
    return {
        "annees": [annees[k] for k in sorted(annees)],
        "decrets_reserves": reserves,
        "nb_avis": avis[0] or 0,
        "nb_avis_reserves": avis[1] or 0,
    }


def interdictions_manifester(conn) -> dict:
    """D4 (approximation de D4.2) : décisions par trimestre et liste des décisions."""
    trimestres: dict[str, dict] = {}
    decisions = []
    for day, attrs in conn.execute(
        "SELECT occurred_on, attributes FROM facts"
        " WHERE fact_type = 'decision_interdiction_manifestation' ORDER BY occurred_on DESC, id"
    ):
        a = json.loads(attrs)
        quarter = f"{day[:4]}-T{(int(day[5:7]) - 1) // 3 + 1}"
        row = trimestres.setdefault(
            quarter, {"trimestre": quarter, "favorable_requerant": 0, "rejet": 0, "autre": 0}
        )
        row[a["issue"] if a["issue"] in ("favorable_requerant", "rejet") else "autre"] += 1
        decisions.append(
            {
                "date": day,
                "juridiction": a["juridiction"],
                "conseil_etat": a["conseil_etat"],
                "numero": a["numero"],
                "refere": a["refere"],
                "solution": a["solution"],
                "issue": a["issue"],
            }
        )
    # Dernier mois couvert : le plus récent des mois archivés (AAAAMM dans le nom des archives).
    months = [
        m.group(1)
        for (ext,) in conn.execute(
            "SELECT external_id FROM raw_documents WHERE source_id = 'justice_admin'"
        )
        if (m := re.search(r"_(\d{6})\.zip$", ext))
    ]
    dernier = max(months) if months else None
    return {
        # Tribunaux administratifs publiés depuis juin 2022 : avant le 3e trimestre 2022, la
        # série ne contient que le Conseil d'État et paraîtrait faible à tort.
        "trimestres": [trimestres[k] for k in sorted(trimestres) if k >= "2022-T3"],
        "decisions": decisions,
        "dernier_mois": f"{dernier[:4]}-{dernier[4:]}" if dernier else None,
    }


def lois_censurees(conn) -> dict:
    """D3.2 : ratio de censure par législature et décisions DC sur des lois."""
    per_leg: dict[int, dict] = {}
    for window_id, period_end, window_days, name, value in conn.execute(
        "SELECT window_id, period_end, window_days, name, value FROM metrics"
        " WHERE indicator_id = 'D3.lois_censurees' AND window_id LIKE 'legislature_%'"
    ):
        num = int(window_id.split("_")[1])
        row = per_leg.setdefault(
            num,
            {
                "legislature": num,
                "fin": period_end,
                "debut": str(_minus_days(period_end, window_days - 1)),
            },
        )
        row[name] = value
    decisions = []
    for day, ref, titre, attrs in conn.execute(
        "SELECT occurred_on, official_ref, title, attributes FROM facts"
        " WHERE fact_type = 'decision_dc_loi' ORDER BY occurred_on DESC, id DESC"
    ):
        a = json.loads(attrs)
        decisions.append(
            {
                "date": day,
                "ref": ref,
                "titre": titre,
                "solution": a["solution"],
                "au_fond": a["au_fond"],
                "censure": a["censure"],
                "organique": a["organique"],
                "url": a["url"],
            }
        )
    return {"legislatures": [per_leg[k] for k in sorted(per_leg)], "decisions": decisions}


def _minus_days(iso: str, n: int):
    import datetime as dt

    return dt.date.fromisoformat(iso) - dt.timedelta(days=n)


if __name__ == "__main__":
    sys.exit(main())
