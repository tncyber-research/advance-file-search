# Security and privacy design

Advance File Search indexes a user's documents. That makes it, by construction,
a program holding a copy of everything sensitive on the machine. This document
records what the application does to deserve that access.

---

## 1. Offline operation

The application makes no network connection of any kind. There is no update
check, no telemetry, no crash reporting, no remote asset.

**How it is enforced, not merely intended:**

| Mechanism | Where |
|---|---|
| No networking module is imported anywhere | `test_no_module_imports_a_networking_library` walks the AST of every source file and fails on `socket`, `ssl`, `http`, `urllib`, `requests`, `httpx`, `asyncio`, `webbrowser`, telemetry SDKs, … |
| Full workflow runs with sockets disabled | `test_full_workflow_with_sockets_disabled` monkey-patches `socket.socket`, `create_connection` and `getaddrinfo` to raise, then indexes and searches the whole fixture corpus |
| Qt network modules are excluded from the bundle | `build/AdvanceFileSearch.spec` `excludes` — `QtNetwork`, `QtWebEngine*`, `QtWebSockets`, `QtHttpServer`, `QtNetworkAuth`, `QtWebView` |
| No WebView anywhere | `test_no_frozen_module_pulls_in_a_web_view` |
| No remote fonts or CDN assets | `test_no_remote_font_or_asset_references`; the theme uses system font families by name |
| Nothing is downloaded at runtime | every dependency is pinned in `requirements.txt` and bundled by PyInstaller |

Excluding the Qt network modules from the *bundle* matters more than the import
convention: a stray import added later fails at build time rather than shipping
network capability.

---

## 2. Local paths only

Version 1 accepts only local Windows file-system paths. See
[ADR 0008](decisions/0008-network-and-link-handling.md) for the full rationale.

Rejected: UNC paths, mapped network drives, URLs of any scheme, the Win32
device namespace, optical drives, and anything without a drive letter.

The critical detail is **ordering**: URL, device and UNC forms are rejected
*before the filesystem is touched*, because `os.stat("\\\\server\\share")`
makes Windows attempt an SMB connection. A test patches `os.stat` to raise and
asserts the rejection still happens.

Directory symlinks, junctions and mount-point reparse points are never
traversed. Cloud "online only" placeholder files are skipped, because reading
one triggers a download.

---

## 3. Data stays local

