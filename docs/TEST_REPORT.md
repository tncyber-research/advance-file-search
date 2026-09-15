# Advance File Search 1.0.0 — System Test Report

**Date:** 2026-09-11
**Build:** `dist\Advance File Search\AdvanceFileSearch.exe` (PyInstaller onedir, windowed)
**Platform:** Windows 11 Education 26200, 64-bit
**Python:** 3.12.10 · **SQLite:** 3.49.1 (FTS5 + trigram available)

| | |
|---|---|
| Automated tests | **619 passed, 1 skipped, 0 failed** (620 collected) |
| Packaged-build acceptance | **41 checks, all passed** |
| GUI walkthrough (source) | **95 checks, all passed** |
| Distribution | 274 files, 134.6 MB |

Includes the second UI revision (application icon, reworked result table and
details panel, search-driven indexing) and the third (compact Open button,
illustrated user manual). See [ADR 0009](decisions/0009-ui-revision.md),
[ADR 0010](decisions/0010-user-manual.md) and sections 4.1–4.2.

The single skip is `test_symlink_directory_is_detected`, which needs Developer
Mode or elevation to create a symlink. The same policy is covered by
`test_scanner_does_not_follow_a_directory_junction`, which passes.

---

## 1. Automated test suite

```
tests/test_query_and_wildcard.py   74
tests/test_search.py               77
tests/test_privacy.py              64
tests/test_parsers.py              58
tests/test_ui.py                   57
tests/test_report.py               44
tests/test_security.py             43
tests/test_scanner_and_indexing.py 43
tests/test_storage.py              35
tests/test_ui_layout.py            34
tests/test_manual.py               34
tests/test_integration.py          30
tests/test_paths.py                27
                                  ---
                                  620
```

Whole suite runs in about 110 seconds. Slowest single test is the 1,000-file
performance run at 3.9 s.

Every test document is generated at run time by `tests/make_fixtures.py`. No
real or confidential document exists anywhere in the repository.

---

## 2. Functional results

### 2.1 Formats

| Format | Fixtures | Result |
|---|---|---|
| TXT | UTF-8, UTF-8 BOM, UTF-16, CP874/TIS-620, 250 KB single line, empty, binary-disguised, CSV | all handled; BOM consumed, not indexed as text |
| PDF | 3-page English, Thai, image-only, AES-256 password-protected, corrupt | page-level units; image-only → `no_text`; protected → `password_protected`; corrupt → `corrupt` |
| DOCX | Thai + English paragraphs, table, header/footer, empty, corrupt, HTML-like text, inflating archive | paragraph/table-cell/header/footer units in body order |
| XLSX | Thai sheet name, hidden sheet, numbers, formula, 400-row sheet, empty, corrupt | cell-level units with sheet + coordinate |

Verified behaviours worth calling out:

* **Hidden worksheets are skipped.** `budget.xlsx` contains a `HiddenSheet`
  with the text "hidden sheet needle"; it is absent from the index.
* **Formulas are not evaluated.** `formula.xlsx` has `=SUM(A1:A2)` with no
  cached result; `10` and `20` are indexed, `30` is not, `=SUM` is not.
* **DOCX body order is preserved.** A table appears in sequence between the
  paragraphs that surround it, not appended after all text.
* **Image-only PDF is a normal outcome**, reported as "No searchable text was
  found. The PDF may be scanned or image-only." — not an error.
* **A UTF-16 BOM is consumed by the codec**, so no `U+FEFF` leaks into the
  first indexed unit. (Found and fixed during testing.)

### 2.2 Thai and English search

The headline requirement. A 300-document prototype measured the problem
directly:

| Tokenizer | `"งบประมาณ"` inside an unspaced run | True occurrences |
|---|---|---|
| `unicode61` | 154 (948 with a prefix query) | 1,882 |
| `trigram` | **1,882** | 1,882 |

`unicode61` misses roughly half of all Thai matches because it treats an entire
unspaced Thai run as one token. The index uses `trigram`. See
[ADR 0001](decisions/0001-thai-search.md).

Verified against the fixture corpus:

