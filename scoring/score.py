"""Métriques brutes -> notes 0-4, uniquement si les seuils de la grille sont figés.

Usage :
    python -m scoring.score [--db CHEMIN] [--grid config/grid.vN.yaml]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scoring.grid import DEFAULT_GRID_PATH, Indicator, load_grid
from storage.db import DEFAULT_DB_PATH, connect, init_db


class ThresholdsNotFrozen(RuntimeError):
    """Refus de noter : au moins un seuil vaut null dans la grille (règle 4)."""


def score_value(indicator: Indicator, value: float) -> int:
    """Convertit une valeur de métrique en note 0-4 selon les seuils de la grille."""
    if not indicator.thresholds_frozen:
        raise ThresholdsNotFrozen(
            f"{indicator.id} : seuils non figés, aucune note ne peut être produite"
        )
    if indicator.direction == "increasing":
        return sum(value >= t for t in indicator.thresholds)
    return sum(value <= t for t in indicator.thresholds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scoring.score")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID_PATH)
    args = parser.parse_args(argv)

    grid = load_grid(args.grid)
    conn = connect(args.db)
    try:
        init_db(conn)
        for indicator in grid.indicators.values():
            if not indicator.thresholds_frozen:
                print(
                    f"[grille {grid.version}] {indicator.id} : seuils non figés, "
                    "métriques brutes seulement, aucune note produite."
                )
                continue
            # Écriture des notes et de la traçabilité score -> faits : étape 5,
            # une fois les métriques calculées.
            raise NotImplementedError(
                f"{indicator.id} : seuils figés mais écriture des notes pas encore implémentée"
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
