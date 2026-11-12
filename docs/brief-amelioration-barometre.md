# Brief d'amélioration — barometre-democratique.fr

Revue externe du 11 novembre 2026, à transmettre à Claude Code.

## 0. Portée et limites de cette revue

- Revue faite à partir du **texte extrait de la page d'accueil** (indice au 10 novembre 2026 : 58/100).
- **Non vérifié** : le rendu visuel, les graphiques, le JavaScript, le code de calcul, l'exactitude des données par rapport aux sources officielles.
- Conséquence : plusieurs points ci-dessous sont des **hypothèses à confirmer dans le code** avant toute correction. Ils sont marqués « À vérifier ».
- Si un constat est faux une fois le code lu, le dire dans le rapport final plutôt que de le « corriger » quand même.

## 1. Règles de travail (neutralité)

Ces règles priment sur tout le reste.

1. **Fixer la méthode avant de regarder le résultat.** Aucun choix de calcul ne doit être retenu parce qu'il fait monter ou baisser l'indice.
2. **Rapporter avant/après.** Pour chaque changement de méthode, donner la valeur de l'indice avant et après, quel que soit le sens.
3. **Ne pas chercher un chiffre « plus alarmant » ni « plus rassurant ».** L'auteur a l'intuition que 58 est trop clément. Certaines corrections ci-dessous font au contraire **baisser** l'indice. Les appliquer quand même si elles sont justifiées.
4. **Séparer description et jugement.** Soit le site décrit (pas de couleurs de verdict, pas de chiffre unique lisible comme une note), soit il juge et l'assume (seuils explicites, justifiés, sourcés). Pas les deux à la fois.
5. **Ne rien supprimer de la section « Méthode et limites ».** C'est le point fort du site.

## 2. P0 — Le chiffre de tête « 58 sur 100 »

### Constats

- Le titre parle de « santé démocratique » et affiche « 58 sur 100 ». Lu comme une note, cela signifie « passable, ça va ». Or sur ce site, **plus haut = plus défavorable**. La polarité est l'inverse de ce que le titre suggère.
- La page écrit « Ce n'est pas une note » juste sous un chiffre sur 100 et une jauge vert → rouge. Le visuel contredit le texte.
- L'échelle est **relative à l'historique français**, pas absolue. 0 ne veut pas dire « tout va bien » : il veut dire « au plus bas jamais observé pour chaque indicateur ». 50 ne veut pas dire « acceptable » : il veut dire « habituel ». Si l'habituel est lui-même dégradé, l'échelle ne le montre pas.
- Le chiffre n'est pas robuste. Avec les mêmes 14 positions, des choix tous défendables donnent :

| Variante de calcul | Résultat |
|---|---|
| Moyenne simple (affichée) | 58,4 |
| Médiane des 14 positions | 53,5 |
| Moyenne par dimension D1–D6, puis moyenne des dimensions | 54,9 |
| Les 4 indicateurs à valeur 0 comptés à position 0 (voir §3.1) | 46,6 |
| Sans les deux séries courtes D5.1 et D4.2 (voir §3.2) | 60,4 |

  L'indice varie donc de **47 à 60** selon la méthode. Un chiffre unique à l'unité près affiche une précision qu'il n'a pas.
- La moyenne masque une répartition bimodale : 6 indicateurs sur 14 sont à 75 ou plus, 2 sont à 25 ou moins, 7 sont au-dessus de 50 et 7 en dessous.
- La dimension D2 (Parlement) compte 4 indicateurs sur 14, D1 en compte 2. La moyenne simple surpondère D2 sans que ce soit un choix annoncé.

### Options (décision de l'auteur)

- **Option A (recommandée) : retirer le chiffre unique du haut de page.** Le remplacer par un constat factuel du type : « 6 indicateurs sur 14 sont dans le quart haut de leur historique, 2 dans le quart bas. » Garder la liste classée, qui est l'information réellement utile. L'indice composite peut rester plus bas dans la page, avec sa fourchette.
- **Option B : garder un indice, mais le renommer et l'encadrer.** Nom qui dit le sens (ex. « indice d'écart à l'habituel »), affichage en écart signé par rapport à 50 (ex. « +8 »), fourchette de sensibilité affichée, plus de « /100 » en gros.
- **Option C : assumer un jugement.** Définir des seuils absolus par indicateur, justifiés par une source externe (Commission de Venise, etc.), publiés avant application. C'est le plus lourd et le plus contestable.

### Critères d'acceptation

- Un visiteur qui ne lit que le haut de page comprend dans quel sens se lit le chiffre.
- Aucun élément visuel ne contredit la phrase « ce n'est pas une note ».
- Si un composite subsiste, sa fourchette de sensibilité est affichée et la formule est publiée.

## 3. P0 — Calcul de la « position »

