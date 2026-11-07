# Pipeline du baromètre. Toutes les commandes passent par uv (dépendances figées dans uv.lock).
#   make test     — lint + tests
#   make rebuild  — reconstruit toute la base dérivée depuis l'archive brute

DB   ?= data/barometre.sqlite
RAW  ?= data/raw
EXPORTS ?= data/exports
GRID ?= config/grid.v0.yaml
AN_LEGISLATURES ?= 17 16 15 14
RUN  := uv run --frozen

.PHONY: css help install init collect collect-seed collect-legi collect-jorf collect-constit collect-cnil collect-senat collect-justice collect-arcom collect-rsf collect-cnctr collect-an collect-datagouv collect-gdelt collect-ddd collect-rapports verify-raw extract metrics score \
	rebuild reproducible controle echantillon prototype prototype-data publication publication-web deployer nouveautes quotidien planifier deplanifier etat lint test

help:
	@echo "Cibles : install init collect collect-seed collect-legi collect-jorf collect-constit collect-cnil collect-senat collect-justice collect-arcom collect-rsf collect-cnctr collect-an collect-datagouv collect-gdelt collect-ddd collect-rapports"
	@echo "         verify-raw"
	@echo "         extract metrics score rebuild reproducible controle echantillon lint test"
	@echo "         prototype prototype-data publication nouveautes quotidien planifier deplanifier etat"
	@echo "Variables : DB=$(DB) RAW=$(RAW) GRID=$(GRID)"

install:
	uv sync --frozen

init:
	$(RUN) python -m storage.db init --db $(DB)

collect: collect-seed collect-an collect-legi collect-jorf collect-constit collect-cnil collect-senat collect-justice collect-arcom collect-rsf collect-cnctr collect-datagouv collect-gdelt collect-ddd collect-rapports

collect-seed: init
	$(RUN) python -m collectors.seed --db $(DB) --raw-dir $(RAW)

collect-legi: init
	$(RUN) python -m collectors.dila --fund legi --db $(DB) --raw-dir $(RAW)

collect-jorf: init
	$(RUN) python -m collectors.dila --fund jorf --db $(DB) --raw-dir $(RAW)

collect-constit: init
	$(RUN) python -m collectors.dila --fund constit --db $(DB) --raw-dir $(RAW)

collect-cnil: init
	$(RUN) python -m collectors.dila --fund cnil --db $(DB) --raw-dir $(RAW)

collect-senat: init
	$(RUN) python -m collectors.senat --db $(DB) --raw-dir $(RAW)

collect-justice: init
	$(RUN) python -m collectors.justice_admin --db $(DB) --raw-dir $(RAW)

collect-rapports: init
	$(RUN) python -m collectors.rapports --db $(DB) --raw-dir $(RAW)

collect-ddd: init
	$(RUN) python -m collectors.ddd --db $(DB) --raw-dir $(RAW) $(if $(DDD_COMPLET),--complet)

collect-gdelt: init
	$(RUN) python -m collectors.gdelt --db $(DB) --raw-dir $(RAW) $(if $(GDELT_JOURS),--max-jours $(GDELT_JOURS))

collect-arcom: init
	$(RUN) python -m collectors.arcom --db $(DB) --raw-dir $(RAW)

collect-rsf: init
	$(RUN) python -m collectors.rsf --db $(DB) --raw-dir $(RAW)

collect-cnctr: init
	$(RUN) python -m collectors.cnctr --db $(DB) --raw-dir $(RAW)

collect-an: init
	$(RUN) python -m collectors.an_opendata --db $(DB) --raw-dir $(RAW) --legislatures $(AN_LEGISLATURES)

# Jeux data.gouv.fr de config/datagouv.yaml ; un sous-ensemble : make collect-datagouv JEUX="cada_avis"
JEUX ?=
collect-datagouv: init
	$(RUN) python -m collectors.datagouv --db $(DB) --raw-dir $(RAW) $(if $(JEUX),--jeux $(JEUX))

# Recalcule le SHA-256 de chaque fichier de l'archive brute.
verify-raw: init
	$(RUN) python -m storage.db verify-raw --db $(DB) --raw-dir $(RAW)

extract: init
	$(RUN) python -m extract.parlement --db $(DB) --raw-dir $(RAW)

metrics: init
	$(RUN) python -m scoring.metrics --db $(DB) --grid $(GRID) --export-dir $(EXPORTS)

score: init
	$(RUN) python -m scoring.score --db $(DB) --grid $(GRID)

