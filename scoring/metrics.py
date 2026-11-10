"""Faits -> métriques brutes, par fenêtre glissante quotidienne et par législature.

Conventions (voir DECISIONS.md) :
  - fenêtre glissante de N jours se terminant le jour J : faits datés de J-(N-1) à J inclus,
    calculée pour chaque jour de [history_start + N - 1, fin des données] ;
  - fenêtre « législature » : de l'ouverture d'une législature à la veille de l'ouverture
    de la suivante (config/legislatures.yaml), arrêtée à la fin des données si en cours ;
  - fin des données : veille de la plus ancienne des dernières collectes des sources
    automatiques (AN, JORF, LEGI), pour ne pas mesurer une période non encore couverte ;
  - `computed_at` : horodatage de l'état de l'archive (dernière collecte), et non l'heure
    du calcul, pour que deux reconstructions produisent exactement la même base ;
  - un ratio (formule définie dans la grille : somme des métriques du numérateur sur
    somme de celles du dénominateur) n'est pas produit si son dénominateur est nul.

Usage :
    python -m scoring.metrics [--db CHEMIN] [--grid config/grid.vN.yaml] [--export-dir DOSSIER]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import yaml

from scoring.grid import DEFAULT_GRID_PATH, Grid, Indicator, Ratio, load_grid
from storage.db import DEFAULT_DB_PATH, ROOT, connect, init_db

LEGISLATURES_PATH = ROOT / "config" / "legislatures.yaml"
DEFAULT_EXPORT_DIR = ROOT / "data" / "exports"
COVERAGE_SOURCES = ("an_opendata", "dila_constit", "dila_jorf", "dila_legi")
COUNT_METRICS = (
    "nb_49_3",
    "nb_textes_49_3",
    "nb_textes_adoptes_49_3",
    "nb_ordonnances",
    "nb_ordonnances_art38",
    "nb_lois",
    "nb_lois_hors_conventions",
    "nb_lois_deferees",
    "nb_lois_censurees",
    "nb_lois_ordinaires_deferees",
    "nb_lois_ordinaires_censurees",
    "nb_qpc",
    "nb_qpc_censures",
    "nb_lois_statut_connu",
    "nb_lois_procedure_acceleree",
    "nb_lois_statut_inconnu",
    "nb_decisions_manifestation",
    "nb_decisions_manifestation_tranchees",
    "nb_decisions_manifestation_favorables",
    "nb_decrets_avis_cnil",
    "nb_decrets_malgre_reserves",
    "nb_decrets_malgre_reserves_a_verifier",
    "nb_avis_cnil_projets_decret",
    "nb_avis_cnil_reserves",
    "secondes_executif",
    "secondes_partis",
    "nb_mois_temps_parole",
    "somme_rangs_rsf",
    "nb_editions_rsf",
    "somme_niveaux_categorie_rsf",
    "nb_editions_categorie_rsf",
    "somme_personnes_surveillees",
    "nb_annees_cnctr",
    "nb_textes_electoraux",
    "nb_textes_electoraux_avant_scrutin",
    "nb_reports_scrutin",
    "nb_scrutins_reportes",
    "nb_journalistes_mesures",
    "nb_journalistes_convoques",
)


@dataclass(frozen=True)
class Event:
    day: dt.date
    fact_id: int
    fact_type: str
    texte_uid: str | None = None
    adopted: bool = False  # engagement 49.3 non suivi d'une censure adoptée
    art38: bool = False  # ordonnance fondée sur l'article 38
    convention: bool = False  # loi autorisant un engagement international
    until: dt.date | None = None  # dernier jour d'une période (régime d'exception)
    metropole: bool = False  # période couvrant le territoire métropolitain
    au_fond: bool = False  # décision du Conseil constitutionnel rendue au fond
    censure: bool = False  # décision de non-conformité (partielle ou totale)
    organique: bool = False  # décision portant sur une loi organique
    statut: str | None = None  # procédure suivie par une loi : acceleree, ordinaire, inconnu
    constitutionnelle: bool = False  # loi constitutionnelle
    finances: bool = False  # loi de finances ou de financement de la sécurité sociale
    issue: str | None = None  # issue d'une décision de justice pour le requérant
    reserve: bool = False  # avis réservé de la CNIL (sur l'avis ou sur le décret qui suit)
    confiance: str | None = None  # confiance du rapprochement avis -> décret
    secondes_executif: int = 0  # temps de parole mensuel (Arcom)
    secondes_partis: int = 0
    rang: int = 0  # rang de la France dans un classement externe (RSF)
    niveau_categorie: int | None = None  # catégorie RSF (0 bonne ... 4 très grave), depuis 2022
    scrutins: tuple[str, ...] = ()  # scrutins reportés par un texte (D1.2, variante)
    personnes: int = 0  # personnes surveillées dans l'année (CNCTR)
    avant_scrutin: bool = False  # texte électoral publié moins d'un an avant le scrutin visé
    nb_journalistes: int = 0  # journalistes visés par une mesure (D5.2)
    comptee: bool = False  # mesure entrant dans la définition de D5.2


# Métriques additives, calculées jour par jour puis sommées sur la fenêtre :
#   - "count" : nombre de faits datés du jour ;
#   - "coverage" : 1 si le jour est couvert par au moins une période (les chevauchements
#     de périodes ne sont comptés qu'une fois).
DAILY_METRICS = {
    "nb_dissolutions": ("count", lambda e: e.fact_type == "dissolution_administrative"),
    "jours_exception": ("coverage", lambda e: e.fact_type == "periode_regime_exception"),
    "jours_exception_metropole": (
        "coverage",
        lambda e: e.fact_type == "periode_regime_exception" and e.metropole,
    ),
    # D7 : faits de presse validés sur GitHub, constats d'autorités, et leur somme.
    "nb_faits_presse_valides": ("count", lambda e: e.fact_type == "fait_presse_valide"),
    "nb_constats_institutionnels": ("count", lambda e: e.fact_type == "constat_institutionnel"),
    "nb_atteintes_pratique": (
        "count",
        lambda e: e.fact_type in ("fait_presse_valide", "constat_institutionnel"),
    ),
}


class DailySeries:
    """Somme d'une métrique additive sur n'importe quel intervalle de jours (sommes cumulées)."""

    def __init__(self, events: list[Event], name: str, origin: dt.date, end: dt.date) -> None:
        kind, keep = DAILY_METRICS[name]
        self.origin, size = origin, (end - origin).days + 1
        daily = [0] * size
        for event in filter(keep, events):
            # un fait compte le jour où il survient ; une période couvre jusqu'à sa fin
            # (en cours : jusqu'à la fin des données)
            last_day = event.day if kind == "count" else event.until or end
            lo = max(0, (event.day - origin).days)
            hi = min(size - 1, (last_day - origin).days)
            for i in range(lo, hi + 1):
                daily[i] = daily[i] + 1 if kind == "count" else 1
        self.cumul = [0]
        for value in daily:
            self.cumul.append(self.cumul[-1] + value)

    def total(self, first: dt.date, last: dt.date) -> float:
        a = max(0, (first - self.origin).days)
        b = min(len(self.cumul) - 1, (last - self.origin).days + 1)
        return float(self.cumul[b] - self.cumul[a]) if b > a else 0.0


@dataclass(frozen=True)
class Window:
    id: str  # 'glissante_365j' ou 'legislature_16'
    days: int
    start: dt.date
    end: dt.date


class WindowState:
    """Compteurs d'une fenêtre, mis à jour par ajout et retrait d'événements."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.textes: Counter[str] = Counter()
        self.textes_adoptes: Counter[str] = Counter()
        self.scrutins: Counter[str] = Counter()  # D1.2 : un scrutin reporté compte une fois

    def _apply(self, event: Event, delta: int) -> None:
        if event.fact_type == "engagement_49_3":
            self.counts["nb_49_3"] += delta
            self.textes[event.texte_uid] += delta
            if event.adopted:
                self.textes_adoptes[event.texte_uid] += delta
        elif event.fact_type == "ordonnance_publiee":
            self.counts["nb_ordonnances"] += delta
            self.counts["nb_ordonnances_art38"] += delta * event.art38
        elif event.fact_type == "loi_promulguee":
            self.counts["nb_lois"] += delta
            self.counts["nb_lois_hors_conventions"] += delta * (not event.convention)
        elif event.fact_type == "decision_dc_loi" and event.au_fond:
            self.counts["nb_lois_deferees"] += delta
            self.counts["nb_lois_censurees"] += delta * event.censure
            if not event.organique:
                self.counts["nb_lois_ordinaires_deferees"] += delta
                self.counts["nb_lois_ordinaires_censurees"] += delta * event.censure
        elif event.fact_type == "loi_procedure":
            # D2.2 : hors engagements internationaux (comme D2), lois constitutionnelles (la
            # procédure accélérée ne s'y applique pas) et lois de finances et de financement
            # (calendrier fixé par la Constitution).
            if event.convention or event.constitutionnelle or event.finances:
                return
            if event.statut == "inconnu":
                self.counts["nb_lois_statut_inconnu"] += delta
            else:
                self.counts["nb_lois_statut_connu"] += delta
                self.counts["nb_lois_procedure_acceleree"] += delta * (event.statut == "acceleree")
        elif event.fact_type == "decision_interdiction_manifestation":
            # Tranchée = le juge a donné raison au requérant ou a rejeté sa demande ;
            # désistements, non-lieux et autres issues ne sont comptés que dans le total.
            self.counts["nb_decisions_manifestation"] += delta
            if event.issue in ("favorable_requerant", "rejet"):
                self.counts["nb_decisions_manifestation_tranchees"] += delta
                self.counts["nb_decisions_manifestation_favorables"] += delta * (
                    event.issue == "favorable_requerant"
                )
        elif event.fact_type == "decret_apres_avis_cnil":
            # Seuls les rapprochements de confiance forte sont comptés ; les autres à part.
            if event.confiance == "faible":
                self.counts["nb_decrets_malgre_reserves_a_verifier"] += delta * event.reserve
            else:
                self.counts["nb_decrets_avis_cnil"] += delta
                self.counts["nb_decrets_malgre_reserves"] += delta * event.reserve
        elif event.fact_type == "avis_cnil_projet_decret":
            self.counts["nb_avis_cnil_projets_decret"] += delta
            self.counts["nb_avis_cnil_reserves"] += delta * event.reserve
        elif event.fact_type == "temps_parole_mois":
            self.counts["secondes_executif"] += delta * event.secondes_executif
            self.counts["secondes_partis"] += delta * event.secondes_partis
            self.counts["nb_mois_temps_parole"] += delta
        elif event.fact_type == "classement_rsf":
            self.counts["somme_rangs_rsf"] += delta * event.rang
            self.counts["nb_editions_rsf"] += delta
            if event.niveau_categorie is not None:
                self.counts["somme_niveaux_categorie_rsf"] += delta * event.niveau_categorie
                self.counts["nb_editions_categorie_rsf"] += delta
        elif event.fact_type == "surveillance_annee":
            self.counts["somme_personnes_surveillees"] += delta * event.personnes
            self.counts["nb_annees_cnctr"] += delta
        elif event.fact_type == "texte_electoral":
            self.counts["nb_textes_electoraux"] += delta
            self.counts["nb_textes_electoraux_avant_scrutin"] += delta * event.avant_scrutin
        elif event.fact_type == "report_scrutin":
            self.counts["nb_reports_scrutin"] += delta
            for scrutin in event.scrutins:
                self.scrutins[scrutin] += delta
        elif event.fact_type == "mesure_journaliste":
            key = "nb_journalistes_mesures" if event.comptee else "nb_journalistes_convoques"
            self.counts[key] += delta * event.nb_journalistes
        elif event.fact_type == "decision_qpc" and event.au_fond:
            self.counts["nb_qpc"] += delta
            self.counts["nb_qpc_censures"] += delta * event.censure

    def add(self, event: Event) -> None:
        self._apply(event, 1)

    def remove(self, event: Event) -> None:
        self._apply(event, -1)

    def values(self, ratios: dict[str, Ratio] | None = None) -> dict[str, float]:
        values = {name: float(self.counts[name]) for name in COUNT_METRICS}
        values["nb_textes_49_3"] = float(sum(1 for n in self.textes.values() if n > 0))
        values["nb_textes_adoptes_49_3"] = float(
            sum(1 for n in self.textes_adoptes.values() if n > 0)
        )
        values["nb_scrutins_reportes"] = float(sum(1 for n in self.scrutins.values() if n > 0))
        for name, ratio in (ratios or {}).items():
            denominator = sum(values[m] for m in ratio.denominator)
            if denominator:
                values[name] = sum(values[m] for m in ratio.numerator) / denominator
        return values