### 3.1 Valeurs nulles affichées vers 40 (À vérifier)

- D1.1 (0 loi → 45), D1.2 (0 report → 39), D3.1 (0 jour → 41), D6.2 (0 décret → 40).
- La page définit 0 comme « le plus bas jamais observé ». Une valeur de 0 est par construction le plus bas possible. Elle devrait donc être à la position 0 selon la définition affichée.
- Hypothèse : rang centile avec ex æquo traités au rang moyen. Beaucoup de mois passés valent 0, donc le 0 tombe au milieu.
- À faire : lire le code, confirmer la formule. Puis **soit** corriger le calcul pour qu'il respecte la définition affichée, **soit** corriger la définition affichée. Documenter le traitement des ex æquo.
- Effet attendu si corrigé vers 0 : l'indice **baisse** d'environ 12 points. Le rapporter tel quel.
- Question de fond à trancher : un indicateur presque toujours à 0 a-t-il sa place dans une moyenne de rangs ? Il ne peut que rester neutre ou monter.

### 3.2 Séries trop courtes

- D5.1 (temps de parole) : données depuis janvier 2025. Position 92 calculée sur moins de deux ans.
- D4.2 (interdictions contestées) : depuis 2022. Position 1.
- Pétitions de plus de 500 000 signatures : effectifs minuscules (valeur 3 → position 99) et série récente (À vérifier : date d'ouverture de la plateforme de l'Assemblée).
- Ces séries pèsent autant que D2.1, suivie depuis 1959.
- À faire : fixer un seuil minimal d'historique (durée et nombre d'observations) pour entrer dans tout composite. En dessous : « hors indice », valeur brute affichée seulement.

### 3.3 Ruptures de série et tendances

Une position dans l'historique suppose une série comparable dans le temps. À vérifier et documenter, indicateur par indicateur :

- **D6.1** : nombre absolu de personnes surveillées. Le cadre légal et l'organe de contrôle datent de 2015, les techniques autorisées ont changé depuis. Une série en hausse tendancielle est mécaniquement « au plus haut ».
- **D2.2** : la « procédure accélérée » a remplacé la « déclaration d'urgence » en 2008. Vérifier que la série depuis 1978 raccorde bien les deux.
- **D3.2** : ouverture de la saisine aux parlementaires en 1974. La page le mentionne, vérifier que le calcul en tient compte.
- **D5.3** : méthode RSF modifiée en 2013 et 2022, nombre de pays variable. Envisager le score RSF plutôt que le rang, ou couper la série aux ruptures.
- **D6.2** : changement de rédaction des avis CNIL depuis 2018, déjà signalé par le site.
- **Crédits annulés** : euros courants, non rapportés au budget. Passer en part des crédits votés.
- **D6.1** : envisager un taux rapporté à la population.

### 3.4 Fenêtres hétérogènes

- La page annonce « valeur des 12 derniers mois », mais certains indicateurs sont annuels, d'autres par législature.
- À faire : afficher pour chaque indicateur sa fenêtre réelle, sa date de début, sa fréquence et la date de la dernière donnée. Plusieurs dates de début manquent aujourd'hui (D1.2, pétitions, crédits, D3.2, D5.3, D6.1, D6.2).

## 4. P1 — Sens de lecture de chaque indicateur

La règle « plus haut = plus défavorable » est appliquée partout. Elle est discutable pour :

- **D3.2 (lois censurées)** : un taux élevé peut signifier un contre-pouvoir qui fonctionne. La page le reconnaît mais l'inclut quand même dans la moyenne.
- **D4.2 (interdictions suspendues ou annulées)** : même ambiguïté. Le sens du « 25 % » n'est pas défini clairement.
- **D2.2 (procédure accélérée)** : outil constitutionnel ordinaire. Justifier pourquoi une hausse est défavorable, avec une source.

À faire :

- Écrire pour chaque indicateur une phrase « pourquoi une hausse est lue comme défavorable », sourcée.
- Sortir du composite les indicateurs à double lecture, ou les présenter à part comme « indicateurs de contre-pouvoir ».

## 5. P1 — Sélection des indicateurs et cadrage

- Tous les indicateurs mesurent des actes de l'exécutif lus comme des contournements. Aucun ne peut enregistrer une amélioration autrement que par l'absence d'actes. Le choix des indicateurs est lui-même un parti pris ; il doit être explicite.
- À faire :
  - Publier les critères d'inclusion et d'exclusion d'un indicateur.
  - Lister les indicateurs envisagés puis écartés, avec la raison.
  - Étudier des indicateurs qui peuvent bouger dans l'autre sens (activité de contrôle parlementaire, délais de jugement, suites données aux avis des autorités indépendantes).
