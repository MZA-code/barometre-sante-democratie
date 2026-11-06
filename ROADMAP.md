# Feuille de route

Mise à jour : 6 novembre 2026. Choix détaillés et constats : [DECISIONS.md](DECISIONS.md).

## Où en est le projet

Le socle tourne : 13 indicateurs collectés et recalculés chaque matin depuis les sources
officielles, reconstruction déterministe (`make reproducible`), 331 tests, CI verte sur
[GitHub](https://github.com/MZA-code/barometre-sante-democratie). Aucune note n'est produite :
les seuils de la grille `v0` valent `null` en attendant le comité de méthode. La page affiche un
**indice illustratif** (moyenne simple des positions historiques, 52 sur 100 au 4 novembre 2026)
et peut désormais être mise en ligne automatiquement sur un hébergement statique.

## Fait

### Indicateurs de la grille

| Code | Indicateur | Source | Depuis |
| --- | --- | --- | --- |
| D1.1 | Règles électorales modifiées peu avant un scrutin | Journal officiel (DILA JORF) | 1993 |
| D1.2 | Scrutins reportés (y compris dans le corps des lois) | Journal officiel | 1990 |
| D2.1 | Contournement du Parlement (49.3, ordonnances) | Assemblée nationale + seed avant 2012 | 1958 |
| D2.2 | Procédure accélérée | Assemblée nationale, Sénat | 1978 |
| D3.1 | Régimes d'exception | Journal officiel + seed | 1958 |
| D3.2 | Lois censurées par le Conseil constitutionnel | DILA CONSTIT | 1958 |
| D4.1 | Dissolutions administratives | Journal officiel | 1990 |
| D4.2* | Interdictions de manifester contestées devant le juge | justice administrative | 2022 |
| D5.1 | Temps de parole de l'exécutif | Arcom | 2025 |
| D5.2 | Journalistes inquiétés (relevé pilote 2023-2025) | seed vérifié | 2023 |
| D5.3 | Classement RSF | RSF | 2002 |
| D6.1 | Techniques de renseignement | CNCTR | 2016 |
| D6.2 | Fichiers créés malgré les réserves de la CNIL | DILA CNIL, Journal officiel | 1983 |

### Contexte et regards extérieurs (non notés)

- [x] **Temps de parole par parti** (Arcom, 21 mois) : libellés de l'Arcom tels quels, somme des
  partis égale au total publié à la seconde près, filtres par période et par média.
- [x] **Déclarations de l'ONU** : 10 déclarations (2019-2026), 20 extraits recopiés mot pour mot
  depuis ohchr.org, filtre par thème.
- [x] **Presse étrangère** (GDELT) : articles étrangers sur des événements situés en France,
  thèmes « manifestations » et « usage de la force par la police » selon le codage de GDELT, pays
  des sites en français ; historique rattrapé jour par jour (47 jours archivés au 6 novembre,
  rattrapage en cours vers janvier 2025).
- [x] **Mobilisations nationales** : 2016, 2019-2020, 2023, plus 7 journées ajoutées le 6 novembre
  (10 et 18 septembre, 2 octobre 2025 ; 17, 24, 31 octobre et 5 novembre 2026), chaque chiffre
  retrouvé avec son attribution dans un article en accès libre.
- [x] Participation aux élections législatives.

### Page et mise en ligne

- [x] **En-tête** : indice illustratif (jauge 0-100, 50 = habituel, sans zones colorées) et vue
  d'ensemble des 13 indicateurs, chacun situé dans son propre historique (rang moyen).
- [x] **Sommaire** qui suit le défilement : colonne à gauche sur grand écran, barre collante sur
  mobile.
- [x] **Mise en ligne** : `make deployer` (rsync en SSH ou FTPS avec certificat vérifié), dernière
  étape de la collecte quotidienne ; configuration locale hors git.
- [x] **Référencement** : chiffres écrits dans le HTML (lisibles sans JavaScript), description,
  Open Graph, JSON-LD `Dataset`, `barometre.md`, `indicateurs.csv`, `llms.txt`, `robots.txt`.
- [x] Dépôt GitHub créé, premiers commits poussés, CI verte.

### Socle technique

Archive brute immuable (SHA-256), reconstruction déterministe, contrôle d'échantillons, collecte
quotidienne à 6 h 30 (timer systemd, attente du réseau, alerte des faits nouveaux dans
`data/exports/nouveautes.md`), dossier des seuils et document de vérification humaine.

## Reste à faire

Rien ne peut être noté tant que le comité n'a pas figé les seuils, et ses décisions supposent que
les saisies manuelles aient été relues.

### Priorité 1 — bloquant pour publier une note

- [ ] **Comité** : figer les 4 bornes des 13 indicateurs (dossier des seuils et variantes), les
  libellés 0-4, les pondérations et le niveau d'alerte global.
- [ ] **Comité** : décider du sort de l'indice illustratif (garder, pondérer, retirer).
- [ ] **Comité** : questions de méthode en suspens — lois de finances dans D2.2, durée cumulée des
  reports pour D1.2, périmètre de D4.2* (« rassemblement » non déclaré, supporters), comparaison
  éventuelle du temps de parole par parti à un critère de représentativité.
- [ ] **Vérification humaine** des saisies manuelles, ligne par ligne : régimes d'exception
  (13 périodes sur 20), seed 49.3 historique, journalistes inquiétés (18 lignes), seed CNCTR,
  déclarations de l'ONU (10), mobilisations 2025-2026 (13 chiffres).
- [ ] **Vérification humaine** des chiffres de manifestants plus anciens : 12 non confirmés, dont
  2 à supprimer faute de confirmation (05/07/2016, 10/12/2019) ; attribution 2016 à confirmer.
- [ ] **Vérification humaine** des cas limites repérés automatiquement : 12 rapprochements CNIL
  de faible confiance, 3 points de la table des scrutins, reports trouvés dans le corps des lois,
  échantillon des 97 décisions D4.2* retirées le 6 novembre.

### Priorité 2 — mise en ligne et fiabilité

- [ ] **Premier envoi sur O2Switch** : remplir `config/deploiement.local` (SSH ou FTPS), puis
  `make deployer` ; vérifier la page à son adresse provisoire.
- [ ] **Domaine** : une fois choisi, `SITE_URL=` dans `config/deploiement.local` (URL canonique,
  `sitemap.xml`), puis HTTPS chez l'hébergeur.
- [ ] **Licence** du code et des données dérivées à choisir (README).
- [ ] Licences à confirmer : Arcom (non explicite), conditions d'utilisation de GDELT,
  législatives 2022 2ᵉ tour sur data.gouv.fr (admise par dérogation).
- [ ] Remplacer le CDN Tailwind (déconseillé en production) par une feuille de style construite.
- [ ] Bornes de catégorie RSF avant 2022 : introuvables à ce jour.
- [ ] Accès aux données Mapping Media Freedom : demande au consortium MFRR (démarche manuelle).
- [ ] Mettre à jour les chiffres D4.2* dans le dossier des seuils et le document de vérification
  humaine (documents claude.ai, à republier s'ils ont disparu).

### Priorité 3 — extensions

- [ ] **Mobilisations** : journées de 2024 ; décompte des organisateurs du 10 septembre 2025.
- [ ] **ONU** : observations finales du comité des droits de l'homme (2024), Examen périodique
  universel (2023), réponses de la France (base des communications interdite aux robots : à
  consulter à la main).
- [ ] **Alerte** : signaler dans `nouveautes.md` les jours où la presse étrangère parle beaucoup
  de manifestations en France, pour savoir quand compléter les relevés manuels.
- [ ] Nouvelles sources : CNCDH, Défenseur des droits, CGLPL.
- [ ] Historique plus long : participation 2002-2012, journalistes inquiétés avant 2023, temps de
  parole avant 2025.
- [ ] Performance : cache du scan CNIL, factorisation des caches de scan (reconstruction ≈ 15 s,
  non urgent).

## Recette du front

Premier passage le 6 novembre 2026 (Chromium, 1366 px et 375 px, thèmes clair et sombre) :
10 anomalies, toutes corrigées et revérifiées.

| # | Constat | Correction |
| --- | --- | --- |
| A1 | Graphiques plus larges que l'écran après un redimensionnement | graphiques bornés à leur conteneur puis redessinés |
| A2 | Carte D5.2 à « 0 » alors que le relevé s'arrête fin 2025 | carte calée sur la fin du relevé, mentionnée |
| A3 | Texte D1.2 périmé (reports dans le corps des lois) | phrase récrite |
| A4 | Étiquette « en cours » tronquée (D4.2*) | étiquette repositionnée |
| A5 | « Aucun » au lieu de « Aucune » (D1.1) | accord avec l'unité |
| A6 | Rang RSF « 1e » | « 1er » |
| A7 | « Bande claire » faux en thème sombre | texte sans couleur |
| A8 | Titre H1 après deux H2 | un seul H1, en tête |
| A9 | Rang RSF lu à l'envers (« supérieur à 13 % ») | texte propre au rang |
| A10 | Segments « autre issue » invisibles en thème sombre (D4.2*) | gris plus soutenu (≈ 5:1) |

Reste à recetter :

- [ ] La page à son adresse en ligne (O2Switch).
- [ ] Les liens vers les sources (≈ 1 160 liens, 18 domaines) : échantillon.
- [ ] Infobulles et clics vers les sources dans les graphiques.
- [ ] Firefox, Safari, lecteur d'écran.
- [ ] Relecture éditoriale complète pour la neutralité du ton, par une personne.
- [ ] Contraste limite des barres secondaires (« recours rejeté », « avis sans réserve ») : à
  trancher.
