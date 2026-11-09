-- Schéma de la base du baromètre.
--
-- Tables en SQL standard, compatibles PostgreSQL (TEXT pour les dates ISO 8601,
-- INTEGER pour les booléens). Seuls les triggers d'immuabilité en fin de fichier
-- sont propres à SQLite et devront être réécrits en PL/pgSQL lors d'une migration.
--
-- Deux familles de tables :
--   * archive : sources, raw_documents, source_checks — jamais modifiées, seulement
--     complétées ;
--   * dérivées : facts, fact_sources, metrics, scores, score_facts — vidées et
--     recalculées intégralement par `make rebuild`.

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,            -- 'an_opendata', 'dila_legi'
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  licence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_documents (
  id INTEGER PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  external_id TEXT NOT NULL,      -- identifiant dans la source
  url TEXT NOT NULL,
  fetched_at TEXT NOT NULL,       -- ISO 8601
  sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
  path TEXT NOT NULL,             -- chemin relatif dans data/raw/
  UNIQUE (source_id, external_id, sha256)
);

-- Vérifications complètes et réussies d'une source, qu'elles aient apporté un document
-- nouveau ou non (une source qui ne publie rien un jour donné est quand même à jour).
-- Bornent la fin des données : scoring/metrics.py:data_end. Journalisées aussi sur disque
-- (data/raw/<source_id>/controles.jsonl) et restaurées par `reindex`.
CREATE TABLE IF NOT EXISTS source_checks (
  source_id TEXT NOT NULL REFERENCES sources(id),
  checked_at TEXT NOT NULL,       -- ISO 8601
  PRIMARY KEY (source_id, checked_at)
);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY,
  indicator_id TEXT NOT NULL,     -- ex. 'D2.contournement_parlement'
  fact_type TEXT NOT NULL,        -- ex. 'engagement_49_3', 'ordonnance_publiee', 'loi_promulguee'
  occurred_on TEXT NOT NULL,      -- date du fait, AAAA-MM-JJ
  title TEXT NOT NULL,
  official_ref TEXT,              -- n° de loi, NOR, n° de texte
  attributes TEXT NOT NULL DEFAULT '{}', -- JSON : fondement d'une ordonnance, lecture d'un 49.3...
  extraction_method TEXT NOT NULL,-- nom + version de l'extracteur
  verified_by_human INTEGER NOT NULL DEFAULT 0 CHECK (verified_by_human IN (0, 1))
);

CREATE INDEX IF NOT EXISTS facts_indicator_date ON facts (indicator_id, occurred_on);

CREATE TABLE IF NOT EXISTS fact_sources (
  fact_id INTEGER NOT NULL REFERENCES facts(id),
  raw_document_id INTEGER NOT NULL REFERENCES raw_documents(id),
  PRIMARY KEY (fact_id, raw_document_id)
);

CREATE INDEX IF NOT EXISTS fact_sources_raw ON fact_sources (raw_document_id);

CREATE TABLE IF NOT EXISTS metrics (
  indicator_id TEXT NOT NULL,
  period_end TEXT NOT NULL,       -- dernier jour de la fenêtre
  window_id TEXT NOT NULL,        -- 'glissante_365j', 'legislature_16'...
  window_days INTEGER NOT NULL,
  name TEXT NOT NULL,             -- ex. 'ratio_contournement'
  value REAL NOT NULL,
  grid_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,      -- état de l'archive utilisé (dernière collecte), déterministe
  PRIMARY KEY (indicator_id, period_end, window_id, name, grid_version)
);

CREATE TABLE IF NOT EXISTS scores (
  indicator_id TEXT NOT NULL,
  period_end TEXT NOT NULL,
  window_id TEXT NOT NULL,
  score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 4),
  grid_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (indicator_id, period_end, window_id, grid_version)
);

CREATE TABLE IF NOT EXISTS score_facts (  -- traçabilité score -> faits
  indicator_id TEXT NOT NULL,
  period_end TEXT NOT NULL,
  window_id TEXT NOT NULL,
  grid_version TEXT NOT NULL,
  fact_id INTEGER NOT NULL REFERENCES facts(id),
  PRIMARY KEY (indicator_id, period_end, window_id, grid_version, fact_id),
  FOREIGN KEY (indicator_id, period_end, window_id, grid_version)
    REFERENCES scores (indicator_id, period_end, window_id, grid_version)
);

-- Règle 1 : l'archive brute est immuable. On ajoute, on ne modifie ni ne supprime.
-- (Spécifique SQLite.)
CREATE TRIGGER IF NOT EXISTS raw_documents_no_update
BEFORE UPDATE ON raw_documents
BEGIN
  SELECT RAISE(ABORT, 'raw_documents est immuable : pas de UPDATE');
END;

CREATE TRIGGER IF NOT EXISTS raw_documents_no_delete
BEFORE DELETE ON raw_documents
BEGIN
  SELECT RAISE(ABORT, 'raw_documents est immuable : pas de DELETE');
END;
