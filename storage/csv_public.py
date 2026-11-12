"""CSV publiés sur le site : neutralise les cellules qu'un tableur lirait comme une formule.

Les titres de faits viennent de sources externes (Journal officiel, flux RSS de presse) : une
cellule commençant par = + - @ (ou une tabulation, un retour chariot) serait exécutée comme
formule à l'ouverture dans Excel ou LibreOffice. Elle est préfixée d'une apostrophe, que le
tableur n'affiche pas. Seules les chaînes sont concernées (les nombres négatifs restent des
nombres).
"""

from __future__ import annotations

DEBUTS_DANGEREUX = ("=", "+", "-", "@", "\t", "\r")


def neutraliser(valeur):
    if isinstance(valeur, str) and valeur.startswith(DEBUTS_DANGEREUX):
        return "'" + valeur
    return valeur


def ligne_sure(ligne: dict) -> dict:
    return {k: neutraliser(v) for k, v in ligne.items()}