- **Repères externes** : afficher les notes V-Dem, Freedom House et le score RSF à côté de l'indice. Le site les annonce comme « non affichées ». C'est le seul moyen de donner un ancrage absolu et comparatif (autres pays), que l'échelle interne ne fournit pas.
- **Section « Législature par législature »** : elle sera lue comme un classement des gouvernements. Vérifier que la présentation est strictement identique pour toutes les périodes, sans commentaire, et que les limites de comparabilité sont rappelées à cet endroit.
- **Définition de la démocratie** : présentée comme une citation unique. Indiquer que la définition est débattue et dire pourquoi celle-ci a été retenue.

## 6. P1 — Transparence et reproductibilité

Un site qui revendique la neutralité doit être vérifiable par un tiers hostile. Aujourd'hui il manque :

- **Données téléchargeables** : un fichier CSV ou JSON par indicateur (valeurs brutes, dates, lien vers la source de chaque ligne).
- **Formules publiées** : calcul de la position, traitement des ex æquo, agrégation.
- **Code source public**, ou à défaut une description assez précise pour refaire le calcul.
- **Journal des modifications** daté : chaque changement de méthode ou correction de donnée, avec l'effet sur l'indice.
- **Canal de signalement d'erreur** : une adresse de contact dédiée. L'anonymat de l'éditeur peut rester ; l'absence totale de contact empêche la correction.
- **« Comité de méthode »** : la page le cite comme instance qui fixera pondérations et seuils. S'il existe, dire qui le compose et comment il décide. S'il n'existe pas encore, retirer la mention : elle donne une caution institutionnelle que le site n'a pas.
- **D7 et D5.2** : publier les critères de vérification « écrits à l'avance » et dire qui vérifie. Si une IA participe à la collecte ou à la vérification, le dire.
- **Outils** : mentionner que le site est développé avec l'aide d'une IA, et quel contrôle humain est exercé sur les données.

## 7. P2 — Incohérences à corriger

- **« 16 indicateurs »** dans le titre et les métadonnées, mais 14 dans l'indice. Harmoniser.
- **« Recalculés chaque jour »** : vrai pour le calcul, pas pour les données (D5.2 arrêté fin 2025, Arcom à trois mois, IGPN à dix mois). Reformuler et afficher la date de dernière donnée par indicateur.
- **Numérotation D2** : pétitions et crédits annulés n'ont pas de sous-numéro, contrairement à D2.1 et D2.2. Le nom de la section varie (« Contournement du Parlement » / « Place du Parlement »).
- **Astérisque de « D4.2\* »** : aucune note ne l'explique.
- **Unités manquantes** dans la liste classée : « 3 », « 1 », « 12 », « 4 » sans unité. D5.3 affiche rang et position côte à côte sans explication.
- **Sommaire** : apparaît vide dans le texte extrait (À vérifier : peut-être généré en JavaScript ; prévoir alors un repli sans JS).
- **Avis « cookies »** alors que le site dit n'en poser aucun. Renommer (stockage local des préférences) ou supprimer l'avis.
- **Participation aux législatives** : citée comme contexte, sans valeur visible dans le texte.

## 8. P2 — Vocabulaire

Termes qui présupposent une conclusion, à remplacer ou à assumer explicitement :

- « santé démocratique » : métaphore sain/malade, alors que le site dit ne pas qualifier le régime.
- « érosion », « atteintes », « contournement » : orientés. Préférer une description de l'acte (« textes adoptés sans vote final »).
- « Ce que les textes ne disent pas » : intertitre qui oriente la lecture de D7.
- « sourcé », « officiel », « comité de méthode » accolés à « illustratif », « prototype » : message contradictoire sur le statut du chiffre. Choisir un registre.

## 9. À conserver

- La section « Méthode et limites », détaillée et franche sur les faiblesses de chaque indicateur.
- Les liens directs vers les textes et décisions sources.
- La distinction droit (D1–D6) / pratique (D7), et le choix de laisser hors indice les relevés non exhaustifs.
- La règle de double source pour D7.
- L'absence de traceurs et de mesure d'audience.
- La mention « Prototype » et « Indice illustratif ».

## 10. Ordre de travail et livrable attendu

1. Lire le code de calcul et confirmer ou infirmer chaque point « À vérifier ».
2. Produire un **rapport de sensibilité** : indice recalculé sous chaque variante du §2, plus celles découvertes dans le code.
3. **S'arrêter et soumettre à l'auteur** le choix entre les options A, B et C du §2, et la liste des indicateurs à sortir du composite (§3.2, §4). Ne pas trancher seul.
4. Appliquer les corrections P0, puis P1, puis P2.
5. Créer le journal des modifications et y consigner tout ce qui précède, avec l'indice avant/après.

Livrable final : un résumé listant ce qui a été changé, ce qui a été vérifié et trouvé correct, ce qui n'a pas pu être vérifié, et la valeur de l'indice à chaque étape.