def load_events(conn: sqlite3.Connection, indicator: Indicator) -> list[Event]:
    placeholders = ",".join("?" * len(indicator.fact_types))
    rows = conn.execute(
        f"SELECT id, fact_type, occurred_on, attributes FROM facts"
        f" WHERE indicator_id = ? AND fact_type IN ({placeholders})"
        f" ORDER BY occurred_on, id",
        (indicator.id, *indicator.fact_types),
    )
    events = []
    for row in rows:
        attrs = json.loads(row["attributes"])
        events.append(
            Event(
                day=dt.date.fromisoformat(row["occurred_on"]),
                fact_id=row["id"],
                fact_type=row["fact_type"],
                texte_uid=attrs.get("texte_uid"),
                adopted=not attrs.get("censure_adoptee", False),
                art38=attrs.get("fondement") == "art38",
                convention=attrs.get("convention_internationale", False),
                until=dt.date.fromisoformat(attrs["fin"]) if attrs.get("fin") else None,
                metropole=attrs.get("metropole", False),
                au_fond=attrs.get("au_fond", False),
                censure=attrs.get("censure", False),
                organique=attrs.get("organique", False),
                statut=attrs.get("statut"),
                constitutionnelle=attrs.get("constitutionnelle", False),
                finances=attrs.get("finances", False),
                issue=attrs.get("issue"),
                reserve=attrs.get("malgre_reserves", attrs.get("avis_reserve", False)),
                confiance=attrs.get("confiance"),
                secondes_executif=attrs.get("secondes_executif", 0),
                secondes_partis=attrs.get("secondes_partis", 0),
                rang=attrs.get("rang", 0) if row["fact_type"] == "classement_rsf" else 0,
                niveau_categorie=attrs.get("niveau_categorie"),
                scrutins=tuple(attrs.get("scrutins_reportes", ())),
                personnes=attrs.get("personnes_surveillees", 0),
                avant_scrutin=attrs.get("moins_d_un_an", False),
                nb_journalistes=attrs.get("nb_journalistes", 0),
                comptee=attrs.get("comptee", False),
            )
        )
    return events


