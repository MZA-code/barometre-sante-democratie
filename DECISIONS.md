# Journal des décisions

Choix de conception et réponses aux questions ouvertes du brief (§10).

## 2026-10-26 — Étape 1 (socle)

- **Stack** : celle du brief (Python 3.12, SQLite, pytest, ruff) ; dépendances gérées et
  figées par `uv` (`uv.lock`) pour la reproductibilité.
- **Fenêtres de calcul** : les deux, glissante 365 jours **et** par législature.
- **49.3 répétés sur un même texte** : chaque engagement est un fait distinct. Deux métriques :
  `nb_49_3` (engagements) et `nb_textes_49_3` (textes distincts). Le ratio de contournement
  utilise les textes distincts (« textes adoptés via 49.3 »).
- **Ordonnances ratifiées / non ratifiées** : pas de pondération en v0 ; le statut de
  ratification et le fondement juridique sont conservés dans `facts.attributes`.
- **Schéma** : celui du brief, avec en plus `facts.attributes` (JSON), une clé primaire et une
  clé étrangère sur `score_facts`, des index, et des triggers SQLite qui interdisent
  `UPDATE`/`DELETE` sur `raw_documents` (règle 1).
- **Convention de notation** : 4 bornes par indicateur ; note = nombre de bornes franchies
  dans le sens défini par `direction`. À valider avec la grille méthodologique.

## 2026-10-26 — Étapes 2 et 3 (collecte)

- **Archive brute** (`storage/archive.py`) : `data/raw/<source>/<id externe>/<sha256><ext>`,
  fichiers en lecture seule, avec à côté un `<sha256>.meta.json` (URL, date de collecte,
  empreinte). L'index `raw_documents` se reconstruit depuis ces métadonnées
  (`storage.db reindex`, appelé par `make rebuild`) : la base entière est reproductible
  depuis le seul disque. `make verify-raw` recalcule toutes les empreintes.
- **Doublons** : une version déjà archivée (même source, même identifiant, même SHA-256)
  n'est jamais réécrite ; un contenu modifié devient une nouvelle version.
- **DILA** (`collectors/dila.py`, fonds `legi` et `jorf`) : dump complet le plus récent puis
  incréments postérieurs ; une archive dont le nom est déjà connu n'est jamais
  retéléchargée.
- **Assemblée** (`collectors/an_opendata.py`) : un zip JSON de dossiers législatifs par
  législature. **Constat** : seules les législatures 14 à 17 (depuis juin 2012) sont
  publiées ; les fichiers des 14e et 15e portent un suffixe romain (`_XIV`, `_XV`).
- **Constat** : le zip de la législature en cours change d'empreinte d'un téléchargement à
  l'autre même sans changement visible (régénéré côté serveur) : chaque collecte crée une
  nouvelle version (~11 Mo). Acceptable ; l'extraction ne lit que la dernière version.
- **Réseau** : le bac à sable de Claude Code n'autorise que `echanges.dila.gouv.fr` et
  `data.assemblee-nationale.fr` (`.claude/settings.local.json`, non versionné).

## 2026-10-26 — Étape 4 (extraction)

- **49.3 dans l'open data AN** : acte `DeclarationGouvernement_Type` avec
  `typeDeclaration.fam_code == "Art.49.3"` (détails et contrôles dans
  `extract/parlement.py`). Un même acte figure dans le dossier du texte et dans un dossier
  dédié « Engagement de la responsabilité gouvernementale » : dédoublonnage par `uid`,
  rattachement au dossier du texte (clé `texte_uid` pour compter les textes distincts).
  Contrôle : 6 (L14), 1 (L15), 23 (L16) engagements, conformes aux décomptes publics.
- **Censure** : un engagement suivi d'une motion de censure adoptée (`TSORTMOT01`) est
  marqué `censure_adoptee` ; il compte dans `nb_49_3` mais son texte n'est pas « adopté via
  49.3 ». Un seul cas : 2 décembre 2024 (PLFSS 2025).
- **Seed historique** (`data/seed/49_3_historique.csv`) : 82 engagements de 1959 à 2006,
  transcrits depuis la page officielle de l'Assemblée et contrôlés contre ses totaux par
  Premier ministre (voir `data/seed/README.md`). Une date corrigée et signalée.
  **Constat** : le bilan de la page (116 engagements) n'est pas à jour des derniers
  gouvernements ; 82 (seed) + 38 (open data) = 120.
- **LEGI n'est pas exhaustif** (contrairement à l'hypothèse du brief) : il ne contient que
  les textes consolidés par la DILA (quelques lois par an sous la IVe République, une
  seule loi de ratification en 2015). On ajoute le fonds **JORF**, fusionné avec LEGI par
  identifiant `JORFTEXT` (`extract/dila.py`).
- **Lois** : natures `LOI`, `LOI_ORGANIQUE`, `LOI_CONSTIT`, date = `DATE_TEXTE` (date de
  promulgation). La nature est gardée en attribut pour filtrer plus tard si besoin.
