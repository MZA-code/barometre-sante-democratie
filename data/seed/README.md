# Seeds manuels

Fichiers construits à la main à partir de listes officielles, pour couvrir les périodes
que les sources ouvertes ne couvrent pas. Ils sont versionnés dans git, archivés comme
documents bruts (source `seed_manuel`) par `make collect-seed`, et les faits qui en
sont tirés portent `extraction_method = 'seed_manuel'` et `verified_by_human = 0`.

## `49_3_historique.csv`

Engagements de responsabilité du Gouvernement (article 49 alinéa 3) de 1958 à 2011.
L'open data de l'Assemblée nationale ne publie les dossiers législatifs qu'à partir de la
XIVe législature (juin 2012) : les engagements postérieurs viennent de cette source.

- **Source** : Assemblée nationale, « Engagements de responsabilité du Gouvernement et
  motions de censure depuis 1958 » (URL dans la colonne `source_url`), consultée le
  2026-10-26.
- **Méthode** : transcription du tableau de la page, puis contrôle des effectifs par
  Premier ministre contre le bilan publié sur la même page (79 engagements jusqu'en
  1997, 3 de 2002 à 2007 : 82 lignes).
- **Colonnes** :
  - `date_engagement` : date ISO retenue ;
  - `date_source` : date telle qu'écrite sur la page (« séance du ... » compris) ;
  - `texte_id` : identifiant de texte attribué à la main, pour compter les textes
    distincts (lectures successives d'un même texte = même identifiant) ;
  - `motion_censure` : dépôt / vote / suffrages, tels qu'écrits sur la page.
- **Corrections** : une seule, signalée dans la colonne `note` (année de l'engagement
  sur l'égalité des chances, 2005 sur la page, 2006 d'après la loi n° 2006-396).
- **À faire** : vérification humaine ligne à ligne, puis passage de `verified_by_human`
  à 1 pour les faits contrôlés.

## `regimes_exception.csv`

Périodes de régime d'exception (état d'urgence, état d'urgence sanitaire, article 16) depuis
mai 1958, pour l'indicateur D3.1.

- **Méthode** : les bornes ont été relevées dans le corps des articles des textes eux-mêmes,
  lus dans l'archive JORF/LEGI le 2026-10-26 ; la colonne `preuve` cite la phrase qui fixe
  les dates. La colonne `textes` liste les identifiants JORFTEXT des textes de déclaration,
  de prorogation et de fin ; l'extraction vérifie qu'ils existent dans l'archive.
- **Colonnes** : `debut` et `fin` = premier et dernier jour couverts (inclus) ;
  `metropole` = la période couvre le territoire métropolitain ; `a_verifier` = une borne
  au moins n'est pas prouvée par un texte de l'archive (motif dans `note`).
- **Limites connues** : corps des textes de 1961 et 1985 absents de l'archive ; décrets de
  levée de 2006 et 2024 absents ; prorogations outre-mer de fin 2021 et début 2022 à
  confirmer. 11 lignes sur 20 sont marquées `a_verifier`.
- **Contrôle** : tout texte de l'archive qui déclare, proroge ou lève un régime
  d'exception sans être cité ici est signalé à chaque extraction.

## `mobilisations_nationales.csv`

Journées nationales de mobilisation, avec côte à côte le décompte du ministère de
l'Intérieur et celui des organisateurs (CGT pour l'intersyndicale), France entière. Donnée
de contexte, hors grille (`contexte.mobilisations`). Mouvements couverts : loi Travail de
2016 (12 journées), projet de réforme des retraites de 2019-2020 (10 journées), réforme des
retraites de 2023 (14 journées), journées de 2024 (3 journées : 15 juin, 1er octobre,
5 décembre), mobilisations de septembre-octobre 2025 (3 journées : 10 et
18 septembre, 2 octobre) et mouvement social de l'automne 2026 (4 journées : 17, 24 et
31 octobre, 5 novembre).

