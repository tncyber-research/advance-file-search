# ADR 0010 — Compact Open button and a bundled illustrated user manual

**Status:** Accepted · **Date:** 2026-09-11
**Builds on** [ADR 0009](0009-ui-revision.md)

## What changed

1. The **Open** column's button shrank from a full-width labelled button to a
   fixed 30 × 24 px folder icon.
2. The toolbar's **About** button became **คู่มือการใช้งาน / User Manual**,
   which opens a bundled HTML manual. About moved into the index menu.
3. A complete step-by-step manual lives in `Manual\`, ships with the build, and
   is generated from the real application.

## 1. Why the button shrank

The first version sized itself from the cell: `_button_rect()` returned
`rect.adjusted(6, 3, -6, -3)`, so the button grew with the column and, at a
104 px column, dominated every row. A button that large reads as the most
important control in the table, which it is not — it is a shortcut.

It is now a fixed-size rect centred in the cell, so the column can be resized
without the button changing shape, and the column default dropped to 58 px.
`sizeHint` returns the button plus a small margin, which gives the column a
sensible minimum.

The glyph is painted, not loaded: `draw_folder_glyph()` strokes a folder
outline with the theme's accent colour. That keeps it crisp at any DPI, needs
no asset, and follows the theme automatically. The trade-off is that the
button no longer carries a text label, so the cell supplies a `ToolTipRole`
string — an icon-only control without a tooltip is a guess.

## 2. Why About moved rather than disappeared

The About dialog is not decoration. handoff §21 requires the privacy statement,
the stated limitations and the third-party licence notices (including the
PyMuPDF AGPL notice) to be reachable from the UI. Replacing About with the
manual would have removed the only route to them.

The index menu is the right home: it is the menu that already holds the
"what is this program doing to my machine" actions — rebuild, delete, open the
data folder. About sits at the bottom of that list.

## 3. The manual is a local HTML file, not a dialog or a web page

A dialog would have meant re-implementing layout, images and navigation in Qt
for a document the user reads once. A hosted page is out of the question: the
application makes no network connection of any kind.

So the manual is a single `Manual\index.html` opened with the shell, in
whatever browser the user already has. This has one real consequence worth
stating: the file must reference **nothing** remote, or opening it would make
the browser — not the application, but still on the user's behalf — talk to a
network. `tests/test_manual.py` enforces that: no absolute or
protocol-relative `src`/`href`, no `url()`, `@import` or `@font-face` pointing
outward, no `<script>`, no inline event handler. All CSS is inline in the file
and all images sit beside it.

Fonts follow the same rule. The requirement was Sarabun at 14–16 px "if
Sarabun is available, otherwise another font". A web font download is not
available to us, so the stack is
`Sarabun, 'Leelawadee UI', 'Noto Sans Thai', Tahoma, 'Segoe UI', system-ui,
sans-serif` — Sarabun is used when the user has it installed, and the fallback
is automatic and local. Body text is 16 px.

Figures are `<img src="images/....svg">` rather than
`<object type="image/svg+xml">`. `<object>` gives the SVG its own browsing
context; `<img>` does not, and the SVGs are static drawings that need nothing
more.

## 4. Screenshots are generated, not taken by hand

`scripts\make_manual_screenshots.py` starts the real `MainWindow` over a
synthetic corpus, drives it through each screen, and grabs 16 PNGs.
`scripts\make_manual_graphics.py` writes the 7 SVG infographics.

The callout badges ("หมายเลข 1", "หมายเลข 2", …) are the part that would rot
fastest. The first attempt hard-coded their pixel positions, and they were
wrong immediately, because the window opened at 1284 × 781 rather than the
requested 1360 × 800 — the screen was smaller. Positions are now derived from
the live widgets:

```python
top_left = widget.mapTo(container, widget.rect().topLeft())
```

so a badge points at the control it names regardless of window size, DPI or
layout changes, and re-running the script after a UI change produces correct
screenshots without anyone nudging coordinates.

The fixture corpus is generated at run time, as everywhere else in this
project. No real document appears in a manual screenshot.

## 5. Consequence for the build

`Manual\` joins `LICENSES\` and `assets\` in the PyInstaller spec, in
`scripts\postbuild.py`'s surface list, and in `scripts\verify_build.py`'s
required files. A build that loses the manual now fails verification rather
than shipping a toolbar button that opens nothing. The button itself degrades
honestly: if the file is missing it says so instead of failing silently.