def data_end(conn: sqlite3.Connection) -> dt.date | None:
    """Veille de la plus ancienne des dernières mises à jour des sources automatiques.

    Une source est à jour à la date de son dernier document collecté ou de sa dernière
    vérification complète réussie (table source_checks), la plus récente des deux : une
    source qui n'a rien publié de nouveau n'est pas en retard pour autant.
    """
    placeholders = ",".join("?" * len(COVERAGE_SOURCES))
    rows = conn.execute(
        f"SELECT source_id, max(t) AS last FROM ("
        f"  SELECT source_id, fetched_at AS t FROM raw_documents"
        f"  UNION ALL SELECT source_id, checked_at FROM source_checks"
        f") WHERE source_id IN ({placeholders})"
        f" AND source_id IN (SELECT source_id FROM raw_documents) GROUP BY source_id",
        COVERAGE_SOURCES,
    ).fetchall()
    if len(rows) < len(COVERAGE_SOURCES):
        return None
    return min(dt.date.fromisoformat(r["last"][:10]) for r in rows) - dt.timedelta(days=1)


def snapshot_stamp(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT coalesce(max(fetched_at), '') FROM raw_documents").fetchone()[0]


def load_legislatures(path: Path = LEGISLATURES_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["legislatures"]


def legislature_windows(legislatures: list[dict], start: dt.date, end: dt.date) -> list[Window]:
    windows = []
    for current, following in zip(legislatures, [*legislatures[1:], None], strict=True):
        w_start = max(current["debut"], start)
        w_end = following["debut"] - dt.timedelta(days=1) if following else end
        w_end = min(w_end, end)
        if w_start <= w_end:
            days = (w_end - w_start).days + 1
            windows.append(Window(f"legislature_{current['numero']}", days, w_start, w_end))
    return windows


# Séries annuelles (une valeur par an, datée par convention) : la fenêtre glissante couvre
# une année civile, du lendemain de la même date un an plus tôt au jour courant, soit 366 jours
# quand elle contient un 29 février. Avec 365 jours, la fenêtre se terminant le 31 décembre d'une
# année bissextile ne contient aucune édition RSF (datée du 1er janvier) et celle se terminant le
# 30 décembre aucune année CNCTR (datée du 31 décembre de l'année précédente).
ANNUAL_FACT_TYPES = frozenset({"classement_rsf", "surveillance_annee"})


def one_year_before(day: dt.date) -> dt.date:
    """Même date un an plus tôt (29 février -> 28 février)."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def window_start(day: dt.date, days: int, annual: bool) -> dt.date:
    """Premier jour de la fenêtre glissante se terminant à `day`."""
    if annual and days == 365:
        return one_year_before(day) + dt.timedelta(days=1)
    return day - dt.timedelta(days=days - 1)


def rolling(
    events: list[Event], days: int, first: dt.date, last: dt.date, ratios: dict[str, Ratio]
):
    """Valeurs de la fenêtre glissante pour chaque jour de [first, last]."""
    annual = bool(events) and all(e.fact_type in ANNUAL_FACT_TYPES for e in events)
    by_day: dict[dt.date, list[Event]] = defaultdict(list)
    for event in events:
        by_day[event.day].append(event)
    state, inside = WindowState(), deque()
    day = window_start(first, days, annual)
    for event in events:  # amorçage : faits antérieurs au premier jour, dans la fenêtre
        if day <= event.day < first:
            state.add(event)
            inside.append(event)
    day = first
    while day <= last:
        for event in by_day.get(day, ()):
            state.add(event)
            inside.append(event)
        horizon = window_start(day, days, annual)
        while inside and inside[0].day < horizon:
            state.remove(inside.popleft())
        yield day, state.values(ratios)
        day += dt.timedelta(days=1)


def window_values(
    events: list[Event], window: Window, ratios: dict[str, Ratio]
) -> dict[str, float]:
    state = WindowState()
    for event in events:
        if window.start <= event.day <= window.end:
            state.add(event)
    return state.values(ratios)


def compute(conn: sqlite3.Connection, grid: Grid, legislatures: list[dict]) -> list[tuple]:
    """Lignes de la table metrics pour tous les indicateurs de la grille."""
    end = data_end(conn)
    if end is None:
        return []
    stamp = snapshot_stamp(conn)
    rows = []
    for indicator in grid.indicators.values():
        known = set(COUNT_METRICS) | set(DAILY_METRICS) | set(indicator.ratios)
        unknown = set(indicator.metrics) - known
        if unknown:
            raise ValueError(f"{indicator.id} : métriques inconnues {sorted(unknown)}")
        events = load_events(conn, indicator)
        origin = min([indicator.history_start - dt.timedelta(days=366), *(e.day for e in events)])
        daily = {
            name: DailySeries(events, name, origin, end)
            for name in indicator.metrics
            if name in DAILY_METRICS
        }
        windows: list[tuple[str, int, dt.date, dict[str, float]]] = []
        for spec in indicator.windows:
            if spec.type == "rolling":
                first = indicator.history_start + dt.timedelta(days=spec.days - 1)
                window_id = f"glissante_{spec.days}j"
                for day, values in rolling(events, spec.days, first, end, indicator.ratios):
                    start = day - dt.timedelta(days=spec.days - 1)
                    values.update({n: s.total(start, day) for n, s in daily.items()})
                    windows.append((window_id, spec.days, day, values))
            else:
                for window in legislature_windows(legislatures, indicator.history_start, end):
                    values = window_values(events, window, indicator.ratios)
                    values.update({n: s.total(window.start, window.end) for n, s in daily.items()})
                    windows.append((window.id, window.days, window.end, values))
        rows += [
            (
                indicator.id,
                day.isoformat(),
                window_id,
                days,
                name,
                values[name],
                grid.version,
                stamp,
            )
            for window_id, days, day, values in windows
            for name in indicator.metrics
            if name in values
        ]
    return rows


def write_metrics(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    with conn:
        conn.execute("DELETE FROM score_facts")
        conn.execute("DELETE FROM scores")
        conn.execute("DELETE FROM metrics")
        conn.executemany(
            "INSERT INTO metrics (indicator_id, period_end, window_id, window_days, name, value,"
            " grid_version, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def format_value(name: str, value: float) -> str:
    integer = name in COUNT_METRICS or name in DAILY_METRICS
    return str(int(value)) if integer else f"{value:.6f}"


def export_csv(conn: sqlite3.Connection, grid: Grid, export_dir: Path) -> list[Path]:
    """Un CSV large par indicateur et type de fenêtre (une ligne par fenêtre)."""
    export_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for indicator in grid.indicators.values():
        for kind, pattern in (("glissante", "glissante_%"), ("legislatures", "legislature_%")):
            rows = conn.execute(
                "SELECT window_id, window_days, period_end, name, value FROM metrics"
                " WHERE indicator_id = ? AND grid_version = ? AND window_id LIKE ?"
                " ORDER BY period_end, window_id, name",
                (indicator.id, grid.version, pattern),
            ).fetchall()
            table: dict[tuple, dict[str, str]] = {}
            for r in rows:
                key = (r["window_id"], r["window_days"], r["period_end"])
                table.setdefault(key, {})[r["name"]] = format_value(r["name"], r["value"])
            path = export_dir / f"{indicator.id}_{grid.version}_{kind}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(["fenetre", "jours", "fin_periode", *indicator.metrics])
                for (window_id, days, period_end), values in table.items():
                    metrics = [values.get(name, "") for name in indicator.metrics]
                    writer.writerow([window_id, days, period_end, *metrics])
            paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scoring.metrics")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID_PATH)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    args = parser.parse_args(argv)

    grid = load_grid(args.grid)
    conn = connect(args.db)
    try:
        init_db(conn)
        rows = compute(conn, grid, load_legislatures())
        write_metrics(conn, rows)
        paths = export_csv(conn, grid, args.export_dir)
    finally:
        conn.close()
    print(f"[metrics] grille {grid.version} : {len(rows)} valeurs")
    for path in paths:
        print(f"[metrics] export : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