- **Ordonnances** : fondement lu dans les visas (« Vu la Constitution, notamment son
  article 38 ») : `art38`, `art74-1`, `art47`, `art47-1`, `art92` ou `inconnu` quand les
  visas sont vides ou ne citent pas la Constitution (on ne suppose pas l'article 38).
- **Ordonnances non gouvernementales** : la nature `ORDONNANCE` des fonds DILA recouvre
  aussi des ordonnances du premier président de la Cour de cassation, du préfet de police
  et des « Rapport au Président de la République relatif à l'ordonnance ... ». On ne garde
  que les ordonnances **numérotées** (« Ordonnance n° ... ») ; 13 actes écartés depuis
  1958, tous contrôlés à la main. Les textes datés `2999-01-01` (date inconnue) sont
  écartés.
- **Rectificatifs et doublons** : le JO publie les rectificatifs comme des textes
  distincts portant le numéro du texte corrigé (≈ 310 cas depuis 1958, ~4 %). Un acte est
  identifié par (type, numéro officiel) ; la version de référence est la version non
  rectificative de plus petit CID, les autres CID sont gardés dans `cid_doublons` et
  leurs documents bruts sont cités par le fait. Les visas de toutes les versions sont
  réunis pour déterminer le fondement d'une ordonnance.
- **Contrôle de cohérence** : pour les 11 528 titres contenant « n° X du J mois AAAA »,
  numéro et date concordent avec `official_ref` et `occurred_on` dans 11 493 cas ; les
  écarts sont des lois de 1941 (numérotation de Vichy), hors période mesurée.
- **Ordre des faits** : tri (date, type, référence, titre) avant insertion : mêmes
  identifiants à chaque reconstruction.
- **Cache** : l'index des textes de chaque archive DILA est mis en cache dans
  `data/cache/<sha256>.<extracteur>.jsonl` (dérivé, supprimable) pour que `make rebuild`
  ne relise pas plusieurs Go à chaque fois.

## 2026-10-26 — Étapes 5 et 6 (métriques, rapport)

- **Fenêtre glissante** de 365 jours, bornes incluses (J-364 à J), calculée chaque jour
  depuis `history_start + 364` (grille : 1958-12-09, ouverture de la Ire législature).
- **Fenêtre législature** : de l'ouverture d'une législature à la veille de la suivante
  (`config/legislatures.yaml` ; dates des législatures 15 à 17 à vérifier).
- **Fin des données** : veille de la plus ancienne des dernières collectes AN / JORF /
  LEGI, pour ne pas mesurer une période non couverte.
- **`computed_at`** = horodatage de l'état de l'archive (dernière collecte), pas l'heure
  du calcul : deux `make rebuild` donnent une base identique (`make reproducible`
  compare les empreintes des tables dérivées).
- **`ratio_contournement`** (formule initiale, remplacée plus bas) = (`nb_textes_adoptes_49_3` + `nb_ordonnances`) /
  (`nb_lois` + `nb_ordonnances`) ; non produit si le dénominateur est nul.
- **Schéma** : `metrics`, `scores` et `score_facts` ont une colonne `window_id` dans leur
  clé (une même date a une valeur glissante et une valeur par législature).
- **Rapports** : `make controle DATE=...` (valeurs + faits + liens + documents bruts) et
  `make echantillon` (20 faits tirés avec une graine fixe, à cocher à la main).

## 2026-10-26 — Réponses du porteur de projet (après l'étape 6)

- **Lois autorisant un engagement international** (ratification, approbation, adhésion...) :
  **exclues** du dénominateur du ratio. Repérées par leur titre (`extract/dila.py`,
  `is_convention_internationale`) : formulations sûres (« autorisant la ratification /
  l'approbation ... ») plus formulations larges avec exclusion des accords internes
  (interprofessionnel, accord local, concession, conventions État–collectivité). Environ
  un tiers des lois depuis 1958. Attribut `convention_internationale` sur chaque loi, à
  auditer par le comité ; `nb_lois` reste publié à titre d'information.
- **Ordonnances** : **seules celles de l'article 38** entrent dans le ratio ;
  `nb_ordonnances` (tous fondements) reste publié à titre d'information.
- **Échelle** : 4 = niveau le plus préoccupant (« alerte »). Libellés à rédiger par le
  comité (`scale.labels` dans la grille).
- **Formule du ratio** : désormais écrite dans la grille (`ratios`), le code ne fait que
  sommer les métriques désignées. La grille v0, encore en brouillon et sans note produite,
  a été complétée plutôt que versionnée (entrée dans `CHANGELOG-GRILLE.md`).

## 2026-10-26 — D3.1 régimes d'exception et D4.1 dissolutions administratives

- **Lecture des archives étendue** (`extract/dila.py`, cache `dila_textes_2`) : en plus des
  lois et ordonnances, les décrets et décisions dont le titre relève de D3 ou D4 sont
  indexés, avec leurs visas.
- **D4.1** (`extract/libertes.py`) : un décret de dissolution est administratif si ses visas
  citent la loi du 10 janvier 1936, l'article L. 212-1 du code de la sécurité intérieure ou
  l'article L. 332-18 du code du sport ; à défaut de visas, si son titre vise une
  association, un groupement ou un mouvement de fait. Exclus : dissolutions volontaires
  approuvées (utilité publique, cultuelles), conseils municipaux, établissements publics.
  77 décrets. **Constat** : avant 1990 le JORF indexe certaines dissolutions sous des titres
  opaques (« ASSOCIATIONS DIVERSES, SIEGE SOCIAL ... », par exemple le 12 juin 1968) : la
  série démarre en 1990 (`history_start`). Un décret peut dissoudre plusieurs groupements :
  on compte des décrets.
- **D3.1** (`extract/exception.py`, `data/seed/regimes_exception.csv`) : les bornes des
  périodes sont dans le corps des articles, pas dans les titres. 20 périodes relevées à la
  main dans les articles archivés, chacune avec la phrase qui fixe ses dates ; 11 marquées
  `a_verifier` (textes de 1958, 1961 et 1985 sans corps dans l'archive, décrets de levée de
  2006 et 2024 absents, prorogations outre-mer de 2021-2022 à confirmer). Contrôle
  automatique : les 32 textes de l'archive qui déclarent, prorogent ou lèvent un régime
  d'exception sont tous cités par une période.
- **Métriques additives** (`scoring/metrics.py`) : `nb_dissolutions` (compte de faits) et
  `jours_exception` / `jours_exception_metropole` (jours couverts, chevauchements comptés
  une fois, période en cours étendue jusqu'à la fin des données).

## 2026-11-05 — Source data.gouv.fr

- **Pourquoi** : le catalogue public-apis (github.com/public-apis/public-apis) a été passé en
  revue ; pour la France, seule l'entrée data.gouv.fr est une source officielle utilisable.
  Les API d'actualités du catalogue (clé, licence restrictive, archivage interdit) sont
  incompatibles avec les règles 1 et 6 ; Wikidata et Wikipedia ne servent qu'au recoupement.
- **Collecteur générique** (`collectors/datagouv.py`) : les jeux sont listés dans
  `config/datagouv.yaml` (identifiant stable, filtres sur le titre et le format, taille
  maximale). Ajouter un jeu ne demande aucun code.
- **Fiche du jeu archivée à chaque collecte** (JSON de l'API, tel quel) : elle prouve la
  licence et la liste des ressources à la date de collecte. Elle contient des compteurs de
  visites : une nouvelle version (quelques dizaines de Ko) est donc créée presque à chaque
  collecte. Accepté.
- **Pas de retéléchargement** : data.gouv.fr publie chaque fichier sous une URL horodatée ;
  une URL déjà archivée pour la même ressource est sautée. Le SHA-1 annoncé par data.gouv.fr
  est contrôlé, un écart est signalé sans bloquer (le fichier reste archivé tel que reçu).
- **Licences** : seules les licences ouvertes listées dans la config sont acceptées. Un jeu
  hors liste exige une `licence_derogation` écrite. **Constat** : les résultats du 2nd tour
  des législatives 2022 sont déclarés « notspecified » alors que le 1er tour (même
  producteur) est sous Licence Ouverte ; admis par dérogation, à confirmer.
- **Premiers jeux** : avis et conseils de la CADA (fichier consolidé, tout l'historique,
  ≈ 200 Mo, republié sous une nouvelle URL à chaque mise à jour) ; résultats « France
  entière » des législatives 2017, 2022 et 2024, deux tours. Aucun indicateur n'en est
  encore tiré : collecte et archive seulement, en attendant la décision du comité.
- **Constat** : le 1er tour 2024 ne publie le niveau France entière qu'en xlsx, sous deux
  ressources de même titre et de même contenu (archivées toutes deux).
- **Environnement** : le projet a été déplacé de `demo/` vers `barometre/` ; `.venv`
  reconstruit avec `uv sync --frozen` (les scripts pointaient vers l'ancien chemin).

## 2026-11-05 — D3.2 lois censurées par le Conseil constitutionnel

- **Source** : fonds DILA CONSTIT (`collectors/dila.py --fund constit`, même stratégie que
  LEGI et JORF : dump complet du 13 juillet 2025 puis incréments). 7 423 décisions, toutes
  natures. `dila_constit` rejoint les sources qui bornent la fin des données.
- **Extraction** (`extract/constit.py`) : seules les métadonnées sont lues (NATURE, NUMERO,
  DATE_DEC, TITRE, SOLUTION). Le corps des décisions, qui nomme des personnes, n'est pas
  utilisé (règle 5).
- **Périmètre** : décisions DC portant sur une loi (805), repérées par le titre (« Loi… »,
  « Lois organiques… », « Troisième loi de finances… »). Exclus : règlements des assemblées,
  traités et engagements internationaux, révision constitutionnelle de 2003, demandes de
  récusation. Les QPC (1 099) sont extraites en contexte, hors ratio.
- **Censure** : SOLUTION commençant par « Non conformité » (partielle ou totale, avec ou
  sans réserve ni effet différé). Les décisions sans examen au fond (irrecevabilité,
  incompétence, rejet, non-lieu) sont gardées comme faits mais n'entrent pas dans les
  comptes.
- **Doublons** : 33 numéros DC ont deux fiches (rééditions qui ajoutent « réserve » à la
  solution) ; le statut de censure ne diverge jamais. On garde la fiche au plus grand
  identifiant ; les deux sont citées dans `constext_doublons`.
- **On compte des décisions** : une décision qui juge deux lois (77-80/81 DC) compte une fois.
- **Deux ratios** : `ratio_censure` (toutes lois, noté si le comité le décide) et
  `ratio_censure_lois_ordinaires` (hors lois organiques, transmises d'office et non
  déférées par choix). Choix du ratio noté : question pour le comité.
- **Prototype** : la position de la carte D3.2 est comparée aux mois observés depuis 1975
  (après la réforme du 29 octobre 1974, petits effectifs avant) ; dans le graphique par
  législature, les législatures de moins de 10 lois jugées sont tracées en contour.

## 2026-11-05 — Collecte quotidienne planifiée

- **Planification locale** : l'archive brute (≈ 7 Go) n'existe que sur le poste ; une tâche
  dans le cloud ou dans la CI n'y aurait pas accès. Timer systemd **utilisateur** (aucun
  droit administrateur) : `make planifier` l'installe, `make deplanifier` le retire,
  `make etat` affiche la dernière exécution.
- **Horaire** : 6 h 30 (± 15 min), après les incréments DILA publiés vers 21 h.
  `Persistent=true` : un passage manqué (poste éteint) est rattrapé au démarrage suivant.
  Sans « linger » systemd, le timer ne tourne que pendant une session ouverte.
- **Exécution** (`ops/quotidien.py`) : chaque collecte est une étape séparée ; un échec
  n'arrête ni les autres collectes ni la reconstruction. Puis `rebuild` et export des
  données du prototype ; le dimanche, `verify-raw` recontrôle toute l'archive. Verrou
  contre deux exécutions simultanées. Journal du jour dans `data/logs/`, historique
  `data/logs/quotidien.jsonl`, état courant `data/exports/etat_quotidien.json`.
- **Assemblée, législature en cours seulement** en quotidien (les précédentes sont closes ;
  `make collect` les recharge toutes).
- **Constat et correction** : le zip de l'Assemblée est régénéré par le serveur avec des
  horodatages internes différents, sans changement de contenu (vérifié : deux versions
  archivées les 26 octobre et 5 novembre avaient les mêmes 10 863 fichiers). En quotidien,
  cela aurait ajouté ≈ 4 Go par an de copies identiques. Le collecteur compare désormais
  le contenu des fichiers du zip à la dernière version archivée et n'archive que s'il
  diffère. Le fichier archivé reste l'original reçu, octet pour octet (règle 1).
- **Alerte** : une étape en échec ou une erreur inattendue déclenche une notification de
  bureau (`notify-send`, urgence critique) qui nomme les étapes et le journal. Vérifié
  depuis le contexte systemd. Une notification impossible (pas de session graphique)
  n'interrompt jamais l'exécution. Une exécution sautée parce qu'une autre tournait
  (code 2) n'est pas un échec.

## 2026-11-05 — D2.2 procédure accélérée

- **Source** : open data de l'Assemblée (déjà archivé pour le 49.3). Engagement = acte
  `ProcedureAccelere_Type` (code `...-PROCACC`) ; texte adopté = acte `Promulgation_Type`,
  qui porte le numéro de la loi. Profondeur : depuis le 20 juin 2012 seulement ; pas de
  seed historique pour l'instant (l'« urgence » d'avant 2008 n'est pas couverte).
- **Unité** : la loi promulguée, dédoublonnée par numéro (238 dossiers figurent dans deux
  législatures). Une loi est « accélérée » si l'un de ses dossiers contient l'engagement.
- **Rapprochement avec le JORF par numéro de loi** : la date du fait est la date de
  promulgation lue au JORF. **Constats** : les 1 020 lois de l'open data AN figurent toutes
  dans le JORF ; le NOR publié par l'Assemblée ne permet pas le rapprochement (629 échecs
  sur 2016-2026) ; une date de promulgation de l'Assemblée est aberrante (« 0021-02-24 »
  pour la loi 2021-191), corrigée par le JORF.
- **Ratio** : lois accélérées / lois dont l'Assemblée publie le dossier, hors lois
  autorisant un engagement international (comme D2) et lois constitutionnelles (la
  procédure accélérée ne s'y applique pas). Les lois de finances restent dans le
  dénominateur (calendrier propre, article 47) : question pour le comité.
- **Couverture rendue visible** : faits `loi_sans_dossier_an` pour les lois du JORF
  promulguées depuis le 20 juin 2012 sans dossier à l'Assemblée. Hors traités : 16 sous la
  XIVe législature (surtout 2012-2013, textes déposés sous la XIIIe), 6 sous la XVe, 1 sous
  la XVIe. Elles ne sont pas dans le ratio et sont affichées à part.
- **Résultat** : 74 % (XIVe), 71 % (XVe), 71 % (XVIe), 64 % (XVIIe, en cours) ; 63 % sur les
  douze derniers mois au 4 novembre 2026.
- **Prototype** : carte D2.2 comparée aux mois observés depuis 2016 (couverture complète),
  une tuile par législature, lois des douze derniers mois. Défaut connu, antérieur : quand
  on rétrécit la fenêtre après chargement, le cadran du haut garde sa largeur et la page
  déborde (pas au chargement direct en largeur mobile).

## 2026-11-05 — Participation aux élections législatives (contexte)

- **Hors grille** : donnée de contexte, sans note ni seuil. Faits `scrutin_participation`,
  indicateur `contexte.participation_legislatives` (absent de `config/grid.v0.yaml`, donc
  ignoré par les métriques et le scoring).
- **Source** : jeux du ministère de l'Intérieur déjà archivés depuis data.gouv.fr ; la date
  et le tour de chaque scrutin sont déclarés dans `config/datagouv.yaml` (clé `scrutin`).
- **Lecture** (`extract/elections.py`) : trois formats (xlsx libellé/valeur en 2017, texte
  Windows-1252 en 2022, xlsx et CSV en 2024), lus avec la bibliothèque standard et
  `defusedxml` (pas de nouvelle dépendance). Seules six colonnes sont lues : inscrits,
  votants, abstentions, blancs, nuls, exprimés. Les colonnes de nuances et de voix ne le
  sont jamais (règle 5).
- **Contrôles** : votants = blancs + nuls + exprimés et inscrits = votants + abstentions,
  sinon l'extraction échoue. Deux ressources d'un même tour qui se contrediraient font
  aussi échouer l'extraction.
- **Taux de référence = 1er tour** : au 2nd tour, les inscrits ne couvrent que les
  circonscriptions où il a lieu (43,3 millions en 2024 contre 49,3 au 1er tour).
- **Résultats**, conformes aux chiffres officiels publiés : 48,70 % / 42,64 % (2017),
  47,51 % / 46,23 % (2022), 66,71 % / 66,63 % (2024).
- **Profondeur** : 2017 seulement ; les résultats agrégés de 2002, 2007 et 2012 ne sont pas
  publiés sous la même forme sur data.gouv.fr (seulement par bureau de vote ou listes de
  candidats). Un seed manuel depuis les résultats officiels serait nécessaire.

## 2026-11-05 — Open data du Sénat (Dosleg) et D2.2 depuis 1978

- **Source** (`collectors/senat.py`) : `dosleg.zip` de data.senat.fr, dump PostgreSQL de la
  base des dossiers législatifs (≈ 16 Mo compressé, 127 Mo de SQL). Licence de data.senat.fr,
  qui reprend la Licence Ouverte. Les CSV publiés à côté (`promulguees.csv`...) ne
  contiennent pas la procédure suivie : seul le dump l'a.
- **Collecte hebdomadaire** (le dimanche, dans `ops/quotidien.py`) : le dump est régénéré
  chaque nuit et son contenu change presque chaque jour ; en quotidien, ≈ 6 Go par an. Une
  version n'est archivée que si son contenu a changé (le dump n'a pas d'horodatage). La
  comparaison de contenu des zip est désormais commune (`storage/archive.py`,
  `store_if_content_changed`), utilisée aussi pour l'Assemblée.
- **Lecture** (`extract/senat.py`) : seul le bloc `COPY loi` est lu, ligne par ligne dans le
  zip (0,3 s). Colonnes : numéro de loi, date de promulgation, type de texte, `urgence`
  (oui / non / dro), dates d'engagement et de retrait de la procédure accélérée.
- **Constats** :
  - le Sénat couvre presque toutes les lois depuis 1978 (921 sur 924 dans les années 1980) ;
  - sur 2012-2026, l'Assemblée et le Sénat concordent pour 997 lois sur 1 019 ; les écarts
    portent sur les lois de finances et de financement (l'Assemblée y enregistre une
    procédure accélérée, le Sénat les classe en urgence « de droit » ou n'enregistre rien),
    sur un retrait de procédure (loi 2013-702, engagée le 16 avril 2013, retirée le 19, que
    seul le Sénat enregistre) et sur la loi spéciale 2025-1316 (engagement enregistré au
    Sénat le 23 décembre 2025, absent du dossier de l'Assemblée) ;
  - le Sénat laisse le champ urgence vide pour une partie des lois de 1998 à 2008 (48 sous
    la XIe législature, 37 sous la XIIe, hors lois exclues).
- **D2.2 redéfini, avant tout gel** :
  - statut « accélérée » si l'une des deux sources enregistre l'engagement, sauf retrait
    enregistré par le Sénat : un engagement enregistré est une preuve positive, son absence
    dans l'autre source peut n'être qu'une lacune (cas de la loi 2025-1316) ;
  - statut « inconnu » si aucune source ne le donne : compté à part
    (`nb_lois_statut_inconnu`), jamais deviné ; le prototype trace en contour les
    législatures où il dépasse 10 % des lois ;
  - lois de finances et de financement de la sécurité sociale (y compris lois de règlement,
    rectificatives et loi spéciale de l'article 45 de la LOLF) exclues : leur calendrier est
    fixé par les articles 47 et 47-1 de la Constitution, le Sénat les classe en urgence « de
    droit », et ce sont elles qui expliquaient presque tous les écarts entre les sources.
    Cela tranche la question laissée au comité plus tôt dans la journée ; le comité peut
    revenir dessus ;
  - historique depuis le 3 avril 1978 (VIe législature) au lieu du 20 juin 2012.
- **Résultat** : 23 % (VIe), 32 % (VIIe), 39 % (VIIIe), 35 % (IXe), 23 % (Xe), 39 % (XIe),
  35 % (XIIe), 46 % (XIIIe), 67 % (XIVe), 75 % (XVe), 77 % (XVIe), 67 % (XVIIe en cours) ;
  66 % sur les douze derniers mois au 4 novembre 2026. Avant 2008, il s'agit de la
  déclaration d'urgence, dont les effets étaient comparables (une lecture par assemblée
  avant la commission mixte paritaire) : la série reste lisible d'un bout à l'autre, mais
  la révision de 2008 est un changement de règle à signaler au lecteur.

## 2026-11-05 — Veille des manifestations : interdictions contestées devant le juge

- **Choix de la source** (décision du porteur de projet) : aucune source ouverte ne donne le
  nombre de manifestations, de manifestants ou de blessés. GDELT (événements codés
  automatiquement depuis la presse) a été testé sur le 3 novembre 2026 : 31 « manifestations »
  localisées en France, surtout depuis la presse étrangère, plusieurs sans rapport (puce
  électronique, contrats de défense, tribune sur la peine de mort), plus de la moitié
  localisées « France » sans précision. Écarté comme source de faits. ACLED n'est pas
  joignable depuis le poste. Retenu : les décisions de la justice administrative sur les
  interdictions de manifester, en données ouvertes.
- **Statut** : approximation automatique de l'indicateur D4.2 du document de grille, qui
  porte sur les arrêtés d'interdiction eux-mêmes (recueils des actes administratifs des
  préfectures, semi-manuel), encore à construire. Identifiant distinct
  (`D4.interdictions_manifester_juge`), affiché « D4.2* » dans le prototype.
- **Source** (`collectors/justice_admin.py`) : opendata.justice-administrative.fr, une archive
  zip par juridiction et par mois ; Conseil d'État depuis juin 2021 (≈ 2,6 Mo par mois),
  tribunaux administratifs depuis juin 2022 (≈ 75 Mo par mois) ; 117 archives, 3,6 Go au
  5 novembre 2026. Licence Ouverte 2.0 et CGU (ne pas dénaturer, ne pas réidentifier). Les
  cours d'appel ne sont pas collectées (l'appel d'un référé-liberté va au Conseil d'État).
  **Seuls les mois terminés** sont archivés, une fois chacun : l'archive du mois en cours
  grossit chaque jour (≈ 27 Go par an en quotidien). Constat : les archives passées sont
  régénérées de temps en temps (décisions de mars 2023 datées de septembre 2026) ; elles ne
  sont pas retéléchargées.
- **Sélection** (`extract/manifestations.py`) : décision qui cite l'article L. 211-4 du code
  de la sécurité intérieure (« sécurité intérieure » à proximité : l'article L. 211-4
  existe dans d'autres codes), ou dont l'exposé des demandes (3 000 premiers caractères)
  contient une phrase associant interdiction, manifestation (ou cortège, défilé) et
  autorité (arrêté, préfet, maire, décision). Mise au point sur mars 2023 (tribunaux) et
  octobre 2026 (Conseil d'État) : un critère plus étroit (formules « portant interdiction de
  la manifestation ») manquait « l'arrêté par lequel le préfet de police a interdit la
  manifestation » ; un critère plus large prenait des dossiers d'étrangers ou
  d'indemnisation mentionnant une manifestation. Les interdictions de **réunions
  publiques** ne sont pas retenues.
- **Précision** contrôlée sur 25 décisions tirées au hasard (graine 20261105) : toutes
  portent sur une restriction du droit de manifester ou de se rassembler sur la voie
  publique ; deux ou trois visent des interdictions de rassemblement ou d'attroupement
  plutôt qu'une manifestation au sens strict (gardées). **Rappel non mesuré** : à vérifier
  par un humain sur un mois connu.
- **Seules les métadonnées** sont conservées (juridiction, numéro, date, type de recours,
  solution, formation) ; le texte n'est ni stocké dans la base ni publié. Cache de lecture
  par archive (`data/cache/<sha>.justice_manif_1.jsonl`) : premier passage ≈ 1 minute.
- **Unité : la décision.** Une interdiction peut produire plusieurs décisions (plusieurs
  requérants, appel au Conseil d'État) : ce n'est pas un nombre d'arrêtés. Issue lue dans
  la solution : « satisfaction » totale ou partielle, annulation, suspension -> favorable au
  requérant ; « rejet » -> rejet ; non-lieux, désistements et autres hors du ratio.
- **Résultat** : 771 décisions (77 du Conseil d'État, 609 en référé) ; depuis le 3e trimestre
  2022, le juge a suspendu ou annulé l'interdiction dans 34 % des décisions tranchées.
  **Constat** : 162 décisions en octobre 2026, réparties sur une vingtaine de tribunaux et
  concentrées les 23 et 24 octobre (pic réel, pas un doublon technique).
- **Collecte** : chaque jour dans `ops/quotidien.py` (les pages d'index seulement, un
  téléchargement par mois et par juridiction quand un mois se termine).
- **Prototype** : décisions par trimestre depuis le 3e trimestre 2022 (premier trimestre
  couvert par les deux sources), trimestre en cours signalé ; carte « D4.2* ».

## 2026-11-05 — Seed manuel des journées de mobilisation (contexte)

- **Statut** : donnée de contexte, hors grille (`contexte.mobilisations`), conforme à la ligne
  « Manifestations et manifestants » du document de grille : chiffres de la police et des
  organisateurs affichés côte à côte, aucun n'étant retenu comme vrai.
- **Pilote borné** : les 14 journées nationales du mouvement contre la réforme des retraites
  de 2023, France entière. Aucun chiffre n'a été écrit de mémoire.
- **Méthode** (détail dans `data/seed/README.md`) : relevé du tableau d'une révision datée de
  Wikipédia (simple point d'entrée vers les articles), puis téléchargement de chaque article
  cité et recherche automatique du chiffre dans son texte ; à défaut, recherche d'un autre
  article en accès libre rapportant le même chiffre, contrôlé de la même façon.
- **Règle respectée** : aucun mur payant contourné. Une tentative de passer par les copies
  d'archive (Wayback Machine) d'articles payants a été refusée par l'environnement ; elle
  n'a pas été contournée. Les accès refusés aux robots (Europe 1, Le Point) n'ont pas été
  contournés non plus.
- **Résultat** : 28 chiffres, 21 retrouvés dans leur source (ministère 11 sur 14,
  organisateurs 10 sur 14) ; les 7 autres portent `controle` = « non vérifié » et sont
  signalés par un « ? » dans le prototype. Toutes les lignes restent `a_verifier = oui`.
- **Non relevés** : chiffres de Paris, forces de l'ordre blessées, interpellations (rapportés
  par la presse mais pas encore contrôlés), autres mouvements.
- **Prototype** : graphique en haltères (point plein ministère, point creux organisateurs,
  reliés par un trait) ; infobulle avec la source de chaque chiffre ; clic = ouvre la source.

## 2026-11-05 — Seed des mobilisations étendu au projet de réforme des retraites 2019-2020

- **Même méthode** que pour 2023 : relevé du tableau de l'article Wikipédia (révision
  241027655 du 4 novembre 2026), téléchargement des articles cités, recherche automatique du
  chiffre ; à défaut, source de remplacement en accès libre contrôlée de la même façon.
- **10 journées, 17 chiffres** : la CGT n'a pas donné d'estimation nationale pour les
  29 janvier, 6 et 20 février 2020. **14 retrouvés dans leur source.** Beaucoup d'articles
  cités ont disparu (La Provence, Le Figaro : 404) ; remplacés par Public Sénat, Maire-info.
- **Non vérifiés** : 10 décembre 2019 (ministère 339 000 : Universalis donne seulement
  « près de trois cent quarante mille » ; CGT 885 000 : retrouvé dans aucune source
  accessible) et 6 février 2020 (ministère 121 000 : article cité disparu, seule source de
  remplacement trouvée chez Europe 1, qui refuse les accès automatisés). Signalés dans la
  colonne `note` et par un « ? » dans le prototype.
- **Prototype** : les mouvements sont séparés par un espace et titrés ; les dates de l'axe
  sont espacées selon la place disponible.

## 2026-11-05 — Seed des mobilisations étendu à la loi Travail 2016

- **Pas de tableau** dans l'article Wikipédia de 2016 (révision 240493497) : les couples de
  chiffres nationaux ont été relevés à la main dans le texte (12 journées, du 9 mars au
  15 septembre 2016), avec les références du même passage. Les journées où l'article ne
  donne que Paris (9 avril, 12 mai) ne sont pas retenues.
- **Contrôle renforcé** : l'attribution étant souvent implicite dans le texte (« entre
  224 000 et 500 000 personnes »), le nombre doit figurer dans la source à moins de 250
  caractères d'une mention de qui l'a compté. Le nombre ne doit pas être la fin d'un nombre
  plus grand (« 70 000 » dans « 170 000 »).
- **Format du seed modifié** : le compteur `organisateurs_cgt` devient `organisateurs`, avec
  une colonne `compte_par` (CGT, Unef, FO, intersyndicale, « syndicats » si la source ne
  précise pas). Les lignes 2019-2020 et 2023 sont migrées avec `compte_par = CGT`, ce
  qu'indiquent leurs sources. Pour 2016, `compte_par` est l'organisateur nommé au plus près
  du chiffre dans la source (une première version, qui prenait le premier nom d'une liste,
  attribuait à tort le 9 mars à l'Unef) : identification automatique, signalée dans `note`.
- **Résultat** : 22 chiffres sur 24 retrouvés avec leur attribution. Wikipédia se contredit
  sur le 19 mai (400 000 et 200 000 selon les syndicats) : la source donne 400 000 selon la
  CGT. Le 17 mars, le chiffre des organisateurs est celui de l'Unef. Non vérifié : le
  5 juillet (articles payants ; RTBF donne 30 000 « selon la préfecture » au niveau national
  et ne connaît aucun total syndical national ; le chiffre de 100 000 n'a été retrouvé dans
  aucune source accessible).
- **Prototype** : titres de mouvement raccourcis (ils se chevauchaient) ; la liste des
  mouvements couverts est calculée depuis les données.

## 2026-11-05 — D6.2 fichiers créés malgré les réserves de la CNIL

- **Sources** : fonds CNIL de la DILA (`collectors/dila.py --fund cnil`, quotidien ; 26 895
  délibérations) pour les avis ; fonds JORF et LEGI déjà archivés pour les décrets. Lecture
  dédiée des décrets dont les visas citent la CNIL (`extract/cnil.py`, cache
  `dila_decrets_cnil_1`, ≈ 9 minutes au premier passage, 998 décrets distincts) : le cache
  des autres indicateurs ne conservait pas leurs visas.
- **Avis retenus** : délibérations dont le titre porte « avis sur un projet de décret »
  (642 depuis 1983).
- **Réserve : critère strict.** Seules comptent les formules par lesquelles la CNIL qualifie
  son avis (« avis défavorable », « avis favorable sous réserve(s) », « émet / exprime des
  réserves ») : 32 avis. Les formules d'observation (« regrette », « demande que ») ne
  comptent pas. Contrôle : les 5 mentions de « avis défavorable » trouvées dans les avis
  désignent toutes les avis que l'administration rendra dans les procédures créées (« aucun
  avis défavorable ne soit pris sur le seul fondement d'un fichier »), pas un avis de la
  CNIL : le critère strict les écarte, un mot-clé les aurait comptés. **Constat** : depuis
  2018 (RGPD), la CNIL ne qualifie presque plus ses avis ; l'indicateur doit se lire avec
  cette rupture de rédaction.
- **Rapprochement avis -> décret publié**, trois méthodes : numéro de délibération cité
  dans les visas (65 décrets) ; date de l'avis citée quand un seul avis sur projet de décret
  porte cette date (321) ; plusieurs avis le même jour : titre le plus proche (indice de
  Jaccard sur les mots significatifs, années et numéros exclus, >= 0,15 avec 0,08 d'avance ;
  250). 519 avis sur 642 retrouvés dans un décret publié.
- **Confiance** : la relecture des 24 décrets publiés malgré des réserves a montré des
  rapprochements faux par date seule (décret de 1991 sur les données fiscales rapproché de
  l'avis sur le fichier du terrorisme ; décret « Aqua-SISE » rapproché d'un avis sur le
  fichier du renseignement pénitentiaire, dont le seul « mot » commun était l'année 2023).
  Un rapprochement par date seule est donc de confiance faible si les titres n'ont pas de
  mot commun (similarité < 0,10) ; il n'est pas compté dans la métrique notée et apparaît
  « à vérifier ». Des titres sans mot commun peuvent pourtant désigner le même objet
  (« réquisitions télématiques » / « mise à disposition de données par voie
  électronique ») : ces cas relèvent de la vérification humaine.
- **Résultat** : 514 décrets rapprochés avec une confiance forte, dont **12 publiés après un
  avis contenant des réserves formelles** (1990-2022) ; 12 autres à vérifier, parmi lesquels
  les décrets modifiant le décret n° 2007-914 (fichiers de renseignement dispensés de
  publication), plausibles mais non démontrés.
- **Prototype** : décrets par année (après avis réservé / autres), liste des décrets publiés
  malgré des réserves avec la formule et la confiance du rapprochement ; carte D6.2.

## 2026-11-05 — D5.1 temps de parole de l'exécutif

- **Source** : relevés mensuels de l'Arcom hors période électorale. Les fichiers CSV ne sont
  publiés que depuis janvier 2025 (20 mois au 5 novembre 2026, jusqu'à août 2026 : un mois
  paraît ≈ 3 mois après sa diffusion). Leur liste est intégrée à la configuration Drupal des
  pages `/temps-parole/hors-elections/recherche/source/<année>` (`collectors/arcom.py`,
  quotidien). Seul le fichier « 1T2T » est archivé. Les jeux de data.gouv.fr ne couvrent que
  les périodes électorales. Le moteur de recherche de l'Arcom remonte à 2000 mais ne donne
  pas de fichiers ; l'interroger page par page reste une piste, non engagée.
- **Licence** : informations publiques ; mentions légales de l'Arcom : utilisation libre sans
  présenter la reproduction comme engageant l'Arcom ni comme garantie par elle.
- **Mesure** (`extract/arcom.py`) : uniquement les agrégats calculés par l'Arcom, « Total
  Pouvoir exécutif » (Gouvernement + propos du Président relevant du débat politique
  national, règle de l'Arcom) et « Total Partis politiques », sommés sur toutes les chaînes,
  radios et types d'émission. Les lignes par parti ne sont pas lues (règle 5). Contrôle :
  chaque colonne doit reproduire la part publiée par l'Arcom à 0,1 point près (vérifié sur
  les 20 fichiers).
- **Fenêtre** : secondes additionnées sur les mois relevés de la fenêtre (pondération par le
  volume de chaque mois) ; `nb_mois_temps_parole` indique combien de mois sont couverts,
  puisque les derniers mois manquent toujours. L'Arcom n'est pas une source qui borne la fin
  des données (sinon tous les indicateurs auraient trois mois de retard).
- **Résultat** : part mensuelle de 14,5 % (septembre 2025) à 37,1 % (décembre 2025) ; 29 % sur
  les douze derniers mois. Aucune référence normative n'est tracée : un seuil relève du
  comité.

## 2026-11-05 — D5.3 classement RSF et D6.1 techniques de renseignement

- **D5.3** (`collectors/rsf.py`, `extract/rsf.py`) : RSF publie un CSV par édition
  (`rsf.org/sites/default/files/import_classement/<année>.csv`), 2002 à 2026 sauf 2011
  (édition « 2011-2012 » publiée en 2012). Encodages variables (UTF-8 jusqu'en 2024,
  Windows-1252 en 2025-2026) et en-têtes variables (« Rank N » / « Rank »). **Le rang est
  suivi**, pas le score : échelle inversée jusqu'en 2012 (convertie dans les fichiers à
  partir de 2013), nouvelle méthodologie en 2022 ; la période du score est conservée en
  attribut. Le nombre de pays classés (139 en 2002, 180 depuis 2014) est conservé. Date
  conventionnelle du fait : 1er janvier de l'année d'édition (date réelle de publication
  non relevée). La France : 11e en 2002, 44e en 2010, 21e en 2024, 25e en 2025 et 2026.
- **D6.1** (`collectors/cnctr.py`, seed `cnctr_surveillance.csv`, `extract/cnctr.py`) : les
  11 rapports d'activité de la CNCTR sont archivés en PDF ; les chiffres annuels sont relevés
  à la main puis retrouvés automatiquement dans le texte du rapport archivé (10 années sur
  10). Métrique : personnes ayant fait l'objet d'au moins une technique de renseignement
  dans l'année (indicateur que la CNCTR calcule de façon constante depuis 2016) : de 20 360
  (2016) à 25 332 (2025), avec un creux à 20 958 en 2022. Les demandes de techniques ne sont
  relevées que depuis 2023 (total unique publié à partir de cette année : 94 902, 98 883,
  100 813). Le premier rapport (octobre 2015 à octobre 2016, 20 282 personnes) n'est pas
  retenu : période décalée ; la série prend l'année civile 2016 publiée dans le rapport 2017.
- **Prototype** : cartes D5.3 et D6.1 ; section « séries annuelles » avec le rang RSF (axe
  inversé, 1 en haut) et les personnes surveillées par année.

## 2026-11-05 — D1.1 règles électorales modifiées avant un scrutin, D1.2 scrutins reportés

- **Calendrier des scrutins** (`extract/scrutins.py`, cache `dila_scrutins_4`, ≈ 9 minutes au
  premier passage) : tiré des décrets de convocation du JORF, sans seed manuel. Date du premier
  tour lue dans l'article de convocation (« Les électeurs sont convoqués le dimanche 9 juin
  2024 ») ou dans le résumé du décret (champ SM, textes anciens). Formules reconnues :
  « convocation des électeurs », « des collèges électoraux » (législatives anciennes),
  décret « décidant de soumettre un projet de loi au référendum » (« sera soumis au
  référendum le … »). Élections partielles écartées (« élection de députés », « du député de
  la 6e circonscription », décrets « annulant la convocation »). Décrets d'un même scrutin
  (outre-mer convoqué la veille) regroupés. **Couverture** : présidentielles depuis 1981,
  législatives générales depuis 1993, européennes depuis 1994, référendums de 2000 et 2005 ;
  les décrets de convocation antérieurs manquent en partie au JORF archivé (référendum de
  1992, législatives de 1981 à 1988, européennes de 1979 à 1989) : D1.1 commence en 1993.
- **D1.1** : seuls les lois, lois organiques et ordonnances sont retenus (article 34 de la
  Constitution : le régime électoral des assemblées relève de la loi). Une première version
  comptait les décrets ; ils se sont révélés être presque tous des textes d'organisation pris
  avant chaque scrutin (composition de la commission de propagande des européennes, décrets
  d'application de l'élection présidentielle), dont le titre recopie celui de la loi
  appliquée. Catégories lues dans le titre : mode de scrutin, découpage, calendrier. Un texte
  peut viser plusieurs types de scrutin (« élection des députés et sénateurs ») : il compte si
  le scrutin suivant de l'un d'eux a lieu moins de 365 jours après sa publication. **Résultat**
  depuis 1993 : 14 lois électorales nationales, dont 3 publiées moins d'un an avant un scrutin
  visé (loi organique de janvier 1995 sur l'élection présidentielle, 93 jours avant ; loi
  organique de 2016 de modernisation des règles de l'élection présidentielle, 362 jours ; loi de
  2018 sur l'élection des représentants au Parlement européen, 334 jours).
- **D1.2** : report ou prorogation (« report », « reportant », « prorogeant / prolongeant la
  durée du mandat », « modifiant le calendrier électoral ») visant une **élection politique**.
  La première version comptait 147 textes : presque tous des prorogations de mandats de
  conseils d'administration, d'ordres professionnels ou de commissions consultatives. Le filtre
  de lecture a dû être élargi (« renouvellement », conseils élus, congrès, assemblées de
  province) : le titre de la loi n° 2021-191 (report des départementales et régionales) ne
  contient ni « élection » ni « mandat ». Décrets d'application exclus (leur titre recopie
  celui de la loi). « Modifiant le calendrier électoral » peut avancer comme reculer un scrutin :
  signalé « à vérifier ». **Résultat** : 16 textes depuis 1990 (report des municipales et
  cantonales de 2007 à 2008, loi n° 2013-403, report du second tour des municipales en 2020,
  loi n° 2021-191, trois reports des élections provinciales de Nouvelle-Calédonie en 2024-2025,
  élections des Français de l'étranger…). **Limites** : un report inscrit dans une loi au titre
  général n'est pas repéré (loi d'urgence du 23 mars 2020) ; la durée cumulée des reports
  prévue par la grille n'est pas mesurée (elle n'est pas dans les titres).
- **Prototype** : frise 1993-2026 des scrutins nationaux (losanges) et des lois électorales
  (cercle plein si publiée moins d'un an avant le scrutin suivant de sa ligne) ; tableau des
  reports ; cartes D1.1 et D1.2.

## 2026-11-05 — D5.2 journalistes inquiétés (seed manuel pilote)

- **Choix de la source** (décision du porteur de projet) : seed manuel vérifié. La base la plus
  complète, Mapping Media Freedom (MFRR, licence CC BY-NC-SA 4.0), n'offre pas d'export public ;
  l'interroger directement avec la clé de recherche intégrée à son site a été refusé par
  l'environnement (contournement d'un accès non prévu pour la réutilisation) et n'a pas été
  tenté autrement. Piste ouverte : demander un accès aux données au consortium MFRR.
- **Relevé pilote 2023-2025** (`data/seed/journalistes_inquietes.csv`) : cas repérés par
  recherche, puis chaque source (RSF, SNJ, SNJ-CGT, presse en accès libre) ouverte et lue ; une
  phrase de la source établissant la mesure est citée et retrouvée mot pour mot par script
  (8 lignes sur 8). 6 mesures comptées (gardes à vue et une condamnation, 7 journalistes) et
  2 convocations en contexte.
- **Unité : la mesure**, pondérée par le nombre de journalistes visés (garde à vue de deux
  journalistes pendant les Jeux olympiques) ; une même personne peut subir plusieurs mesures
  (garde à vue puis condamnation, Radio Bip / Média 25, 2023). Convocations et auditions hors du
  champ de la grille (gardes à vue, interpellations, poursuites) : comptées à part.
- **Données personnelles** : le nom des journalistes n'est pas relevé, seulement le média,
  l'autorité et le contexte.
- **Limites** : relevé non exhaustif (cas rendus publics et retrouvés seulement) ; RSF indique
  « au moins cinq professionnels de la presse interpellés » au premier semestre 2023, ce relevé
  en compte deux pour la même période. Dates approximatives signalées (`date_approximative`).
  La valeur de D5.2 ne doit pas être lue comme un total.
- **Prototype** : carte D5.2 et tableau des cas (mesure liée à sa source, extrait en
  infobulle).

## 2026-11-05 — Séries annuelles : fenêtre d'une année civile (correctif)

- **Constat** (préparation du dossier des seuils) : les éditions RSF sont datées du 1er janvier
  et les années CNCTR du 31 décembre. Une fenêtre de 365 jours se terminant le 31 décembre d'une
  année bissextile commence le 2 janvier : elle ne contenait aucune édition RSF, et D5.3 n'avait
  pas de valeur ce jour-là (2004, 2008, 2012, 2016, 2020, 2024). Même défaut pour D6.1 le
  30 décembre des années bissextiles.
- **Correctif** (`scoring/metrics.py`, `ANNUAL_FACT_TYPES`, `window_start`) : pour les
  indicateurs dont tous les faits sont annuels (`classement_rsf`, `surveillance_annee`), la
  fenêtre glissante couvre une année civile, du lendemain de la même date un an plus tôt au
  jour courant (366 jours quand elle contient un 29 février). Les autres indicateurs gardent
  la fenêtre de 365 jours. Aucune fenêtre ne remonte à plus d'un an : sans édition RSF 2011,
  l'année 2011 reste sans valeur.
- **Effet** : D5.3 a une valeur tous les jours sauf en 2011 (pas d'édition) ; D6.1 tous les
  jours sauf le 30 décembre 2016, premier jour de la série (l'année 2016 est datée du
  31 décembre). Tests : `tests/test_metrics.py`.

## 2026-11-05 — Variantes calculées pour le dossier des seuils

Variantes demandées au comité dans le dossier de fixation des seuils, calculées comme
métriques de contexte (aucune ne change la métrique notée de la grille v0) :

- **D2.1 bis — 49.3 seul** : `nb_textes_adoptes_49_3` existait déjà ; aucune modification de
  code. Depuis 1958 : 0 pendant 55 % des jours, maximum 8 textes sur 365 jours (décembre 1990).
- **D1.2 bis — scrutins reportés** (`nb_scrutins_reportes`) : chaque texte de report est
  rattaché aux scrutins qu'il reporte par la table manuelle `config/scrutins_reportes.yaml`
  (type d'élection + année prévue, lus dans le titre ; à défaut l'année du texte). Un scrutin
  reporté par plusieurs textes ne compte qu'une fois dans la fenêtre. Un texte absent de la
  table compte pour un scrutin (`rattachement: a_rattacher`, clé `texte-<numéro>`) et doit être
  ajouté. Effet : 7 textes -> 4 scrutins fin 2020 (second tour des municipales : quatre textes) ;
  1 texte -> 2 scrutins fin 2005 (municipales et cantonales de 2007). Table établie sur les
  seuls titres : à vérifier.
- **D5.3 bis — catégorie RSF** (`categorie_rsf`, niveau 0 « bonne situation » à 4 « situation
  très grave ») : bornes de score publiées par RSF pour les éditions depuis 2022 (85 / 70 / 55 /
  40), lues sur la page de méthodologie 2024 de rsf.org (et les pages anglaises 2022, 2024,
  2026) et contrôlées contre la colonne « Situation » de l'édition 2024 (180 pays concordants ;
  l'extracteur échoue si la catégorie publiée de la France contredit les bornes). Les bornes
  des éditions 2013-2021 (autre échelle) n'ont pas été trouvées sur rsf.org : pas de catégorie
  avant 2022, pas de valeur reprise de mémoire. France : « situation plutôt bonne » (niveau 1)
  de 2022 à 2026.

## 2026-11-05 — Combler les manques (D5.2, D1.2, D4.2*)

- **D5.2 — 10 cas ajoutés** au seed `journalistes_inquietes.csv` (18 lignes) : recherche dans
  les communiqués de RSF, du SNJ, du SNJ-CGT, de la FEJ (EFJ) et la presse en accès libre pour
  2023-2025, chaque extrait vérifié mot pour mot dans sa source. Dont 6 mesures comptées (gardes
  à vue du 17 et du 20 mars 2023 à Paris, poursuite d'un pigiste de Reporterre, garde à vue puis
  mise en examen d'un photojournaliste dans l'enquête Lafarge, gardes à vue de décembre 2024 et
  juillet 2025) et 4 convocations (comptées à part). Écartés : un second journaliste gardé à vue
  le 17 mars 2023 (il manifestait, selon son propre média), une mention incidente de deux
  auditions en avril 2023 (une seule source, sans date), une plainte en diffamation d'une
  ministre (plainte privée, pas une poursuite engagée par une autorité). Au 15 mai 2023, date du
  communiqué de RSF (« au moins cinq professionnels de la presse ont été interpellés »), le relevé
  compte désormais 4 interpellations ou gardes à vue, contre 2 auparavant.
- **D1.2 — reports inscrits dans le corps d'une loi** (`extract/scrutins.py`,
  `passages_report`, `SCAN_VERSION = dila_scrutins_5`) : les articles (JORFARTI) des lois et
  ordonnances sont lus ; un passage est retenu s'il reporte un tour, une élection ou un
  renouvellement général (« … est reporté ») ou proroge le mandat d'élus (« mandat des
  conseillers … est prorogé »), et s'il vise une élection politique (`POLITIQUE`) ; exclusions
  (représentants d'élus dans des comités, ordres professionnels, dates budgétaires). Les textes
  déjà retenus par leur titre ne sont pas comptés deux fois. Faits marqués `detection:
  corps_du_texte`, `a_verifier`. Sur le dump JORF : 52 lois ou ordonnances candidates, 4 après
  filtre, dont 2 nouvelles (loi n° 2020-290 d'urgence covid-19, qui reporte le second tour des
  municipales ; loi n° 2021-689 de sortie de crise sanitaire, prorogation conditionnelle des
  conseillers des Français de l'étranger). Non repérée : prorogation de 2003 de membres du
  Conseil supérieur des Français de l'étranger (Côte d'Ivoire), dont le passage ne nomme pas
  l'assemblée.
- **D4.2\* — rappel mesuré sur mars-avril 2023** : liste de référence établie à partir de la
  presse, des communiqués de la LDH et des sites des tribunaux (décisions lues). Sur 9 décisions
  dans le périmètre retrouvées dans l'open data, 6 étaient retenues. Oublis : TA Paris
  n° 2306532 (seuls « cortèges, défilés et rassemblements » cités : le pré-filtre exigeait
  « manifestation ») — **corrigé** (`PREFILTRE_MANIF`, `SCAN_VERSION = justice_manif_2`,
  +12 décisions sur toute la période) ; TA Paris n° 2307231 (interdiction de « rassemblement
  non déclaré ») et TA Châlons n° 2300733 (itinéraire interdit à Reims) — **non corrigés** :
  ajouter « rassemblement » aux mots retenus ferait entrer 186 décisions, dont environ la moitié
  hors sujet (arrêtés municipaux contre les regroupements, rave-parties, rassemblements de
  véhicules). Rappel après correction : 7 sur 9. Une décision de la liste (TA Paris, 29 avril
  2023, Stade de France) n'a pas pu être identifiée par son numéro.

## 2026-11-05 — Publication du prototype

- Page Artifact privée sur claude.ai (https://claude.ai/artifact/Wd69scryvAZ4Yiggq1c5AF),
  construite par `front/publication/build.py` (`make publication`) à partir du prototype et de
  `data.js` ; voir `front/publication/README.md`. Partage décidé par le porteur de projet
  (menu Partager de la page).
- Correction au passage : le titre « Cinq indicateurs suivis » datait d'une version ancienne ;
  il est désormais calculé à partir des données (13 indicateurs).
- Mise à jour manuelle : la page n'est pas republiée par la collecte quotidienne.

## 2026-11-05 — Faits nouveaux du jour (alerte quotidienne)

- `ops/nouveautes.py`, appelé par `make quotidien` après une reconstruction réussie (et
  `make nouveautes` à la main). La base étant reconstruite chaque jour, les faits sont comparés
  par une clé stable (indicateur, type, référence officielle ou titre, date) à la liste de
  l'exécution précédente (`data/cache/faits_connus.json`, ≈ 7 Mo). Première exécution : liste
  enregistrée, rien signalé.
- Sorties : `data/exports/nouveautes.md` (et copie datée dans `data/logs/`), bilan dans
  `etat_quotidien.json` (`faits_nouveaux`). Notification de bureau d'information (urgence
  normale, distincte de l'alerte d'échec) seulement s'il y a des faits marquants.
- Faits marquants (`MARQUANTS`) : engagements 49.3, dissolutions, reports de scrutin, textes
  électoraux à moins d'un an d'un scrutin, régimes d'exception, lois censurées (au fond),
  décrets malgré réserves CNIL (confiance forte), décisions sur des interdictions de
  manifester, journalistes inquiétés, éditions RSF, années CNCTR, mois Arcom. Les autres types
  (lois, ordonnances, avis, QPC…) sont comptés.
- Un fait « nouveau » peut être ancien : décision de justice mise en ligne avec retard, ou
  extracteur modifié ; il est listé avec sa propre date. Les faits disparus sont signalés
  (correction de source ou d'extraction). Ton : le résumé décrit, il ne qualifie pas.

## 2026-11-06 — Collecte quotidienne sans réseau, corrections après revue de code

- **Passage du 06/11 sans réseau** : au réveil du portable, le minuteur rattrapé
  (`Persistent=true`) s'est déclenché avant le Wi-Fi ; les 10 collectes réseau ont échoué
  (résolution DNS), `nouveautes.md` annonçait pourtant « aucun fait nouveau ».
  `network-online.target` est sans effet pour un service utilisateur. Corrections :
  `ops/quotidien.py` attend jusqu'à 10 min que `echanges.dila.gouv.fr` ou `www.data.gouv.fr`
  se résolve (puis lance quand même) ; si des collectes échouent, `nouveautes.md` commence par
  « Collecte incomplète » avec leur liste, et `etat_quotidien.json` porte `sources_en_echec`.
- **`ops/nouveautes.py` — clé des faits** : la référence officielle seule confondait des faits
  distincts (un même décret ouvre l'état d'urgence sanitaire à La Réunion et en Martinique le
  même jour) ; un fait nouveau de même clé qu'un fait connu n'aurait jamais été signalé. La clé
  inclut désormais le titre, et des faits entièrement identiques sont numérotés. Liste des faits
  connus : `data/cache/faits_connus.v2.json` (nouveau format, réenregistrée le 06/11).
- **D4.2\* — décisions hors sujet** (`extract/manifestations.py`, `SCAN_VERSION =
  justice_manif_4`, extracteur `/2`) : 97 décisions retirées, toutes relues par échantillon ou
  par leur phrase de demande : sanctions antidopage de l'AFLD (« interdiction de participer à
  toute manifestation sportive »), interdictions de stade, sanctions de fédérations sportives,
  épreuves nautiques, arrêté de prévention des incendies interdisant les « manifestations
  sportives, de loisirs et culturelles ». Règle : « manifestation » suivi de sportive, nautique,
  aérienne, motorisée ou automobile n'est pas une manifestation au sens de la liberté de
  manifester ; une phrase qui cite le dopage ou l'AFLD n'est pas lue. Aucune décision de la
  liste de référence de mars-avril 2023 n'est perdue (rappel inchangé : 7 sur 9).
- **D4.2\* — sens de l'issue quand l'administration fait appel** : devant le Conseil d'État,
  quand le ministre (ou un préfet, une commune) est l'appelant, « Rejet » signifie que
  l'interdiction reste suspendue ou annulée. L'issue est désormais lue du point de vue de la
  personne qui conteste l'interdiction (`appel_administration`, inversion des issues). 3
  décisions concernées (CE n° 464520, 490870, 493601), auparavant comptées défavorables.
- **D4.2\* — solutions « Rejet PAPC » du Conseil d'État** (« R.822-5 Rejet PAPC défaut
  ministère avocat », « R.822-5-3 Rejet PAPC référé ») : comptées comme rejets (et non plus
  « autre », hors des décisions tranchées).
- **D4.2\* — dédoublonnage** : clé = juridiction + nom de fichier (le même nom
  `DTA_2301082_20230228.xml` désigne deux décisions, au TA de Strasbourg et au TA de
  Versailles). Aucune collision dans le relevé actuel.
- Effet D4.2\* : 783 → 686 décisions ; part des interdictions censurées, législature 16 :
  38,9 % → 39,4 % ; législature 17 : 30,0 % → 30,1 %.
- **D6.2 — avis CNIL publiés deux fois** (même numéro, même date, deux identifiants
  CNILTEXT : n° 2016-347 et 2022-083) : comptés une fois (`dedup_avis`, extracteur `/2`).
  640 avis au lieu de 642 ; un décret de plus rapproché par la date (637 au lieu de 636).
- **D5.1 — contrôle Arcom** : conformément à ce qu'annonçait le module, les deux parts publiées
  (exécutif et partis) sont contrôlées, et leur absence fait échouer l'extraction (aucun fichier
  actuel concerné) ; lignes de longueurs différentes : erreur explicite.
