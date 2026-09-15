-- Advance File Search - schema version 1
-- All statements are static DDL. Runtime queries are always parameterized.

CREATE TABLE IF NOT EXISTS roots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    display_path            TEXT    NOT NULL,
    normalized_path         TEXT    NOT NULL UNIQUE,
    created_at              TEXT    NOT NULL,
    last_index_started_at   TEXT,
    last_index_completed_at TEXT,
    last_index_status       TEXT,
    file_count              INTEGER NOT NULL DEFAULT 0,
    schema_version          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS files (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    root_id                 INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    display_path            TEXT    NOT NULL,
    normalized_path         TEXT    NOT NULL,
    relative_path           TEXT    NOT NULL,
    file_name               TEXT    NOT NULL,
    file_name_folded        TEXT    NOT NULL,
    extension               TEXT    NOT NULL,
    mime_category           TEXT    NOT NULL DEFAULT '',
    size_bytes              INTEGER NOT NULL DEFAULT 0,
    created_time            REAL,
    modified_time           REAL,
    fingerprint             TEXT    NOT NULL DEFAULT '',
    content_status          TEXT    NOT NULL DEFAULT 'indexed',
    parser_version          INTEGER NOT NULL DEFAULT 1,
    unit_count              INTEGER NOT NULL DEFAULT 0,
    char_count              INTEGER NOT NULL DEFAULT 0,
    indexed_at              TEXT,
    last_seen_run_id        INTEGER,
    error_code              TEXT    NOT NULL DEFAULT '',
    error_message_sanitized TEXT    NOT NULL DEFAULT '',
    UNIQUE (root_id, normalized_path)
);

CREATE INDEX IF NOT EXISTS idx_files_root            ON files(root_id);
CREATE INDEX IF NOT EXISTS idx_files_root_ext        ON files(root_id, extension);
CREATE INDEX IF NOT EXISTS idx_files_root_modified   ON files(root_id, modified_time);
CREATE INDEX IF NOT EXISTS idx_files_root_name       ON files(root_id, file_name_folded);
CREATE INDEX IF NOT EXISTS idx_files_root_seen       ON files(root_id, last_seen_run_id);
CREATE INDEX IF NOT EXISTS idx_files_status          ON files(root_id, content_status);

CREATE TABLE IF NOT EXISTS content_units (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sequence       INTEGER NOT NULL,
    location_type  TEXT    NOT NULL,
    location_label TEXT    NOT NULL DEFAULT '',
    location_json  TEXT    NOT NULL DEFAULT '{}',
    text           TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_units_file ON content_units(file_id, sequence);

-- Full-text index over content units.  An external-content table keeps the
-- document text stored exactly once (in content_units) while FTS5 provides
-- fast candidate retrieval.
--
-- The tokenizer is 'trigram', not 'unicode61'.  Thai does not put spaces
-- between words, so unicode61 turns a whole Thai run into a single token and
-- a search for a word inside that run finds nothing.  The trigram tokenizer
-- gives true substring matching in any script, which is what users expect
-- from a file-content search.  See docs/decisions/0001-thai-search.md.
--
-- Consequences handled in the search layer:
--   * queries shorter than 3 characters cannot use this index (bounded LIKE
--     fallback instead);
--   * matching is case-insensitive, so Match case is verified locally;
--   * whole-word and ?/* wildcards are verified locally.
CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
    text,
    content='content_units',
    content_rowid='id',
    tokenize='trigram'
);

-- Separate FTS index for file names and relative paths so that name-only
-- searches never have to scan content rows.  Also trigram, so that Thai file
-- names are searchable by any fragment.
CREATE VIRTUAL TABLE IF NOT EXISTS name_fts USING fts5(
    file_name,
    relative_path,
    content='files',
    content_rowid='id',
    tokenize='trigram'
);

-- Triggers keep both FTS indexes in sync with their content tables.
CREATE TRIGGER IF NOT EXISTS content_units_ai AFTER INSERT ON content_units BEGIN
    INSERT INTO content_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS content_units_ad AFTER DELETE ON content_units BEGIN
    INSERT INTO content_fts(content_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS content_units_au AFTER UPDATE ON content_units BEGIN
    INSERT INTO content_fts(content_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO content_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO name_fts(rowid, file_name, relative_path)
    VALUES (new.id, new.file_name, new.relative_path);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO name_fts(name_fts, rowid, file_name, relative_path)
    VALUES ('delete', old.id, old.file_name, old.relative_path);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO name_fts(name_fts, rowid, file_name, relative_path)
    VALUES ('delete', old.id, old.file_name, old.relative_path);
    INSERT INTO name_fts(rowid, file_name, relative_path)
    VALUES (new.id, new.file_name, new.relative_path);
END;

CREATE TABLE IF NOT EXISTS index_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    root_id             INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    started_at          TEXT    NOT NULL,
    finished_at         TEXT,
    status              TEXT    NOT NULL DEFAULT 'running',
    mode                TEXT    NOT NULL DEFAULT 'update',
    files_discovered    INTEGER NOT NULL DEFAULT 0,
    files_processed     INTEGER NOT NULL DEFAULT 0,
    files_indexed       INTEGER NOT NULL DEFAULT 0,
    files_unchanged     INTEGER NOT NULL DEFAULT 0,
    files_skipped       INTEGER NOT NULL DEFAULT 0,
    files_failed        INTEGER NOT NULL DEFAULT 0,
    files_no_text       INTEGER NOT NULL DEFAULT 0,
    files_deleted       INTEGER NOT NULL DEFAULT 0,
    elapsed_seconds     REAL    NOT NULL DEFAULT 0,
    application_version TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_runs_root ON index_runs(root_id, started_at DESC);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
