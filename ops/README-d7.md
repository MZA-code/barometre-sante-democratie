# D7 · Libertés en pratique : mise en service sur le serveur

Ces étapes se font une seule fois, sur l'hébergement (terminal SSH ou terminal cPanel). Le cron
de 6 h 30 (`ops/cron.sh`) récupère le code ; tant que `config/github.local` n'existe pas, tout
ce qui touche à GitHub ne fait rien (sans erreur).

## 1. Préparer le compte serveur et sa clé GitHub

Le serveur agit avec le compte `arnaudmanza`, distinct du validateur `MZA-code` : ce qu'il
fait (ouvrir les fiches, poser la catégorie d'origine) ne compte jamais comme une validation,
même si la clé fuyait (`comptes_serveur` dans `config/validateurs_d7.yaml`).

1. Depuis `MZA-code` : dépôt → *Settings* → *Collaborators* → inviter `arnaudmanza` avec le
   rôle **Write** (il doit pouvoir créer des étiquettes). Accepter l'invitation depuis
   `arnaudmanza`.
2. Depuis `arnaudmanza` : *Settings* → *Developer settings* → *Personal access tokens* →
   *Tokens (classic)* → *Generate new token (classic)*. Les clés à grain fin ne donnent pas
   accès au dépôt d'un autre compte.
3. Nom : `barometre-d7` ; expiration : 1 an (noter la date) ; une seule case : **public_repo**.
4. Générer et copier la clé (elle commence par `ghp_`).

## 2. Poser la clé sur le serveur

```sh
cd ~/barometre
git pull --ff-only
cp config/github.local.exemple config/github.local
chmod 600 config/github.local
nano config/github.local      # remplacer ghp_xxx par la vraie clé
```

## 3. Premier essai à la main

```sh
cd ~/barometre
export PATH="$HOME/.local/bin:$PATH" UV_PYTHON=/opt/alt/python312/bin/python3.12
make collect-rss                        # flux RSS + liste des communes (≈ 1 min)
make collect-gdelt-trad GDELT_JOURS=3   # reprise : 3 jours de presse française (≈ 6 min)
make collect-titres                     # titres des articles candidats GDELT
uv run --frozen python -m ops.issues_d7 --dry-run   # combien d'issues seraient ouvertes
make publier-issues                     # ouvre les issues sur GitHub
make collect-decisions                  # premier instantané des issues
```

Les issues apparaissent sur
https://github.com/MZA-code/barometre-sante-democratie/issues?q=label%3Ad7 .

## 4. Ajouter la tâche horaire dans cPanel

*Tâches cron* → ajouter, réglage personnalisé « toutes les heures, à la minute 5 » :

```
5 * * * * $HOME/barometre/ops/decisions.sh >> $HOME/barometre/data/logs/decisions.log 2>&1
```

Elle lit aussi les flux RSS (ils ne gardent que leurs derniers articles) et ne republie le site
que si une décision a changé. La ligne du cron de 6 h 30
(`30 6 * * * $HOME/barometre/ops/cron.sh …`) reste telle quelle.

## Au quotidien

- Chaque matin, la collecte ouvre les issues des nouveaux faits candidats repérés dans les flux
  RSS, plus au maximum 20 issues de reprise (faits depuis juillet 2024, repérés dans GDELT,
  du plus récent au plus ancien).
- Sur GitHub (site ou application mobile), poser `validé`, `rejeté` ou `doublon`, et corriger
  l'étiquette `cat:` si besoin. Les critères sont écrits dans chaque issue.
- Un fait que la collecte ne voit pas : *New issue* → modèle « D7 · Signaler un fait ».
- La décision est en ligne dans l'heure. D7 entre dans l'indice d'ensemble une fois toute la
  reprise relue.

## Vérifier

```sh
tail -20 ~/barometre/data/logs/decisions.log
tail -40 ~/barometre/data/logs/cron.log
```
