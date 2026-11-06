# Baromètre de la santé démocratique — Brief technique, étape 2

> À placer à la racine du dépôt et à donner à Claude Code comme point de départ.
> Méthodologie de référence : grille d'indicateurs v0 (doc « Baromètre de la santé démocratique française — Grille d'indicateurs »).

## 1. Contexte en trois phrases

Le projet mesure à quelle distance la France se trouve d'un régime autoritaire, à partir de faits vérifiables et d'une grille d'indicateurs publiée à l'avance. L'outil note des **actes**, jamais des partis : aucune logique du code ne doit dépendre de l'identité politique d'un acteur. Chaque note affichée doit pouvoir être remontée jusqu'aux documents sources qui la justifient.

## 2. Périmètre de cette étape

Construire le socle de collecte et de stockage, puis **un seul indicateur de bout en bout** :

**D2 — Contournement du Parlement** (recours au 49.3 et aux ordonnances).

Hors périmètre pour l'instant : interface du cadran, indicateurs semi-manuels, comité de notation, déploiement public.

## 3. Règles non négociables

1. **Archive brute immuable.** Tout document collecté est stocké tel quel, avec son URL, sa date de collecte et son empreinte SHA-256. On ne retouche jamais une donnée brute ; on dérive.
2. **Traçabilité.** Chaque `fact` pointe vers au moins un document brut. Chaque score pointe vers les `facts` qui l'ont produit.
3. **Grille versionnée et figée.** Indicateurs, seuils et pondérations vivent dans `config/grid.vX.yaml`. Le code de scoring lit ce fichier et n'embarque aucun seuil en dur. Changer un seuil = nouvelle version + entrée dans `CHANGELOG-GRILLE.md` + recalcul complet de l'historique.
4. **Pas de score sans seuils figés.** Tant qu'un seuil vaut `null` dans la grille, le pipeline calcule et publie la **métrique brute** mais refuse de produire une note 0-4. Cela empêche d'ajuster les seuils après avoir vu les données.
5. **Neutralité dans le code.** Aucun nom de parti, de personnalité ou de camp dans la logique de calcul ni dans les filtres. Les acteurs peuvent apparaître dans les données brutes, jamais comme critère.
6. **Reproductibilité.** `make rebuild` doit reconstruire toute la base dérivée depuis l'archive brute, de façon déterministe.

## 4. Sources de données

| Source | Contenu utile | Accès | Remarque |
| --- | --- | --- | --- |
| Open data de l'Assemblée nationale (data.assemblee-nationale.fr) | Dossiers législatifs, actes de procédure, scrutins | Téléchargement libre, JSON / XML | Source primaire pour le 49.3 |
| Tricoteuses (tricoteuses.fr, git.en-root.org/tricoteuses) | Données de l'Assemblée et du Sénat nettoyées en JSON, avec schémas | Libre | Bon point de départ ; toujours vérifier contre la source officielle |
| Open data DILA (echanges.dila.gouv.fr/OPENDATA) — fonds JORF et LEGI | Journal officiel, lois, ordonnances, décrets | Libre, XML, sans clé | LEGI est exhaustif pour lois et ordonnances depuis 1945 |
| API Légifrance via PISTE (api.piste.gouv.fr) | Même contenu, interrogeable | OAuth2, inscription manuelle | Optionnel ; à n'utiliser que si les dumps DILA ne suffisent pas |

Licence des données publiques : Licence Ouverte Etalab 2.0. Conserver la mention de source pour chaque document.

## 5. Stack proposée

- **Python 3.12** pour collecte et calcul (écosystème données, parsing XML).
- **SQLite** pour commencer (un fichier, versionnable, suffisant à ce volume), schéma compatible PostgreSQL pour plus tard.
- **pytest** pour les tests, **ruff** pour le style.
- Archive brute sur disque dans `data/raw/` (ignorée par git), indexée en base.

Si tu préfères une autre stack, propose-la avec une justification avant de coder.

## 6. Structure du dépôt

```
barometre/
├── BRIEF.md
├── CHANGELOG-GRILLE.md
├── config/
│   └── grid.v0.yaml          # indicateurs, seuils, poids
├── collectors/
│   ├── an_opendata.py        # Assemblée nationale
│   └── dila_legi.py          # lois et ordonnances
├── extract/
│   └── parlement.py          # documents bruts -> facts
├── scoring/
│   ├── metrics.py            # facts -> métriques brutes
│   └── score.py              # métriques -> notes 0-4 (si seuils figés)
├── storage/
│   ├── schema.sql
│   └── db.py
├── data/raw/                 # archive immuable (gitignore)
├── tests/
└── Makefile                  # collect, extract, score, rebuild, test
```

## 7. Modèle de données