- **D5.3 — colonne « Situation » RSF** : contrôlée seulement à partir de l'édition 2022 (bornes
  antérieures non vérifiées) ; aucun fichier actuel concerné.
- **D1.2** : les reports repérés dans le corps des lois ne sont plus ignorés quand aucun autre
  texte électoral n'est trouvé (cas limite, sans effet sur les données actuelles).
- Non retenu de la revue : réécriture d'un article par un incrément JORF ultérieur (le JORF
  publie des textes, non des versions consolidées ; un report publié reste un fait). Différé :
  cache du scan CNIL, factorisation des quatre `cached_scan`, double lecture XML dans
  `scrutins.parse_article` (performance seulement ; reconstruction complète ≈ 15 s).

## 2026-11-06 — Temps de parole par parti (contexte de D5.1, non noté)

- **Demande** du porteur de projet : montrer quels partis sont les plus présents à la télévision
  et à la radio. Source : les relevés mensuels de l'Arcom déjà archivés (21 mois, janvier 2025 à
  septembre 2026), qui publient le temps de chaque parti, chaîne par chaîne.
- **Extraction** (`extract/arcom.py`, `parse_partis`, `extract_partis`, fait
  `temps_parole_partis_mois`, indicateur `contexte.temps_parole_partis`, hors grille) : toutes
  les lignes situées entre « Part Pouvoir exécutif » et « Total Partis politiques », sous le
  libellé publié par l'Arcom, sans regroupement ni renommage. Règle 5 : aucun nom de parti dans
  le code, les lignes sont repérées par leur position (un test le vérifie).
