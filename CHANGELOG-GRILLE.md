# Changelog de la grille d'indicateurs

Toute modification d'indicateur, de seuil ou de pondération crée un nouveau fichier
`config/grid.vN.yaml` (les versions précédentes ne sont jamais modifiées), une entrée
ci-dessous et un recalcul complet de l'historique (`make rebuild GRID=config/grid.vN.yaml`).

## v0 — 2026-10-26 (brouillon, non figée)

- Ajout du 2026-11-05 (avant tout gel), métriques de contexte pour le dossier des seuils :
  `nb_scrutins_reportes` (D1.2, scrutins distincts, table `config/scrutins_reportes.yaml`) ;
  `categorie_rsf` = `somme_niveaux_categorie_rsf / nb_editions_categorie_rsf` (D5.3,
  catégories RSF depuis 2022). Métriques notées inchangées.
- Correctif du 2026-11-05 (avant tout gel) : pour les séries annuelles (D5.3 RSF, D6.1
  CNCTR), la fenêtre glissante couvre une année civile (366 jours si elle contient un
  29 février) ; elle perdait l'édition annuelle le 31 décembre (RSF) ou le 30 décembre
  (CNCTR) des années bissextiles. Aucune note n'avait été produite.
- Indicateur **D2 — Contournement du Parlement** (`D2.contournement_parlement`).
  - Faits : `engagement_49_3`, `ordonnance_publiee`, `loi_promulguee`.
  - Fenêtres : glissante de 365 jours et par législature.
  - Début de l'historique : 1958-12-09 (ouverture de la Ire législature).
  - Métriques : `nb_49_3`, `nb_textes_49_3`, `nb_textes_adoptes_49_3`, `nb_ordonnances`,
    `nb_ordonnances_art38`, `nb_lois`, `nb_lois_hors_conventions`, `ratio_contournement`.
  - `ratio_contournement = (nb_textes_adoptes_49_3 + nb_ordonnances_art38)
    / (nb_lois_hors_conventions + nb_ordonnances_art38)` : un texte est « adopté via 49.3 »
    s'il a fait l'objet, dans la fenêtre, d'au moins un engagement non suivi d'une motion
    de censure adoptée ; seules les ordonnances de l'article 38 comptent ; les lois
    autorisant un engagement international (ratification, approbation...) sont exclues.
    La formule des ratios est écrite dans la grille (`ratios`), pas dans le code.
  - Échelle : 0 = fonctionnement démocratique normal, 4 = alerte maximale ; libellés des
    niveaux à rédiger par le comité.
  - Modifiée le 2026-10-26 avant tout gel (réponses du porteur de projet aux questions
    ouvertes) ; aucune note n'avait été produite avec la version précédente.
  - Seuils et pondération : `null`, à fixer par le comité. Aucune note 0-4 n'est produite.
- Indicateur **D3.1 — Régimes d'exception** (`D3.regimes_exception`) : `jours_exception`
  (au moins une partie du territoire), `jours_exception_metropole` ; historique depuis le
  9 décembre 1958.
- Indicateur **D4.1 — Dissolutions administratives** (`D4.dissolutions_administratives`) :
  `nb_dissolutions` ; historique depuis le 1er janvier 1990 (fiabilité de l'indexation du JO).
- Indicateur **D3.2 — Lois censurées** (`D3.lois_censurees`), ajouté le 2026-11-05 avant
  tout gel : `ratio_censure = nb_lois_censurees / nb_lois_deferees` (décisions DC au fond
  portant sur une loi, non-conformité partielle ou totale), `ratio_censure_lois_ordinaires`
  (hors lois organiques), et en contexte `nb_qpc`, `nb_qpc_censures` ; historique depuis le
  9 décembre 1958. Le comité doit dire si D3.2 est noté ou seulement affiché.
- Indicateur **D2.2 — Procédure accélérée** (`D2.procedure_acceleree`), ajouté le
  2026-11-05 avant tout gel : `ratio_procedure_acceleree = nb_lois_procedure_acceleree /
  nb_lois_dossier_an` (lois promulguées dont l'Assemblée publie le dossier, hors lois
  autorisant un engagement international et lois constitutionnelles) ; métrique de
  couverture `nb_lois_sans_dossier_an` ; historique depuis le 20 juin 2012 (ouverture de
  l'open data de l'Assemblée).
- **D2.2 modifié le 2026-11-05, avant tout gel** (aucune note produite) : statut de chaque
  loi lu dans l'open data de l'Assemblée **et** dans la base Dosleg du Sénat ; historique
  avancé au 3 avril 1978 (VIe législature) ; lois de finances et de financement de la
  sécurité sociale exclues (calendrier fixé par la Constitution) ; métriques renommées
  `nb_lois_statut_connu`, `nb_lois_procedure_acceleree`, `nb_lois_statut_inconnu` (les lois
  dont aucune source ne donne la procédure sont comptées à part). Raisons : DECISIONS.md.
- Indicateur **D4.2\* — Interdictions de manifester contestées devant le juge**
  (`D4.interdictions_manifester_juge`), ajouté le 2026-11-05 avant tout gel : approximation
  automatique de l'indicateur D4.2 du document de grille (arrêtés préfectoraux, collecte
  semi-manuelle), qui reste à construire. `ratio_interdictions_censurees =
  nb_decisions_manifestation_favorables / nb_decisions_manifestation_tranchees` (décisions où
  le juge a suspendu ou annulé l'interdiction, sur les décisions où il a donné raison au
  requérant ou rejeté sa demande) ; `nb_decisions_manifestation` en contexte ; historique
  depuis le 1er juin 2022 (open data des tribunaux administratifs).
