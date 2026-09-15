# Roadmap

Status as of 2026-09-15. Nothing is ticked here that is not verifiable in the
repository: test results are in `docs/TEST_REPORT.md`, and build results come
from `scripts/verify_build.py` and `scripts/test_packaged_build.py`.

Priority: **P1** blocks a release · **P2** valuable next · **P3** nice to have.

## Completed

- [x] SQLite schema with external-content FTS5 and synchronising triggers
- [x] Thai substring search via the trigram tokenizer, measured against
      `unicode61` before the choice was made
- [x] Incremental indexing: add, modify, rename, delete, rebuild
- [x] Per-file transactions so one bad document cannot abort a run
- [x] Cancellation that leaves the index usable
- [x] PDF, DOCX, XLSX and text parsers, including CP874/TIS-620 and UTF-16
- [x] Query parser with phrases, `*` and `?`, and a linear (non-regex) matcher
- [x] Filters (type, date, size, subfolder), six sort orders, ranking
- [x] Match locations: page, paragraph, table cell, sheet/cell, line
- [x] Match preview with highlighting drawn as plain text
- [x] Thai and English interface with key-parity enforced by a test
- [x] Search-driven indexing (no "update index" button to remember)
- [x] Per-row Open-folder and Open-file buttons, with an "Open with" fallback
- [x] Reveal-in-Explorer through the shell API, correct for paths with spaces
- [x] Offline guarantee enforced by tests and by stripping binaries from the
      distribution
- [x] Log privacy: no document text, no search terms
- [x] PyInstaller onedir packaging, post-build stripping, build verification
- [x] Packaged acceptance test run with the system Python (41 checks)
- [x] Illustrated Thai user manual and project report, generated from the
      running application
- [x] Ten architecture decision records
- [x] Repository documentation and `.gitignore` for publication

## In progress

- [ ] **P1** Publish the repository and keep documentation in step with the
      code from here on

## Planned

- [ ] **P1** Decide the PyMuPDF licence question (AGPL vs commercial vs
      replacing the library), then add the matching `LICENSE` file —
      `docs/decisions/0007-pdf-library-licensing.md`
- [ ] **P1** Network-monitor observation run over a full session
      (`docs/SECURITY.md` §11)
- [ ] **P1** Clean-machine test on Windows without Python or build tools
      (`docs/BUILD.md`)
- [ ] **P2** CI workflow running `ruff` and the non-GUI tests on Windows
- [ ] **P2** Clear the 57 remaining lint findings (`docs/HANDOFF.md` §5)
- [ ] **P2** Configure a type checker and get it to a clean baseline
- [ ] **P3** Schema-migration path for index versions beyond v1

## Backlog

Not scheduled. Each would need its own decision record, and several conflict
with the constraints that define the product.

- [ ] **P2** Search history and saved searches — would need storage that today
      deliberately does not exist, since search terms are never persisted
- [ ] **P2** Index several root folders at once and search across them
- [ ] **P3** Export results to CSV or Excel
- [ ] **P3** Legacy `.doc` and `.xls` support
- [ ] **P3** Local OCR for scanned PDFs — a large dependency, and it must stay
      entirely offline
- [ ] **P3** Linux and macOS support: the core is portable, `winplat/` is not
- [ ] **P3** A scheduled background refresh of the index