| Query | Result |
|---|---|
| `งบประมาณ` | 5 files — TXT (UTF-8, BOM, CP874), DOCX, PDF |
| `ครุภัณฑ์` | 6 files, including the XLSX cell `งบประมาณ 2568!A2` |
| `งบประมาณครุภัณฑ์` (full phrase) | 4 files |
| `๒๕๖๘` (Thai numerals) | 4 files |
| `2568` (Arabic numerals) | 4 files |
| `1,250,000` | 1 file, correct line |
| `Budget งบประมาณ` (mixed) | matched |
| Thai file name, Thai folder name | matched |
| Thai sheet name reported as a location | `ชีต: งบประมาณ 2568, เซลล์: F12` |

### 2.3 Search options

| Option | Test | Result |
|---|---|---|
| Match case | `BUDGET` → 0, `budget` → 3, `Budget` → 1 | correct |
| Whole word | `budget` → 3, `udge` → 0 | correct |
| Exact phrase | `annual equipment budget report` → 3; reordered → 0 | correct |
| `*` wildcard | `bud*et`, `*ครุภัณฑ์*`, `utf8_*` | correct |
| `?` wildcard | `need?e` → 6, `need??e` → 0 | correct |
| Scope: names only | `thai` → 4, all `match_source=name` | correct |
| Scope: content only | `thai` → 0 (no fixture has it in text) | correct |
| Scope: both | `budget.xlsx` correctly reported as `both` | correct |
| Short term (`งบ`, 2 chars) | falls back to a bounded scan, 5 files | correct |

### 2.4 Locations

| Format | Reported as |
|---|---|
| PDF | `หน้า 2` / `Page 2` |
| DOCX paragraph | `ย่อหน้า 24` / `Paragraph 24` |
| DOCX table | `ตาราง 1 แถว 2 คอลัมน์ 3` |
| XLSX | `ชีต: งบประมาณ 2568, เซลล์: F12` |
| TXT | `บรรทัด 135` / `Line 135` |

A matching spreadsheet cell shows its row neighbours, so `ครุภัณฑ์สำนักงาน`
displays as `ครุภัณฑ์สำนักงาน | 3 | 45000` rather than as a bare cell.

### 2.5 Filters, sorting, paging

All six sort fields, all filter types (extension, date range, size range,
subfolder), paging and the result limit were exercised through both the search
service and the real UI. A subfolder filter containing `%` correctly matches
nothing rather than widening the search.

### 2.6 Incremental indexing

| Scenario | Expected | Observed |
|---|---|---|
| First run, 24 files | index everything | 15 indexed, 4 no-text, 5 failed, 5 skipped |
| Re-run, nothing changed | skip all | 24 unchanged, 0 indexed, **0.02 s** |
| Add 1 file | index 1 | 1 indexed, 23 unchanged |
| Modify 1 file | replace it | 1 indexed; old content no longer findable |
| Delete 1 file | remove it | 1 deleted; row gone from `files` |
| Rename 1 file | delete + add | 1 indexed, 1 deleted, new name searchable |
| Rebuild | re-extract all | 0 unchanged, all re-indexed |
| Repeat update ×3 | no orphans | `content_units` = `content_fts`, 0 orphans |

### 2.7 Performance (1,000 synthetic text files)

| Operation | Time |
|---|---|
| Full index build | 2.95 s |
| No-op update | 0.21 s |
| Index size | 1.8 MB |
| `งบประมาณ` | < 10 ms |
| `budget report` | < 10 ms |
| `token7_13` | < 10 ms |

Comfortably inside the "search returns within about one second" target for the
2,000–3,000 file workload, with headroom.

---

## 3. Security and privacy results

### 3.1 Offline operation — release blocker, PASSED

| Check | Result |
|---|---|
| No source file imports a networking library (AST scan of all 33 modules) | PASS |
| Full index + search with `socket.socket`, `create_connection` and `getaddrinfo` patched to raise | PASS |
| `logging_setup` does not import `logging.handlers`, `socket` or `pickle` | PASS |
| No WebView or Qt network class referenced anywhere | PASS |
| No remote font or CDN reference | PASS |
| Fresh interpreter importing the app loads no HTTP client | PASS |