```sql
CREATE TABLE sources (
  id TEXT PRIMARY KEY,            -- 'an_opendata', 'dila_legi'
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  licence TEXT NOT NULL
);

CREATE TABLE raw_documents (
  id INTEGER PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  external_id TEXT NOT NULL,      -- identifiant dans la source
  url TEXT NOT NULL,
  fetched_at TEXT NOT NULL,       -- ISO 8601
  sha256 TEXT NOT NULL,
  path TEXT NOT NULL,             -- chemin dans data/raw/
  UNIQUE (source_id, external_id, sha256)
);

CREATE TABLE facts (
  id INTEGER PRIMARY KEY,
  indicator_id TEXT NOT NULL,     -- ex. 'D2.contournement_parlement'
  fact_type TEXT NOT NULL,        -- ex. 'engagement_49_3', 'ordonnance_publiee', 'loi_promulguee'
  occurred_on TEXT NOT NULL,      -- date du fait
  title TEXT NOT NULL,
  official_ref TEXT,              -- n° de loi, NOR, n° de texte
  extraction_method TEXT NOT NULL,-- nom + version de l'extracteur
  verified_by_human INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE fact_sources (
  fact_id INTEGER REFERENCES facts(id),
  raw_document_id INTEGER REFERENCES raw_documents(id),
  PRIMARY KEY (fact_id, raw_document_id)
);

CREATE TABLE metrics (
  indicator_id TEXT NOT NULL,
  period_end TEXT NOT NULL,       -- fin de la fenêtre glissante
  window_days INTEGER NOT NULL,
  name TEXT NOT NULL,             -- ex. 'ratio_contournement'
  value REAL NOT NULL,
  grid_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (indicator_id, period_end, name, grid_version)
);

CREATE TABLE scores (
  indicator_id TEXT NOT NULL,
  period_end TEXT NOT NULL,
  score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 4),
  grid_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (indicator_id, period_end, grid_version)
);

CREATE TABLE score_facts (           -- traçabilité score -> faits
  indicator_id TEXT, period_end TEXT, grid_version TEXT,
  fact_id INTEGER REFERENCES facts(id)
);
```

## 8. Premier indicateur : D2 — Contournement du Parlement

**Ce qu'on mesure** : la part des textes adoptés sans vote final du Parlement ou par délégation au gouvernement.

**Faits à extraire**
- `engagement_49_3` : chaque engagement de la responsabilité du gouvernement sur un texte (article 49 alinéa 3), avec date et texte concerné.
- `ordonnance_publiee` : chaque ordonnance publiée au Journal officiel.
- `loi_promulguee` : chaque loi promulguée.

**Métriques**, sur une fenêtre glissante de 365 jours, calculées chaque jour :
- `nb_49_3`, `nb_ordonnances`, `nb_lois`
- `ratio_contournement = (textes adoptés via 49.3 + ordonnances) / (lois promulguées + ordonnances)`

**Seuils** : `null` dans `grid.v0.yaml`, à fixer par le comité avant tout calcul de note. Le pipeline produit seulement les métriques tant qu'ils ne sont pas renseignés.

**Points à vérifier dans les données, pas à supposer**
- Comment l'open data de l'Assemblée code un engagement de responsabilité (type ou code d'acte dans les dossiers législatifs). Explorer d'abord, documenter le champ retenu dans `extract/parlement.py`, ajouter un test sur un cas connu.
- Profondeur historique réelle de chaque source. Si l'open data de l'Assemblée ne remonte pas à 1958, prévoir un fichier `data/seed/49_3_historique.csv` construit à partir d'une liste officielle, chaque ligne avec sa référence, marquée `extraction_method = 'seed_manuel'`.
- Distinguer ordonnances de l'article 38 et ordonnances d'autres fondements, et garder le fondement dans le fait.

## 9. Plan de travail et critères d'acceptation

1. **Socle** — schéma, `db.py`, `Makefile`, CI de tests.
   *Accepté si* `make test` passe et `make rebuild` sur une base vide ne plante pas.
2. **Collecteur DILA LEGI** — téléchargement incrémental, archivage, index en base.
   *Accepté si* deux exécutions successives ne créent aucun doublon et chaque fichier a son SHA-256.
3. **Collecteur Assemblée** — idem pour les dossiers législatifs de la législature en cours, puis des précédentes.
4. **Extraction** — `facts` pour les trois types, chacun relié à ses documents bruts.
   *Accepté si* un échantillon de 20 faits tirés au hasard est vérifiable à la main via `official_ref` et l'URL.
5. **Métriques** — calcul quotidien sur fenêtre glissante, export CSV.
   *Accepté si* `make rebuild` donne deux fois exactement le même résultat.
6. **Rapport de contrôle** — script qui sort, pour une date donnée, la valeur de chaque métrique et la liste des faits qui la composent, avec leurs liens.

À chaque étape : s'arrêter, résumer ce qui a été fait, les choix pris et les incertitudes rencontrées dans les données, avant de passer à la suivante.

## 10. Questions ouvertes pour le porteur de projet

- Fenêtre de 365 jours, ou par législature, ou les deux ?
- Un même texte soumis plusieurs fois au 49.3 (lectures successives) compte-t-il une ou plusieurs fois ?
- Faut-il pondérer les ordonnances de ratification rapide différemment de celles jamais ratifiées ?
