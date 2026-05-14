-- NoemaForge error learning loop schema (0.27.7)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS processing_runs (
  run_id TEXT PRIMARY KEY,
  component TEXT NOT NULL,
  book_id TEXT,
  model_id TEXT,
  model_version TEXT,
  prompt_hash TEXT,
  profile_id TEXT,
  policy_epoch TEXT,
  code_version TEXT,
  thresholds_json TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  run_status TEXT NOT NULL DEFAULT 'running' CHECK (run_status IN ('running','completed','failed','cancelled')),
  error_code TEXT,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS error_events (
  error_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE CASCADE,
  component TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info','low','medium','high','critical')),
  error_type TEXT NOT NULL,
  source_address_json TEXT,
  object_kind TEXT,
  object_id TEXT,
  predicted_payload_json TEXT,
  expected_payload_json TEXT,
  source_defect INTEGER NOT NULL DEFAULT 0 CHECK (source_defect IN (0,1)),
  review_status TEXT NOT NULL DEFAULT 'open' CHECK (review_status IN ('open','reviewed','adjudicated','dismissed')),
  created_at TEXT NOT NULL,
  reviewer_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_events_component ON error_events(component, error_type, severity, review_status);
CREATE INDEX IF NOT EXISTS idx_error_events_run ON error_events(run_id, created_at);

CREATE TABLE IF NOT EXISTS corrections (
  correction_id TEXT PRIMARY KEY,
  error_id TEXT NOT NULL REFERENCES error_events(error_id) ON DELETE CASCADE,
  corrected_by TEXT NOT NULL,
  correction_kind TEXT NOT NULL,
  old_value_json TEXT,
  new_value_json TEXT NOT NULL,
  rationale TEXT,
  created_at TEXT NOT NULL,
  approved_for_training INTEGER NOT NULL DEFAULT 0 CHECK (approved_for_training IN (0,1)),
  approved_for_eval INTEGER NOT NULL DEFAULT 0 CHECK (approved_for_eval IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_corrections_error ON corrections(error_id, created_at);

CREATE TABLE IF NOT EXISTS adjudications (
  adjudication_id TEXT PRIMARY KEY,
  error_id TEXT NOT NULL REFERENCES error_events(error_id) ON DELETE CASCADE,
  correction_id TEXT REFERENCES corrections(correction_id) ON DELETE SET NULL,
  adjudicated_by TEXT NOT NULL,
  adjudication_status TEXT NOT NULL CHECK (adjudication_status IN ('accepted','rejected','needs_followup')),
  reasoning TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adjudications_error ON adjudications(error_id, created_at);

CREATE TABLE IF NOT EXISTS regression_cases (
  regression_case_id TEXT PRIMARY KEY,
  source_error_id TEXT NOT NULL REFERENCES error_events(error_id) ON DELETE CASCADE,
  source_correction_id TEXT REFERENCES corrections(correction_id) ON DELETE SET NULL,
  component TEXT NOT NULL,
  input_payload_json TEXT NOT NULL,
  expected_payload_json TEXT NOT NULL,
  acceptance_policy_json TEXT,
  promoted_at TEXT NOT NULL,
  promoted_by TEXT NOT NULL,
  case_status TEXT NOT NULL DEFAULT 'active' CHECK (case_status IN ('active','retired'))
);
CREATE INDEX IF NOT EXISTS idx_regression_cases_component ON regression_cases(component, case_status, promoted_at);

CREATE TABLE IF NOT EXISTS training_deltas (
  training_delta_id TEXT PRIMARY KEY,
  source_error_id TEXT NOT NULL REFERENCES error_events(error_id) ON DELETE CASCADE,
  source_correction_id TEXT NOT NULL REFERENCES corrections(correction_id) ON DELETE CASCADE,
  target_model_family TEXT NOT NULL CHECK (target_model_family IN ('prep_labeler','chunk_planner','claim_extractor','entity_linker','conflict_detector')),
  delta_payload_json TEXT NOT NULL,
  export_status TEXT NOT NULL DEFAULT 'pending' CHECK (export_status IN ('pending','exported','consumed','rejected')),
  created_at TEXT NOT NULL,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_training_deltas_target ON training_deltas(target_model_family, export_status, created_at);
