-- NoemaForge durable prep-store schema (0.27.9)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
  book_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_path TEXT,
  source_mime TEXT,
  source_size_bytes INTEGER,
  book_title TEXT,
  edition TEXT,
  language TEXT,
  book_checksum TEXT NOT NULL,
  book_checksum_alg TEXT NOT NULL DEFAULT 'sha256',
  canonicalization_profile TEXT NOT NULL,
  enqueue_ts TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','normalizing','labeling','chunk_planning','extracting','completed','failed','rejected')),
  last_error_code TEXT,
  last_error_message TEXT,
  UNIQUE(source_id, book_checksum, canonicalization_profile)
);

CREATE TABLE IF NOT EXISTS book_queue_entries (
  ingest_queue_entry_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  queue_name TEXT NOT NULL DEFAULT 'default',
  ingest_queue_position INTEGER NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  enqueued_at TEXT NOT NULL,
  dequeued_at TEXT,
  completed_at TEXT,
  queue_status TEXT NOT NULL DEFAULT 'queued' CHECK (queue_status IN ('queued','leased','completed','failed','cancelled')),
  worker_id TEXT,
  lease_expires_at TEXT,
  UNIQUE(queue_name, ingest_queue_position),
  UNIQUE(book_id)
);
CREATE INDEX IF NOT EXISTS idx_book_queue_status ON book_queue_entries(queue_name, queue_status, priority, ingest_queue_position);

CREATE TABLE IF NOT EXISTS chapters (
  chapter_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_no INTEGER,
  chapter_title TEXT,
  chapter_path TEXT,
  raw_char_start INTEGER,
  raw_char_end INTEGER,
  UNIQUE(book_id, chapter_no, chapter_path)
);

CREATE TABLE IF NOT EXISTS sections (
  section_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_path TEXT NOT NULL,
  section_title TEXT,
  section_level INTEGER,
  raw_char_start INTEGER,
  raw_char_end INTEGER,
  UNIQUE(book_id, section_path)
);

CREATE TABLE IF NOT EXISTS normalized_text_artifacts (
  normalized_text_artifact_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_id TEXT REFERENCES sections(section_id) ON DELETE CASCADE,
  artifact_scope TEXT NOT NULL CHECK (artifact_scope IN ('book','chapter','section')),
  normalization_version TEXT NOT NULL,
  canonicalization_profile TEXT NOT NULL,
  normalized_text_checksum TEXT NOT NULL,
  normalized_text_checksum_alg TEXT NOT NULL DEFAULT 'sha256',
  artifact_relpath TEXT,
  artifact_encoding TEXT NOT NULL DEFAULT 'utf-8',
  text_length_chars INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(book_id, chapter_id, section_id, artifact_scope, normalization_version, canonicalization_profile, normalized_text_checksum)
);
CREATE INDEX IF NOT EXISTS idx_norm_artifacts_book ON normalized_text_artifacts(book_id, artifact_scope);