**The packaged build has no networking capability at all.** These files are
not merely unused — they are absent from the distribution:

```
_socket.pyd        _ssl.pyd         select.pyd
libssl-3.dll       libcrypto-3.dll
Qt6Network.dll     Qt6Qml.dll       Qt6Quick.dll      Qt6Pdf.dll
```

Two problems had to be solved to get there, both found by testing:

1. `logging.handlers` imports `socket` and `pickle` at module level, to define
   `SocketHandler` and `SysLogHandler`. A ~60-line
   `SizeRotatingFileHandler` replaces it. Rotation is covered by a test that
   writes 400 records against a 2 KB limit and asserts the active log stays
   under its cap with exactly the configured number of backups.
2. PyInstaller injects a `multiprocessing` runtime hook that imports `socket`.
   `multiprocessing` is now excluded; the application uses `QThread`.

### 3.2 Local-paths-only enforcement — PASSED

All rejected, with the correct verdict and a clear message:

```
\\server\share            \\?\UNC\server\share      \\127.0.0.1\c$
http:// https:// ftp:// sftp:// webdav:// smb:// file:// mailto:
javascript: data: shell:
\\.\PhysicalDrive0        \\?\GLOBALROOT\...
mapped network drives (GetDriveTypeW = DRIVE_REMOTE)
optical drives            relative paths           empty paths
```

**Ordering verified:** `os.stat` and `os.path.exists` were patched to raise,
and hostile paths were still rejected — proving no SMB/WebDAV connection
attempt can be triggered by validating a path.

Junction loops, symlinks, reparse points and cloud placeholder files are
skipped. A `mklink /J` loop pointing at its own ancestor terminates with the
correct file count.

### 3.3 Log privacy — PASSED

| Check | Result |
|---|---|
| A unique token in a document never appears in the log | PASS |
| A unique search query never appears in the log | PASS |
| A secret inside a file that *fails to parse* never appears | PASS |
| No traceback is ever written | PASS |
| Every record is a single line | PASS |
| Path logging can be disabled | PASS |
| Rotation is configured and actually rotates | PASS |

Confirmed again against the log written by the **packaged** application.

### 3.4 SQL injection and FTS metacharacters — PASSED

10 injection strings × 17 FTS metacharacter strings × 3 search scopes. After
every one, the schema and the row count of all five tables were compared
byte-for-byte against a baseline, then `PRAGMA integrity_check` was run.

```
'; DROP TABLE files; --        " OR 1=1 --
' UNION SELECT * FROM sqlite_master --
'; ATTACH DATABASE 'evil.db' AS evil; --
'; PRAGMA writable_schema=1; --
NEAR(a b)   a AND b NOT c   ((((   """""   *   ^   column:value   %   _   \
```

Nothing changed. A file *named* `quote'and; drop table-- 100% (a) [b] & #1.txt`
and a file whose *content* is `'; DROP TABLE files; --` are both indexed as
ordinary data and are findable by searching for them.

### 3.5 Denial of service — PASSED (defect found and fixed)

A real vulnerability was found during testing. The first wildcard
implementation translated `*` into a regular expression:

| Pattern | Subject | Before | After |
|---|---|---|---|
| `a*a*a*b` | 600 chars | **21.6 s** | — |
| `a*a*a*a*a*b` | 4,000 chars | did not complete | **0.04 ms** |
| `*a*a*a*a*a*` | 20,000 chars | — | 0.04 ms |
| `a?a?a?a?a?b` | 20,000 chars | — | 17 ms |
| `งบ*ประมาณ*ครุ*ภัณฑ์*x` | 40,000 chars | — | 0.48 ms |

Anyone typing `a*a*a*b` into the search box could have frozen the application.
The matcher was rewritten as a linear segment scanner with no regex engine
([ADR 0005](decisions/0005-wildcards-and-redos.md)). Five
`@pytest.mark.security` tests now assert a sub-second bound so a future change
cannot reintroduce it.