- **Contrôle** : pour chaque mois et chaque colonne, la somme des partis égale le total Arcom à
  la seconde près (vérifié sur les 21 mois, 0 écart) ; un parti en double ou une chaîne
  rattachée à deux types de service fait échouer l'extraction. Aucune variante d'orthographe
  entre les mois (95 libellés distincts). Chiffres de la page recalculés indépendamment depuis
  les CSV bruts (12 derniers mois : 3 349 h de temps de parole des partis, 87 partis).
- **Présentation** : barres horizontales d'une seule couleur, triées par temps cumulé, 15 partis
  puis les autres regroupés ; filtres par période et par média (type de service ou chaîne).
  Aucune comparaison à un critère de représentativité (résultats électoraux, groupes
  parlementaires) : ce serait un choix de méthode, à soumettre au comité s'il est souhaité. Le
  temps de l'exécutif reste décompté à part (D5.1).
- **Alerte quotidienne** : les 21 faits mensuels ont été ajoutés à la référence des faits connus
  pour ne pas être annoncés comme nouveaux ; les mois suivants le seront normalement.

## 2026-11-06 — Déclarations de l'ONU sur la France (regards extérieurs, non noté)

- **Demande** du porteur de projet : mettre en avant ce que disent les organes de l'ONU sur la
  France, notamment sur le maintien de l'ordre lors des manifestations. **Périmètre choisi** :
  sources officielles de l'ONU (experts indépendants, Haut-Commissariat, comités des traités,
  Examen périodique universel) ; le Conseil de l'Europe n'est pas inclus.
