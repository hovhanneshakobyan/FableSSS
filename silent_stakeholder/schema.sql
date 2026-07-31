PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY, text TEXT NOT NULL, date_iso TEXT, star INTEGER,
  chars INTEGER, star_band TEXT, ym TEXT, version_id INTEGER,
  cluster_id INTEGER DEFAULT -1,
  llm_latent INTEGER, llm_symptom TEXT, llm_mechanism TEXT,
  llm_workaround INTEGER, llm_happy_friction INTEGER, llm_severity INTEGER
);
CREATE INDEX IF NOT EXISTS ix_r_star ON reviews(star_band, star);
CREATE INDEX IF NOT EXISTS ix_r_ym   ON reviews(ym);
CREATE INDEX IF NOT EXISTS ix_r_clu  ON reviews(cluster_id);

CREATE TABLE IF NOT EXISTS sentences (
  review_id TEXT, text TEXT, intention TEXT, topic TEXT
);
CREATE INDEX IF NOT EXISTS ix_s_rev ON sentences(review_id);
CREATE INDEX IF NOT EXISTS ix_s_int ON sentences(intention);

CREATE TABLE IF NOT EXISTS issues (
  number INTEGER PRIMARY KEY, title TEXT, body TEXT, text_concat TEXT,
  state TEXT, created_at TEXT, closed_at TEXT, days_open INTEGER,
  type_label TEXT, milestone TEXT, html_url TEXT, comments INTEGER,
  is_stale_open INTEGER DEFAULT 0, cluster_id INTEGER DEFAULT -1,
  state_reason TEXT, labels_json TEXT,
  ym TEXT, is_needs_info INTEGER DEFAULT 0, is_not_planned INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_i_state ON issues(state);
CREATE INDEX IF NOT EXISTS ix_i_type  ON issues(type_label);
CREATE INDEX IF NOT EXISTS ix_i_ms    ON issues(milestone);
CREATE INDEX IF NOT EXISTS ix_i_clu   ON issues(cluster_id);

CREATE TABLE IF NOT EXISTS clusters (
  cluster_id INTEGER, side TEXT, label TEXT, size INTEGER, top_terms TEXT,
  PRIMARY KEY (cluster_id, side)
);

CREATE TABLE IF NOT EXISTS pairs (
  r_cluster INTEGER, i_cluster INTEGER,
  cosine REAL, lexical_overlap REAL, divergence REAL,
  PRIMARY KEY (r_cluster, i_cluster)
);
CREATE INDEX IF NOT EXISTS ix_p_div ON pairs(divergence DESC);

CREATE TABLE IF NOT EXISTS candidates (
  cand_id TEXT PRIMARY KEY, label TEXT, status TEXT,
  query_terms TEXT, symptom_terms TEXT, mechanism_terms TEXT,
  n_reviews INTEGER, n_issues INTEGER,
  pol_symptom REAL, pol_mechanism REAL, pii REAL, bridge INTEGER,
  score REAL, rejection_reason TEXT, failing_component TEXT
);

CREATE TABLE IF NOT EXISTS gaps (
  gap_id TEXT PRIMARY KEY, rank INTEGER, need TEXT, verdict TEXT,
  confidence INTEGER, components_json TEXT, falsifier TEXT,
  roadmap_response TEXT, narrative TEXT,
  resolution_lag_days INTEGER, backtest TEXT
);

CREATE TABLE IF NOT EXISTS gap_evidence (
  gap_id TEXT, kind TEXT, ref_id TEXT, role TEXT, quote TEXT,
  PRIMARY KEY (gap_id, kind, ref_id)
);
CREATE INDEX IF NOT EXISTS ix_e_rev ON gap_evidence(kind, ref_id);

CREATE TABLE IF NOT EXISTS run_manifest (key TEXT PRIMARY KEY, value TEXT);

CREATE VIRTUAL TABLE IF NOT EXISTS reviews_fts
  USING fts5(text, content='reviews', content_rowid='rowid', tokenize='porter unicode61');
CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts
  USING fts5(title, text_concat, content='issues', content_rowid='number', tokenize='porter unicode61');