Also verified: query length cap (500), term cap (24), wildcard cap, result
limits, candidate-row limits, and cancellation returning promptly.

### 3.6 Output safety — PASSED

Document content is never rendered as markup. Snippets are plain text plus
integer offsets; the Qt delegate paints with `QPainter.drawText` and fills a
rectangle behind the highlighted ranges.

A DOCX containing `<b>bold</b> <script>alert("x")</script>` is indexed, found,
and displayed as those literal characters. Confirmed by test **and** by
inspecting a rendered screenshot of the result table.

### 3.7 Untrusted input — PASSED

| Input | Result |
|---|---|
| 20 corrupt DOCX + 1 good file | run completes, good file indexed |
| Zip-bomb DOCX (19 KB → 20 MB) | reported as corrupt, no memory exhaustion |
| `.exe`, `.bat`, `.docm` in the corpus | never indexed, never opened |
| `~$lock.docx` | skipped |
| Binary file named `.txt` | detected, reported as no-text |
| File vanishing between scan and read | run completes, entry removed |
| File name with `' ; -- % ( ) [ ] & #` | indexed as data, searchable |

`open_file` refuses executables, missing files and remote paths. Explorer is
invoked with an argument list, never a command string — a path containing
`" & calc.exe & "` travels as one argument no shell parses.

---

## 4. UI verification

64 scripted interactions against real Qt widgets, plus 56 automated UI tests.

| Area | Result |
|---|---|
| First-run state, search disabled until an index exists | PASS |
| Root selection, recent roots, remote-root rejection | PASS |
| Index progress dialog: phases, counters, determinate bar, cancel, problem list | PASS |
| Search through the UI, Thai and English | PASS |
| Details panel, expandable match locations | PASS |
| Filters panel narrowing results | PASS |
| All six sort options | PASS |
| Missing file: struck through, actions disabled, warning shown, offers reindex | PASS |
| Copy path to clipboard | PASS |
| Settings dialog edits a copy; flags when a reindex is needed | PASS |
| About dialog with privacy statement, limitations, licences | PASS |
| Thai UI and English UI both render and search | PASS |
| Window resizes 1040×640 → 1600×900 | PASS |
| Keyboard shortcuts (Ctrl+F, Ctrl+Shift+E/C, F5) | PASS |
| Accessible names on all major controls | PASS |
| UI stays responsive during search (event loop ticks) | PASS |
| Geometry and column widths persist | PASS |
| Match column keeps a readable width when a neighbour is widened | PASS |

Two layout defects were found by inspecting rendered screenshots and fixed: an
unset date filter displayed as `1/1/1980` instead of blank, and a stale status
message persisted after a later clean search.

### 4.1 UI revision (second round)

31 further tests in `tests/test_ui_layout.py`, plus a 95-check scripted
walkthrough against the real widgets.

| Change | Verified |
|---|---|
| Multi-resolution icon in the title bar and taskbar | 8 sizes (16–256) packed into the ICO; transparent background confirmed by pixel alpha; rendered and inspected at every size |
| Location column removed | header set asserted in both languages |
| Match preview with highlighted query | text, location label, highlighted runs, Thai preserved exactly, out-of-range highlights clamped |
| Preview shows markup as literal text | `<script>` fixture round-trips unchanged; highlight proven to be character formatting, not markup |
| Details omits relative path and file type | field list asserted |
| Full path elided at folder boundaries, complete on hover | fits the label at 1400 px and at the 1040 px minimum |
| Open column button reveals the folder | click path asserted; inert for missing files and for child rows; a click outside the button does nothing |
| Larger base font | 11 pt floor, taller rows |
| Searching builds the index when none exists | dialog completes, then the search runs automatically |
| Later searches refresh in the background | results immediate, UI stays enabled, refresh completes, activity indicator clears |
| Refresh is throttled | a repeat search does not re-scan |
| Typing never triggers indexing | debounce fires with no index run |

Three defects were found and fixed during this round:

1. **The window icon was never set.** `QApplication.setWindowIcon` was not
   called, so the title bar showed a placeholder even though the `.exe` had an
   icon resource.
