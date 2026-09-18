# Handoff

Everything a new maintainer needs to pick this project up. Written
2026-09-18, against the state of the working tree on that date.

`handoff.md` in the repository root is a different document: it is the
original specification the project was built from, kept for reference.

---

## 1. Goal and context

Advance File Search exists so that someone who remembers a phrase from a
document can find the document again, without the documents leaving their
machine. Two constraints shaped nearly every decision:

1. **Offline is a requirement, not a preference.** The target users handle
   government and internal paperwork. Any design that would upload, sync or
   phone home was rejected, and the absence of networking is enforced by
   tests and by stripping the binaries from the distribution.
2. **Thai has to work properly.** Thai does not space its words. This ruled
   out the default full-text tokenizer and drove the choice of an FTS5
   trigram index, which in turn drove the verification layer in the search
   service (case sensitivity, whole-word and wildcards are checked in memory
   because the index cannot express them).

---

## 2. What is done

| Area | State |
|---|---|
| Indexing | Complete: scan, fingerprint, per-file transactions, incremental update, cancellation, deletion detection |
| Formats | PDF, DOCX, XLSX, TXT/MD/CSV/LOG, with encoding detection for Thai legacy code pages |
| Search | Query parsing, trigram index, in-memory verification, filters, ranking, snippets, location reporting |
| UI | Main window, index progress dialog, settings, about, advanced filters, match preview, per-row actions, Thai/English |
| Storage | SQLite schema v1, external-content FTS with triggers, WAL, migrations |
| Packaging | PyInstaller onedir, post-build stripping, build verification, packaged acceptance test |
| Documentation | User manual and project report (Thai, illustrated), build/security/test docs, 10 ADRs |
| Tests | 620 collected; 619 pass, 1 skipped |
| Lint | Clean; every suppression carries its reason in place |
| CI | GitHub Actions on Windows: lint + 529 non-GUI tests required, 91 Qt tests advisory |

---

## 3. What is not done

- **PyMuPDF licensing decision.** AGPL-3.0 or commercial. Blocks distribution
  outside the organisation that built it. See §6.
- **Network-monitor observation run.** The automated equivalents pass and the
  distribution contains no networking binaries, but nobody has yet watched the
  process with a network monitor for a full session, which is the last item on
  the release checklist in `docs/SECURITY.md`.
- **Clean-machine test.** Copying the distribution to a Windows PC with no
  Python and no build tools, and working through `docs/BUILD.md`.
- **No packaging for other platforms.** Windows only, by design for v1.

---

## 4. Key technical decisions

The full set is in `docs/decisions/` (ADR 0001–0010); the ones that explain
the most code:

| Decision | Why | Consequence |
|---|---|---|
| FTS5 **trigram** tokenizer | `unicode61` finds ~8% of Thai matches inside unspaced runs; trigram finds all of them | Case, whole-word and wildcard semantics must be re-checked in memory; terms under 3 characters fall back to a bounded scan |
| **External-content** FTS tables + triggers | Document text is stored once, not twice | The index cannot drift, because SQLite keeps it in sync |
| Fingerprint = size + mtime + parser version | Hashing every file would cost as much as re-indexing | A file edited to the same size with a restored timestamp is missed; "Rebuild" exists for that |
| Own wildcard matcher, no regex | A user's query is untrusted input; regex opens ReDoS | Linear matching, bounded wildcard count |
| Painted plain text, no HTML rendering | Document content must never be interpreted as markup | Highlighting is drawn with `QPainter` / `QTextCharFormat` |
| `SHOpenFolderAndSelectItems` instead of `explorer.exe /select,` | Command-line quoting breaks on spaces | No command line is built for reveal at all |
| PyInstaller **onedir**, not onefile | onefile unpacks to a temp folder on every start and attracts anti-virus attention | Distribution is a folder, not a single file |
| Own rotating log handler | `logging.handlers` imports `socket`, which would put a socket module in the distribution | A small handler in `logging_setup.py` |

---

## 5. Known issues and technical debt

**Lint is clean.** `ruff check .` reports nothing. Getting there fixed 72
findings and left the rest suppressed *in place*, each with the reason written
next to it: swallowed exceptions on shutdown paths, Qt-mandated default
arguments, a lock file deliberately held open for the process lifetime,
`SystemRoot`'s Windows spelling, and the SQL placeholder counting. One rule is
declined project-wide in `pyproject.toml` with its reason — `UP042` would turn
`class X(str, Enum)` into `StrEnum`, which changes what `str(member)` returns,
and several of those values are formatted into messages and stored in the
database.

