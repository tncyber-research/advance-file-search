# Decision log

Every decision with a real trade-off is recorded as an ADR in
[`decisions/`](decisions/), stating the context, the decision, its
consequences and the alternatives that were rejected. This file is the index,
plus the decisions taken in the current round that have not earned an ADR of
their own.

## Architecture decision records

| ADR | Decision | Why it matters |
|---|---|---|
| [0001](decisions/0001-thai-search.md) | Thai search strategy: FTS5 `trigram`, not `unicode61` | Measured first: `unicode61` found 154 of 1,882 real matches inside unspaced Thai. Everything in the search layer follows from this |
| [0002](decisions/0002-database-design.md) | One SQLite database with external-content FTS | Document text stored once; triggers keep the index in step |
| [0003](decisions/0003-xlsx-granularity.md) | Index spreadsheets cell by cell; never recalculate formulas | A result can name the sheet and cell; a stored value is reported, never a computed one |
| [0004](decisions/0004-fingerprint.md) | Detect change by size + mtime + parser version | Hashing every file costs as much as re-indexing; "Rebuild" covers the gap |
| [0005](decisions/0005-wildcards-and-redos.md) | A linear wildcard matcher instead of a regex engine | A user's query is untrusted input; no catastrophic backtracking is possible |
| [0006](decisions/0006-packaging.md) | PyInstaller onedir, Qt exclusions, long-path handling, single instance | Faster starts, fewer anti-virus problems, and a distribution that can be inspected |
| [0007](decisions/0007-pdf-library-licensing.md) | PyMuPDF for PDF text, with its AGPL obligation stated | **Open decision for the project owner** before any external distribution |
| [0008](decisions/0008-network-and-link-handling.md) | Refuse network paths; do not follow reparse points | Keeps the offline promise and stops scan loops |
| [0009](decisions/0009-ui-revision.md) | Result table, match preview, search-driven indexing | Removed the "update index" button; moved location next to the text it describes |
| [0010](decisions/0010-user-manual.md) | Compact Open button; manual as a local HTML file | A bundled document may not reference anything remote |

## Decisions in this round (2026-09-15)

Recorded here rather than as ADRs: each is small, and none changes the
architecture.

### Reveal a file through the shell API instead of `explorer.exe /select,`

**Context.** Revealing a file opened the wrong folder whenever the path
contained a space. `subprocess` builds a Windows command line from an
argument list using MSVC quoting, so the single argument
`/select,C:\folder with space\file.txt` was emitted quoted in full; Explorer
parses its own command line and stops recognising the switch. The symptom
appeared with Thai folder names because those usually contain spaces, but an
English path with a space failed identically.

**Decision.** Call `SHOpenFolderAndSelectItems` through `ctypes`, passing the
path as a string. Fall back to opening the containing folder if the shell
refuses.

**Consequences.** No command line is built for this operation at all, which
removes the whole quoting question and one process launch. A test asserts, by
AST, that `reveal_in_explorer` calls no `subprocess` function. The cost is a
small amount of `ctypes` and COM lifecycle code, and behaviour that cannot be
exercised on a non-Windows machine.

**Alternatives.** Passing a pre-quoted command-line string to `Popen` would
have worked, but it re-introduces exactly the string-building this project
avoids everywhere else. Always opening the folder without selecting the file
would have been simpler and worse for the user.

### Widen a short snippet with its neighbouring units

**Context.** One line of a text file is one indexed unit, so a match on a
short line produced a preview too short to judge the document by.

**Decision.** When a snippet is shorter than 150 characters, join the two
units either side and rebuild the snippet over the combined text; the snippet
builder recomputes highlight offsets on the string it returns, so nothing has
to be translated.

**Consequences.** Previews read as context. The cost is one extra bounded
query per short match, and a preview that may include text from adjacent
lines — which is the point, but it means the preview is not literally "the
matching unit" any more.

### Second row button, with an "Open with" fallback

**Context.** Opening a document from a result meant selecting the row and
using the bottom action bar; and on a machine with no program registered for
the type, the attempt reported a bare failure.

**Decision.** Paint two icon buttons per row (folder, then file), and when
Windows reports `ERROR_NO_ASSOCIATION` / `ERROR_GEN_FAILURE`, re-open through
the shell's `openas` verb — the standard "Open with" chooser.

**Consequences.** One more column width (96 px) and a delegate that has to
hit-test two rectangles. Users on machines without Word or a PDF reader get a
choice instead of a dead end.

### Repository hygiene for publication

**Context.** The project was not under version control; the working tree also
holds a 137 MB build output, a virtual environment and Windows `desktop.ini`
files.

**Decision.** Add a `.gitignore` covering build output, the virtual
environment, caches, generated fixtures, logs, local databases and OS files;
apply `ruff`'s safe automatic fixes; annotate the four security-rule false
positives in place; add per-file lint ignores for the pytest fixture-import
idiom and for scripts whose purpose is to launch a subprocess.

**Consequences.** The repository holds sources, tests, documentation and the
generated manual assets (about 4 MB) and nothing that can be rebuilt from
them. 57 advisory lint findings remain and are listed in
`HANDOFF.md` §5 rather than being silenced.

**Not decided.** No `LICENSE` file has been added: none was specified, and
choosing one is the owner's call — particularly while the PyMuPDF question in
ADR 0007 is open.