- **Méthode** : seed manuel `data/seed/onu_declarations.csv` (`extract/onu.py`, fait
  `declaration_onu`, indicateur `contexte.declarations_onu`, hors grille). Pilote de 10
  déclarations (2019-2026), repérées par recherche puis lues sur ohchr.org ; extraits recopiés
  par script depuis le texte de la page (20 sur 20 retrouvés). Version française quand elle
  existe, sinon l'anglais original, sans traduction maison.
- **Accès** : ohchr.org refuse les requêtes automatiques (HTTP 403) ; les pages ont été ouvertes
  une à une dans un navigateur. Les bases interdites aux robots (communications des procédures
  spéciales, base des organes de traités) n'ont pas été interrogées : les réponses de la France
  ne sont donc pas encore relevées.
- **Neutralité** : aucun résumé ni qualification ajoutés ; chaque fiche cite le constat principal
  et, quand la déclaration en contient une, la phrase qui en donne une autre facette
  (violences visant les forces de l'ordre, appel au calme, demande d'enquête).

## 2026-11-06 — La France dans la presse étrangère (GDELT, regards extérieurs, non noté)

- **Méthode choisie** par le porteur de projet : la base ouverte GDELT plutôt qu'une liste de
  titres choisie à la main (la sélection des titres serait un parti pris).
