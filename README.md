# Baromètre de la santé démocratique

Mesurer, à partir de faits vérifiables et d'une grille publiée à l'avance, à quelle distance la
France se trouve d'un régime autoritaire. L'outil note des **actes**, jamais des partis : chaque
chiffre affiché remonte jusqu'aux documents officiels qui le justifient.

> **Statut : prototype.** La grille `v0` est un brouillon : aucun seuil ni aucune pondération
> n'est encore fixé par le comité de méthode. Le pipeline publie donc des **métriques brutes**,
> jamais de note officielle. L'indice affiché en tête de page est **illustratif** (moyenne
> simple, poids égaux).

Point de départ et règles : [BRIEF.md](BRIEF.md) · Choix et constats : [DECISIONS.md](DECISIONS.md) ·
Grille : [config/grid.v0.yaml](config/grid.v0.yaml) et [CHANGELOG-GRILLE.md](CHANGELOG-GRILLE.md) ·
Seeds manuels : [data/seed/README.md](data/seed/README.md)

## Principes

1. **Archive brute immuable** : tout document collecté est conservé tel quel (URL, date,
   SHA-256) ; on dérive, on ne retouche jamais.
2. **Traçabilité** : chaque fait pointe vers au moins un document brut, chaque métrique vers ses
   faits.
3. **Grille versionnée et figée** : indicateurs, seuils et pondérations vivent dans
   `config/grid.vX.yaml`, jamais dans le code.
4. **Pas de note sans seuils figés** : tant qu'un seuil vaut `null`, seule la métrique brute est
   produite.
5. **Neutralité dans le code** : aucun nom de parti, de personnalité ou de camp dans la logique de
   calcul ni dans les filtres (un test le vérifie pour le temps de parole par parti).
6. **Reproductibilité** : `make rebuild` reconstruit toute la base dérivée depuis l'archive brute,
   de façon déterministe (`make reproducible` le vérifie).

Règles éditoriales : ton informatif, aucun chiffre sans source vérifiée mot pour mot, pas de nom de
journaliste, aucun contenu payant archivé.

## Ce que mesure le baromètre

### Indicateurs de la grille (13)

| Code | Indicateur | Depuis |
| --- | --- | --- |
| D1.1 | Règles électorales modifiées peu avant un scrutin | 1993 |
| D1.2 | Scrutins reportés | 1990 |
| D2.1 | Contournement du Parlement (49.3 et ordonnances) | 1958 |
| D2.2 | Procédure accélérée | 1978 |
| D3.1 | Régimes d'exception | 1958 |
| D3.2 | Lois censurées par le Conseil constitutionnel | 1958 |
| D4.1 | Dissolutions administratives | 1990 |
| D4.2* | Interdictions de manifester contestées devant le juge (approximation) | 2022 |
| D5.1 | Temps de parole de l'exécutif | 2025 |
| D5.2 | Journalistes inquiétés (relevé pilote, non exhaustif) | 2023 |
| D5.3 | Classement RSF de la liberté de la presse | 2002 |
| D6.1 | Techniques de renseignement (personnes surveillées) | 2016 |
| D6.2 | Fichiers créés malgré les réserves de la CNIL | 1983 |

### Contexte et regards extérieurs (non notés)

Affichés à côté des indicateurs, sans entrer dans aucun calcul : temps de parole par parti
(Arcom), journées de mobilisation nationale (ministère et organisateurs côte à côte), participation
aux élections législatives, déclarations des organes de l'ONU sur la France, couverture de la France
par la presse étrangère (GDELT).

## Sources