# Réindexe l'archive brute, vide les tables dérivées puis les recalcule.
rebuild: init
	$(RUN) python -m storage.db reindex --db $(DB) --raw-dir $(RAW)
	$(RUN) python -m storage.db reset-derived --db $(DB)
	$(MAKE) extract metrics score DB=$(DB) RAW=$(RAW) EXPORTS=$(EXPORTS) GRID=$(GRID)

# Rapport de contrôle pour une date : make controle DATE=2023-03-31 [WINDOW=legislature_16]
DATE ?=
WINDOW ?= glissante_365j
controle:
	$(RUN) python -m scoring.report controle --db $(DB) --grid $(GRID) --date $(DATE) \
		--window $(WINDOW) --output $(EXPORTS)/controle_$(WINDOW)_$(DATE).md

# Échantillon de 20 faits à vérifier à la main (critère de l'étape 4).
echantillon:
	$(RUN) python -m scoring.report echantillon --db $(DB) --n 20 \
		--output $(EXPORTS)/echantillon_faits.md

# Prototype front (jetable) : export des données puis page servie en local.
prototype: prototype-data
	@echo "Prototype : http://127.0.0.1:8765"
	cd front/prototype && python3 -m http.server 8765 --bind 127.0.0.1

prototype-data:
	$(RUN) python front/prototype/export_data.py --db $(DB)

# Faits nouveaux depuis la dernière exécution (fait aussi par make quotidien).
nouveautes:
	$(RUN) python -m ops.nouveautes --db $(DB)

# Version publiable du prototype (page claude.ai) dans front/publication/dist/.
publication: prototype-data
	$(RUN) python front/publication/build.py

# Feuille de style de la version web (Tailwind 3.4.5, exécutable autonome vérifié par SHA-256).
# À relancer après tout changement de classes dans front/prototype/index.html ; le résultat
# (front/publication/tailwind.css) est versionné : la construction quotidienne n'en dépend pas.
TAILWIND := .outils/tailwindcss-3.4.5
TAILWIND_SHA256 := 7cf6c8ea7a77c03a92fce1a2d868a482cc8cb48547871725f83f659cb774be8b
$(TAILWIND):
	mkdir -p .outils
	curl -fsSL -o $@.tmp https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.5/tailwindcss-linux-x64
	echo "$(TAILWIND_SHA256)  $@.tmp" | sha256sum -c -
	chmod +x $@.tmp && mv $@.tmp $@

css: $(TAILWIND)
	$(TAILWIND) -c front/publication/tailwind.config.js -i front/publication/tailwind.in.css \
		-o front/publication/tailwind.css --minify

# Version pour un hébergement public, puis envoi (config/deploiement.local, hors git).
publication-web: prototype-data
	$(RUN) python front/publication/build.py --web

deployer: publication-web
	$(RUN) python -m ops.deployer

# --- Exécution quotidienne (ops/quotidien.py, timer systemd utilisateur) -----------------
SYSTEMD_USER := $(HOME)/.config/systemd/user

quotidien:
	$(RUN) python -m ops.quotidien

planifier:
	mkdir -p $(SYSTEMD_USER)
	sed -e 's|@RACINE@|$(CURDIR)|g' -e 's|@UV@|$(shell command -v uv)|g' \
		ops/systemd/barometre-quotidien.service > $(SYSTEMD_USER)/barometre-quotidien.service
	cp ops/systemd/barometre-quotidien.timer $(SYSTEMD_USER)/barometre-quotidien.timer
	systemctl --user daemon-reload
	systemctl --user enable --now barometre-quotidien.timer
	systemctl --user list-timers barometre-quotidien.timer

deplanifier:
	-systemctl --user disable --now barometre-quotidien.timer
	rm -f $(SYSTEMD_USER)/barometre-quotidien.service $(SYSTEMD_USER)/barometre-quotidien.timer
	systemctl --user daemon-reload

etat:
	@cat data/exports/etat_quotidien.json 2>/dev/null || echo "Aucune exécution quotidienne enregistrée."
	@systemctl --user list-timers barometre-quotidien.timer 2>/dev/null || true

# Critère d'acceptation : deux reconstructions successives donnent la même base.
reproducible:
	$(MAKE) rebuild DB=$(DB) RAW=$(RAW) EXPORTS=$(EXPORTS) GRID=$(GRID)
	$(RUN) python -m storage.db fingerprint --db $(DB) > data/.fingerprint-1
	$(MAKE) rebuild DB=$(DB) RAW=$(RAW) EXPORTS=$(EXPORTS) GRID=$(GRID)
	$(RUN) python -m storage.db fingerprint --db $(DB) > data/.fingerprint-2
	diff data/.fingerprint-1 data/.fingerprint-2 && echo "Reconstruction reproductible"

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

test: lint
	$(RUN) pytest