2. **The details path was silently clipped.** `QLabel` derives its
   `minimumSizeHint` from the full text, so a long path made the panel demand
   more width than it had and whole path components disappeared. Fixed with an
   eliding label that reports a small fixed hint.
3. **The Match column collapsed.** With a larger font and a wider details
   panel, the fixed columns squeezed the stretching Match column to a few
   characters. Column widths were reduced and a floor added.

### 4.2 UI revision (third round)

26 tests in `tests/test_manual.py`, plus a scripted check of the two changes
against the real window.

| Change | Verified |
|---|---|
| Open-folder button reduced to an icon | 30 × 24 px glyph centred in the cell; column 58 px (was 104); size no longer grows with the column |
| The button still explains itself | tooltip `เปิดโฟลเดอร์ที่เก็บไฟล์นี้` on the cell, present in both languages |
| The button still works | click reveals the folder; inert on child rows and missing files |
| About replaced by **คู่มือการใช้งาน** in the toolbar | toolbar reads `สถานะดัชนี · ตั้งค่า · คู่มือการใช้งาน · ตัวกรองขั้นสูง ▾` |
| About is still reachable | moved into the index menu, which now reads `อัปเดตดัชนี · สร้างดัชนีใหม่ทั้งหมด · ลบดัชนี · เปิดโฟลเดอร์ข้อมูลโปรแกรม · เกี่ยวกับโปรแกรม` |
| The manual button opens the manual | resolves `Manual\index.html` from both the source tree and the packaged layout and hands it to the shell |
| The manual is complete | 58,568 characters, all nine required sections present, `Create by TnCyber@CS 2026` in the footer |
| The manual is illustrated | 23 image files, 20 referenced, every reference resolves; PNG magic bytes and SVG roots checked |
| **The manual is offline** | no `http:`/`https:`/`//` in any `src`, `href`, `url()`, `@import` or `@font-face`; no `<script>`; no inline event handler |
| The manual honours the font requirement | `Sarabun` first in the stack with local fallbacks; body font-size 16 px |
| The manual ships with the build | `Manual\index.html` added to the spec, the post-build surface list, and `verify_build.py` |

Screenshots in the manual are captured from the running application by
`scripts\make_manual_screenshots.py`, and the numbered callout badges are
positioned from live widget geometry rather than hard-coded pixels, so they
follow the controls when the layout changes. See
[ADR 0010](decisions/0010-user-manual.md).

One defect was found and fixed during this round, and it was not cosmetic:

**A search could fail while the index refreshed in the background.** The
search-driven refresh added in the previous round made searching and indexing
genuinely concurrent for the first time. A search issued while the indexer was
optimizing the FTS table failed with `vtable constructor failed: content_fts`
and returned an empty result list — indistinguishable, to the user, from "no
matches". SQLite errors are now classified, and a search that hits a transient
one drops its thread connection, waits 120 ms and retries once. Four tests
cover it, including one that runs a real reader against a real writer.

### 4.3 Project report (third round, documentation)

44 tests in `tests/test_report.py`.

| Requirement | Verified |
|---|---|
| The report exists and is substantial | `Manual/report.html`, 80,882 characters, 14 sections |
| All fourteen requested topics are present | one parametrized test per section heading |
| Twelve diagrams drawn and used | architecture · modules · tech stack · index flow · search flow · thread and database connections · data flow · ERD · UX layout · test summary · timeline · revision history |
| Numbered screenshots referenced from the prose | 7 callout captures, including two new ones (settings dialog, index menu) generated by the same capture script |
| Every referenced image exists | 25 references, all resolving |
| **Offline** | no remote `src`/`href` (protocol-relative included), no `url()`/`@import`/`@font-face`, no `<script>`, no inline handler |
| Font requirement | Sarabun first with local fallbacks, body 16 px |
| Tech stack documented in detail | all 11 technologies named and their role stated |
| Database documented | all 7 tables named |
| Test results included | the measured numbers, not just the claim |
| Revision history | all three rounds, with the application version left at 1.0.0 |
| **Not linked from the UI** | a test greps `advance_file_search/ui/` for `report.html` and fails if anything references it |
| Ships with the build | `Manual/report.html` added to `verify_build.py`'s required files |