| Data | Location |
|---|---|
| Index | `%LOCALAPPDATA%\Advance File Search\index\search_index.sqlite3` |
| Logs | `…\logs\application.log` (rotated, 5 MB × 3) |
| Settings | `…\settings\settings.json` |
| Backups | `…\backups\` (pre-migration and quarantined damaged indexes) |
| Temp | `…\temp\` (swept on every launch) |

Nothing mutable is written beside the executable — the program may be installed
under `C:\Program Files`, where a normal user cannot write.

Document content leaves the application only when the user explicitly opens a
file or copies a path.

---

## 4. Logging

Two guarantees are enforced by the logging layer itself rather than by
call-site discipline, because "remember not to log that" is not a control:

1. **Every record is flattened and sanitized.** `PrivacyFilter` strips
   newlines and control characters and truncates, so document text cannot
   smuggle structure into the log.
2. **Tracebacks are never written.** A parser traceback can embed a fragment of
   the document that broke it. The sanitized exception *type and message* are
   logged instead.

Search queries and snippets are never passed to the logger by any caller, and
`test_searching_does_not_log_the_query_or_snippets` proves it by searching for
a unique token and asserting it does not appear in the log file.

File-path logging can be turned off in Settings → Privacy & Logs; the
`safe_path_field()` helper then emits `path=<redacted>`.

---

## 5. Untrusted input handling

Every indexed document is treated as hostile input.

* **No macros, scripts or embedded actions are executed.** `.docm`, `.xlsm`
  and every executable extension have no parser at all and are refused by
  extension before a file is opened.
* **No hyperlinks, remote templates or external workbook links are followed.**
  `openpyxl` is loaded with `keep_links=False`; only visible DOCX link *text*
  is indexed.
* **No PDF JavaScript, launch actions, annotations, attachments or embedded
  files are touched.** Only the text layer is read.
* **No formula evaluation.** XLSX uses `data_only=True`, indexing the cached
  result Excel stored.
* **Parsers never raise.** `DocumentParser.parse()` converts every failure into
  a `ParseResult`. One bad file cannot abort an indexing run — a test indexes a
  folder of 20 corrupt DOCX files plus one good one and asserts the good one is
  indexed.
* **Resource limits** on file size, page count, cell count, line count, unit
  text length and total document characters bound a hostile document. A
  "zip bomb" DOCX fixture that inflates to 20 MB from a 19 KB archive is
  handled as a corrupt file.

---

## 6. SQL and query safety

* **All SQL is parameterized.** The only text ever interpolated into a
  statement is a sort direction chosen from a closed enum and a savepoint name
  generated from an internal counter (and validated as alphanumeric anyway).
* **FTS5 expressions are built from escaped literals.** Each term becomes a
  double-quoted FTS5 string with internal quotes doubled, which makes
  operators (`AND`, `OR`, `NEAR(…)`, `*`, `(`) inert data.
* **`LIKE` patterns escape `%`, `_` and `\`** with an explicit `ESCAPE` clause,
  so a folder named `%` cannot widen a subfolder filter.
* **NUL bytes are stripped** from queries before they reach SQLite.
* **Query length, term count and wildcard count are capped.**
* **Extensions cannot be loaded**; `enable_load_extension(False)` is set on
  every connection.

`tests/test_privacy.py` runs 10 SQL-injection strings and 17 FTS
metacharacter strings through every search scope, and asserts after each that
the schema and every table's row count are byte-identical, then runs
`PRAGMA integrity_check`.

---

## 7. Denial of service

A search box that anyone can type into must not be able to freeze the
application.

The wildcard matcher does **not** use a regular-expression engine. Translating
`*` to `.*` makes `a*a*a*b` take 21.6 seconds against 600 characters, and
document units can be 200,000 characters. The matcher is a linear segment
scanner instead — same pattern, 0.04 ms. See
[ADR 0005](decisions/0005-wildcards-and-redos.md).

Searches run on a worker thread with a cancellation token, candidate retrieval
is row-limited, and result sets are capped and paged.

---

## 8. Output safety

Document content is **never rendered as markup**.

Snippets are plain text plus `[start, end)` highlight offsets. The Qt delegate
paints the text with `QPainter.drawText` and fills a rectangle behind the
highlighted ranges. There is no HTML, no rich-text engine, and therefore
nothing to inject.

A fixture document containing `<script>alert("x")</script>` is indexed, found,
and displayed as those literal characters — verified both by a test and by
inspection of a rendered screenshot.

---

## 9. Process and data integrity

* **Single instance.** Two SQLite writers must never share the index. The guard
  is an exclusive OS lock on byte 0 of a lock file — not a PID file, which goes
  stale after a crash. Verified with a real subprocess.
* **Per-file atomicity.** Each file's delete-and-reinsert runs inside a
  `SAVEPOINT`; a failure rolls that file back and leaves the previous valid
  entry intact.
* **Safe cancellation.** Completed batches stay committed, the in-flight file
  rolls back, and deleted-file cleanup runs *only* after a complete scan — so
  cancelling can never shrink the index.
* **Crash recovery.** Index runs left in `running` state are marked failed on
  the next launch, so the UI never claims an indexing run is still going.
* **Damaged index.** Quarantined to `backups\` with a timestamp, never deleted,
  and a fresh index is created so the application still starts.
* **Newer schema.** Reported, not modified — downgrading cannot destroy an
  index.

---

## 10. Dependencies

All pinned in `requirements.txt`; nothing is fetched at runtime.

| Package | Version | Licence |
|---|---|---|
| PySide6 (+ Essentials, Addons, shiboken6) | 6.11.2 | LGPL-3.0 |
| PyMuPDF | 1.26.5 | **AGPL-3.0 or commercial** |
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| et-xmlfile | 2.0.0 | MIT |
| lxml | 6.0.2 | BSD-3-Clause |
| typing_extensions | 4.15.0 | PSF-2.0 |

> **PyMuPDF is AGPL-3.0 or commercial.** Distributing this application outside
> the organisation that built it requires either releasing the whole
> application under the AGPL with source available, or buying a commercial
> PyMuPDF licence. `pyproject.toml` currently says `Proprietary`, which is
> incompatible with the first option. See
> [ADR 0007](decisions/0007-pdf-library-licensing.md) for the alternatives and
> the size of the change. Internal use is unaffected.

None of these packages performs telemetry. Notices are collected into
`LICENSES/` by `scripts/collect_licenses.py`, bundled next to the executable
and shown in the About dialog.

---

## 11. Release checklist

Before asserting the privacy statement in the About dialog:

1. `python -m pytest -m security` — all pass.
2. `python -m pytest` — full suite passes.
3. Build with `build/AdvanceFileSearch.spec`; confirm no console window.
4. Run the packaged `.exe` on a machine with **network access blocked**:
   index, search Thai and English, open a result, reveal in Explorer, restart,
   update the index.
5. Watch the process with a network monitor for the whole session; any
   outbound connection attempt is a release blocker.
6. Read `%LOCALAPPDATA%\Advance File Search\logs\application.log` and confirm
   it contains no document content and no search queries.
7. Confirm `LICENSES/` ships beside the executable.

Results of the last run are in [TEST_REPORT.md](TEST_REPORT.md).
