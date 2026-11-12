"""Indice d'écart à l'habituel : composition, position de chaque indicateur, sensibilité.

Règles fixées par l'auteur le 2026-11-12 (docs/rapport-sensibilite-2026-11-12.md), avant tout
calcul de leur effet :

- position d'un indicateur = part des mois de son historique strictement inférieurs à la
  valeur actuelle + la moitié de la part des mois égaux (rang moyen des ex æquo) ;
- un indicateur n'entre dans l'indice que si son historique compte au moins cinq ans de
  points mensuels (HISTORIQUE_MIN_MOIS) ;
- les indicateurs à double lecture (CONTRE_POUVOIR) sont présentés à part : une hausse peut
  traduire un contrôle qui fonctionne autant qu'une situation dégradée ;
- l'indice est la moyenne simple des positions retenues, affichée en écart à 50 (niveau
  habituel), avec la fourchette obtenue par d'autres agrégations défendables (VARIANTES).
"""

from __future__ import annotations

import statistics

HISTORIQUE_MIN_MOIS = 60
CONTRE_POUVOIR = {
    "D3.lois_censurees": (
        "indicateur de contre-pouvoir : une part élevée de lois censurées peut traduire "
        "un contrôle constitutionnel qui fonctionne autant que des lois plus fragiles"
    ),
    "D4.interdictions_manifester_juge": (
        "indicateur de contre-pouvoir : une part élevée d'interdictions annulées peut traduire "
        "un juge qui protège la liberté de manifester autant que des interdictions abusives"
    ),
}


def position(valeurs: list[float], actuel: float, ex_aequo: str = "moyen") -> float:
    """Place de `actuel` parmi `valeurs`, de 0 à 1. `ex_aequo` : 'moyen', 'bas' ou 'haut'."""
    inf = sum(v < actuel for v in valeurs)
    egaux = sum(v == actuel for v in valeurs)
    part = {"moyen": 0.5, "bas": 0.0, "haut": 1.0}[ex_aequo]
    return (inf + part * egaux) / len(valeurs)


def position_dim(d: dict, ex_aequo: str = "moyen") -> float:
    return position([m["v"] for m in d["mensuel"]], d["actuel"], ex_aequo)


def dans_indice(d: dict) -> bool:
    return not d.get("fin_couverture") and not d.get("hors_indice")


def composer(dimensions: list[dict]) -> None:
    """Marque `contre_pouvoir` et `hors_indice` selon les règles ci-dessus (sans écraser une
    raison déjà posée, comme celle de D7)."""
    for d in dimensions:
        d["contre_pouvoir"] = d["id"] in CONTRE_POUVOIR
        if d.get("hors_indice") or d.get("fin_couverture"):
            continue
        if d["contre_pouvoir"]:
            d["hors_indice"] = CONTRE_POUVOIR[d["id"]]
        elif len(d["mensuel"]) < HISTORIQUE_MIN_MOIS:
            ans = round(len(d["mensuel"]) / 12, 1)
            duree = f"{ans:g} an{'s' if ans >= 2 else ''}".replace(".", ",")
            d["hors_indice"] = (
                f"historique de {duree}, moins des {HISTORIQUE_MIN_MOIS // 12} ans "
                "requis pour entrer dans l'indice"
            )


def _par_dimension(retenus: list[dict]) -> float:
    groupes: dict[str, list[float]] = {}
    for d in retenus:
        groupes.setdefault(d["id"].split(".")[0], []).append(position_dim(d))
    return statistics.mean(statistics.mean(v) for v in groupes.values())


VARIANTES = (
    ("moyenne", "Moyenne simple, ex æquo au rang moyen (méthode retenue)",
     lambda r: statistics.mean(position_dim(d) for d in r)),
    ("mediane", "Médiane des positions",
     lambda r: statistics.median(position_dim(d) for d in r)),
    ("par_dimension", "Moyenne par dimension (D1 à D6), puis moyenne des dimensions",
     _par_dimension),
    ("ex_aequo_bas", "Ex æquo au rang le plus bas (une valeur nulle habituelle compte pour 0)",
     lambda r: statistics.mean(position_dim(d, "bas") for d in r)),
    ("ex_aequo_haut", "Ex æquo au rang le plus haut",
     lambda r: statistics.mean(position_dim(d, "haut") for d in r)),
)  # fmt: skip


def indice(dimensions: list[dict]) -> dict:
    """Valeur retenue (0-100), écart signé à 50 et sensibilité aux choix d'agrégation."""
    retenus = [d for d in dimensions if dans_indice(d)]
    variantes = [
        {"id": vid, "libelle": lib, "valeur": round(100 * f(retenus), 1)}
        for vid, lib, f in VARIANTES
    ]
    valeur = variantes[0]["valeur"]
    ecarts = [round(v["valeur"]) - 50 for v in variantes]
    return {
        "valeur": valeur,
        "ecart": round(valeur) - 50,
        "nb_indicateurs": len(retenus),
        "ecart_min": min(ecarts),
        "ecart_max": max(ecarts),
        "variantes": variantes,
    }
