# ADR 0002 — One SQLite database, external-content FTS

**Status:** Accepted · **Date:** 2026-09-11

## Decision

A single SQLite database at
`%LOCALAPPDATA%\Advance File Search\index\search_index.sqlite3` holds every
indexed root.

## Why one database rather than one per root

* A search is always scoped to one root, which is a `WHERE root_id = ?`
  predicate — cheap, and the same predicate the UI needs anyway.
* One file means one migration path, one integrity check, one backup and one
  place to delete. Per-root files multiply every maintenance operation and turn
  "delete all my index data" into a directory walk instead of one action.
* The single-instance guard already ensures a single writer, so the usual
  argument for splitting (write contention) does not apply.

## Schema shape

`roots` → `files` → `content_units`, with `ON DELETE CASCADE` throughout and
`PRAGMA foreign_keys = ON`. Deleting a root removes its files and their content
in one statement and cannot leave orphans.

The FTS tables use **external content**:

```sql
CREATE VIRTUAL TABLE content_fts USING fts5(
    text, content='content_units', content_rowid='id', tokenize='trigram');
```

Document text is stored once, in `content_units`. A standalone FTS table would
store it twice, and for a trigram index that is a significant cost. Triggers
keep the index in sync on insert, update and delete, so no code path can forget
to maintain it — a test asserts `count(content_fts) == count(content_units)`
after repeated update cycles.

## Granularity

One content unit per PDF page, per DOCX paragraph and table cell, per non-empty
XLSX cell, and per TXT line. See ADR 0003 for the spreadsheet reasoning.

## Durability

`journal_mode = WAL` lets the UI keep searching while the indexer writes.

`synchronous = NORMAL` rather than `FULL`: under WAL, `NORMAL` cannot corrupt
the database, it can only lose the most recent commits after a power loss — and
the index is always rebuildable from the user's own documents. Trading a little
durability for a large write-throughput gain is the right call for derived
data.

`secure_delete = ON` so removed document text is zeroed rather than left
readable in free pages, and **Delete Index** runs `VACUUM` afterwards to return
those pages to the filesystem.

## Migrations

Schema versions are explicit integers in `PRAGMA user_version`. Steps are
registered in `MIGRATION_STEPS` and each runs inside one transaction together
with its version bump, so an interrupted migration rolls back whole.

* A database written by a **newer** build raises `IncompatibleIndexError`
  rather than being modified, so downgrading cannot destroy an index.
* A **damaged** file is moved to `backups\` with a timestamp, never deleted,
  and a fresh index is created so the application still starts.
* A pre-migration backup is taken before any destructive step, keeping the five
  most recent.
