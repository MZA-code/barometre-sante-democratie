# D7 · Libertés en pratique — document de conception

Date : 2026-11-10. Statut : à valider par l'utilisateur avant tout plan ou code.

## 1. Intention

L'indice actuel mesure surtout le **droit écrit et les décisions officielles** (lois, procédures,
décisions de justice, avis d'autorités indépendantes). L'utilisateur constate dans l'actualité
quotidienne (exemples cités : manifestants arrêtés au hasard à Strasbourg, trombinoscopes d'élèves
saisis par la police à Brest, pressions sur l'expression dans un collège et une école d'art) un
autre phénomène : **la loi reste en place, mais ceux qui doivent l'appliquer ou la protéger ne la
respectent pas**. C'est ce que la littérature appelle l'érosion démocratique (Bermeo 2016,
Levitsky et Ziblatt 2018, Scheppele 2018 ; références affichées sur le site depuis `0ac6710`).

But : faire entrer ces **atteintes aux droits en pratique** dans l'indice, sous la forme d'une
nouvelle dimension **D7 · Libertés en pratique**.

Exigence n° 1 de l'utilisateur : le résultat doit être **incontestable**. Une personne qui ne
partage pas ses opinions (élu, préfet, journaliste d'un autre bord) ne doit pas pouvoir écarter le
baromètre comme « militant ». D'où : plusieurs sources, critères fixés à l'avance, trace publique
de chaque décision.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Recenser des faits datés d'atteinte aux libertés par une autorité publique (police, préfecture,
  administration, gouvernement, direction d'établissement public), classés dans des catégories
  fixées à l'avance.
- Ne compter un fait que s'il est **établi** : par une source institutionnelle, ou par la presse
  recoupée **et** validée par un humain.
- Valider les faits de presse **sans session Claude ni accès serveur** : par les issues GitHub du
  dépôt public, depuis le site ou l'application mobile.
- Publication automatique : les décisions prises sur GitHub apparaissent sur le site **dans
  l'heure**.

**Non-objectifs (v1)**
- Pas de back-office web hébergé.
- Pas d'archivage du texte des articles (droit d'auteur, articles payants) : titre, média, date,
  adresse seulement.
- Pas d'exhaustivité : D7 suit ce qui est rendu public et recoupé, et le dit.

**Anti-objectifs (échec même si « ça marche »)**
- Un fait compté sur la foi d'un seul média.
- Des catégories choisies ou retouchées après avoir vu les faits.
- Un critère qui dépend d'un parti, d'une personnalité ou d'un camp (BRIEF.md §3.5).
- Le nom d'un particulier dans une issue ou dans un fait stocké.
- Un fait déjà compté dans un autre indicateur (D4.2\*, D5.2, D6.2…) compté une seconde fois.

## 3. Contraintes du projet (rappel, non négociables)

BRIEF.md §3 s'applique entièrement : archive brute immuable (SHA-256), traçabilité fait → document,
grille versionnée (`config/grid.v0.yaml` + `CHANGELOG-GRILLE.md`), pas de note 0-4 tant que les
seuils valent `null`, neutralité dans le code, `make rebuild` déterministe depuis l'archive.

Exploitation (mémoire projet) : la production tourne sur O2Switch (`~/barometre`, cron cPanel
`ops/cron.sh` à 6 h 30, `git pull --ff-only` puis `make quotidien`). Claude ne se connecte pas au
serveur : il donne les commandes, l'utilisateur les lance. Le dépôt GitHub est public.

## 4. Ce qui a été décidé avec l'utilisateur

1. **Définition et références** affichées en haut du site (fait, `0ac6710`).
2. **Plusieurs sources, résultat incontestable** (§1).
3. **Validation humaine des faits de presse** ; l'automatique ne suffit pas.
4. **Validation par issues GitHub** (méthode retenue contre un back-office hébergé).
5. **Publication toutes les heures** quand il y a de nouvelles décisions.
6. **Sources institutionnelles** comptées sans relecture humaine.

## 5. Fonctionnement

### 5.1 Deux voies d'entrée

| Voie | Exemples | Relecture | Compte quand |
| --- | --- | --- | --- |
| Institutionnelle | Défenseur des droits, CGLPL, CNCDH, juge administratif, CEDH, Conseil de l'Europe, ONU | aucune | dès extraction |
| Presse | articles de médias français | humaine, sur GitHub | recoupé **et** étiqueté `validé` |

### 5.2 Voie presse, de bout en bout

1. **Repérage** (dans la collecte quotidienne) : articles de médias français dont le titre ou le
   codage relève d'une catégorie D7.
2. **Regroupement** des articles qui décrivent le même fait (même lieu, dates proches, même
   catégorie).
3. **Recoupement** : un groupe devient candidat s'il réunit au moins **deux médias appartenant à
   des groupes de propriétaires différents**.