- **Accès** : l'API de recherche de GDELT renvoie « trop de requêtes » (HTTP 429) dès la première
  requête et ne remonte qu'à trois mois ; on utilise les fichiers publics de GDELT 2.0 (une
  tranche de 15 minutes : événements et mentions), téléchargés sans restriction.
- **Archive** : les fichiers bruts (≈ 18 Mo par jour) ne sont pas archivés tels quels ; le
  collecteur (`collectors/gdelt.py`) archive pour chaque jour UTC un extrait filtré, compressé et
  déterministe (≈ 50 à 120 Ko) : mentions web d'événements dont le lieu d'action est en France,
  avec le code de l'événement, le domaine et l'adresse de l'article ; aucun texte d'article.
  Tranches absentes listées en tête de fichier. Table GDELT « domaine -> pays » (mai 2018)
  archivée une fois.
- **Mesure** (`extract/gdelt.py`, fait `couverture_etrangere_mois`, indicateur
  `contexte.presse_etrangere`) : articles distincts de sites étrangers, sites distincts, pays des
  sites, et deux thèmes du codage automatique CAMEO de GDELT : « manifestations » (code racine
  14) et « usage de la force par la police » (codes 17, 18, 19 avec la police parmi les acteurs).
  Ces thèmes décrivent le codage de la base, pas un jugement ; la page le dit.
