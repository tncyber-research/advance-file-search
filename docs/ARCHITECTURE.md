# Architecture

A single-process Windows desktop application. There is no server, no local
web server, no IPC and no network stack — what looks like a "back end" is the
engine layer running on worker threads inside the same process.

The Thai-language edition of this material, with rendered diagrams, is in
`Manual/report.html`.

---

## 1. Layers

```mermaid
flowchart TB
    subgraph P["Presentation — UI thread"]
        MW["MainWindow"]
        DLG["Index / Settings / About dialogs"]
        MODEL["ResultModel + delegates"]
        I18N["theme + i18n"]
    end

    subgraph E["Engine — worker threads"]
        COORD["IndexCoordinator"]
        PARSE["Parsers: PDF, DOCX, XLSX, TXT"]
        SEARCH["SearchService"]
        QUERY["QueryParser, wildcard, ranking, snippets"]
    end

    subgraph S["Storage — local disk"]
        DB[("index.db (SQLite + FTS5, WAL)")]
        SET["settings.json"]
        LOG["app.log"]
        DOC["User documents (read-only)"]
    end

    MW -->|"start, cancel"| COORD
    MW -->|"start, cancel"| SEARCH
    COORD -->|"Qt signals: progress"| MW
    SEARCH -->|"Qt signals: results"| MW
    COORD --> PARSE
    SEARCH --> QUERY
    DOC --> PARSE
    COORD --> DB
    DB --> SEARCH
    SET --> MW
    COORD --> LOG
```

The dependency direction is enforced by package boundaries: `ui` may call
`search`, `indexing`, `storage` and `core`; nothing below `ui` imports it.
That is what makes almost the whole system testable without opening a window.

| Package | Responsibility |
|---|---|
| `core` | Constants, value objects, settings, path security, i18n, app paths |
| `indexing` | Walking the tree, fingerprinting, parsing, writing units |
| `search` | Parsing the query, running it, verifying, ranking, snippets |
| `storage` | Connections, schema, migrations, repositories |
| `ui` | Windows, dialogs, models, delegates, worker wrappers |
| `winplat` | Windows-specific path handling, shell integration, single instance |

---

## 2. Indexing

```mermaid
flowchart TD
    A["Search pressed, or Update index"] --> B["Scanner walks the folder"]
    B --> C{"Excluded?"}
    C -->|"shortcut, junction, ~$ temp,<br/>too large, unsupported type"| X["Skip"]
    C -->|no| D["Fingerprint = size + mtime + parser version"]
    D --> E{"Same as stored?"}
    E -->|yes| U["Count as unchanged"]
    E -->|no| F["Pick parser by extension"]
    F --> G["Split into content units with locations"]
    G --> H["Write inside a per-file SAVEPOINT"]
    H --> I["Triggers update content_fts and name_fts"]
    I --> J["Files not seen this run are deleted from the index"]
    J --> K["Write run statistics to index_runs"]
```

A unit is the smallest addressable piece of a document: a PDF page, a Word
paragraph or table cell, a spreadsheet cell, a line of text. Storing units
rather than whole documents is what allows the application to answer *where*
a match is, and it bounds the memory used by any single file.

Failure is per file. A corrupt or password-protected document is recorded
with an error code and the run continues.

---

## 3. Search

```mermaid
flowchart TD
    Q["Query text"] --> V["Length and term limits"]
    V --> P["QueryParser: phrases, wildcards, filters"]
    P --> S{"Term shorter than 3 characters?"}
    S -->|yes| L["Bounded LIKE scan"]
    S -->|no| T["FTS5 trigram: name_fts and/or content_fts"]
    T --> C["Verify in memory: case, whole word, wildcards"]
    L --> C
    C --> F["Apply metadata filters"]
    F --> R["Rank: name over content, frequency, recency"]
    R --> N["Build snippets and locations"]
    N --> UI["Return to the UI thread"]
```

The verification step exists because the index cannot express everything the
query can. A trigram index is case-insensitive and knows nothing about word
boundaries or wildcards, so it is treated as a fast candidate filter and the
real semantics are applied to the candidate text.

When the matching unit is short — one line of a text file, say — the units on
either side are pulled in and the snippet is rebuilt over the combined text,
so the preview reads as context rather than a fragment.

---

## 4. Concurrency

| Thread | Does | Database connection |
|---|---|---|
| UI | Draws, and reads small facts such as index status | Its own |
| Search worker | Runs one search, reports results | Its own, read-only in practice |
| Index worker | Runs one indexing pass, reports progress | Its own, writing |

Rules that keep this safe:

- Connections are never shared between threads.
- WAL journalling lets the search read while the indexer writes.
- Every result carries a job number; the UI discards anything that is not the
  current job, so a slow search cannot overwrite a newer one.
- Cancellation is a flag checked at safe points, never a killed thread.
- A search that hits a transient SQLite error (`database is locked`,
  `vtable constructor failed` while the FTS index is being optimised) drops
  its connection, waits 120 ms and retries once — the failure mode that made
  a search return an empty list while the index refreshed.

---

## 5. Data model

```mermaid
erDiagram
    roots ||--o{ files : contains
    roots ||--o{ index_runs : "has history"
    files ||--o{ content_units : "split into"
    files ||--|| name_fts : "mirrored by trigger"
    content_units ||--|| content_fts : "mirrored by trigger"

    roots {
        int id PK
        text display_path
        text normalized_path UK
        text last_index_status
    }
    files {
        int id PK
        int root_id FK
        text display_path
        text fingerprint
        text content_status
        text error_code
    }
    content_units {
        int id PK
        int file_id FK
        int sequence
        text location_type
        text location_json
        text text
    }
    content_fts {
        text text "FTS5 external content"
    }
    name_fts {
        text file_name "FTS5 external content"
        text relative_path
    }
    index_runs {
        int id PK
        int root_id FK
        text mode
        int files_indexed
    }
```

Both FTS tables are **external-content** tables: the text lives once in
`content_units` (or `files`) and the index refers back to it. Six triggers
keep them in step, so correctness does not depend on every write path
remembering to update the index.

`PRAGMA` settings: `journal_mode=WAL`, `synchronous=NORMAL`,
`foreign_keys=ON`, `secure_delete=ON`. The last one matters here: text
removed from the index is overwritten rather than left in free pages.

---

## 6. Integrations

There are three, all local:

| Integration | Mechanism | Note |
|---|---|---|
| Opening a document | `os.startfile`, falling back to the `openas` verb | The shell chooses the program; the application never executes anything itself |
| Revealing a file | `SHOpenFolderAndSelectItems` via `ctypes` | No command line is built, so quoting cannot break it |
| Single instance | Named mutex | Prevents two processes writing one index |

No HTTP client, no telemetry, no update check, no WebView, no fonts or assets
fetched at run time. `scripts/verify_build.py` fails the build if a Qt network
or WebEngine DLL appears in the distribution.

---

## 7. Design decisions

Recorded as ADRs in [`decisions/`](decisions/) and indexed in
[`DECISIONS.md`](DECISIONS.md). The ones that explain the most structure:
trigram tokenization (0001), the database design (0002), cell-level
spreadsheet granularity (0003), fingerprinting instead of hashing (0004), the
wildcard matcher (0005), onedir packaging (0006), and the local-path and
reparse-point rules (0008).
