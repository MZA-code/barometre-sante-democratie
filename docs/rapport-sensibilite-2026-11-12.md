# Rapport de vérification et de sensibilité — 12 novembre 2026

Réponse aux étapes 1 et 2 du brief (`docs/brief-amelioration-barometre.md`). Aucune modification
du site ni du calcul n'a été faite : l'étape 3 (choix de l'auteur) précède toute correction.

Données : `data.js` en ligne au 12/11/2026 (données au 11/11/2026, archive du 12/11 06:05 UTC).
Indice affiché à cette date : **58,5** (58 arrondi). 14 indicateurs dans l'indice, 16 au total
(D5.2 relevé arrêté au 31/12/2025, D7 hors indice pendant la reprise du passé).

## 1. Points « À vérifier » du brief

| Point | Verdict | Constat dans le code |
|---|---|---|
| §3.1 Formule de la position | **Confirmé** | `index.html:1018` : part des mois strictement inférieurs + ½ part des mois égaux (rang moyen). Chaque point mensuel est la valeur de la fenêtre glissante de 365 jours à la fin du mois. |
| §3.1 Valeurs nulles vers 40 | **Confirmé, mais choix délibéré et déjà annoncé** | Commentaire `index.html:1011-1013` et texte affiché : « une valeur partagée par beaucoup de mois, zéro compris, est placée au milieu ». La contradiction relevée par le brief vient de la phrase « 0 si c'est le niveau le plus bas jamais observé », qui reste fausse pour un zéro. |
| §3.1 Effet si 0 → position 0 | **Confirmé** | 58,5 → 46,6 (−11,9). |
| §3.2 D5.1 série courte | **Confirmé** | 12 points mensuels (première fenêtre complète : décembre 2025). Déjà signalée « série courte » (astérisque, repère gris) mais **comptée** dans l'indice. |
| §3.2 D4.2 depuis 2022 | **Partiellement faux** | Données depuis 2022, mais première fenêtre de 12 mois complète en mai 2023 : 43 points. Au-dessus du seuil `SERIE_COURTE` (36 mois), donc non signalée. |
| §3.2 Pétitions | **Confirmé** | 63 points depuis septembre 2021 ; 87 % des mois à 0 ; valeur 3 → position 99. Non signalée comme courte. |
| §3.3 D2.2 raccord urgence / procédure accélérée | **Correct** | `extract/procedure.py` compte l'un ou l'autre engagement ; trou connu du champ urgence au Sénat 1998-2008 compensé par les autres sources. |
| §3.3 D3.2 réforme de 1974 | **Correct** | Série depuis janvier 1975, soit après l'ouverture de la saisine. |
| §3.3 D5.3 rang RSF | **Confirmé** | Le rang est la métrique (`extract/rsf.py`) ; les trois périodes de méthode du score sont stockées mais non utilisées ; nombre de pays non pris en compte. |
| §3.3 Crédits annulés en euros courants | **Confirmé** | `extract/budget.py:11` le dit : ni inflation ni rapport au budget. |
| §3.3 D6.1 nombre absolu | **Confirmé** | Série depuis 2016 (120 points), pas de rapport à la population. |
| §7 « 16 indicateurs » / 14 dans l'indice | **Confirmé** | `seo.py:nb_indicateurs` compte toutes les dimensions. |
| §7 Astérisque de D4.2* | **Confirmé** | Signifie « approximation » (README, DECISIONS) ; non expliqué sur la page. Collision avec l'astérisque « série courte » de la liste classée. |
| §7 Sommaire vide sans JS | **Confirmé** | `#toc-panel` et la nav latérale sont remplis en JavaScript (`index.html:2566`), aucun repli `<noscript>`. |
| §7 Avis « cookies » | **Confirmé** | `#avis-cookies` ; seul stockage : `localStorage` (thème, avis vu). |

Non vérifié : rendu visuel, exactitude des données face aux sources officielles, date d'ouverture
de la plateforme de pétitions de l'Assemblée, section « Législature par législature » (présentation
identique entre périodes), mention V-Dem / Freedom House.

## 2. Positions par indicateur

