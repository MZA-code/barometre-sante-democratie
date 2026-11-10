# D7 · Libertés en pratique — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** ajouter l'indicateur D7 (atteintes aux libertés en pratique). Il compte les constats
institutionnels et les faits de presse recoupés puis validés à la main par issues GitHub, et le
site se republie dans l'heure après chaque décision.

**Architecture :**
- **Presse.** Les candidats sont dérivés des extraits GDELT déjà archivés (codes CAMEO, au moins
  deux groupes de presse). Leurs titres sont collectés pour dédoublonner les dépêches. Le serveur
  ouvre une issue par candidat ; un instantané de chaque issue est archivé comme document brut, et
  les faits D7 en sont dérivés.
- **Voie institutionnelle.** Constats de manquement du Défenseur des droits, à partir des fiches
  déjà collectées.
- **Tâche horaire.** Elle ne refait que la lecture des issues et la publication.

**Tech Stack :** Python 3.12, SQLite, pytest, ruff, API REST GitHub (urllib, sans dépendance
nouvelle), Makefile, cron cPanel.

**Spec :** `docs/superpowers/specs/2026-11-10-libertes-en-pratique-design.md` (à lire avant toute
tâche : §2 anti-objectifs, §5 bis choix, §7 réponses de l'utilisateur).

## Global Constraints

- BRIEF.md §3 : archive brute immuable (`storage.archive.store`, jamais d'UPDATE/DELETE), chaque
  fait cite ≥ 1 document brut (`write_facts` le vérifie), seuils `null`, aucun nom de parti ou de
  personne dans la logique, `make rebuild` déterministe depuis l'archive.
- Aucune dépendance Python nouvelle (`uv.lock` inchangé) : HTTP par `collectors.http`.
- Code, messages, commentaires et textes du site en français, dans le style des modules voisins
  (docstring de module qui documente source, règles, usage).
- Indicateur : `D7.libertes_en_pratique`, `history_start: 2024-07-01`, fenêtres `rolling 365` et
  `legislature`.
- Fact types : `fait_presse_valide`, `constat_institutionnel`. Métriques :
  `nb_faits_presse_valides`, `nb_constats_institutionnels`, `nb_atteintes_pratique` (somme,
  métrique notée).
- Catégories (clés exactes) : `interpellations`, `expression`, `reunion`, `surveillance`, `force`,
  `decisions_ignorees`.
- Étiquettes GitHub (noms exacts) : `d7`, `en-attente`, `validé`, `rejeté`, `doublon`,
  `cat:<clé>`.
- Recoupement : ≥ 2 **groupes de propriétaires** distincts, après fusion des articles au titre
  identique une fois normalisé (dépêche reprise).
- Issue : titre `[D7] <libellé catégorie> · <lieu> · <AAAA-MM-JJ>` ; corps = média, date, lien de
  chaque article, **sans titre d'article** ; marqueur caché `<!-- d7:gdelt:<evenement_id> -->`.
- Seules comptent les étiquettes posées par un compte de `config/validateurs_d7.yaml` (contenu
  initial : `MZA-code`).
- Reprise : au plus **20** issues de reprise ouvertes par jour, plus récentes d'abord, en plus
  des candidats des 7 derniers jours.
- D7 hors de l'indice d'ensemble tant qu'un candidat antérieur à aujourd'hui n'a pas d'issue
  décidée.
- Secrets hors dépôt : `config/github.local` (gitignoré), clés `GITHUB_TOKEN=` et
  `GITHUB_DEPOT=MZA-code/barometre-sante-democratie`.

## Review Focus

1. **Étiquette posée par un tiers** (compte hors liste) ou étiquettes contradictoires
   (`validé` + `rejeté`, deux `cat:`) : le fait ne compte pas et figure dans le rapport « à
   corriger ». Test dans la tâche 5.
2. **Issue fermée ou supprimée côté GitHub** : la fermeture ne change rien, seules les étiquettes
   comptent. Une issue disparue de la liste garde son dernier instantané. Test dans la tâche 4.
3. **API GitHub indisponible, quota épuisé (403/429) ou jeton absent** : la tâche horaire sort
   proprement (code 0, message), sans republication ni trace partielle. Tests dans les tâches 4
   et 7.
4. **Tâche horaire lancée pendant le cron de 6 h 30** : verrou commun `data/.quotidien.lock`, la
   tâche horaire saute son tour. Test dans la tâche 7.
5. **Relance de la publication des issues** (double cron, plantage au milieu) : aucune issue en
   double, grâce au marqueur relu dans les instantanés **et** dans la liste des issues ouvertes
   avant toute création. Test dans la tâche 6.

---

### Task 1 : grille, configuration et calcul de D7

**Files :**
- Modify : `config/grid.v0.yaml` (nouvel indicateur après D6), `CHANGELOG-GRILLE.md`,
  `scoring/metrics.py` (`DAILY_METRICS`), `.gitignore` (`config/github.local`)
- Create : `config/medias_groupes.yaml`, `config/validateurs_d7.yaml`,
  `config/github.local.exemple`
- Test : `tests/test_d7_grille.py`

**Interfaces :**
- Produces :
  - `grid.indicators["D7.libertes_en_pratique"]` ;
  - bloc YAML `categories:` de l'indicateur, chaque clé portant `libelle`, `compte`,
    `ne_compte_pas` (listes de phrases) et `codes_cameo` (liste, éventuellement vide). Le calcul
    l'ignore ; les tâches 2, 6 et 8 le lisent par `scoring.grid.load_raw(path) -> dict` (à créer
    si absent : YAML brut) ;
  - `config/medias_groupes.yaml` : `groupes: {<groupe>: [<domaine>, ...]}`, avec une `source:`
    citée en tête (carte « Médias français, qui possède quoi », Monde diplomatique et Acrimed,
    édition datée). Couvrir au moins la presse nationale, l'AFP, les principaux régionaux,
    France Télévisions et Radio France ;
  - `config/validateurs_d7.yaml` : `validateurs: [MZA-code]`.

- [ ] **Step 1 : écrire les tests**

```python
def test_d7_dans_la_grille():
    ind = load_grid().indicators["D7.libertes_en_pratique"]
    assert ind.fact_types == ("fait_presse_valide", "constat_institutionnel")
    assert ind.scored_metric == "nb_atteintes_pratique"
    assert str(ind.history_start) == "2024-07-01"
    assert not ind.thresholds_frozen


def test_categories_figees():
    cats = load_raw(GRID_PATH)["indicators"]["D7.libertes_en_pratique"]["categories"]
    assert set(cats) == {
        "interpellations",
        "expression",
        "reunion",
        "surveillance",
        "force",
        "decisions_ignorees",
    }
    assert all(c["libelle"] and c["compte"] and c["ne_compte_pas"] for c in cats.values())


def test_comptage_d7():  # deux faits presse + un constat le même jour
    # fixture en mémoire : init_db, 3 faits D7, compute() -> fenêtre glissante du jour
    assert valeurs["nb_faits_presse_valides"] == 2
    assert valeurs["nb_constats_institutionnels"] == 1
    assert valeurs["nb_atteintes_pratique"] == 3


def test_domaine_dans_un_seul_groupe():
    groupes = yaml.safe_load(open("config/medias_groupes.yaml"))["groupes"]
    domaines = [d for ds in groupes.values() for d in ds]
    assert len(domaines) == len(set(domaines)) and "afp.com" in domaines
```

- [ ] **Step 2 : lancer les tests, qui doivent échouer.** `uv run pytest tests/test_d7_grille.py -v` : échec (indicateur absent).
- [ ] **Step 3 : implémenter.**
  - Grille : l'indicateur avec `description`, `categories`, seuils `null` et `weight: null`.
  - `compte` et `ne_compte_pas` : critères constatables (spec §5 bis.2). Par exemple, pour
    `interpellations`, « au moins 10 interpellations lors d'un même événement, rapportées par
    deux groupes » ; pour `reunion`, « une interdiction contestée devant le juge ne compte pas
    (D4.2\*) » ; les journalistes vont dans D5.2.
  - `codes_cameo` :
    - `interpellations` : `173` ;
    - `force` : `175`, `18`, `19` (racines), avec la police (`COP`) comme acteur 1 ;
    - `reunion` : `1721`, `1723`, `175` quand l'acteur 2 est `OPP`, `CVL` ou absent ;
    - `expression` : `1721`, `1722` ;
    - `surveillance` et `decisions_ignorees` : `[]` (pas de code CAMEO : voie institutionnelle
      ou issue ouverte à la main, voir tâche 6).
  - Trois entrées `count` dans `DAILY_METRICS` ; la somme comme troisième entrée « count » sur
    les deux types.
  - Entrée datée du 2026-11-10 dans `CHANGELOG-GRILLE.md`, au même format que les ajouts du 05/11.
- [ ] **Step 4 : relancer les tests, qui doivent passer.** `uv run pytest -q` : tout vert.
- [ ] **Step 5 : message de commit prévu** « D7 : indicateur, catégories et groupes de presse » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 2 : candidats presse dérivés de GDELT

**Files :**
- Create : `extract/d7_candidats.py`
- Test : `tests/test_d7_candidats.py`

**Interfaces :**
- Consumes : `extract.gdelt.lire_jour(data: bytes) -> tuple[list[str], list[dict]]`, colonnes
  de `collectors.gdelt.COLONNES` ; config de la tâche 1.
- Produces :
  - `@dataclass(frozen=True) class Candidat` : `evenement_id: str`, `jour: str` (AAAA-MM-JJ),
    `categorie: str`, `lieu: str`, `articles: tuple[Article, ...]`, `groupes: tuple[str, ...]` ;
  - `@dataclass(frozen=True) class Article` : `url: str`, `domaine: str`, `groupe: str`,
    `mention_utc: str` ;
  - `categorie(row: dict, categories: dict) -> str | None` ;
  - `groupe_de(domaine: str, groupes: dict) -> str | None` : sous-domaines rattachés au domaine
    parent, `None` si inconnu ;
  - `pre_candidats(rows: list[dict], categories: dict, groupes: dict) -> list[Candidat]` :
    regroupement par `evenement_id`, seuls les articles de domaines connus, ≥ 2 groupes ;
  - `pre_candidats_archives(conn, raw_dir, depuis: dt.date) -> list[Candidat]` : tous les jours
    archivés, triés par (`jour`, `evenement_id`), déterministe.

- [ ] **Step 1 : écrire les tests.**
  - `test_categorie_arrestation_par_police` : `code_evenement="173"`, `acteur1_type="COP"`
    donne `"interpellations"`.
  - `test_categorie_hors_d7` : `code_evenement="040"` donne `None`.
  - `test_un_seul_groupe_ne_suffit_pas` : deux domaines du même groupe donnent `[]`.
  - `test_deux_groupes_recoupent` : `lemonde.fr` + `lefigaro.fr` donnent 1 candidat,
    `groupes` triés.
  - `test_domaine_inconnu_ignore` : `blog-perso.fr` + `lemonde.fr` donnent `[]`.
  - `test_sous_domaine` : `www.ouest-france.fr` va dans le groupe d'`ouest-france.fr`.
  - `test_categories_concurrentes` : l'événement prend la première catégorie dans l'ordre de la
    grille.
- [ ] **Step 2 : lancer les tests, qui doivent échouer.** `uv run pytest tests/test_d7_candidats.py -v` : échec à l'import.
- [ ] **Step 3 : implémenter `extract/d7_candidats.py`.** Le lieu est la colonne `lieu` telle
  quelle.
- [ ] **Step 4 : relancer les tests, qui doivent passer.** `uv run pytest tests/test_d7_candidats.py -v` : PASS.
- [ ] **Step 5 : mesurer le volume.** Commande :

```bash
uv run python -c "from extract.d7_candidats import *; ..." # compter par jour sur l'archive locale
```

  Rapporter à l'utilisateur la moyenne et le maximum de candidats par jour et la répartition par
  catégorie, sur les jours GDELT archivés. **Point d'arrêt :** si la moyenne dépasse 15 par
  jour, proposer de durcir la règle (≥ 3 groupes, ou ≥ N mentions) et attendre sa réponse avant
  la tâche 6.
- [ ] **Step 6 : message de commit prévu** « D7 : candidats presse depuis GDELT » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 3 : titres des articles candidats et fusion des dépêches

**Files :**
- Create : `collectors/presse_titres.py`
- Modify : `extract/d7_candidats.py` (`candidats(...)`), `config/sources.yaml` (source
  `presse_titres`), `Makefile` (`collect-titres`)
- Test : `tests/test_presse_titres.py`, `tests/test_d7_candidats.py`

**Interfaces :**
- Consumes : `pre_candidats_archives`, `storage.archive.store`, `collectors.http.urlopen`.
- Produces :
  - `titre_de_page(html: bytes) -> str | None` : `og:title`, sinon `<title>`, entités décodées ;
  - `collect(conn, raw_dir, opener=urlopen, sleep=time.sleep, depuis=dt.date(2024, 7, 1)) -> int` :
    pour chaque URL de pré-candidat non archivée, lit au plus 256 Kio, puis archive un JSON
    `{"url", "titre"}` (`external_id` = sha256 de l'URL, `suffix=".json"`). Une page en échec est
    archivée avec `"titre": null` (pas de réessai infini). Une requête par seconde ;
  - `normaliser_titre(t: str) -> str` : minuscules, sans accents ni ponctuation, suffixe
    « - <média> » retiré ;
  - `candidats(conn, raw_dir, depuis) -> list[Candidat]` : pré-candidats, articles au même titre
    normalisé fusionnés en une source, puis ≥ 2 groupes de nouveau exigés. Un article sans titre
    connu reste une source à part entière.

- [ ] **Step 1 : écrire les tests.**
  - `titre_de_page` : cas `og:title`, cas `<title>` seul, cas sans titre.
  - `test_depeche_reprise_ne_recoupe_pas` : deux groupes, même titre normalisé, donnent `[]`.
  - `test_titres_differents_recoupent` : 1 candidat.
  - `test_collect_archive_une_fois` : faux opener, deux passages, une seule requête par URL.
  - `test_page_en_echec` : `titre` vaut `null`, pas d'exception.
- [ ] **Step 2 : lancer les tests, qui doivent échouer.**
- [ ] **Step 3 : implémenter.** Le texte des articles n'est jamais archivé, seulement le JSON
  (spec §2).
- [ ] **Step 4 : relancer les tests, qui doivent passer.** `uv run pytest -q` : tout vert.
- [ ] **Step 5 : message de commit prévu** « D7 : titres des candidats, fusion des dépêches » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 4 : instantanés des issues GitHub

**Files :**
- Create : `collectors/github_d7.py`
- Modify : `config/sources.yaml` (source `github_d7`), `Makefile` (`collect-decisions`)
- Test : `tests/test_github_d7.py`

**Interfaces :**
- Produces :
  - `lire_config(path=ROOT/"config/github.local") -> tuple[str, str] | None` : (jeton, dépôt),
    `None` si absent ;
  - `class Api` : `get(chemin: str, params: dict) -> tuple[list | dict, dict]` (corps, en-têtes),
    `post(chemin, corps) -> dict`, `patch(chemin, corps) -> dict` ; pagination par l'en-tête
    `Link` ; `ErreurApi` levée sur 4xx/5xx ;
  - `instantane(issue: dict, evenements: list[dict]) -> dict` :
    `{"numero", "etat", "titre", "corps", "etiquettes": [..triées], "poses": {etiquette: {"par": login, "le": iso}}}`.
    `poses` garde, pour chaque étiquette **présente**, son dernier événement `labeled` ;
  - `collect(conn, raw_dir, api: Api, maintenant=now_iso) -> int` :
    - liste `GET /repos/{depot}/issues?labels=d7&state=all&since=<dernier contrôle>` ;
    - pour chaque issue, `GET .../issues/{n}/events`, puis `store(..., external_id=str(numero),
      suffix=".json")` d'un JSON trié (`sort_keys`). Un contenu inchangé ne crée pas de document
      (idempotence de `store`) ;
    - enregistre un `source_checks` ;
    - retourne le nombre de documents **nouveaux** ;
  - `main()` : sans config, affiche « [github_d7] config/github.local absent : rien à faire » et
    renvoie 0 ; `ErreurApi` affiche le message et renvoie 0, sans `source_checks`.

- [ ] **Step 1 : écrire les tests** (faux `Api` en mémoire) :
  - `test_instantane_garde_le_dernier_poseur` ;
  - `test_collect_idempotent` : deux passages, `1` puis `0` ;
  - `test_issue_modifiee_nouvelle_version` ;
  - `test_issue_fermee_conserve_etiquettes` ;
  - `test_sans_config_sort_0` ;
  - `test_quota_epuise_sort_0_sans_controle` (403 avec `x-ratelimit-remaining: 0`).
- [ ] **Step 2 : lancer les tests, qui doivent échouer.**
- [ ] **Step 3 : implémenter.**
  - En-têtes : `Authorization: Bearer`, `Accept: application/vnd.github+json`,
    `X-GitHub-Api-Version: 2022-11-28`.
  - `since` : `checked_at` du dernier `source_checks` de `github_d7`, sans `since` au premier
    passage.
- [ ] **Step 4 : relancer les tests, qui doivent passer.**
- [ ] **Step 5 : message de commit prévu** « D7 : instantanés des issues GitHub » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 5 : faits D7 (presse validée et constats du Défenseur des droits)

**Files :**
- Create : `extract/d7.py`
- Modify : `extract/parlement.py` (`extract_all` : `+ d7.extract(conn, raw_dir)`)
- Test : `tests/test_d7.py`

**Interfaces :**
- Consumes : derniers instantanés (`latest_documents(conn, "github_d7")`),
  `config/validateurs_d7.yaml`, `extract.ddd.lire_fiche`, `latest_documents(conn, "ddd_juridique")`.
- Produces :
  - `decision(inst: dict, validateurs: set[str]) -> tuple[str, str | None, str | None]` : renvoie
    (`statut`, `categorie`, `motif`). `statut` vaut `valide`, `rejete`, `doublon`, `en_attente`
    ou `a_corriger`. `motif` est renseigné si le statut est `a_corriger` (étiquette d'un tiers,
    étiquettes contradictoires, aucune ou plusieurs `cat:`) ;
  - `evenement_de(corps: str) -> str | None` : lit le marqueur `<!-- d7:gdelt:<id> -->` ;
  - `extract(conn, raw_dir) -> list[FactDraft]` :
    - `fait_presse_valide` : `occurred_on` = `jour` du candidat (le candidat est recalculé par
      `candidats()` à partir de `evenement_id`) ; `attributes` = `{"categorie", "lieu", "issue",
      "valide_par", "valide_le", "groupes"}` ; `raw_document_ids` = instantané + extraits GDELT
      du jour + JSON de titres ;
    - `constat_institutionnel` : fiche DDD dont le `type` contient « Décision » **et** dont le
      résumé contient « manquement », sauf « aucun manquement », « pas de manquement » ou
      « absence de manquement ». `occurred_on` = date de la fiche. Catégorie `force` si un
      mot-clé contient « force » ou « violence », sinon `reunion`. `attributes` =
      `{"categorie", "date_acte": null, "numero"}` ;
  - `etat_d7(conn, raw_dir) -> dict` : `{"en_attente": int, "a_corriger": [(numero, motif)],
    "reprise_complete": bool, "reprise_validee_jusqu_au": str | None}`. Lu par les tâches 6 et 8.

- [ ] **Step 1 : écrire les tests.**
  - `test_valide_par_validateur` : un fait.
  - `test_valide_par_tiers_ne_compte_pas` : statut `a_corriger`, motif « étiquette posée par un
    compte non validateur ».
  - `test_valide_et_rejete_a_corriger`.
  - `test_doublon_ne_compte_pas`.
  - `test_categorie_corrigee` : le validateur change `cat:force` en `cat:interpellations`.
  - `test_constat_ddd` : une fiche de décision avec manquement donne un fait ; une fiche
    « aucun manquement » n'en donne pas ; une recommandation générale non plus.
  - `test_aucun_nom_dans_les_faits` : les attributs ne contiennent aucune autre clé que celles
    listées.
- [ ] **Step 2 : lancer les tests, qui doivent échouer.**
- [ ] **Step 3 : implémenter.** Vérifier la règle DDD sur l'archive locale (dix fiches tirées au
  hasard, résultat noté dans la docstring, comme dans les autres extracteurs).
- [ ] **Step 4 : relancer les tests, qui doivent passer.** `make rebuild` s'achève sans erreur.
- [ ] **Step 5 : message de commit prévu** « D7 : faits validés et constats du Défenseur des droits » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 6 : publication des issues candidates

**Files :**
- Create : `ops/issues_d7.py`, `.github/ISSUE_TEMPLATE/d7-signalement.md`
- Modify : `Makefile` (`publier-issues`)
- Test : `tests/test_issues_d7.py`

**Interfaces :**
- Consumes : `candidats()` (tâche 3), `collectors.github_d7.Api`, `lire_config`, les
  instantanés.
- Produces :
  - `corps_issue(c: Candidat, cat: dict) -> str` contient, dans l'ordre :
    - une ligne de contexte (lieu, date, catégorie proposée) ;
    - la liste « média (groupe) · date · lien » ;
    - les critères `compte` et `ne_compte_pas` de la catégorie ;
    - la consigne « poser `validé`, `rejeté` ou `doublon` ; corriger la catégorie en changeant
      l'étiquette `cat:` » ;
    - le marqueur `<!-- d7:gdelt:<id> -->` ;
  - `a_ouvrir(candidats, deja: set[str], aujourd_hui: dt.date, quota_reprise=20) -> list[Candidat]` :
    tous les candidats des 7 derniers jours sans issue, puis au plus `quota_reprise` plus
    anciens, du plus récent au plus ancien ;
  - `assurer_etiquettes(api)` : crée les étiquettes manquantes (noms des Global Constraints) ;
  - `publier(api, conn, raw_dir, aujourd_hui) -> int` : `deja` = marqueurs des instantanés ∪
    marqueurs des issues `d7` relues par l'API juste avant. Crée chaque issue avec ses étiquettes
    `d7`, `en-attente` et `cat:<clé>`.
  - Modèle `d7-signalement.md` : pour signaler à la main un fait sans code CAMEO (surveillance,
    décisions ignorées). Étiquettes `d7`, `en-attente`, et une section « liens (≥ 2 groupes) ».
    `evenement_de` renvoie `None` pour ces issues : `extract/d7.py` les traite avec
    `occurred_on` = date indiquée dans le corps (ligne `Date : AAAA-MM-JJ`). Ajouter ce cas et
    son test dans la tâche 5 si cette tâche est déjà faite.

- [ ] **Step 1 : écrire les tests.**
  - `test_corps_sans_titre_d_article` : aucun titre du JSON de titres n'apparaît dans le corps.
  - `test_quota_reprise` : 50 anciens candidats + 3 récents donnent 23 issues, les plus récentes
    d'abord.
  - `test_pas_de_doublon_si_issue_deja_ouverte` : le marqueur est vu par l'API mais pas encore
    dans un instantané, 0 création.
  - `test_relance_apres_plantage` : un premier passage s'arrête après 2 créations ; le second
    ne recrée pas ces 2 issues.
- [ ] **Step 2 : lancer les tests, qui doivent échouer.**
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 : relancer les tests, qui doivent passer.**
- [ ] **Step 5 : message de commit prévu** « D7 : ouverture des issues candidates » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 7 : tâche horaire, tâche quotidienne et reprise GDELT

**Files :**
- Create : `ops/decisions.py`, `ops/decisions.sh` (exécutable)
- Modify : `ops/quotidien.py` (`COLLECTES` : `collect-titres` après `collect-gdelt`, puis
  `collect-decisions` ; `publier-issues` après `deployer`), `collectors/gdelt.py`
  (`DEPUIS = dt.date(2024, 7, 1)`), `ops/quotidien.py` (`GDELT_JOURS=10`), `Makefile`
- Test : `tests/test_decisions.py`, `tests/test_quotidien.py`

**Interfaces :**
- Consumes : `ops.quotidien.LOCK_PATH`, `collectors.github_d7.collect`, les cibles `rebuild`,
  `prototype-data` et `deployer`.
- Produces : `executer(dry_run=False, lancer=subprocess.run) -> int`.
  - Verrou `LOCK_EX | LOCK_NB` pris : message « exécution quotidienne en cours, tour sauté »,
    retour 0.
  - Sinon : collecte des décisions. Si elle n'apporte rien de nouveau, retour 0 sans
    reconstruction.
  - Sinon : `rebuild`, `prototype-data`, `deployer`. Journal dans
    `data/logs/decisions.log`.
  - `decisions.sh` : même préambule que `cron.sh` (PATH, UV_PYTHON, `cd`) **sans** `git pull`,
    puis `exec nice -n 19 uv run --frozen python -m ops.decisions`.

- [ ] **Step 1 : écrire les tests.**
  - `test_verrou_pris_saute_le_tour`.
  - `test_rien_de_nouveau_pas_de_rebuild` : faux `lancer`, aucun appel à `rebuild`.
  - `test_nouveau_document_republie` : appels `rebuild`, `prototype-data`, `deployer` dans
    l'ordre.
  - Dans `test_quotidien.py` : ordre des étapes mis à jour.
- [ ] **Step 2 : lancer les tests, qui doivent échouer.**
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 : relancer les tests, qui doivent passer.** `uv run pytest -q` : tout vert.
- [ ] **Step 5 : message de commit prévu** « D7 : tâche horaire et reprise GDELT depuis juillet 2024 » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 8 : affichage sur le site

**Files :**
- Modify : `front/prototype/export_data.py` (`DIMENSIONS` + `"D7.libertes_en_pratique"`,
  champ `hors_indice`, bloc `d7`), `front/prototype/index.html`, `front/publication/tailwind.css`
  (`make css`)
- Test : `tests/test_build_web.py` (existants), `tests/test_d7_export.py`

**Interfaces :**
- Consumes : `etat_d7()` (tâche 5), faits D7.
- Produces :
  - `data.js` :
    - `dimensions[i].hors_indice` : chaîne d'explication ou `null`. Pour D7 tant que
      `reprise_complete` est faux : « reprise du passé en cours de relecture (validée jusqu'au
      … ) » ;
    - `D.d7` = `{"par_categorie": {...12 derniers mois}, "faits": [ {date, categorie, lieu,
      issue_url, sources} ], "en_attente": n, "validateurs": 1}` ;
  - page :
    - `dansIndice = d => !d.fin_couverture && !d.hors_indice`, et la note sous la jauge cite la
      raison ;
    - nouvelle section `t-d7` « D7 · Libertés en pratique », entrée de sommaire « D7 · Libertés
      en pratique » (icône `hand`) placée après D6 ;
    - la section contient : barres par catégorie, liste des faits avec lien vers l'issue, la
      mention « Faits validés par un seul relecteur » quand `validateurs == 1`, le nombre en
      attente et la limite « un sujet très couvert n'est pas forcément plus fréquent » ;
    - l'encadré de la section définition (« à ce jour… en préparation ») est mis à jour.

- [ ] **Step 1 : écrire `tests/test_d7_export.py`.**
  - `hors_indice` est renseigné si la reprise est incomplète, `None` sinon.
  - Aucune clé de nom de personne dans `D.d7.faits`.
- [ ] **Step 2 : lancer les tests, qui doivent échouer.**
- [ ] **Step 3 : implémenter, puis lancer `make css`.**
- [ ] **Step 4 : vérifier.**
  - `uv run pytest -q` : tout vert.
  - Aperçu local (`make prototype`), Playwright à 1400 et 375 px : aucun défilement
    horizontal ; D7 grisé dans la vue d'ensemble avec sa raison.
- [ ] **Step 5 : message de commit prévu** « D7 : affichage, hors indice pendant la reprise » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).

### Task 9 : mise en service sur le serveur (instructions, pas de code serveur par Claude)

**Files :**
- Create : `ops/README-d7.md`

- [ ] **Step 1 : rédiger les étapes pour l'utilisateur.**
  1. Créer un jeton à grain fin (dépôt `barometre-sante-democratie` seul, permission
     « Issues : Read and write », expiration 1 an).
  2. Créer `~/barometre/config/github.local` (`chmod 600`).
  3. Lancer `make collect-decisions` et `make publier-issues` à la main pour un premier essai.
  4. Ajouter la ligne cPanel
     `5 * * * * $HOME/barometre/ops/decisions.sh >> $HOME/barometre/data/logs/decisions.log 2>&1`.
  5. Rappeler que le cron de 6 h 30 (`30 6 * * *`) doit rester tel quel.
- [ ] **Step 2 : message de commit prévu** « D7 : instructions de mise en service » (pas de commit sans l'accord de l'utilisateur : on regroupe en fin de lot).
- [ ] **Step 3 : demander « je commite et je pousse ? »** (règle du projet),
  puis lui donner les étapes du README.