- **Limites affichées** : presse surtout anglophone ; reprises d'agence comptées une fois par
  site (d'où le nombre de sites distincts) ; table des pays de 2018 (sites absents écartés et
  comptés à part) ; noms de pays en anglais (table GDELT).
- **Historique** : ≈ 2 minutes de téléchargement par jour. Rattrapage depuis janvier 2025 du plus
  récent au plus ancien : 5 jours par passage quotidien (`collect-gdelt`, `GDELT_JOURS=5`), plus
  un rattrapage lancé à la main le 06/11 sur une base séparée. Pendant un rattrapage, l'archive
  grossit : `make reproducible` peut alors différer entre ses deux reconstructions.

## 2026-11-06 — En-tête de page : vue d'ensemble des 13 indicateurs (remplace le cadran D2.1)

- **Constat** du porteur de projet : le cadran du haut de page ne portait que sur D2.1
  (contournement du Parlement), avec un seuil de bascule illustratif de 50 %.
- **Choix** (porteur de projet, 2026-11-06) : une vue d'ensemble descriptive, sans note. Pour
  chacun des 13 indicateurs de la grille, un repère place la valeur des douze derniers mois parmi
  tous les mois observés depuis le début de la série (`part_mois_inferieurs`, déjà calculé pour
  les cartes) ; le titre compte les indicateurs situés dans le tiers le plus haut de leur propre
  historique. Toutes les directions de la grille sont « increasing » : plus haut = plus
  défavorable selon la grille (rang RSF compris).