| Source | Accès | Mise à jour |
| --- | --- | --- |
| [Assemblée nationale](https://data.assemblee-nationale.fr) | open data | automatique |
| [DILA](https://echanges.dila.gouv.fr/OPENDATA/) : LEGI, JORF, CONSTIT, CNIL | open data | automatique |
| [Sénat](https://data.senat.fr/dosleg/) (Dosleg) | open data | automatique (hebdomadaire) |
| [Justice administrative](https://opendata.justice-administrative.fr/) | open data | automatique |
| [Arcom](https://www.arcom.fr/temps-parole/hors-elections) : temps de parole | fichiers mensuels | automatique (≈ 3 mois de décalage) |
| [RSF](https://rsf.org/fr/classement) : classement | fichier annuel | automatique |
| [CNCTR](https://www.cnctr.fr/rapports-activit%C3%A9) : rapports | PDF annuels | automatique |
| [data.gouv.fr](https://www.data.gouv.fr) : résultats électoraux | open data | automatique |
| [GDELT 2.0](https://www.gdeltproject.org/data.html) : presse en ligne mondiale | fichiers publics | automatique |
| Seeds manuels (`data/seed/`) : 49.3 avant 2012, régimes d'exception, journalistes inquiétés, mobilisations, déclarations de l'ONU, chiffres CNCTR | relevé à la main, chaque chiffre vérifié dans sa source | manuelle |

Les relevés manuels n'ont pas d'API (chiffres de manifestants, déclarations de l'ONU,
journalistes inquiétés) : ils se complètent à la main dans `data/seed/`, puis `make collect-seed`.

## Démarrage

Prérequis : Python 3.12, [uv](https://docs.astral.sh/uv/), `make`.

```sh
make install            # dépendances figées (uv)
make collect            # toutes les sources (≈ 11 Go au premier passage, plusieurs heures)
make rebuild            # archive brute -> faits -> métriques (-> notes si seuils figés)
make test               # ruff + pytest
make publication        # page autonome dans front/publication/dist/
```

## Contrôles

```sh
make verify-raw                         # recalcule le SHA-256 de toute l'archive brute
make reproducible                       # deux rebuild successifs, empreintes comparées
make controle DATE=2023-03-31           # métriques + faits + liens pour une date
make controle DATE=2023-03-31 WINDOW=legislature_16
make echantillon                        # 20 faits tirés au hasard, à vérifier à la main
```

Sorties dans `data/exports/` (CSV des métriques, rapports Markdown).

## Mise à jour quotidienne

```sh
make quotidien      # toutes les collectes, rebuild, export du prototype (une fois, à la main)
make planifier      # installe le timer systemd utilisateur : tous les jours à 6 h 30
make etat           # dernière exécution (statut, durée de chaque étape) et prochaine échéance
make nouveautes     # faits nouveaux depuis la dernière exécution (aussi fait par make quotidien)
make deplanifier    # retire le timer
```

Journaux dans `data/logs/` ; une source en panne n'empêche pas les autres (voir
`ops/quotidien.py`). Chaque jour, les faits nouveaux sont résumés dans
`data/exports/nouveautes.md`. L'historique GDELT est rattrapé progressivement (5 jours par
passage, `GDELT_JOURS`).

## Déploiement sur un serveur

- **Archive brute** : `data/raw/` n'est pas versionnée (≈ 11 Go). La copier depuis une machine
  existante (`rsync -a data/raw/ serveur:barometre/data/raw/`) ou tout recollecter avec
  `make collect`. Prévoir au moins 20 Go de disque.
- **Collecte** : `make planifier` sur le serveur (timer systemd utilisateur ; activer
  `loginctl enable-linger` pour qu'il tourne sans session ouverte).
- **Page** : `make publication` produit une page statique dans `front/publication/dist/`
  (`index.html` + `data.js`), à servir par n'importe quel serveur web. La publication
  automatique après la collecte quotidienne reste à brancher.

## Organisation

| Dossier | Rôle |
| --- | --- |
| `collectors/` | téléchargement et archivage : `an_opendata`, `senat`, `justice_admin`, `arcom`, `rsf`, `cnctr`, `dila` (LEGI, JORF, CONSTIT, CNIL), `datagouv`, `gdelt`, `seed` |
| `storage/` | schéma SQLite, archive brute immuable (`archive.py`), base (`db.py`) |
| `extract/` | documents bruts -> faits (un module par source ou indicateur) |
| `scoring/` | grille (`grid.py`), métriques (`metrics.py`), notes (`score.py`), rapports (`report.py`) |
| `front/prototype/` | page du baromètre (`index.html`) et export des données (`export_data.py`) |
| `front/publication/` | construction de la page autonome (`build.py`) |
| `ops/` | exécution quotidienne (`quotidien.py`), alerte des faits nouveaux (`nouveautes.py`), unités systemd |
| `config/` | grille, sources, paramètres des collectes |
| `data/seed/` | seeds manuels versionnés, voir leur [README](data/seed/README.md) |
| `data/raw/` | archive brute (non versionnée) |
| `data/cache/`, `data/exports/`, `data/logs/` | dérivés, supprimables |
| `tests/` | tests (pytest) et fixtures |

## Licence

À définir : code et données dérivées. Chaque source garde sa propre licence, rappelée dans
`config/sources.yaml` et sur la page.