4. **Issue GitHub** ouverte par le serveur pour chaque candidat : catégorie proposée, date, lieu
   (commune ou département), liste des articles (média, titre tel que publié, date, lien),
   étiquettes `d7`, `en-attente`, `cat:<catégorie>`.
5. **Décision** de l'utilisateur sur GitHub : étiquette `validé` ou `rejeté`, catégorie corrigée en
   changeant l'étiquette `cat:`, commentaire libre.
6. **Relecture des décisions** par le serveur (tâche horaire) : instantané de l'état des issues
   `d7` archivé comme document brut, puis faits D7 dérivés de cet instantané.
7. **Publication** : si l'instantané a changé, recalcul et republication (≈ 15 s).

Un fait en attente est affiché comme tel sur le site (nombre de candidats en attente) et ne compte
pas.

### 5.3 Catégories (brouillon, à figer avant tout comptage)

Tirées de la liste de la Commission de Venise et des signaux d'alerte de Levitsky et Ziblatt. Chaque
catégorie vise un **acte d'une autorité publique**.

| Clé | Catégorie | Exemples d'actes |
| --- | --- | --- |
| `interpellations` | Interpellations ou gardes à vue collectives sans suite | encerclements, interpellations de masse classées sans suite |
| `expression` | Entraves à l'expression ou à la création | sanction, interdiction ou pression administrative visant une opinion, une œuvre, un enseignement |
| `reunion` | Entraves à la réunion et à la manifestation | dispersions, interdictions hors arrêté contesté (sinon déjà dans D4.2\*) |
| `surveillance` | Fichage et surveillance hors cadre | collecte de données d'élèves, de manifestants, de militants sans base légale claire |
| `force` | Usage disproportionné de la force | blessures graves lors d'opérations de maintien de l'ordre, constatées par une source |
| `decisions_ignorees` | Décisions de justice ou d'autorités non respectées | administration qui n'exécute pas une décision, réitère un acte annulé |

Les atteintes visant des journalistes restent dans D5.2 ; les interdictions de manifester
contestées devant le juge restent dans D4.2\* (anti-doublon, §2).

### 5.4 Calcul

- Métriques : nombre de faits validés par catégorie et total, sur fenêtre glissante de 365 jours et
  par législature, comme les autres indicateurs.
- Ajout à `config/grid.v0.yaml` (grille encore en brouillon, même pratique que les ajouts du
  05/11), avec entrée dans `CHANGELOG-GRILLE.md`. Seuils `null` : métrique brute publiée, pas de
  note 0-4.
- Le site explique la limite principale : un sujet très couvert par les médias n'est pas forcément
  plus fréquent ; les sources institutionnelles servent de contrepoids.

### 5.5 Tâche horaire et clé GitHub

- Nouvelle ligne cron cPanel (donnée à l'utilisateur, posée par lui), par exemple
  `5 * * * * $HOME/barometre/ops/decisions.sh`. Le script ne collecte rien : il lit les issues,
  archive l'instantané, et ne recalcule et republie que si l'instantané a changé. Il ne doit pas
  tourner en même temps que le cron de 6 h 30 (verrou).
- Clé GitHub à grain fin, limitée à **ce seul dépôt** et aux **issues** (lecture et écriture),
  créée par l'utilisateur, stockée sur le serveur hors du dépôt (`config/deploiement.local` ou
  fichier dédié ignoré par git).

### 5.6 Protection des personnes

- Aucun nom de particulier dans les faits stockés (catégorie, date, lieu, sources seulement), comme
  pour D5.2.
- Les issues reprennent les titres d'articles **tels que publiés** ; si un titre nomme un
  particulier, l'utilisateur peut le masquer en modifiant l'issue. Les agents publics ne sont pas
  nommés non plus : on note l'autorité (préfecture, commissariat, rectorat), pas la personne.

## 5 bis. Choix de Claude (à vérifier par l'utilisateur)

Tranchés après la relecture du document par un constructeur indépendant.

1. **Fait institutionnel « établi »** : seulement un **constat d'atteinte** par l'autorité. Cela
   comprend la décision du Défenseur des droits concluant à un manquement, la suspension ou
   l'annulation de l'acte par le juge administratif, et l'arrêt de la CEDH constatant une
   violation par la France. Une simple saisine, une enquête ouverte ou un rapport général ne
   comptent pas. Chaque fait porte deux dates, celle de l'acte (si connue) et celle du constat.
   Le comptage se fait à la date du constat, la seule toujours connue. Le site affiche les deux.
2. **Critères écrits** : chaque catégorie reçoit, avant tout comptage, des règles de décision
   écrites dans la grille (ce qui compte, ce qui ne compte pas, cas limites). Le validateur les
   applique sans jugement libre. Les critères invérifiables à la parution sont reformulés en
   faits constatables. Par exemple, « gardes à vue collectives sans suite » devient « au moins
   10 interpellations lors d'un même événement, rapportées par deux groupes ». Un éventuel
   « sans suite » ultérieur est noté en commentaire, pas exigé.