- **Ce qui n'est pas fait** : aucune pondération, aucun seuil, aucun indice unique (option
  « indice illustratif » écartée : un chiffre unique se lit comme un verdict). Le seuil
  illustratif de 50 % disparaît de l'en-tête ; D2.1 garde sa jauge dans sa propre section.
- **Hors calcul** : déclarations de l'ONU, presse étrangère, temps de parole par parti,
  mobilisations, participation (données de contexte).
- **Garde-fou** : séries de moins de 36 mois (D5.1, D5.2 au 06/11) signalées par un astérisque et
  un repère gris, leur position historique étant peu significative.

## 2026-11-06 — Indice illustratif en tête de page (moyenne simple, non validée)

- **Demande** du porteur de projet : un chiffre unique, simple à lire par le plus grand nombre,
  au-dessus de la vue d'ensemble. Option « indice illustratif » retenue cette fois, avec ses
  garde-fous.
- **Calcul** (dans la page, `position` et `drawIndice`) : pour chacun des 13 indicateurs de la
  grille, position de la valeur des douze derniers mois dans son historique mensuel, au **rang
  moyen** (part des mois plus bas + moitié des mois égaux) ; indice = moyenne simple × 100, poids
  égaux, séries courtes comprises. Au 4 novembre 2026 : **52 sur 100** (recalculé à part en
  Python : 51,9).
- **Correction de méthode** au passage : la vue d'ensemble utilisait la part des mois
  strictement plus bas ; un indicateur sans aucun cas (valeur nulle comme 81 % des mois pour
  D3.1) était classé « au plus bas jamais observé » au lieu d'« habituel ». Avec le rang moyen,
  l'indice passe de 40 à 52 ; la vue d'ensemble utilise la même position. Les cartes gardent
  leur formulation exacte (« supérieur à X % des mois observés »).
- **Lecture affichée** : 0 = plus bas jamais observé partout, 50 = habituel, 100 = plus haut
  partout ; titre en trois cas (proche de l'habitude à ± 5 points, plus haut, plus bas). Jauge
  d'une seule couleur, sans zones colorées (ce seraient des seuils déguisés) ; mention
  « Indice illustratif » et absence de pondérations et de seuils du comité rappelées à côté.
- **Hors calcul** : données de contexte (ONU, presse étrangère, temps de parole par parti,
  mobilisations, participation).

## 2026-11-06 — Mise en ligne sur un hébergement mutualisé, référencement (SEO et GEO)

- **Hébergement** : mutualisé (O2Switch), sans domaine pour l'instant. La collecte (archive de
  ≈ 11 Go, traitements de plusieurs minutes, timer systemd) reste sur la machine qui a
  l'archive ; l'hébergement ne reçoit que des fichiers statiques. Claude ne travaille pas sur
  le serveur (décision du porteur de projet).
- **Envoi** (`ops/deployer.py`, `make deployer`, dernière étape de `make quotidien`) : rsync en
  SSH ou FTPS (bibliothèque standard, mot de passe dans `~/.netrc`), configuration hors git dans
  `config/deploiement.local` (exemple versionné). Données avant la page ; en FTPS, nom
  temporaire puis renommage. Sans configuration : aucun envoi, étape réussie.
- **Version web** (`build.py --web`) : document HTML complet (Font Awesome compris), sans lien
  vers les documents de travail privés de claude.ai (la construction échoue s'il en reste un).
- **Référencement** (`front/publication/seo.py`) : la page construisant ses chiffres en
  JavaScript, l'indice, son explication et la vue d'ensemble sont aussi écrits dans le HTML ;
  titre, description, Open Graph, JSON-LD `Dataset` ; fichiers `barometre.md` (résumé sourcé),
  `indicateurs.csv`, `llms.txt` (assistants d'IA ; consigne de ne pas présenter l'indice
  illustratif comme une note officielle), `robots.txt`, `favicon.svg`. URL canonique et
  `sitemap.xml` seulement avec `SITE_URL` (domaine). Positions et indice calculés comme dans la
  page (rang moyen), testés.

## 2026-11-07 — Site en ligne : couleurs de la jauge, aucun service tiers, mentions légales

- **Couleurs de la jauge** (choix du porteur de projet) : arc rempli jusqu'à la valeur, du vert
  (0) au rouge sombre (100) en passant par le jaune (50), l'orange et le rouge ; la valeur est
  marquée par un trait. Une échelle à milieu neutre (gris autour de 50) a été proposée puis
  écartée : le porteur de projet préfère une progression continue du vert au rouge. Ces
  couleurs ne sont pas des seuils de la grille : l'avis « indice illustratif » le rappelle, et
  le texte du titre reste la lecture de référence.
- **Aucun service tiers** : feuille Tailwind construite (`make css`), polices et icônes
  hébergées sur le site ; la construction échoue si une ressource externe réapparaît. Aucun
  cookie : avis d'information sans recueil de consentement (rien n'y est soumis).
- **Mentions légales** : éditeur non professionnel anonyme (identité communiquée à
  l'hébergeur, LCEN), coordonnées de l'hébergeur relevées sur o2switch.fr (pied de page et
  conditions générales de vente) le 7 novembre 2026.
- **En-têtes** (`.htaccess`) : HSTS (un an, sans sous-domaines), CSP limitée au site lui-même
  (scripts et styles en ligne admis : la page en contient), `nosniff`, `Referrer-Policy`,
  `X-Frame-Options`. Cache : `assets/` un an (fichiers immuables, à renommer s'ils changent),
  page et données revalidées à chaque visite. Page 404 dédiée, image de partage 1200 × 630
  (`front/publication/apercu.png`, source `apercu.html`).