| Indicateur | Position | Rang bas (part <) | Points mensuels | Depuis | Mois à 0 |
|---|---:|---:|---:|---|---:|
| D2.3 Pétitions classées | 99,2 | 98,4 | 63 | 2021-09 | 87 % |
| D6.1 Techniques de renseignement | 95,0 | 90,0 | 120 | 2016-12 | 0 % |
| D5.1 Temps de parole exécutif | 91,7 | 83,3 | **12** | 2025-12 | 0 % |
| D2.4 Crédits annulés | 84,4 | 83,8 | 240 | 2006-12 | 0 % |
| D4.1 Dissolutions | 81,5 | 79,9 | 432 | 1990-12 | 45 % |
| D2.2 Procédure accélérée | 76,0 | 75,9 | 572 | 1979-04 | 0 % |
| D2.1 Contournement du Parlement | 58,8 | 58,7 | 804 | 1959-12 | 25 % |
| D3.2 Lois censurées | 47,8 | 47,0 | 623 | 1975-01 | 1 % |
| D1.1 Règles électorales | 45,5 | 0,0 | 396 | 1993-12 | 91 % |
| D3.1 Régimes d'exception | 40,5 | 0,0 | 804 | 1959-12 | 81 % |
| D6.2 Fichiers malgré réserves CNIL | 40,2 | 0,0 | 516 | 1983-12 | 80 % |
| D1.2 Scrutins reportés | 39,0 | 0,0 | 432 | 1990-12 | 78 % |
| D5.3 Classement RSF | 17,6 | 13,4 | 276 | 2002-12 | 0 % |
| D4.2* Interdictions contestées | 1,2 | 0,0 | 43 | 2023-05 | 0 % |

Répartition : 6 indicateurs ≥ 75, 2 ≤ 25, 7 au-dessus de 50, 7 en dessous (constat du brief confirmé).

## 3. Sensibilité de l'indice

Mêmes données, seule la méthode change.

| Variante | Indice | Écart |
|---|---:|---:|
| A. Moyenne simple, rang moyen (**affiché**) | 58,5 | — |
| B. Médiane des 14 positions | 53,3 | −5,2 |
| C. Moyenne par dimension D1–D6, puis moyenne | 54,9 | −3,6 |
| D. Les 4 valeurs nulles à position 0 | 46,6 | −11,9 |
| E. Ex æquo au rang bas pour tous (part strictement inférieure) | 45,0 | −13,5 |
| F. Ex æquo au rang haut pour tous (part inférieure ou égale) | 71,9 | +13,4 |
| G1. Séries ≥ 36 mois seulement (13 ind., sans D5.1) | 55,9 | −2,6 |
| G2. Séries ≥ 60 mois seulement (12 ind., sans D5.1, D4.2) | 60,5 | +2,0 |
| G3. Séries ≥ 120 mois seulement (11 ind., sans D5.1, D4.2, D2.3) | 56,9 | −1,6 |
| H. Sans les indicateurs à double lecture D3.2 et D4.2 | 64,1 | +5,6 |
| I. Sans D2.2 procédure accélérée | 57,1 | −1,4 |
| J. Normalisation min-max au lieu du rang | 38,6 | −19,9 |
| K. Séries ≥ 36 mois et sans double lecture (11 ind.) | 61,6 | +3,1 |
| L. Sans les indicateurs actuellement nuls (10 ind.) | 65,3 | +6,8 |

**Fourchette : 38,6 à 71,9** selon des choix tous défendables. Hors min-max et hors convention
« rang haut » (les deux plus éloignées de la définition affichée), elle reste de 45 à 65.

Constats ajoutés à ceux du brief :

- Le traitement des ex æquo est à lui seul le choix le plus lourd (45,0 / 58,5 / 71,9) parce que
  quatre indicateurs sont nuls la plupart des mois.
- Les variantes vont dans les deux sens : exclure les séries courtes ou les indicateurs à double
  lecture fait **monter** l'indice (jusqu'à 64), corriger les zéros le fait **baisser** (47).
  Aucune ne peut être retenue pour son effet ; l'affichage d'un chiffre unique à l'unité près
  n'est pas tenable.
- Les points mensuels sont des fenêtres glissantes de 12 mois qui se chevauchent : 120 points
  pour D6.1 représentent environ 10 observations indépendantes (une par an). La durée réelle d'une
  série se compte en années, pas en points.

Reproductibilité : les cinq variantes affichées sur le site sont calculées par
`scoring/indice.py` (`VARIANTES`) à chaque publication ; les autres lignes du tableau
ci-dessus ont été calculées une fois, à la main, sur le `data.js` en ligne du 12/11.

## 4. Décisions de l'auteur (étape 3) et effet

1. Chiffre de tête : la question « La France est-elle encore une démocratie ? » reçoit la
   réponse des classements internationaux. L'indice devient un « écart à l'habituel » signé,
   avec sa fourchette (option B du brief, au second rang).
2. Ex æquo : rang moyen conservé, définition affichée corrigée.
3. Historique minimal : 5 ans.
4. D3.2 et D4.2 : à part, comme indicateurs de contre-pouvoir.

Effet combiné, sur les mêmes données : 58,5 → **61,6**, soit un écart de **+12**. La
fourchette sur les 11 indicateurs retenus va de −4 à +28 (médiane +9, par dimension +5,
rang bas −4, rang haut +28).
