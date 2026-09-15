# ADR 0009 — Result table, match preview and search-driven indexing

**Status:** Accepted · **Date:** 2026-09-11
**Supersedes parts of** handoff §11.2 (suggested layout) and §6.2 (index button)

## What changed

1. A proper multi-resolution application icon, shown in the title bar, the
   taskbar and Alt-Tab.
2. The **Location** column is gone from the result table; the source location
   now sits with the text it describes, in the match-preview panel.
3. A **match preview** in the details panel: a few lines of the document text
   around the hit, with the query highlighted, in a visually distinct well.
4. The details panel no longer repeats **relative path** and **file type**.
5. An **Open** column with a per-row button that reveals the file in Explorer.
6. A larger base font.
7. The **Create / Update Index** button is gone. Searching builds the index
   when there is none, and refreshes it in the background when there is.

## 1. Icon

Qt's ICO writer emits a single resolution, and Windows rescaling a 256 px icon
into a 16 px title bar produces mush. `scripts/make_icon.py` therefore renders
each size natively and writes the ICO container directly (header, directory
entries, PNG payloads).

The design simplifies as the canvas shrinks: below 24 px the text lines are
dropped and the sheet outline switches from pale grey to the accent colour with
a heavier stroke, because a light outline vanishes against a title bar. The
background is fully transparent so the icon sits cleanly on any surface.

The icon is *drawn in code*, not committed as opaque bytes — consistent with
the rule that nothing in this application is a downloaded or unreviewable
asset.

`QApplication.setWindowIcon` was never called before this change: the `.exe`
carried an icon resource (so Explorer showed one) but the running window did
not, which is why the title bar showed a generic placeholder.

## 2–3. Location column → match preview

The Location column was competing for horizontal space with the thing people
actually read — the matching text — and a value like
`Sheet: งบประมาณ 2568, Cell: F12` never fitted in a table cell anyway.

Moving it into the preview panel puts the location next to the text it
describes, and frees the table for a wider Match column.

The preview is a `QFrame` with a tinted background and an accent left edge, so
it reads as *content from the document* rather than as more metadata. It shows
three lines; the location sits on its own full-width line above the text
(sharing a row with the caption clipped it).

**Safety:** the text is inserted with `setPlainText` and highlighted through
`QTextCursor` + `QTextCharFormat`. No markup is ever parsed, so a document
containing `<script>` is displayed as those literal characters. A test asserts
exactly that, and that the highlighted runs are character formatting rather
than injected markup.

Selecting one of the expanded location rows previews *that* match rather than
the file's best one, and those child rows now name their own location in the
Name column.

A name-only match has no document text to show, so the panel says so instead
of leaving an empty box that looks broken.

## 4. Details panel

Relative path and file type were both already columns in the table. Removing
them leaves room for what is not in the table.

The full path is a middle-elided single line rather than a wrapped block. A
deep Windows path wrapped into a narrow side panel was being clipped — whole
components disappeared silently — because `QLabel` derives its
`minimumSizeHint` from the full text and demanded more width than the panel
had. `ElidedPathLabel` reports a small fixed hint instead, so the layout gives
it whatever room exists and the text is fitted to that.

Elision cuts at folder boundaries rather than mid-component: Qt's `ElideMiddle`
produced `C:\Users\PROXMO…lsx\budget.xlsx`, where `lsx` is noise.
`elide_path()` drops whole folders and keeps the drive and the file name:

```
C:\…\scratchpad\v2corpus\เอกสาร\xlsx\budget.xlsx
```

The complete path stays available as the tooltip, through Copy Path and through
the context menu.

## 5. Open column

A `QPushButton` per row would mean one widget per visible result. The button is
painted by `OpenFolderDelegate` and the click is handled in `editorEvent`,
which costs nothing per row and scrolls smoothly.

It is drawn only on file rows, and disabled when the file is missing, so the
control never offers something it cannot do. A double-click on the button is
swallowed so it does not also trigger the tree's "open the file" action.

## 6. Font size

The base size now starts from the platform's own UI font and adds a step, with
an 11 pt floor. Thai needs more vertical room than Latin — vowels and tone
marks stack above and below the base line — and the Windows default of 9 pt
made them cramped. Row height went up to match.

Because the font got bigger and the details panel got wider, the fixed columns
were squeezing the stretching Match column to a few characters. Column widths
were reduced and `_keep_snippet_readable` clamps a neighbour that would push
Match below a readable minimum.

## 7. Searching builds the index

The old flow had a discoverability problem: a first-time user selects a folder,
types a query, and gets nothing, because they have not pressed a separate
button first.

Now pressing **Search** (button or Enter):

* **no index yet** — builds it with the progress dialog, then runs the search
  automatically. This one is worth waiting for: there is nothing to search
  until it finishes.
* **index exists** — searches immediately against what is there, and refreshes
  the index in the background. If the refresh changes anything, the search is
  re-run so the list is not stale.

Searching the existing index *first* is the important part. A user who has just
typed a query wants results now, not after a scan of their documents folder.

### What is deliberately not done

**Debounced typing does not index.** Only an explicit Search does. Re-scanning
the folder on every keystroke would be unusable, and a test pins this.

**The background refresh is throttled** to once per 20 seconds per root.
Without it, pressing Search repeatedly would re-`stat` the whole tree each
time — cheap per file, but real work on a large one.

**The background refresh does not disable the UI.** Only a blocking build
does. The user can keep typing and searching against the index that exists.

Manual **Update Index**, **Rebuild Index** and **Delete Index** remain in the
index menu, and F5 forces a refresh past the throttle — the automatic path
covers the common case, not every case.
