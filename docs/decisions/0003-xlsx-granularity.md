# ADR 0003 — XLSX granularity and formula handling

**Status:** Accepted · **Date:** 2026-09-11

## Granularity

One content unit per non-empty cell of each **visible** worksheet.

Row-level units were considered. They produce a smaller index, but a match can
then only be reported as "row 12", which is far less useful than
`Sheet: งบประมาณ 2568, Cell: F12` when someone is hunting for a number in a
large workbook.

Row *context* is still shown in the snippet, but it is reconstructed at search
time from the neighbouring cells of the same row. Storing it would duplicate
every value in the workbook.

Hidden **worksheets** are skipped: they are usually working scratch space, and
someone searching their documents does not expect hits from a sheet they cannot
see. Hidden **rows and columns** are indexed, because they hold real data that
merely happens to be collapsed.

## Formulas are not recalculated

`openpyxl.load_workbook(..., data_only=True)` returns the **cached result**
Excel stored when the file was last saved. Formulas are never evaluated.

This is a security boundary as much as a scope decision: evaluating a
spreadsheet formula means implementing, or delegating to, an expression engine
that runs data taken from an untrusted file.

The consequence is stated plainly in the About dialog and the Settings screen:
a workbook written by a tool that did not cache results has empty formula
cells, and those cells are not searchable. A fixture (`formula.xlsx`) and a
test pin this so it cannot drift into "we sometimes index formulas".

## Other limits

* `read_only=True` streams worksheets instead of loading the whole workbook.
* `keep_links=False` — external workbook links are never resolved.
* Charts, images and drawing text are out of scope for version 1.
* `MAX_XLSX_CELLS = 500,000` and `MAX_CELL_TEXT_LENGTH = 100,000` bound a
  hostile or pathological workbook.
* `.xlsm` has no parser at all: macro-enabled formats are refused by extension
  before any file is opened.

## Value rendering

Cell values are rendered the way a user would search for them: integers without
a trailing `.0`, dates as `YYYY-MM-DD`, booleans as Excel's own `TRUE`/`FALSE`,
and NaN/infinity as nothing. Without this, `45000` stored as a float would be
indexed as `45000.0` and a search for `45000` would still match (substring) but
a search for the exact displayed value would look wrong in the snippet.