Keep it at zero: the CI job fails on any new finding.

**Other debt**

- CI covers lint and the 529 tests that need no windowing system. The 91 Qt
  widget tests run in an advisory job, because whether real windows can be
  created depends on the session the runner provides; they must still be run
  on a desktop before a release.
- No type checker configured. Type hints are used throughout but nothing
  verifies them.
- `Manual/report.html` and `Manual/index.html` are edited as files; their
  figures are generated by scripts. The screenshots must be regenerated
  whenever the UI changes, or the manual quietly goes stale
  (`pytest tests/test_manual.py` catches missing images, not wrong ones).
- Manual screenshots show a synthetic corpus under a temp path that includes
  the build machine's short user name. Harmless, but regenerate them on a
  machine whose user name you are happy to publish.
- The index has no schema-migration path beyond version 1; `app_meta` records
  the version, and the code currently only handles v1.

---

## 6. Risks and cautions

- **PyMuPDF is AGPL-3.0 or commercial.** Distributing the built application
  externally requires either releasing this application under the AGPL with
  source, or a commercial licence. `pyproject.toml` says `Proprietary`, which
  conflicts with the first option. The PDF parser is the only module that
  imports it, and its tests are written against the result contract, so a
  BSD/MIT replacement can be validated without rewriting them
  (`docs/decisions/0007-pdf-library-licensing.md`).
- **The repository has no LICENSE file.** Default copyright therefore applies.
  Decide this before making the repository public.
- **Do not add a dependency casually.** Every addition has to be re-checked
  against the offline guarantee (does it import `socket`?) and the licence
  position.
- **Do not let the UI thread touch the database for anything slow.** The
  search and index workers exist for that; a long query on the UI thread
  freezes the window.
- **Concurrency is real now.** Searching refreshes the index in the
  background, so a read can race a write. `DatabaseTransientError` plus a
  single retry handles it; keep that path when touching the search service.

---

## 7. How to resume work

```bat
cd Advance_FileSearch
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
set PYTHONPATH=%CD%
.venv\Scripts\python.exe -m advance_file_search.app --debug
```

Read in this order: `README.md` for the shape of the project,
`docs/ARCHITECTURE.md` for how the pieces fit, `docs/decisions/` for why they
fit that way, `docs/TEST_REPORT.md` for what has actually been verified.

---

## 8. Files worth knowing

| Path | Why it matters |
|---|---|
| `advance_file_search/storage/schema.sql` | The whole data model, with the trigram reasoning in comments |
| `advance_file_search/search/search_service.py` | Query execution, verification, ranking, snippet building, the retry path |
| `advance_file_search/indexing/coordinator.py` | The indexing run: scan, fingerprint, parse, per-file transaction |
| `advance_file_search/core/security.py` | Path validation — the gate that keeps network and reparse-point paths out |
| `advance_file_search/winplat/windows_shell.py` | Opening files and folders; the only place that talks to the shell |
| `advance_file_search/ui/main_window.py` | Everything the user sees, and the worker orchestration |
| `advance_file_search/core/i18n.py` | Every user-visible string, in two languages |
| `build/AdvanceFileSearch.spec` + `scripts/postbuild.py` | What ships and what is stripped |
| `scripts/verify_build.py`, `scripts/test_packaged_build.py` | The gates a release must pass |

---

## 9. Verification status (2026-09-18)

| Check | Result |
|---|---|
| `pytest` | PASS — 619 passed, 1 skipped, 0 failed (620 collected) |
| `ruff check .` | PASS — no findings |
| Type check | NOT RUN — no type checker is configured |
| `pip check` | PASS — no broken requirements |
| PyInstaller build | PASS |
| `scripts/verify_build.py` | PASS — all checks |
| `scripts/test_packaged_build.py` | PASS — 41 checks, run with system Python |
| Packaged self-test over a Thai corpus | PASS |
| Secret scan (grep for keys, tokens, passwords, e-mail addresses) | PASS — nothing found beyond a `user@example.com` test fixture |

---

## 10. Recommended next actions

1. Decide the PyMuPDF licence question, then add the matching `LICENSE` file.
2. Do the clean-machine test and the network-monitor run; both are the last
   items on the release checklist in `docs/SECURITY.md`.
3. Configure a type checker and get it to a clean baseline; CI already has a
   place to run it.
4. Consider a schema-migration path before the first change to `schema.sql`
   that cannot be solved by rebuilding the index.
5. Watch whether the advisory GUI job passes on the runner over a few runs. If
   it does, promote it to required; if it never can, say so in the workflow and
   stop looking at it.