The report states plainly that the system has no server, and explains that the
"server side" of the requested client/server diagram is played by the
in-process engine and storage layers. Inventing a server to satisfy the shape
of the request would have made the document wrong.

### 4.4 Manual revision (fourth round)

33 tests in `tests/test_manual.py`.

| Requirement | Verified |
|---|---|
| Responsive page | viewport meta, breakpoints at 1100 px and 640 px, wide tables scroll inside `.tablewrap`; checked by rendering the page at 383 px and confirming `scrollWidth == clientWidth` |
| Base font size | 14 px first, raised to **16 px** after the owner reported it was too small to read; no prose in the document is now below 16 px, and a test asserts the floor |
| Sarabun first, local fallbacks | `Sarabun, TH Sarabun New, Leelawadee UI, Noto Sans Thai, …`; no `@font-face`, no CDN |
| Preface, objectives, benefits, intended use | one test per topic |
| Minimum and recommended specification | `Windows 10` · `Windows 11` · `64 บิต` · `8 กิกะไบต์` · a recommended column |
| Other operating systems and prerequisites | states that Linux and macOS are out of scope, and that no other software need be installed |
| Installation, with a picture of what to double-click | `fig_install.svg` plus `AdvanceFileSearch.exe` named in the prose |
| **Screen explained region by region** | four region captures (`20_area_top` … `23_area_actions`), each ≤ 6 badges, because one picture with 14 badges is unreadable |
| Every sub-dialog captured and explained | progress dialog, three settings tabs, index menu, About |
| Step-by-step procedures | four numbered walkthroughs, cross-referencing badge numbers by figure |
| Scope, limitations, troubleshooting | present, with eight FAQ entries |
| Credit line with month and year | `Create by TnCyber@CS · กันยายน 2569 (September 2026)` — a regex checks the year is there |

Two real UI defects were found while capturing the screenshots for this round:

15. **The About dialog's Close button was in English.** Qt supplies its own
    label for a standard button, so a Thai interface showed `Close`. Now
    translated through the same table as everything else.
16. **A settings checkbox was labelled for the wrong thing.** The switch that
    remembers the advanced filters between sessions reused the string
    "ตัวกรองขั้นสูง", which reads as a switch for the filters themselves. It has
    its own string now.

Both are small, and both were only visible because the manual's screenshots are
captured from the real application rather than drawn.

### 4.5 Field fixes (fifth round)

Three problems reported after the owner used the build on real documents.
All three are fixed, with 14 new tests.

| Reported as | Actual cause | Fix | Tests |
|---|---|---|---|
| "Open folder does nothing for Thai folder names with spaces, though the tooltip shows the right path" | Not Thai at all — **spaces**. `subprocess` turns an argument list into a command line with MSVC quoting, so `/select,C:\folder with space\file.txt` became `"/select,C:\folder with space\file.txt"`. Explorer parses its own command line and no longer recognises the switch, so it opened its default folder | Dropped the subprocess: the shell is asked directly through `SHOpenFolderAndSelectItems`, which takes a path and builds no command line. Falls back to opening the containing folder | 3 (incl. one asserting reveal calls no `subprocess`, by AST) |
| "The matching text on the right is too short to tell whether it is the right file" | One line of a text file is one indexed unit; a short line makes a short snippet | When a snippet comes out under 150 characters, the two units either side are joined in and the snippet is rebuilt over the combined text (highlights are recomputed, not translated). Preview grew to four lines; snippet context 90 → 130 characters | 4 |
| "Add an Open-file button after the Open-folder button; use Open with when the program is missing" | New feature | Each row now paints two icon buttons. `open_file` catches `ERROR_NO_ASSOCIATION` / `ERROR_GEN_FAILURE` and reopens through the shell's `openas` verb — the Windows "Open with" chooser | 7 |

The first one is worth keeping as a lesson: the symptom pointed at Thai text,
and the cause was quoting. An English path with a space failed identically,
which is what identified it.

---

## 5. Packaged build acceptance