CREATE TABLE IF NOT EXISTS processing_runs (
  run_id TEXT PRIMARY KEY,
  component TEXT NOT NULL CHECK (component IN ('normalizer','sentence_splitter','topic_labeler','adjacency_builder','split_planner','passage_builder','claim_extractor','entity_linker','concept_linker','conflict_detector')),
  book_id TEXT REFERENCES books(book_id) ON DELETE SET NULL,
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
CREATE INDEX IF NOT EXISTS idx_processing_runs_book ON processing_runs(book_id, component, started_at);

CREATE TABLE IF NOT EXISTS sentences (
  sentence_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_id TEXT REFERENCES sections(section_id) ON DELETE CASCADE,
  normalized_text_artifact_id TEXT NOT NULL REFERENCES normalized_text_artifacts(normalized_text_artifact_id) ON DELETE CASCADE,
  sentence_no INTEGER NOT NULL,
  paragraph_no INTEGER,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  token_estimate INTEGER,
  text_hash TEXT NOT NULL,
  text_hash_alg TEXT NOT NULL DEFAULT 'sha256',
  UNIQUE(normalized_text_artifact_id, sentence_no),
  CHECK(char_start <= char_end)
);
CREATE INDEX IF NOT EXISTS idx_sentences_lookup ON sentences(book_id, chapter_id, section_id, sentence_no);

CREATE TABLE IF NOT EXISTS sentence_topic_maps (
  sentence_topic_map_id TEXT PRIMARY KEY,
  sentence_id TEXT NOT NULL UNIQUE REFERENCES sentences(sentence_id) ON DELETE CASCADE,
  labeling_run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE RESTRICT,
  topic_tags_json TEXT NOT NULL,
  topic_signature TEXT NOT NULL,
  topic_confidence REAL NOT NULL CHECK (topic_confidence >= 0.0 AND topic_confidence <= 1.0),
  adjacency_group_id TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_sentence_topic_signature ON sentence_topic_maps(topic_signature);
CREATE INDEX IF NOT EXISTS idx_sentence_topic_group ON sentence_topic_maps(adjacency_group_id);

CREATE TABLE IF NOT EXISTS adjacency_groups (
  adjacency_group_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_id TEXT REFERENCES sections(section_id) ON DELETE CASCADE,
  built_run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE RESTRICT,
  sentence_start_id TEXT NOT NULL REFERENCES sentences(sentence_id) ON DELETE RESTRICT,
  sentence_end_id TEXT NOT NULL REFERENCES sentences(sentence_id) ON DELETE RESTRICT,
  topic_signature TEXT NOT NULL,
  topic_tags_union_json TEXT NOT NULL,
  cohesion_score REAL,
  estimated_tokens INTEGER,
  CHECK(cohesion_score IS NULL OR (cohesion_score >= 0.0 AND cohesion_score <= 1.0))
);
CREATE INDEX IF NOT EXISTS idx_adj_groups_lookup ON adjacency_groups(book_id, chapter_id, section_id);

CREATE TABLE IF NOT EXISTS split_nodes (
  split_node_id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_id TEXT REFERENCES sections(section_id) ON DELETE CASCADE,
  built_run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE RESTRICT,
  parent_split_node_id TEXT REFERENCES split_nodes(split_node_id) ON DELETE CASCADE,
  adjacency_group_id TEXT REFERENCES adjacency_groups(adjacency_group_id) ON DELETE SET NULL,
  sentence_start_id TEXT NOT NULL REFERENCES sentences(sentence_id) ON DELETE RESTRICT,
  sentence_end_id TEXT NOT NULL REFERENCES sentences(sentence_id) ON DELETE RESTRICT,
  char_start INTEGER,
  char_end INTEGER,
  estimated_tokens INTEGER,
  split_strategy TEXT,
  split_reason TEXT,
  boundary_mode TEXT NOT NULL DEFAULT 'sentence_span' CHECK (boundary_mode IN ('sentence_span','char_span','clause_window')),
  fragment_spec_json TEXT,
  split_depth INTEGER NOT NULL DEFAULT 0,
  leaf_sequence_no INTEGER,
  is_leaf INTEGER NOT NULL DEFAULT 0 CHECK (is_leaf IN (0,1)),
  chunk_quality_metrics_json TEXT,
  CHECK(split_depth >= 0),
  CHECK((char_start IS NULL AND char_end IS NULL) OR (char_start <= char_end))
);
CREATE INDEX IF NOT EXISTS idx_split_nodes_lookup ON split_nodes(book_id, chapter_id, section_id, is_leaf, leaf_sequence_no);
CREATE INDEX IF NOT EXISTS idx_split_nodes_parent ON split_nodes(parent_split_node_id);

CREATE TABLE IF NOT EXISTS passage_origins (
  passage_origin_id TEXT PRIMARY KEY,
  passage_id TEXT NOT NULL,
  book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_id TEXT REFERENCES sections(section_id) ON DELETE CASCADE,
  normalized_text_artifact_id TEXT NOT NULL REFERENCES normalized_text_artifacts(normalized_text_artifact_id) ON DELETE CASCADE,
  split_leaf_id TEXT REFERENCES split_nodes(split_node_id) ON DELETE RESTRICT,
  sentence_start_id TEXT NOT NULL REFERENCES sentences(sentence_id) ON DELETE RESTRICT,
  sentence_end_id TEXT NOT NULL REFERENCES sentences(sentence_id) ON DELETE RESTRICT,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  quote_fingerprint TEXT NOT NULL,
  extraction_run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE RESTRICT,
  trace_level TEXT NOT NULL DEFAULT 'L2',
  trace_completeness_score REAL NOT NULL DEFAULT 0.0 CHECK (trace_completeness_score >= 0.0 AND trace_completeness_score <= 1.0),
  UNIQUE(passage_id)
);
CREATE INDEX IF NOT EXISTS idx_passage_origins_book ON passage_origins(book_id, chapter_id, section_id);

CREATE TABLE IF NOT EXISTS claim_origins (
  claim_origin_id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  book_id TEXT REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(chapter_id) ON DELETE CASCADE,
  section_id TEXT REFERENCES sections(section_id) ON DELETE CASCADE,
  normalized_text_artifact_id TEXT REFERENCES normalized_text_artifacts(normalized_text_artifact_id) ON DELETE CASCADE,
  passage_id TEXT NOT NULL,
  split_leaf_id TEXT REFERENCES split_nodes(split_node_id) ON DELETE RESTRICT,
  sentence_start_id TEXT,
  sentence_end_id TEXT,
  char_start INTEGER,
  char_end INTEGER,
  primary_address_json TEXT NOT NULL,
  evidence_spans_json TEXT NOT NULL,
  claim_mode TEXT NOT NULL CHECK (claim_mode IN ('quoted','extracted','abstracted','inferred','aggregated')),
  quote_fingerprint TEXT NOT NULL,
  extraction_run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE RESTRICT,
  trace_level TEXT NOT NULL DEFAULT 'L3',
  trace_completeness_score REAL NOT NULL DEFAULT 0.0 CHECK (trace_completeness_score >= 0.0 AND trace_completeness_score <= 1.0),
  UNIQUE(claim_id)
);
CREATE INDEX IF NOT EXISTS idx_claim_origins_book ON claim_origins(book_id, chapter_id, section_id, claim_mode);
CREATE INDEX IF NOT EXISTS idx_claim_origins_passage ON claim_origins(passage_id);
