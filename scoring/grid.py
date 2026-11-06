"""Chargement et validation de la grille d'indicateurs (config/grid.vX.yaml).

C'est le seul point d'entrée vers les seuils et pondérations : aucun autre module
ne doit embarquer de valeur de seuil.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRID_PATH = ROOT / "config" / "grid.v0.yaml"

GRID_FILENAME = re.compile(r"^grid\.(v\d+)\.yaml$")
NB_THRESHOLDS = 4
DIRECTIONS = ("increasing", "decreasing")
WINDOW_TYPES = ("rolling", "legislature")


class GridError(ValueError):
    """La grille est mal formée."""


@dataclass(frozen=True)
class Window:
    type: str
    days: int | None = None


@dataclass(frozen=True)
class Ratio:
    """Ratio défini par la grille : somme(numérateur) / somme(dénominateur)."""

    numerator: tuple[str, ...]
    denominator: tuple[str, ...]


@dataclass(frozen=True)
class Indicator:
    id: str
    label: str
    fact_types: tuple[str, ...]
    windows: tuple[Window, ...]
    metrics: tuple[str, ...]
    scored_metric: str
    direction: str
    thresholds: tuple[float | None, ...]
    weight: float | None
    history_start: dt.date
    ratios: dict[str, Ratio]

    @property
    def thresholds_frozen(self) -> bool:
        return all(t is not None for t in self.thresholds)


@dataclass(frozen=True)
class Grid:
    version: str
    status: str
    indicators: dict[str, Indicator]
    scale_meaning: str | None = None


def load_grid(path: Path | str = DEFAULT_GRID_PATH) -> Grid:
    path = Path(path)
    match = GRID_FILENAME.match(path.name)
    if not match:
        raise GridError(f"{path.name} : le fichier doit s'appeler grid.vN.yaml")

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    version = data.get("version")
    if version != match.group(1):
        raise GridError(
            f"{path.name} : version {version!r} différente du nom de fichier ({match.group(1)})"
        )

    indicators = {
        ind_id: _parse_indicator(ind_id, raw) for ind_id, raw in data["indicators"].items()
    }
    scale = data.get("scale") or {}
    return Grid(
        version=version,
        status=data["status"],
        indicators=indicators,
        scale_meaning=scale.get("meaning"),
    )


def _parse_indicator(ind_id: str, raw: dict) -> Indicator:
    metrics = tuple(raw["metrics"])
    if raw["scored_metric"] not in metrics:
        raise GridError(f"{ind_id} : scored_metric {raw['scored_metric']!r} absente de metrics")

    direction = raw["direction"]
    if direction not in DIRECTIONS:
        raise GridError(f"{ind_id} : direction doit valoir {' ou '.join(DIRECTIONS)}")

    thresholds = tuple(raw["thresholds"])
    if len(thresholds) != NB_THRESHOLDS:
        raise GridError(f"{ind_id} : {NB_THRESHOLDS} seuils attendus, {len(thresholds)} trouvés")
    set_thresholds = [t for t in thresholds if t is not None]
    if set_thresholds and len(set_thresholds) != NB_THRESHOLDS:
        raise GridError(f"{ind_id} : seuils partiellement renseignés, tout ou rien")
    if set_thresholds:
        ordered = sorted(set_thresholds, reverse=direction == "decreasing")
        if list(thresholds) != ordered or len(set(thresholds)) != NB_THRESHOLDS:
            raise GridError(f"{ind_id} : seuils non strictement monotones pour {direction}")

    windows = tuple(_parse_window(ind_id, w) for w in raw["windows"])
    ratios = {
        name: _parse_ratio(ind_id, name, r, metrics) for name, r in raw.get("ratios", {}).items()
    }
    if not isinstance(raw.get("history_start"), dt.date):
        raise GridError(f"{ind_id} : history_start doit être une date AAAA-MM-JJ")

    return Indicator(
        id=ind_id,
        label=raw["label"],
        fact_types=tuple(raw["fact_types"]),
        windows=windows,
        metrics=metrics,
        scored_metric=raw["scored_metric"],
        direction=direction,
        thresholds=thresholds,
        weight=raw.get("weight"),
        history_start=raw["history_start"],
        ratios=ratios,
    )


def _parse_ratio(ind_id: str, name: str, raw: dict, metrics: tuple[str, ...]) -> Ratio:
    if name not in metrics:
        raise GridError(f"{ind_id} : ratio {name!r} absent de metrics")
    ratio = Ratio(tuple(raw["numerateur"]), tuple(raw["denominateur"]))
    for component in ratio.numerator + ratio.denominator:
        if component not in metrics or component == name:
            raise GridError(f"{ind_id} : {name} utilise {component!r}, absente de metrics")
    if not ratio.denominator:
        raise GridError(f"{ind_id} : {name} sans dénominateur")
    return ratio


def _parse_window(ind_id: str, raw: dict) -> Window:
    if raw["type"] not in WINDOW_TYPES:
        raise GridError(f"{ind_id} : type de fenêtre inconnu {raw['type']!r}")
    if raw["type"] == "rolling" and not isinstance(raw.get("days"), int):
        raise GridError(f"{ind_id} : une fenêtre glissante exige un nombre de jours entier")
    return Window(type=raw["type"], days=raw.get("days"))