`python scripts\test_packaged_build.py "dist\Advance File Search"` — run with
the **system** Python, outside the build virtual environment.

| Group | Checks | Result |
|---|---|---|
| Runs without the build environment | 3 | PASS |
| Formats and Thai text | 5 | PASS |
| GUI starts, creates its data tree | 6 | PASS |
| Single-instance guard | 2 | PASS |
| Log privacy | 4 | PASS |
| No networking capability bundled | 7 | PASS |
| Index integrity | 4 | PASS |
| Distribution contents | 5 | PASS |

The packaged executable self-test indexes all four formats and searches Thai:

```
Advance File Search 1.0.0 self-test
  frozen : True
  [PASS] SQLite has FTS5
  [PASS] trigram tokenizer available
  discovered=24 indexed=15 no_text=4 failed=5 skipped=5 in 0.62s
  Thai search 'ก' -> 7 files (2.2 ms)
  [PASS] database integrity
  file types indexed: {'.txt': 8, '.docx': 5, '.pdf': 5, '.xlsx': 5, '.csv': 1}
SELF-TEST PASSED
```

The GUI window was confirmed to render from the packaged binary: title
`Advance File Search`, visible, 1056×679, captured with `PrintWindow` and
inspected. Thai first-run screen renders correctly, privacy statement visible
in the status bar.

`AdvanceFileSearch.exe --selftest <folder>` is available as a support
diagnostic.

---

## 6. Defects found and fixed during testing

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | Wildcard matching used a regex; `a*a*a*b` took 21.6 s over 600 chars — a search box anyone can type into could freeze the application | **High** | Fixed: linear segment matcher, 0.04 ms |
| 2 | `unicode61` tokenizer missed ~50 % of Thai matches | **High** | Fixed: trigram tokenizer |
| 3 | Single-instance lock taken at the current file position, then the PID was written — moving it. Two instances locked different bytes and both ran | **High** | Fixed: lock byte 0 explicitly; PID written after it |
| 4 | Parsers used plain `Path`, so a file deeper than `MAX_PATH` was reported as *missing* rather than indexed | Medium | Fixed: `safe_path()` in `DocumentParser.parse` |
| 5 | A connection that failed during PRAGMA setup was never registered, so a damaged index stayed locked and could not be quarantined | Medium | Fixed: close on failure |
| 6 | `IndexWorker` opened the database without migrating; a deleted index file produced "no such table: roots" | Medium | Fixed: worker uses `open_index` |
| 7 | UTF-16 BOM decoded into the first indexed unit as `U+FEFF` | Low | Fixed: BOM-aware codec names |
| 8 | Unset date filter displayed as `1/1/1980` | Low | Fixed |
| 9 | Stale status message persisted after a later clean search | Low | Fixed |
| 10 | `logging.handlers` pulled `socket` into the bundle | Low (blocked the stronger offline guarantee) | Fixed: own rotating handler |
| 11 | `QApplication.setWindowIcon` was never called, so the title bar and Alt-Tab showed a placeholder | Low | Fixed: multi-resolution icon loaded at startup |
| 12 | The details panel clipped long paths, dropping whole folder components | Medium | Fixed: eliding label that cuts at folder boundaries |
| 13 | The Match column collapsed to a few characters once the font and details panel grew | Medium | Fixed: reduced column widths plus a minimum width for Match |
| 14 | A search running while the background index refresh optimized the FTS table failed with `vtable constructor failed`, returning an empty result list | **High** | Fixed: transient SQLite errors are classified and retried once |
| 15 | The About dialog's Close button showed Qt's English label in the Thai interface | Low | Fixed: translated through the application's own table |
| 16 | The "remember the advanced filters" checkbox was labelled "advanced filters", which reads as a switch for the filters | Low | Fixed: its own string |
| 17 | Reveal-in-Explorer opened the wrong folder whenever the path contained a space, because the `/select,` argument was quoted as a whole | **High** — the feature silently did the wrong thing | Fixed: the shell API is called directly, with no command line |
| 18 | The match preview showed only the matching line, which is often too short to identify a document | Medium | Fixed: neighbouring units are folded in when the snippet is short |
| 19 | Opening a file whose type has no registered program reported a bare failure | Low | Fixed: falls back to the Windows "Open with" chooser |

