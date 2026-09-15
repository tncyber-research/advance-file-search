# ADR 0007 — PyMuPDF and the AGPL obligation

**Status:** Accepted, with an open decision for the project owner
**Date:** 2026-09-11

## The issue

Handoff §5.3 recommends PyMuPDF for PDF extraction, and PyMuPDF is what this
build uses. PyMuPDF is **dual licensed: GNU Affero GPL v3, or a commercial
licence from Artifex**. Its bundled `COPYING` file says exactly that and
nothing more.

The AGPL is strongly copyleft. For a desktop application that is distributed to
other people, using an AGPL library means one of:

1. release the whole of Advance File Search under the AGPL, with source
   available to recipients; or
2. buy a commercial PyMuPDF licence from Artifex.

`pyproject.toml` currently declares the project licence as `Proprietary`, which
is **incompatible** with option 1. That is not a technical defect — the
application works correctly — but it is a distribution blocker that has to be
settled before the build leaves the organisation that made it.

This does not affect purely internal use: the AGPL's obligations are triggered
by conveying the software to others, not by running it yourself.

## Why the decision was not made unilaterally

The handoff names PyMuPDF explicitly, and PyMuPDF is genuinely the best tool
for the job here — it is fast, it handles malformed PDFs without crashing, it
reports encryption cleanly, and it reads a text layer without any OCR
machinery. Swapping it out on licensing grounds is a business decision, not an
engineering one, so the library stays and the obligation is documented instead.

## If a permissive licence is required

The PDF parser is deliberately the only module that touches PyMuPDF:

```
advance_file_search/indexing/parsers/pdf_parser.py
```

It implements one method, `_parse`, behind the same `DocumentParser` contract
every other format uses. Replacing it is a contained change:

| Candidate | Licence | Notes |
|---|---|---|
| `pypdf` | BSD-3-Clause | pure Python, no binary dependency; slower, and text extraction quality on complex layouts is lower |
| `pdfminer.six` | MIT | good extraction quality, noticeably slower, heavier dependency |

Either can report page-level text, which is all the location model needs
(`LOC_PAGE` with a 1-based page number). The parser tests in
`tests/test_parsers.py` are written against the `ParseResult` contract rather
than against PyMuPDF, so they would validate a replacement unchanged — including
the image-only, password-protected and corrupt-PDF cases.

The one behaviour that would need re-checking is encryption handling: PyMuPDF
distinguishes "encrypted but openable with an empty password" from "password
protected", and the replacement must map both onto the same
`ParseOutcome.PASSWORD_PROTECTED` result rather than raising.

## What was done

* The obligation is stated at the top of `LICENSES/INDEX.txt`, which ships next
  to the executable and is shown in the About dialog.
* `docs/SECURITY.md` repeats it in the dependency section.
* This ADR records the alternatives and the size of the change, so the choice
  can be made later without re-doing the analysis.