3. **Noms** : les issues ne reprennent **pas** les titres d'articles. Elles portent un titre
   neutre généré (`[D7] <catégorie> · <département> · <date>`), puis le média, la date et le lien
   de chaque article. Les titres servent au regroupement et restent dans l'archive brute
   (`data/raw/`, non publiée). L'instantané des issues ne contient donc aucun nom.
4. **Doublons** :
   - les faits de presse et les constats institutionnels forment deux sous-métriques
     (`nb_faits_presse_valides`, `nb_constats_institutionnels`), plus leur total ;
   - le validateur peut poser l'étiquette `doublon` avec « doublon de #N » en commentaire ; le
     fait est alors fusionné et compté une fois ;
   - les séries de contexte existantes (`contexte.interpellations`, `contexte.usage_force`)
     restent hors calcul, donc sans double compte, et sont affichées à côté de D7.
5. **Dépêches AFP** : des articles de médias différents dont le titre est identique ou quasi
   identique comptent pour une seule source. Le recoupement exige deux sources ainsi
   dédoublonnées.
6. **Validateur** : l'instantané enregistre, pour chaque étiquette `validé`, `rejeté` ou
   `doublon`, qui l'a posée et quand. Seules comptent les étiquettes posées par un compte de la
   liste `config/validateurs_d7.yaml`. Voir §7 pour le contenu de cette liste.

## 6. Ce qui est laissé au constructeur

- Le choix des flux de presse (RSS des médias, extraits GDELT déjà archivés, ou les deux) et les
  règles de repérage, à condition qu'elles soient **déterministes** et versionnées (pas de modèle
  de langage dans la v1 : la relecture humaine reste le filtre).
- La table médias → groupes de propriétaires, versionnée dans `config/`, avec sa source citée.
- Les règles de regroupement des articles en un même fait.
- Le format de l'issue et de l'instantané archivé.
- Quelles sources institutionnelles brancher dès la v1 (le Défenseur des droits et la justice
  administrative sont déjà collectés ; CGLPL, CNCDH, CEDH sont nouveaux).
- La présentation de D7 sur le site, dans le style des autres dimensions.

## 7. Questions ouvertes (réponses de l'utilisateur attendues)

1. ~~Qui valide ?~~ **Réponse (2026-11-10) : l'utilisateur seul pour le moment.** Il fige aussi les
   critères des catégories avant le premier comptage. `config/validateurs_d7.yaml` ne contient que
   son compte GitHub ; le site indique « faits validés par un seul relecteur » tant que c'est le cas,
   et la liste pourra s'étendre sans changement de code.
2. ~~Profondeur historique ?~~ **Réponse (2026-11-10) : reprise du passé depuis juillet 2024**
   (début de la XVIIe législature). Conséquences, choix de Claude :
   - presse passée : les flux RSS ne remontent pas si loin ; la reprise s'appuie sur les extraits
     GDELT (adresses d'articles de médias français), dont le rattrapage, aujourd'hui arrêté au
     27/02/2026, est prolongé jusqu'au 1er juillet 2024 (≈ 18 Mo téléchargés par jour traité,
     seul l'extrait filtré est archivé) ;
   - sources institutionnelles : reprises sur la même période (extraction, pas de validation) ;
   - **ouverture des fiches étalée** : au plus 20 nouvelles fiches de reprise par jour, les plus
     récentes d'abord, en plus des fiches du jour ; le site affiche l'avancement (« reprise
     validée jusqu'au … ») et D7 n'entre dans l'indice d'ensemble qu'une fois la reprise
     entièrement relue, pour ne pas afficher une série incomplète comme une baisse.

## 8. Révision du 2026-11-10 (après mesure du volume, validée par l'utilisateur)

Mesure sur 3 jours : le flux GDELT anglophone ne contient aucun média français ; avec le flux
traduit, la règle « même événement GDELT » ne donne aucun candidat (GDELT attribue presque
toujours un identifiant par article). Décision de l'utilisateur : **flux RSS** des médias
français pour le flux quotidien (`config/flux_rss.yaml`, `collectors/rss.py`,
`extract/d7_rss.py`) :
- mots-clés par catégorie, terme d'autorité et de contexte, fixés dans la grille (bloc `rss`) ;
- lieu : commune de 5 000 habitants ou plus citée dans le titre ou le résumé (liste INSEE) ;
- même fait : même commune, même catégorie, à deux jours au plus ; recoupement par deux groupes
  de propriétaires après fusion des dépêches reprises ;
- flux lus toutes les heures (ils ne gardent que leurs derniers articles).
GDELT (flux traduit, regroupé par jour, lieu et catégorie, lieu « France » écarté) ne sert plus
qu'à la reprise, pour les jours antérieurs au début de la collecte RSS. Le signalement manuel
reste ouvert. Compte serveur : `arnaudmanza` (`comptes_serveur`), validateur : `MZA-code`.
Essai réel du 2026-11-10 : 1 154 articles, un candidat (Brest, trombinoscopes, 4 groupes).