---

## 7. Definition of done (handoff §21)

| # | Requirement | Status |
|---|---|---|
| 1 | Runs on clean Windows 10/11 64-bit without Python | ✅ verified with system Python, frozen build |
| 2 | Launches through `AdvanceFileSearch.exe` | ✅ |
| 3 | No `.bat`, `.cmd`, browser or server | ✅ verified |
| 4 | Works with network access disabled | ✅ no network capability is bundled |
| 5 | Makes no outbound connection | ✅ automated + binaries absent; manual monitor pending |
| 6 | Accepts only local folders and drives | ✅ 38 security tests |
| 7 | Indexes PDF, DOCX, XLSX, TXT | ✅ 58 parser tests |
| 8 | Skips image-only PDFs without OCR | ✅ |
| 9 | Creates and updates an SQLite/FTS5 index | ✅ |
| 10 | Detects new, modified and deleted files | ✅ |
| 11 | Searches Thai and English names and content | ✅ |
| 12 | Core filters and documented wildcards | ✅ |
| 13 | Shows snippet and source location | ✅ |
| 14 | Shows file metadata | ✅ |
| 15 | Opens the original file | ✅ |
| 16 | Opens Explorer and selects the file | ✅ |
| 17 | UI responsive during indexing | ✅ worker-thread test |
| 18 | Cancellation without corrupting the index | ✅ |
| 19 | Does not log content or queries | ✅ |
| 20 | Handles corrupt and inaccessible files | ✅ |
| 21 | Synthetic automated tests | ✅ 620 |
| 22 | Build documentation and dependency versions | ✅ |
| 23 | Privacy statement | ✅ in the About dialog, `PRIVACY.txt` and the user manual |
| 24 | Third-party licence notices | ✅ 11 files bundled |
| 25 | Offline and network-monitoring acceptance | ⚠️ automated parts pass; **manual monitor run outstanding** |
| — | Project report (added at the owner's request, beyond §21) | ✅ `Manual\report.html`, bundled, not linked from the UI |
| — | User manual (added at the owner's request, beyond §21) | ✅ `Manual\index.html`, bundled and verified |

---

## 8. Outstanding items

Two things cannot be closed from this environment and need a person:

1. **Network-monitoring acceptance run** (handoff §2.8 step 10). The automated
   equivalent passes and the packaged build physically lacks socket support,
   but watching the process with a network monitor for a full session is a
   separate, human confirmation. Procedure:
   [SECURITY.md § 11](SECURITY.md#11-release-checklist).

2. **Clean-machine test** on a Windows box with no Python and no build tools.
   Procedure: [BUILD.md](BUILD.md#clean-machine-test).

And one decision belongs to the project owner:

3. **PyMuPDF is AGPL-3.0 or commercial.** Distributing outside the
   organisation that built this requires either releasing the whole
   application under the AGPL with source, or a commercial licence.
   `pyproject.toml` currently says `Proprietary`, which conflicts with the
   first option. Internal use is unaffected. The PDF parser is the only module
   that touches PyMuPDF and can be moved to `pypdf` (BSD) or `pdfminer.six`
   (MIT) — the parser tests are written against the result contract, not the
   library, so they would validate a replacement unchanged.
   See [ADR 0007](decisions/0007-pdf-library-licensing.md).

## 9. Known limitations (by design, documented in the UI)

* No OCR; scanned PDFs report "no searchable text" rather than failing.
* Legacy `.doc` and `.xls` are not supported.
* Word page numbers cannot be determined without rendering; DOCX matches
  report paragraph and table positions.
* Excel formulas are not recalculated; the stored cached value is indexed.
* Network, NAS and cloud locations are out of scope for version 1.
* Trigram matching means search is substring-based: `budget` also matches
  `prebudgeting`. **Whole word** is available when that is not wanted.
* Queries shorter than three characters use a bounded scan rather than the
  index, and are slower on a large corpus.
