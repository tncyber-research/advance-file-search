Advance File Search 1.0.0
=========================

Search inside your own documents, on your own computer, with no Internet
connection.

Advance File Search builds a private index of the file names and text content
of the documents in a folder you choose, then lets you search that index and
jump straight to the file.


PRIVACY
-------
Advance File Search processes documents and search queries entirely on this
computer. It does not upload files, use cloud services, send usage data, or
require an Internet connection.

Your documents, the text extracted from them, the search index, your search
queries and the results all stay in:

    %LOCALAPPDATA%\Advance File Search\

Nothing is sent anywhere. See LICENSES\INDEX.txt for the components used.


GETTING STARTED
---------------
1. Double-click AdvanceFileSearch.exe
2. Click "Select Folder..." and choose a local folder or drive
3. Type what you are looking for and press Search

That is all. There is no separate "build the index" step: the first search
builds the index for that folder, and later searches check for changed files
and update it in the background while you read the results.

The first search on a large folder takes a while, because every document has
to be read once. After that it is fast.

Double-click a result to open the file. Each row also has an "Open folder"
button that shows the file in File Explorer.

The panel on the right shows the matching text with your search words
highlighted, plus where in the document it was found - the page, the paragraph,
the worksheet and cell, or the line number.


WHAT IT SEARCHES
----------------
    .pdf     PDF files that contain a text layer
    .docx    Word documents
    .xlsx    Excel workbooks
    .txt     Plain text

Optionally (enable in Settings): .md, .csv, .log

Both Thai and English content are supported, including Thai file names and
folder names.


SEARCH TIPS
-----------
    budget              find this text anywhere
    "annual budget"     find this exact phrase
    งบ*                 * matches any number of characters
    report_256?         ? matches exactly one character

Use the "Advanced filters" panel for:
  - Match case, Exact phrase, Whole word
  - File type, date modified, file size
  - Restricting the search to one subfolder

"Search in:" chooses whether to look at file names, contents, or both.


WHAT IT DOES NOT DO
-------------------
  - No OCR. Scanned or image-only PDFs contain no text to search, and the
    program will tell you so rather than pretending otherwise.
  - Legacy .doc and .xls files are not supported.
  - Word page numbers cannot be determined without rendering the document, so
    matches in Word files report the paragraph, or the table, row and column.
  - Excel formulas are not recalculated. The value stored in the file is what
    gets indexed. A workbook saved by a tool that did not store results will
    have empty formula cells.
  - Network drives, NAS, UNC paths (\\server\share) and cloud storage are not
    supported in version 1. Local drives and folders only.
  - No AI, no cloud, no semantic search, no question answering.


INDEX MAINTENANCE
-----------------
Normally you do not need this: searching keeps the index up to date.

For the times you do, the index menu (top right) has:

  Update Index    re-reads only the files that changed since last time
  Rebuild Index   discards the index and reads everything again
  Delete Index    removes the index for the selected folder
  Open Application Data Folder

F5 also forces an immediate update.

Updating is fast: unchanged files are skipped without being opened.

Deleting the program folder does not delete your index. To remove everything,
also delete %LOCALAPPDATA%\Advance File Search\


REQUIREMENTS
------------
  Windows 10 or 11, 64-bit
  8 GB RAM
  A few GB of free disk space for the index
  Python is NOT required


TROUBLESHOOTING
---------------
"Advance File Search is already running"
    Only one copy can run at a time, because two copies would write to the
    same index. Check the taskbar.

A file shows in results but will not open
    It was moved or deleted after it was indexed. Update the index.

A PDF is not found even though you can see the text in it
    It is probably a scan. This program does not do OCR.

Indexing skipped files
    Open the problem list at the end of the indexing run. Common reasons are
    password-protected files, files larger than the size limit, and files
    another program had open.

Logs are at %LOCALAPPDATA%\Advance File Search\logs\ and never contain your
document text or your search queries.