- Indicateur **D6.2 — Fichiers créés malgré les réserves de la CNIL**
  (`D6.traitements_malgre_reserves`), ajouté le 2026-11-05 avant tout gel : métrique notée
  `nb_decrets_malgre_reserves` (décrets publiés après un avis de la CNIL sur leur projet
  contenant des réserves formelles, rapprochement de confiance forte) ; en contexte
  `nb_decrets_avis_cnil`, `nb_avis_cnil_reserves`, `nb_avis_cnil_projets_decret` et
  `nb_decrets_malgre_reserves_a_verifier` (rapprochements de confiance faible, non comptés) ;
  historique depuis 1983.
- Indicateur **D5.1 — Temps de parole de l'exécutif** (`D5.temps_parole_executif`), ajouté
  le 2026-11-05 avant tout gel : `part_executif = secondes_executif / (secondes_executif +
  secondes_partis)`, secondes additionnées sur les mois relevés de la fenêtre, d'après les
  agrégats « Total Pouvoir exécutif » et « Total Partis politiques » de l'Arcom ;
  `nb_mois_temps_parole` en contexte ; historique depuis le 1er janvier 2025.
- Indicateur **D5.3 — Classement RSF** (`D5.classement_rsf`), ajouté le 2026-11-05 avant
  tout gel : `rang_rsf = somme_rangs_rsf / nb_editions_rsf` (rang de la France, éditions
  datées par convention du 1er janvier de leur année) ; historique depuis 2002.
- Indicateur **D6.1 — Techniques de renseignement** (`D6.techniques_renseignement`), ajouté
  le 2026-11-05 avant tout gel : `personnes_surveillees = somme_personnes_surveillees /
  nb_annees_cnctr` (personnes ayant fait l'objet d'au moins une technique dans l'année,
  années datées du 31 décembre) ; historique depuis 2016.
- Indicateur **D1.1 — Règles électorales modifiées peu avant un scrutin**
  (`D1.regles_electorales_avant_scrutin`), ajouté le 2026-11-05 avant tout gel : lois, lois
  organiques et ordonnances touchant au mode de scrutin, au découpage ou au calendrier d'un
  scrutin national, publiées moins de 365 jours avant le scrutin suivant d'un type visé
  (`nb_textes_electoraux_avant_scrutin`) ; historique depuis 1993 (calendrier complet).
- Indicateur **D1.2 — Scrutins reportés** (`D1.scrutins_reportes`), ajouté le 2026-11-05 avant
  tout gel : textes reportant une élection politique ou prorogeant des mandats électifs
  (`nb_reports_scrutin`) ; la durée cumulée des reports prévue par la grille n'est pas encore
  mesurée ; historique depuis 1990.
- Indicateur **D5.2 — Journalistes inquiétés** (`D5.journalistes_inquietes`), ajouté le
  2026-11-05 avant tout gel : `nb_journalistes_mesures` (journalistes visés par une garde à
  vue, une interpellation, une poursuite, une mise en examen ou une condamnation, seed manuel
  vérifié) ; `nb_journalistes_convoques` en contexte ; historique depuis 2023 (relevé pilote,
  non exhaustif).
- Seuils de D1.1, D1.2, D2.2, D3.1, D3.2, D4.1, D4.2\*, D5.1, D5.2, D5.3, D6.1 et D6.2 : `null`.

### 2026-11-06 — Extraction (sans changement de grille)

- D4.2\* : décisions sportives, antidopage et nautiques exclues ; issue lue du point de vue du
  contestataire quand l'administration fait appel ; « Rejet PAPC » compté comme rejet
  (`justice_manifestations/2`). 783 → 686 décisions. Détail : DECISIONS.md, 2026-11-06.
- D6.2 : avis CNIL publiés sous deux identifiants comptés une fois (`cnil_avis_decrets/2`).