- **Ajout du 2026-11-06** (2025 et 2026) : journées repérées sur Wikipédia (articles
  « Mouvement du 10 septembre 2025 » et « Mouvement social de l'automne 2026 en France »), puis
  chaque chiffre retrouvé avec son attribution dans un article en accès libre, téléchargé et
  relu phrase par phrase. Les bilans du ministère publiés sur interieur.gouv.fr refusent les
  requêtes automatiques (HTTP 403) et n'ont pas pu être contrôlés par script. Pas de décompte
  national des organisateurs retrouvé pour le 10 septembre 2025.
- **Critère de sélection** (2026-11-06, appliqué à 2024) : journée nationale de manifestations
  appelée ou rejointe par au moins une confédération syndicale nationale, avec un décompte
  national du ministère de l'Intérieur (ou des « autorités »). Journées de 2024 retenues :
  15 juin (intersyndicale et associations, contre l'extrême droite), 1er octobre
  (interprofessionnelle CGT, FSU, Solidaires), 5 décembre (fonction publique, intersyndicale).
  Sources en accès libre (ICI, CNews), chiffres et attributions relus phrase par phrase. Réserve
  sur le 15 juin : un document de la FSU présente les 640 000 de la CGT comme le total des 15 et
  16 juin.

- **Relevé** : tableau « Toute la France » des articles Wikipédia « Mouvement social contre
  la réforme des retraites en France de 2023 » (révision 240431610 du 16 octobre 2026) et
  « Mouvement social contre le projet de réforme des retraites en France de 2019-2020 »
  (révision 241027655 du 4 novembre 2026) ; lien permanent dans la colonne `releve_via`.
  Pour 2016, l'article « Mouvement social contre la loi Travail en France de 2016 » (révision
  240493497 du 18 octobre 2026) n'a pas de tableau : les couples de chiffres nationaux ont
  été relevés à la main dans le texte, avec les références du même passage. Wikipédia ne sert qu'à trouver les
  chiffres et les articles qui les rapportent ; il n'est pas la source.
- **Contrôle automatique** (2026-11-05) : chaque article cité a été téléchargé et le chiffre
  recherché dans son texte, sous ses écritures courantes (« 1 120 000 », « 1,12 million »...).
  Quand l'article cité était inaccessible (mur payant, accès refusé aux robots) ou ne
  contenait plus le chiffre (page en direct modifiée), un autre article en accès libre
  rapportant le même chiffre a été cherché et contrôlé de la même façon ; il remplace alors
  la source (`controle` le signale). Aucun mur payant n'a été contourné, aucune copie
  d'archive d'un article payant n'a été utilisée.
- **Attribution (2016)** : le texte de Wikipédia n'attribue pas toujours explicitement les
  chiffres. Le contrôle exige alors que le nombre figure dans la source à moins de 250
  caractères d'une mention de qui l'a compté (ministère, Intérieur, Beauvau, police,
  autorités / CGT, FO, Unef, intersyndicale, syndicats, organisateurs). L'organisateur
  retenu dans `compte_par` est celui que la source nomme au plus près du chiffre
  (« syndicats » si elle ne précise pas) : identification automatique, signalée dans
  `note`, à confirmer.
- **Compteur `ministere_interieur`** : décompte officiel national, que la presse attribue au
  ministère de l'Intérieur, à « la police » ou aux « autorités ».
- **Résultat** : 57 chiffres sur 69 retrouvés dans leur source.
  - 2016 : 22 sur 24. Le 19 mai, Wikipédia donne deux chiffres syndicaux contradictoires
    (400 000 et 200 000) : la source (Le Figaro) donne 400 000 selon la CGT. Le 17 mars, le
    chiffre des organisateurs est celui de l'Unef (journée appelée par les organisations de
    jeunesse). Non vérifié : le 5 juillet (articles cités payants ; RTBF donne 30 000 « selon
    la préfecture » au niveau national et indique qu'aucun total syndical national n'était
    publié ; le chiffre de 100 000 n'a été retrouvé nulle part).
  - 2023 : 21 sur 28 (ministère 11 sur 14, organisateurs 10 sur 14) ;
  - 2019-2020 : 14 sur 17 (ministère 8 sur 10, organisateurs 6 sur 7 ; la CGT n'a pas donné
    d'estimation nationale pour les 29 janvier, 6 et 20 février 2020). Non vérifiés : le
    10 décembre 2019 (article cité disparu ; Universalis donne « près de trois cent quarante
    mille » pour le ministère, sans le chiffre exact ; le chiffre CGT de 885 000 n'a été
    retrouvé dans aucune source accessible) et le 6 février 2020 (article cité disparu).
  Les chiffres non vérifiés gardent la source citée par Wikipédia, avec `controle` =
  « non vérifié ».
- **Colonnes** : `date` (ISO), `mouvement`, `journee` (numéro d'ordre dans le relevé du mouvement),
  `perimetre`, `compteur` (`ministere_interieur` ou `organisateurs`), `manifestants`,
  `compte_par` (qui a compté : ministère de l'Intérieur, CGT, intersyndicale, FO...),
  `source_site`, `source_titre`, `source_url`, `controle`, `releve_via`, `a_verifier`,
  `note`.
- **Non relevés dans ce pilote** : chiffres de Paris (non contrôlés), forces de l'ordre
  blessées, interpellations. Les communiqués officiels du ministère de l'Intérieur ne sont
  pas publiés en données ouvertes : seules des sources de presse les rapportent.
- **À faire** : vérification humaine des 28 lignes (en priorité les 7 « non vérifié »),
  puis passage de `a_verifier` à « non » ; extension à d'autres mouvements (retraites
  2010, gilets jaunes...).

## `cnctr_surveillance.csv`

Chiffres annuels de la Commission nationale de contrôle des techniques de renseignement
(CNCTR), pour l'indicateur D6.1.

- **Source** : rapports d'activité de la CNCTR, archivés en PDF (source `cnctr_rapports`,
  `collectors/cnctr.py`) ; colonne `rapport` = fichier archivé, `rapport_url` = adresse.
- **Méthode** : pour chaque année, chiffre relevé dans le rapport de l'année (pour 2016, dans
  le tableau du rapport 2017), puis recherche automatique du nombre dans le texte du PDF
  archivé (2026-11-05) : les 10 années sont retrouvées.
- **Colonnes** : `annee`, `personnes_surveillees` (personnes ayant fait l'objet d'au moins une
  technique de renseignement dans l'année, indicateur calculé par la CNCTR depuis 2016),
  `demandes_techniques` (total des demandes de techniques domestiques individuelles, publié
  à partir de 2023 seulement ; vide avant), `controle`, `a_verifier`, `note`.
- **Limites** : le premier rapport porte sur la période du 3 octobre 2015 au 2 octobre 2016
  (20 282 personnes) ; la série retient l'année civile 2016 (20 360), publiée dans le rapport
  2017. Les rapports antérieurs à 2023 donnent les demandes par catégorie de technique, sans
  total unique comparable : non relevées.

## `journalistes_inquietes.csv`

Mesures des autorités visant des journalistes dans l'exercice de leur métier, pour
l'indicateur D5.2. **Relevé pilote 2023-2025, non exhaustif.**

- **Sources** : communiqués de RSF et des syndicats de journalistes (SNJ, SNJ-CGT), presse en
  accès libre. Les cas ont été repérés par recherche, puis chaque source ouverte et lue.
  Mapping Media Freedom (MFRR) n'a pas été utilisé : pas d'export public, et l'interrogation
  directe de sa base n'est pas un accès prévu pour la réutilisation.
- **Contrôle** : la colonne `extrait` cite une phrase de la source établissant la mesure ; un
  script vérifie qu'elle y figure mot pour mot (18 lignes sur 18, 2026-11-05). Les 10 lignes
  ajoutées le 2026-11-05 (recherche dans les communiqués RSF, SNJ, EFJ et la presse en accès
  libre, 2023-2025) ont été vérifiées de la même façon.
- **Colonnes** : `date` (jour de la mesure), `date_approximative` (oui si la source ne donne pas
  le jour exact ; voir `note`), `mesure` (`garde_a_vue`, `interpellation`, `poursuite`,
  `mise_en_examen`, `condamnation`, `convocation`), `nb_journalistes`, `media`, `autorite`,
  `contexte`, `source_url`, `extrait`, `controle`, `a_verifier`, `note`.
- **Choix** : le nom des journalistes n'est pas relevé. Une même personne peut faire l'objet de
  plusieurs mesures (garde à vue puis condamnation) : l'unité est la mesure. Les convocations
  et auditions ne relèvent pas de la définition de la grille (gardes à vue, interpellations,
  poursuites) et sont comptées à part.
- **À faire** : vérification humaine, extension aux années antérieures (gilets jaunes,
  manifestations de 2020 contre la loi « sécurité globale »…), recoupement avec les bilans
  annuels de RSF ; RSF indique par exemple « au moins cinq professionnels de la presse
  interpellés » au premier semestre 2023, quand ce relevé en compte deux pour la même période.

## `onu_declarations.csv`

Déclarations publiques des organes de l'ONU visant la France, en particulier le maintien de
l'ordre lors des manifestations. **Contexte, hors grille : aucune note n'en est tirée.
Relevé pilote, non exhaustif (10 déclarations, 2019-2026).**

- **Périmètre** (décision du porteur de projet, 2026-11-06) : communiqués des experts
  indépendants (procédures spéciales du Conseil des droits de l'homme), points de presse du
  Haut-Commissariat, déclarations et observations des comités des traités (CERD, comité contre
  la torture, comité des droits de l'homme), Examen périodique universel.
- **Accès** : pages de ohchr.org, autorisées par son `robots.txt` mais refusées aux requêtes
  automatiques (HTTP 403) ; chaque page a donc été ouverte une à une dans un navigateur, comme
  par un lecteur. Les bases de l'ONU interdites aux robots (communications des procédures
  spéciales `spcommreports.ohchr.org`, base des organes de traités `tbinternet.ohchr.org`) n'ont
  pas été interrogées.
- **Contrôle** : `extrait` et `extrait_complementaire` sont recopiés par script depuis le texte
  de la page (comparaison insensible aux seuls guillemets, apostrophes et espaces) ; 20 extraits
  sur 20 retrouvés le 2026-11-06. Version française de la page quand elle existe (`langue` =
  `fr`), sinon l'original anglais (`en`), sans traduction maison.
- **Choix des extraits** : la phrase qui porte le constat principal ; en complément, quand la
  déclaration en contient une, la phrase qui en donne une autre facette (violences visant les
  forces de l'ordre, appel au calme, demande d'enquête).
- **Colonnes** : `organe`, `type` (communiqué, point de presse, déclaration d'alerte rapide,
  observations finales), `theme` (maintien de l'ordre et manifestations, législation de
  sécurité, discriminations et forces de l'ordre, Nouvelle-Calédonie).
- **Limites** : les réponses de la France ne sont pas relevées (elles figurent dans la base des
  communications, non interrogée) ; recherche des déclarations par moteur de recherche,
  donc non exhaustive. À compléter : observations finales du comité des droits de l'homme
  (2024), Examen périodique universel (2023).

## `interpellations_mobilisations.csv`

Interpellations et gardes à vue lors des journées nationales de `mobilisations_nationales.csv`,
France entière et Paris, **telles qu'annoncées par une autorité** (ministère ou ministre de
l'Intérieur, préfecture de police, parquet ; « les autorités » ou « la police » quand la source
ne précise pas, signalé dans `note`). Donnée de contexte, hors grille
(`contexte.interpellations`). Une ligne par journée, périmètre et mesure (`interpellations`,
`gardes_a_vue`).

- **Relevé du 2026-11-07** : 50 chiffres pour 26 des 46 journées, trouvés par recherche web
  dans des articles en accès libre ; aucun chiffre de mémoire, aucun chiffre d'association ou
  de syndicat, aucun mur payant contourné. La colonne `citation` recopie la phrase qui porte le
  chiffre.
- **Contrôle** (2026-11-07) : chaque article a été retéléchargé et la citation recherchée dans
  son texte (`controle`) : 44 retrouvées telles quelles (nombre parfois écrit en lettres ou
  avec un point comme séparateur), 2 aux guillemets près ; les 4 pages de France 24, qui
  refusent les téléchargements par script, ont été vérifiées dans un navigateur.
- **Bilans** : le dernier bilan national publié pour la journée est retenu ; un bilan
  provisoire (« à 18 h », « pour l'instant ») l'est faute de mieux, avec l'heure en `note`.
  17 octobre 2026 : 2 628 retenus (rappelés par le ministère le 25 octobre) ; le bilan
  « consolidé » du 18 octobre (2 397) et un bilan provisoire (1 200) sont cités en note.
- **Non retenus** : chiffres sans autorité nommée (ex. 7 et 11 mars 2023, 14 juin 2016,
  6 juin 2023), approximations (« plus d'une centaine »). 2019-2020 : seulement des chiffres
  parisiens retrouvés.
- **À relire** (`a_verifier` = oui pour toutes les lignes) : attributions vagues, bilans
  provisoires, périmètre « agglomération parisienne » du 31 octobre 2026.

## `usage_force_annuel.csv`

Séries annuelles officielles sur l'usage de la force, relevées dans les rapports annuels publiés
sur vie-publique.fr (archivés par `collectors/rapports.py`). Donnée de contexte, hors grille
(`contexte.usage_force`). Une ligne par série et par année, avec le document, la page du PDF
et la ligne ou la phrase citée.

- `igpn_lbd_declarations`, `igpn_lbd_munitions`, `igpn_gmd_declarations`, `igpn_gmd_munitions`
  (2017-2024) : tableaux du rapport annuel de l'IGPN 2024 (p. 87 et 106 du PDF), dernière
  édition retenue car les chiffres sont révisés d'une édition à l'autre. Police nationale,
  toutes circonstances (fichier TSUA, déclaratif) ; gendarmerie et grenades lacrymogènes non
  couvertes ; GENL comptée avec la GMD depuis septembre 2020.
- `igpn_blesses_mo_vu` (2018, 2019, 2023, 2024) : blessés (ITT d'au moins 9 jours) lors
  d'opérations de maintien de l'ordre ou de violences urbaines ; non publié sous cette forme
  pour 2020-2022 ; recensement pérennisé fin 2023 (rupture de couverture).
- `ddd_reclamations_deontologie` (2018, 2019, 2021-2025) : réclamations reçues en
  « déontologie de la sécurité » (rapports d'activité 2019, 2023, 2025 du Défenseur des
  droits) ; 2020 non relevé.
- **Contrôle** (2026-11-07) : chaque valeur relue à la page indiquée (`pdftotext`) ; les
  phrases en colonnes vérifiées dans l'ordre de lecture. Recherche des sources : rapport
  d'instruction du 2026-11-07 (IGPN, IGGN, ministère, Défenseur des droits, Parlement) ;
  aucune série mensuelle ni propre aux manifestations n'existe.

## `reperes_internationaux.csv`

Classements internationaux affichés en tête de page pour répondre à « la France est-elle
encore une démocratie ? » (décision du 2026-11-12) : le jugement est celui de ces
organismes, pas du baromètre. Lu directement par `front/prototype/export_data.py` (pas de
fait en base : ce ne sont pas des indicateurs du baromètre).

- Une ligne par source, la dernière édition seulement ; mettre à jour à chaque parution
  (V-Dem en mars, Freedom House en février-mars) et noter la date de lecture dans `controle`.
- `categorie_democratique` : `oui` si la catégorie attribuée à la France est une catégorie
  démocratique de la source (V-Dem : démocratie libérale ou électorale ; Freedom House :
  pays libre).
- Le classement de l'Economist Intelligence Unit n'est pas repris : sa page officielle n'a
  pas pu être lue le 2026-11-12. À ajouter après lecture de la source primaire.
- Le classement RSF n'est pas ici : il vient de l'indicateur D5.3 (dernière édition).

## `opinion_cevipof.csv`

Second axe de la tête de page, « ce qu'en pensent les Français » (décision du 2026-11-12) :
résultats du Baromètre de la confiance politique du CEVIPOF (Sciences Po), enquête
OpinionWay en ligne, vague 17, du 12 au 28 janvier 2026, 3 166 inscrits sur les listes
électorales (méthode des quotas ; marge d'incertitude de 0,7 à 1,7 point).
Rapport : https://www.sciencespo.fr/cevipof/sites/sciencespo.fr.cevipof/files/Barometre_confiance_CEVIPOFVague17_fev2026_vd1.pdf
Lu directement par `front/prototype/export_data.py` (pas de fait en base).

- Format long : `indicateur;pays;date;valeur;page;note`, valeur en % de répondants, `page`
  = page du rapport (numérotation du PDF).
- `q22_fonctionne_bien` / `q22_fonctionne_mal` : « Diriez-vous qu'en France la démocratie
  fonctionne très bien, assez bien, pas très bien ou pas bien du tout ? », sous-totaux
  « bien » et « pas bien ». Série de décembre 2009 à janvier 2026 lue sur le graphique de
  la page 34 (étiquettes des points, appariées par couleur de courbe) ; comparaison de cinq
  pays page 35.
- `q55_*` : « Je vais vous décrire différents types de systèmes politiques […] cette façon
  de gouverner le pays serait très bonne, assez bonne, assez mauvaise ou très mauvaise »,
  part « bonne » : système démocratique, homme fort sans parlement ni élections, armée
  (page 93).
- `q56_*` : part « d'accord » avec : « C'est utile de voter… », « La démocratie
  fonctionnerait mieux si les citoyens étaient associés de manière directe… », « En
  démocratie rien n'avance, il vaudrait mieux moins de démocratie mais plus d'efficacité »
  (page 96).
- Droits : rapport © Sciences Po ; seuls quelques chiffres sont repris, cités avec leur
  source (droit de courte citation). Mettre à jour à chaque vague (février) et vérifier
  les valeurs passées, que le CEVIPOF peut réviser.
- **Contrôle** (2026-11-12) : valeurs relues sur le rapport (`pdftotext` et image de la
  page 34).
- L'Eurobaromètre (satisfaction envers le fonctionnement de la démocratie) n'est pas
  repris : son site ne s'affiche qu'en JavaScript et n'a pas pu être lu le 2026-11-12.
