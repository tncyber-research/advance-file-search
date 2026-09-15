\# Advance File Search — Development Handoff



\## 1. Project overview



\*\*Project name:\*\* Advance File Search  

\*\*Version:\*\* 1.0 / MVP  

\*\*Application type:\*\* Windows desktop application  

\*\*Primary language:\*\* Python  

\*\*Target users:\*\* One local user per installation  

\*\*Target platform:\*\* Windows 10/11 64-bit  

\*\*Distribution:\*\* PyInstaller `onedir` package with an `.exe` launcher  

\*\*Network requirement:\*\* None  

\*\*Security mode:\*\* 100% offline, local processing only



Advance File Search is a local desktop application for indexing and searching file names and textual content inside documents stored on the user's computer.



The application must allow the user to select a local folder or drive, create or update a search index, search the indexed content, inspect matching snippets and source locations, and open the original file or its containing folder.



The MVP supports:



\- PDF containing an existing text layer

\- DOCX

\- XLSX

\- TXT



The MVP explicitly excludes:



\- OCR

\- Scanned/image-only PDF text recognition

\- Legacy DOC

\- Legacy XLS

\- NAS

\- UNC paths

\- Network shares

\- Cloud storage integration

\- Local or cloud LLMs

\- Semantic/vector search

\- Question answering

\- Browser-based services

\- Multi-user access



\---



\# 2. Non-negotiable security and privacy requirements



These requirements have the highest priority. Do not weaken, reinterpret, or bypass them without explicit approval.



\## 2.1 Offline-only operation



The application must work 100% offline after installation.



It must not:



\- Call any cloud API

\- Call any AI API

\- Connect to analytics services

\- Send telemetry

\- Send crash reports

\- Check for updates automatically

\- Download models, packages, metadata, icons, fonts, certificates, or configuration

\- Upload documents, extracted text, search queries, file metadata, logs, or errors

\- Open outbound sockets

\- Run a local web server

\- Embed online content

\- Use a WebView that might load remote resources

\- Use third-party libraries that silently transmit usage data

\- Resolve remote URLs

\- Depend on CDN-hosted assets



All UI assets, fonts, icons, libraries, and runtime files must be bundled locally.



\## 2.2 No network paths



Version 1 must accept only local Windows file-system paths.



The application must reject or not offer indexing for:



\- UNC paths, such as `\\\\server\\share`

\- Mapped network drives when they can be identified as remote drives

\- HTTP/HTTPS paths

\- FTP paths

\- WebDAV paths

\- Cloud-provider URLs

\- Windows network namespace paths



If a selected drive is detected as a remote drive, show a clear message:



> Advance File Search version 1 supports local drives and folders only.



Do not silently proceed with remote paths.



\## 2.3 Local-only data processing



The following data must stay on the user's computer:



\- Original documents

\- Extracted document text

\- Search index

\- Search queries

\- Search results

\- File metadata

\- Error logs

\- Settings

\- Recent folders

\- Temporary files



No document content may be copied outside local application-controlled storage, except when the user explicitly opens or copies the original file using Windows.



\## 2.4 Local storage locations



Default writable application data directory:



```text

%LOCALAPPDATA%\\Advance File Search\\

```



Recommended structure:



```text

%LOCALAPPDATA%\\Advance File Search\\

├── index\\

│   └── search\_index.sqlite3

├── logs\\

│   └── application.log

├── settings\\

│   └── settings.json

├── temp\\

└── backups\\

```



Do not write mutable data beside the executable by default because the application may be installed under a protected directory.



Optional portable mode may be considered after MVP, but it is not required for version 1.



\## 2.5 Log minimization



Logs must not contain:



\- Extracted document content

\- Search queries by default

\- Matching snippets

\- Spreadsheet cell values

\- Full document dumps

\- Authentication secrets

\- Environment-variable dumps

\- Stack traces containing document content



Logs may contain only operational information such as:



\- Timestamp

\- Application version

\- Operation type

\- File path that failed, when needed for troubleshooting

\- Sanitized exception type and message

\- Indexing statistics

\- Database maintenance events



Provide a setting to disable file-path logging if practical.



Use log rotation and prevent unlimited log growth.



Suggested defaults:



\- Maximum log file size: 5 MB

\- Retained log files: 3

\- Log level: INFO

\- Debug logging disabled in release builds



\## 2.6 Temporary-file safety



Avoid writing extracted document text into temporary plaintext files.



Prefer in-memory processing followed by direct insertion into SQLite.



If a temporary file is unavoidable:



\- Store it only under the application temp directory

\- Use unpredictable file names

\- Restrict permissions where practical

\- Delete it immediately after use

\- Attempt cleanup after crashes and on the next launch

\- Never place temporary content in a shared directory



\## 2.7 Dependency and build security



\- Pin all direct dependencies to reviewed versions.

\- Maintain a lock file or fully pinned requirements file.

\- Do not download dependencies at application runtime.

\- Do not execute macros, embedded scripts, or external document links.

\- Do not invoke Microsoft Office to process documents.

\- Do not use LibreOffice headless conversion in MVP.

\- Treat every indexed document as untrusted input.

\- Catch parser errors and continue safely.

\- Do not use Python `eval`, `exec`, unsafe deserialization, or shell command construction from user input.

\- Use parameterized SQL exclusively.

\- Do not load arbitrary plugins from indexed folders.

\- Do not execute files while indexing.

\- Do not follow Windows shortcuts as index targets.

\- Do not process executable files.

\- Do not use document-embedded URLs.



\## 2.8 Security acceptance test



Before release, verify the application while outbound network access is blocked.



Minimum test:



1\. Disconnect or block Internet access.

2\. Launch the application.

3\. Select a local folder.

4\. Build an index.

5\. Search Thai and English text.

6\. Open result locations.

7\. Restart the application.

8\. Update the index.

9\. Confirm all core functions still work.

10\. Monitor the process and verify that it makes no outbound network connection attempts.



Any unexpected network attempt is a release-blocking defect.



\---



\# 3. Product goals



\## 3.1 Primary goals



1\. Search file names and document contents quickly.

2\. Work completely offline.

3\. Preserve user privacy.

4\. Provide clear source locations for every content match.

5\. Support Thai and English document content.

6\. Handle approximately 2,000–3,000 files reliably.

7\. Update an existing index without unnecessarily reprocessing unchanged files.

8\. Keep the UI responsive during indexing and searching.

9\. Make it easy to open the original file or reveal it in File Explorer.

10\. Provide a clean, modern, light-themed Windows desktop interface.



\## 3.2 Non-goals



Version 1 is not intended to:



\- Answer natural-language questions

\- Summarize documents

\- Calculate totals across documents

\- Perform semantic search

\- Search image content

\- OCR scanned PDFs

\- Search cloud storage

\- Search network shares

\- Synchronize indexes between computers

\- Support concurrent users

\- Replace document access controls

\- Modify document contents

\- Render full documents inside the application

\- Guarantee exact Word pagination



\---



\# 4. Supported environment



\## 4.1 Operating system



Required:



\- Windows 10 64-bit

\- Windows 11 64-bit



Not required for MVP:



\- macOS

\- Linux desktop

\- Windows on ARM

\- Windows 7/8

\- Windows Server certification



\## 4.2 Suggested hardware



Minimum:



\- 64-bit dual-core or quad-core CPU

\- 8 GB RAM

\- SSD storage

\- At least 3–5 GB free space in addition to original documents

\- No GPU required



Recommended:



\- 4 or more CPU cores

\- 8–16 GB RAM

\- SSD

\- 5–20 GB free space

\- No GPU required



The application must avoid loading complete large document collections into memory.



\## 4.3 Target workload



Initial MVP target:



\- 2,000–3,000 supported files

\- Local SSD or local HDD

\- Mixed Thai and English content

\- Documents ranging from small files to moderately large office files

\- One user and one running application instance



The design should remain reasonable for higher file counts, but optimization beyond this target is not a release requirement.



\---



\# 5. Proposed technology stack



\## 5.1 Application and UI



\- Python 3.12 or another explicitly approved supported version

\- PySide6 for the desktop UI

\- Qt model/view architecture for search result presentation

\- `QThread`, `QThreadPool`, or `QRunnable` for background work



Do not perform long-running indexing on the UI thread.



\## 5.2 Search index



Use SQLite with FTS5.



Reasons:



\- Fully local

\- No server process

\- Suitable for single-user use

\- Easy to package

\- Supports efficient full-text search

\- Supports transactional updates

\- Avoids OpenSearch and Java runtime overhead



Verify that the SQLite runtime bundled with the application has FTS5 enabled.



\## 5.3 File parsers



Recommended libraries:



\- PDF: PyMuPDF

\- DOCX: python-docx

\- XLSX: openpyxl

\- TXT: Python standard library with safe encoding detection strategy



Do not enable OCR.



\## 5.4 Packaging



Use PyInstaller in `onedir` mode.



Expected distribution:



```text

Advance File Search\\

├── AdvanceFileSearch.exe

├── \_internal\\

├── assets\\

├── LICENSES\\

└── README.txt

```



Requirements:



\- User launches the program by double-clicking `AdvanceFileSearch.exe`

\- No `.bat` or `.cmd` launcher

\- Python does not need to be installed

\- Build as a windowed application without a console in the release configuration

\- Keep a separate console-enabled debug build if helpful

\- Include all local assets

\- Include third-party license notices



Do not use `onefile` mode for MVP.



\---



\# 6. Functional requirements



\## 6.1 Folder or drive selection



The user must select a local folder or local drive before indexing or searching.



Required behavior:



\- Provide a folder selection dialog.

\- Allow selecting a root such as `D:\\`.

\- Include subfolders recursively.

\- Display the currently selected search root clearly.

\- Save previously indexed roots in local settings.

\- Provide a recent-root selector if practical.

\- Validate that the root still exists before searching.

\- Disable Search when no valid indexed root is selected.

\- Disable or clearly label unavailable roots.

\- Reject remote/network paths.



The application may support multiple separately indexed roots, but search must be scoped to the root selected by the user.



\### Root identity



Store each indexed root as a separate logical source with a stable `root\_id`.



Normalize paths carefully:



\- Resolve redundant separators.

\- Handle case-insensitive Windows paths.

\- Preserve a display path.

\- Store a normalized comparison path.

\- Avoid following paths outside the selected root through links or reparse points.



\### Symbolic links and reparse points



For MVP:



\- Do not follow directory symbolic links.

\- Do not follow junctions.

\- Do not follow mount-point reparse paths.

\- Skip them safely and report a non-fatal warning count.



This prevents recursion loops and unintended indexing outside the selected root.



\---



\## 6.2 Index creation



Provide a button such as:



> Create / Update Index



For a root with no existing index:



1\. Scan supported files recursively.

2\. Read metadata.

3\. Extract searchable content.

4\. Record source locations.

5\. Insert searchable units and metadata into SQLite.

6\. Commit in manageable batches.

7\. Report progress and errors.

8\. Mark the index run as completed only when finalization succeeds.



The UI must show:



\- Current phase

\- Current file name or a privacy-safer relative path

\- Files discovered

\- Files processed

\- Files indexed successfully

\- Files skipped

\- Files failed

\- Elapsed time

\- Progress bar, determinate when total is known

\- Cancel button



The UI must remain responsive.



\---



\## 6.3 Incremental index update



If an index already exists, update it rather than rebuilding everything.



Determine whether a file changed using at least:



\- Normalized path

\- File size

\- Last modified timestamp



Optional stronger detection:



\- Fast content hash only when necessary

\- Full SHA-256 for ambiguity or configurable verification



Required update logic:



\- New file: extract and insert

\- Changed file: remove old searchable units, re-extract, and replace atomically

\- Deleted file: remove metadata and searchable units

\- Moved/renamed file: may be treated as delete plus add in MVP

\- Unchanged file: skip parsing

\- Unsupported file: ignore

\- Temporary Office file such as `\~$name.docx`: skip

\- Hidden/system files: make behavior configurable; default to skip system files and include normal hidden documents only if explicitly enabled



Do not leave a partially updated file entry if parsing fails. Keep the previous valid index entry until replacement succeeds, or clearly mark the file as stale. Prefer atomic per-file replacement.



\### Cancellation behavior



When the user cancels:



\- Stop safely between files or safe processing checkpoints.

\- Do not corrupt the index.

\- Commit completed file transactions.

\- Roll back the currently incomplete file transaction.

\- Mark the indexing run as cancelled.

\- Keep previously valid index data searchable.



\---



\## 6.4 Supported file types



\### Required



\- `.pdf`

\- `.docx`

\- `.xlsx`

\- `.txt`



Extension matching must be case-insensitive.



\### Explicitly unsupported in version 1



\- `.doc`

\- `.xls`

\- PDF requiring OCR

\- Image-only PDF content

\- Password-protected documents

\- Encrypted documents

\- NAS and UNC paths



\### Optional low-risk additions



These may be added only after required formats are stable:



\- `.md`

\- `.csv`

\- `.log`

\- `.rtf` only if a safe and reliable parser is selected

\- `.pptx` only as a later scoped feature



Do not add formats merely because a generic parser claims broad support. Each format requires tests, location semantics, and failure handling.



\---



\# 7. Extraction requirements by format



\## 7.1 PDF



Use PyMuPDF.



Extract text per page.



Store:



\- File ID

\- Page number, 1-based

\- Extracted text

\- Optional page label if available

\- Sequence order

\- Extraction status



Search-result location format:



```text

Page 12

```



Thai UI:



```text

หน้า 12

```



Rules:



\- Do not OCR.

\- If no extractable text is found, mark the file as `no\_text`.

\- Show a user-facing status such as:



&#x20; > No searchable text was found. The PDF may be scanned or image-only.



\- Do not treat an empty-text PDF as an application error.

\- Handle encrypted or malformed PDFs safely.

\- Do not execute embedded actions, JavaScript, links, attachments, or multimedia.

\- Do not extract embedded files in MVP.



\## 7.2 DOCX



Use python-docx.



Extract:



\- Paragraph text

\- Table cell text

\- Optional header/footer text only if implementation is stable and clearly labeled

\- Preserve document order as reasonably as possible



Location types:



\- Paragraph number, 1-based

\- Table number, row, and column



Examples:



```text

Paragraph 24

Table 2, row 5, column 3

```



Thai UI:



```text

ย่อหน้า 24

ตาราง 2 แถว 5 คอลัมน์ 3

```



Important limitation:



DOCX page numbers are not reliable without rendering through a word processor. Do not claim to show exact Word page numbers.



Do not:



\- Execute macros

\- Follow hyperlinks

\- Load remote templates

\- Open external linked objects

\- Process embedded executable content



`.docm` is out of scope for MVP.



\## 7.3 XLSX



Use openpyxl in read-only mode where appropriate.



Extract cell values from visible worksheets.



Store:



\- Workbook file ID

\- Worksheet name

\- Cell coordinate

\- Displayable value

\- Optional row context

\- Cell data type

\- Sequence order



Location example:



```text

Sheet: Budget 2568, Cell: F12

```



Thai UI:



```text

ชีต: งบประมาณ 2568, เซลล์: F12

```



Rules:



\- Use `data\_only=True` for stored formula results in the search index.

\- Do not calculate formulas.

\- Clearly document that formulas are not recalculated.

\- If practical, optionally store formula text separately without evaluating it.

\- Do not load external workbook links.

\- Do not execute macros.

\- Ignore charts, images, and drawing text in MVP.

\- Skip empty cells.

\- Apply sensible maximum text length per cell.

\- Handle large worksheets without loading the entire workbook into memory when possible.

\- Sanitize worksheet names only for display safety; preserve their actual Unicode names in metadata.



`.xlsm` is out of scope unless explicitly approved later.



\## 7.4 TXT



Read text using a controlled encoding strategy.



Recommended order:



1\. UTF-8 with BOM

2\. UTF-8

3\. UTF-16 when BOM indicates it

4\. Windows-874 or TIS-620 as explicit Thai fallbacks

5\. Conservative fallback with replacement only after recording an encoding warning



Do not depend on an online encoding service.



Extract and store text by line or manageable blocks.



Location example:



```text

Line 135

```



Thai UI:



```text

บรรทัด 135

```



Preserve original line numbers.



Set a reasonable maximum size for TXT files or stream large files line by line.



\---



\# 8. Search behavior



\## 8.1 Search modes



Required:



1\. Search file names and content

2\. Search file names only

3\. Search content only



Optional:



\- Exact phrase

\- Match case

\- Whole word

\- Advanced pattern mode



The default search should be simple and understandable.



\## 8.2 Thai and English support



The search must support Unicode Thai and English.



Test at minimum:



\- Thai words

\- Thai phrases with spaces

\- English words

\- Mixed Thai and English

\- Arabic numerals

\- Thai numerals if present

\- File names containing Thai characters

\- Paths containing Thai characters



SQLite FTS5 tokenization behavior for Thai must be tested carefully. Thai text does not consistently use spaces between words.



For MVP, exact substring fallback may be required to make Thai search practical.



Recommended hybrid local strategy:



\- Use FTS5 for fast candidate retrieval where possible.

\- Apply local verification against extracted text for:

&#x20; - Case-sensitive matching

&#x20; - Exact substring matching

&#x20; - `?` wildcard

&#x20; - More complex `\*` patterns

&#x20; - Whole-word behavior

\- Ensure fallback work is bounded and does not scan all raw files on every search.



Do not promise linguistic Thai word segmentation unless a fully local library is deliberately included and tested.



\## 8.3 Query options



Required options:



\- Match case

\- Exact phrase

\- File names/content/both

\- File type filter

\- Date modified range

\- Size range

\- Scope to selected indexed root

\- Scope to a subfolder under that root



Desired wildcard support:



\- `\*` matches zero or more characters

\- `?` matches exactly one character



Examples:



```text

งบ\*

รายงาน\_256?

"งบประมาณครุภัณฑ์"

```



The UI must explain wildcard behavior.



\### Security



Never concatenate raw query input into SQL.



Use:



\- Parameterized SQL

\- Strictly controlled FTS query construction

\- Pattern escaping

\- Query-length limit

\- Wildcard-complexity limit

\- Execution timeout or cancellation strategy where practical



Reject pathological patterns likely to cause excessive resource use.



\## 8.4 Search result ranking



Suggested ranking order:



1\. Exact file-name match

2\. File-name prefix match

3\. Exact content phrase

4\. Content term match

5\. Recently modified file as a mild tie-breaker



Allow sorting by:



\- Relevance

\- File name

\- File type

\- File size

\- Date modified

\- Full path



\## 8.5 Search-result grouping



Recommended default:



\- One top-level result per file

\- Show the best matching snippet

\- Show a match count

\- Allow expanding to view more matching locations



Alternative acceptable MVP:



\- One result per matching location



If using location-level rows, avoid presenting duplicate file metadata confusingly.



Set a default result limit, for example 200 rows, with pagination or “load more.”



\---



\# 9. Search-result data



Each result must show:



\- File name

\- Full path

\- Relative path under selected root

\- File type

\- File size

\- Date created, when available

\- Date modified

\- Match source:

&#x20; - File name

&#x20; - Content

&#x20; - Both

\- Matching snippet of approximately 1–2 lines

\- Highlighted query match

\- Source location

\- Match count where applicable

\- Index status or warning where relevant



Location labels:



\- PDF: page

\- DOCX: paragraph or table/cell

\- XLSX: worksheet and cell

\- TXT: line



\## 9.1 Snippet generation



Snippets must:



\- Include context before and after the match

\- Preserve Unicode safely

\- Avoid splitting surrogate pairs or corrupting Thai text

\- Normalize excessive whitespace for display

\- Highlight matches in the UI without injecting HTML from document content

\- Be generated from locally indexed text

\- Not be stored in logs



If rich text or HTML-like rendering is used, escape document content before adding highlight markup.



\## 9.2 Missing original file



If an indexed file no longer exists:



\- Show a clear missing-file state.

\- Disable Open File and Reveal in Explorer.

\- Offer to update the index.

\- Do not crash.



\---



\# 10. File and Explorer actions



Required actions:



\## 10.1 Open file



\- Open using the Windows default application.

\- Require an explicit user action, such as double-click or button press.

\- Never automatically open a search result.

\- Confirm the file still exists.

\- Use safe OS APIs.

\- Do not construct an unsafe shell command.



\## 10.2 Open containing folder



Open File Explorer and select the file.



Expected Windows behavior is equivalent to:



```text

explorer.exe /select,"C:\\path\\to\\file.pdf"

```



Implement safely using an argument list rather than an unescaped command string.



If selection is unavailable, open the containing folder.



\## 10.3 Copy path



Provide:



\- Copy full path

\- Optional copy containing-folder path



\## 10.4 Open source location



Optional for MVP:



\- PDF page-level opening depends on the installed PDF viewer and cannot be guaranteed.

\- DOCX paragraph navigation cannot be guaranteed.

\- XLSX cell navigation cannot be guaranteed.



Do not claim reliable direct navigation inside external applications unless verified.



The required behavior is to show the source location in Advance File Search and allow the original file to be opened.



\---



\# 11. UI/UX requirements



\## 11.1 General design



\- Modern Windows desktop appearance

\- Light theme

\- Low-saturation neutral palette

\- Clear typography

\- Good contrast

\- Support full-screen and resizable window

\- Responsive layout

\- No remote fonts

\- No remote icons

\- All assets bundled locally



Suggested visual tone:



\- White and light gray surfaces

\- Muted blue or teal primary accent

\- Subtle borders

\- Minimal shadows

\- Clear selected-row state

\- Avoid bright or excessive colors



\## 11.2 Main screen layout



Suggested structure:



```text

┌──────────────────────────────────────────────────────────────┐

│ Advance File Search                         \[Settings] \[Help] │

├──────────────────────────────────────────────────────────────┤

│ Search root: \[D:\\Documents                         ] \[Select] │

│ Index status: Ready | 2,845 files | Updated: ...  \[Update]   │

├──────────────────────────────────────────────────────────────┤

│ \[ Search query..................................... ] \[Search]│

│ \[Advanced filters ▼]                                        │

├──────────────────────────────────────────────────────────────┤

│ Results: 138                         Sort: \[Relevance ▼]      │

│ ┌──────────────────────────────────────────────────────────┐ │

│ │ Name | Location | Type | Size | Modified | Snippet       │ │

│ └──────────────────────────────────────────────────────────┘ │

├──────────────────────────────────────────────────────────────┤

│ \[Open File] \[Open Folder] \[Copy Path]                        │

└──────────────────────────────────────────────────────────────┘

```



\## 11.3 First-run state



When no index exists:



\- Explain the workflow.

\- Prompt the user to select a local folder or drive.

\- Disable Search.

\- Offer Create Index.

\- State clearly that processing occurs locally and offline.



Suggested copy:



> Select a local folder or drive to create a private search index. Files and search data remain on this computer.



Thai localization may be added if included in MVP:



> เลือกโฟลเดอร์หรือไดรฟ์ภายในเครื่องเพื่อสร้างดัชนีค้นหา ไฟล์และข้อมูลการค้นหาจะอยู่ภายในเครื่องนี้เท่านั้น



\## 11.4 Index progress dialog/panel



Show:



\- Progress bar

\- Current phase

\- Processed/total count

\- Success/skip/failure counts

\- Elapsed time

\- Cancel

\- Expandable error summary



Do not show extracted content in the progress UI.



\## 11.5 Accessibility



At minimum:



\- Keyboard navigation

\- Visible keyboard focus

\- Tooltips

\- Resizable text where Qt permits

\- Sufficient contrast

\- Do not rely only on color for status

\- Accessible names for important controls



\---



\# 12. Suggested architecture



Use clear separation of concerns.



```text

advance\_file\_search/

├── app.py

├── ui/

│   ├── main\_window.py

│   ├── index\_dialog.py

│   ├── settings\_dialog.py

│   ├── result\_model.py

│   ├── delegates.py

│   └── resources/

├── core/

│   ├── models.py

│   ├── paths.py

│   ├── security.py

│   ├── settings.py

│   └── constants.py

├── indexing/

│   ├── scanner.py

│   ├── coordinator.py

│   ├── worker.py

│   ├── fingerprint.py

│   └── parsers/

│       ├── base.py

│       ├── pdf\_parser.py

│       ├── docx\_parser.py

│       ├── xlsx\_parser.py

│       └── txt\_parser.py

├── search/

│   ├── query\_parser.py

│   ├── search\_service.py

│   ├── wildcard.py

│   ├── snippets.py

│   └── ranking.py

├── storage/

│   ├── database.py

│   ├── migrations.py

│   ├── repositories.py

│   └── schema.sql

├── platform/

│   ├── windows\_paths.py

│   └── windows\_shell.py

├── logging\_setup.py

├── tests/

├── build/

└── docs/

```



\## 12.1 Parser interface



Define a common parser interface.



Conceptual example:



```python

class DocumentParser(Protocol):

&#x20;   supported\_extensions: set\[str]



&#x20;   def extract(self, file\_path: Path) -> ParsedDocument:

&#x20;       ...

```



Suggested models:



```python

@dataclass

class ParsedDocument:

&#x20;   metadata: DocumentMetadata

&#x20;   units: list\[ContentUnit]

&#x20;   warnings: list\[str]



@dataclass

class ContentUnit:

&#x20;   sequence: int

&#x20;   location\_type: str

&#x20;   location\_label: str

&#x20;   location\_data: dict\[str, Any]

&#x20;   text: str

```



For very large files, support an iterator/generator instead of requiring all units in memory.



\---



\# 13. Suggested database design



Use migration-managed SQLite schema.



Enable:



```sql

PRAGMA foreign\_keys = ON;

PRAGMA journal\_mode = WAL;

```



Evaluate `synchronous=NORMAL` versus `FULL` based on performance and durability. Prefer safety for metadata updates.



\## 13.1 Tables



\### `roots`



```text

id

display\_path

normalized\_path

created\_at

last\_index\_started\_at

last\_index\_completed\_at

last\_index\_status

file\_count

schema\_version

```



\### `files`



```text

id

root\_id

display\_path

normalized\_path

relative\_path

file\_name

extension

mime\_category

size\_bytes

created\_time

modified\_time

fingerprint

content\_status

parser\_version

indexed\_at

last\_seen\_scan\_id

error\_code

error\_message\_sanitized

```



Unique constraint:



```text

(root\_id, normalized\_path)

```



\### `content\_units`



```text

id

file\_id

sequence

location\_type

location\_label

location\_json

text

```



\### FTS virtual table



Possible approach:



```sql

CREATE VIRTUAL TABLE content\_fts USING fts5(

&#x20;   file\_name,

&#x20;   relative\_path,

&#x20;   content,

&#x20;   content='...',

&#x20;   tokenize='unicode61'

);

```



The final FTS design may use an external-content table or a dedicated denormalized search-document table.



The implementation must support:



\- Linking matches back to a file

\- Linking matches to a content unit

\- Efficient deletion/replacement per file

\- Snippet generation

\- Thai Unicode content



\### `index\_runs`



```text

id

root\_id

started\_at

finished\_at

status

files\_discovered

files\_processed

files\_indexed

files\_skipped

files\_failed

files\_deleted

application\_version

```



\### `settings`



Prefer a local JSON settings file or Qt settings for non-sensitive UI preferences. Avoid storing document content in settings.



\## 13.2 Database migrations



\- Use explicit schema versions.

\- Back up the database before destructive migration.

\- Do not silently delete a user's index.

\- If the index is incompatible, offer a clear Rebuild Index action.

\- Handle interrupted migrations safely.



\---



\# 14. Index integrity and resilience



The application must tolerate:



\- Corrupt documents

\- Files disappearing during scanning

\- Permission errors

\- Files locked by another program

\- Very long paths

\- Thai file names

\- Large files

\- Unexpected parser exceptions

\- Insufficient disk space

\- Database locked errors

\- Application termination during indexing



Required behavior:



\- One bad file must not abort the entire run.

\- Errors should be summarized.

\- The index must remain searchable after a partial or cancelled update.

\- Use transactions.

\- Perform SQLite integrity checks after suspicious shutdowns if appropriate.

\- Provide:

&#x20; - Update Index

&#x20; - Rebuild Index

&#x20; - Delete Index

&#x20; - Open application data folder

\- Require confirmation before deleting or rebuilding an index.

\- Display estimated impact where practical.



\## 14.1 Single-instance behavior



For MVP, enforce one application instance per user or prevent concurrent writers.



If a second instance starts:



\- Focus the existing instance, or

\- Show a message that the application is already running.



Never allow two indexing processes to write to the same SQLite database simultaneously.



\---



\# 15. File-system scanning rules



Default included extensions:



```text

.pdf

.docx

.xlsx

.txt

```



Default skipped items:



\- Application data directory

\- Windows system directories when indexing a whole drive

\- Recycle Bin

\- System Volume Information

\- Temporary Office files beginning with `\~$`

\- Temporary files

\- Symlinks and junctions

\- The search-index database itself

\- Application installation directory if inside the selected root

\- Hidden system files

\- Files exceeding configurable safety limits



If the user selects an entire system drive, show a warning that scanning may take a long time and may encounter protected system folders.



Recommended exclusions for a whole-drive scan:



```text

$RECYCLE.BIN

System Volume Information

Windows

Program Files

Program Files (x86)

ProgramData

%LOCALAPPDATA%\\Advance File Search

```



Do not hardcode exclusions without allowing review. Present sensible defaults.



\---



\# 16. Limits and defensive controls



Set configurable or documented safety limits.



Suggested starting points:



\- Maximum query length: 500 characters

\- Maximum displayed results: 200 initially

\- Maximum snippets per file: 10

\- Maximum snippet length: 500 characters

\- Maximum logged error message length: 1,000 characters

\- Maximum individual cell text: 100,000 characters

\- Maximum extracted unit text length: define per format

\- Maximum file size: warn or skip above a configurable threshold, initially 500 MB

\- Search cancellation for expensive wildcard queries



These values should be constants or settings, not scattered magic numbers.



If a file is skipped due to a limit, show the reason.



\---



\# 17. Performance requirements



No strict benchmark is required before real sample documents are available, but aim for:



\- UI remains responsive throughout indexing.

\- Search returns common indexed queries within approximately one second on typical hardware.

\- Advanced wildcard or case-sensitive verification may take longer but must be cancellable or bounded.

\- Incremental update should skip unchanged files.

\- Memory use should remain stable for the target workload.

\- XLSX and TXT parsing should stream where practical.

\- Database writes should be batched safely.



Add performance instrumentation that records timings without recording document content.



\---



\# 18. Error handling



User-facing errors should be clear and non-technical.



Examples:



\### No text in PDF



> This PDF does not contain searchable text. It may be a scanned document.



\### Password-protected file



> This file is password-protected and was not indexed.



\### Access denied



> Advance File Search does not have permission to read this file.



\### File disappeared



> The file was moved or deleted before indexing completed.



\### Disk space



> There is not enough free disk space to update the index.



\### Invalid network path



> Version 1 supports local folders and drives only.



Detailed technical errors may be recorded in sanitized logs, but document content must not be logged.



\---



\# 19. Localization



The core application must fully support Unicode.



Preferred MVP language:



\- Thai UI as primary, if feasible

\- English fallback or optional UI language



At minimum, internal architecture must not prevent localization.



Do not hardcode user-facing strings throughout business logic. Centralize strings or use Qt translation infrastructure.



Date, time, and file sizes should use a consistent display format. Store internal timestamps in an unambiguous format.



Do not alter years found inside documents. Search document text exactly as extracted.



\---



\# 20. Testing strategy



\## 20.1 Unit tests



Required areas:



\- Path normalization

\- Local versus network-path detection

\- Extension filtering

\- File fingerprint comparison

\- TXT encoding handling

\- Query escaping

\- Wildcard conversion

\- Case-sensitive verification

\- Snippet extraction

\- Highlight range calculation

\- Database CRUD

\- Incremental-update decisions

\- Safe Explorer argument generation



\## 20.2 Parser tests



Create representative local fixtures:



\### PDF



\- English text

\- Thai text

\- Multiple pages

\- Empty/image-only PDF

\- Password-protected PDF

\- Corrupt PDF



\### DOCX



\- Thai and English paragraphs

\- Tables

\- Empty document

\- Corrupt document

\- Hyperlinks that must not be followed



\### XLSX



\- Multiple sheets

\- Thai worksheet names

\- Text and numbers

\- Formula with cached value

\- Empty workbook

\- Large sheet

\- External links that must not be followed

\- Corrupt workbook



\### TXT



\- UTF-8

\- UTF-8 BOM

\- UTF-16

\- Windows-874/TIS-620

\- Mixed Thai and English

\- Very long line

\- Large streamed file



Do not commit real confidential documents into the repository. Use synthetic test fixtures only.



\## 20.3 Integration tests



Test:



\- First index build

\- Incremental update

\- New file

\- Modified file

\- Deleted file

\- Renamed file

\- Cancelled indexing

\- Search after cancellation

\- Rebuild

\- Missing root

\- Missing result file

\- Database migration

\- App restart

\- Whole-drive selection warning



\## 20.4 Security/privacy tests



Verify:



\- Application works with network disabled.

\- No HTTP client is needed.

\- No outbound connection is attempted.

\- No document content is written to logs.

\- No query text is logged by default.

\- Temporary files are removed.

\- UNC paths are rejected.

\- Mapped network drives are rejected when detected.

\- SQL injection strings do not alter the database.

\- FTS metacharacters do not crash the application.

\- HTML-like document text is safely escaped in snippets.

\- Embedded document links are not followed.

\- Files are never executed during indexing.

\- Release build does not expose a debug console.

\- No bundled dependency performs telemetry.



\## 20.5 Packaging tests



Test on a clean Windows machine or VM without Python installed:



\- Start from `.exe`

\- Build index

\- Search Thai and English

\- Update index

\- Open file

\- Reveal file in Explorer

\- Restart

\- Uninstall/delete the program folder

\- Verify user index remains or is removed according to documented behavior

\- Confirm no runtime download occurs



\---



\# 21. Definition of done for version 1



Version 1 is complete when all the following are true:



1\. Runs on a clean Windows 10/11 64-bit machine without Python installed.

2\. Launches through `AdvanceFileSearch.exe`.

3\. Does not require `.bat`, `.cmd`, a browser, or a server.

4\. Works with network access disabled.

5\. Makes no expected outbound network connection.

6\. Accepts only local folders and drives.

7\. Indexes supported PDF, DOCX, XLSX, and TXT files.

8\. Correctly skips image-only PDFs without OCR.

9\. Creates and updates an SQLite/FTS5 index.

10\. Detects new, modified, and deleted files.

11\. Searches Thai and English file names and content.

12\. Supports core filters and documented wildcard behavior.

13\. Displays a matching snippet and source location.

14\. Shows file metadata.

15\. Opens the original file.

16\. Opens File Explorer and selects the file.

17\. Keeps the UI responsive during indexing.

18\. Supports cancellation without corrupting the index.

19\. Does not log document content or search queries by default.

20\. Handles corrupt and inaccessible files without crashing.

21\. Includes synthetic automated tests.

22\. Includes build documentation and dependency versions.

23\. Includes a privacy statement explaining local-only processing.

24\. Includes third-party license notices.

25\. Passes offline and network-monitoring acceptance tests.



\---



\# 22. Suggested implementation phases



\## Phase 0 — Repository and security baseline



\- Create project structure.

\- Set Python version.

\- Pin dependencies.

\- Set up linting, formatting, tests, and type checking.

\- Add a security/privacy document.

\- Add dependency-license tracking.

\- Add offline constraints to developer documentation.

\- Ensure no runtime network dependency.



Deliverable:



\- Empty application window

\- Test framework

\- Build configuration

\- Security baseline



\## Phase 1 — Storage and core models



\- SQLite connection management

\- Schema and migrations

\- Root records

\- File metadata records

\- Content units

\- FTS5 prototype

\- Transaction handling



Deliverable:



\- Database unit tests

\- Insert, update, delete, and basic search



\## Phase 2 — Parsers



Implement in this order:



1\. TXT

2\. PDF

3\. DOCX

4\. XLSX



Deliverable:



\- Synthetic parser fixtures

\- Location metadata

\- Safe failures

\- No temporary plaintext dumps



\## Phase 3 — Scanner and indexing



\- Folder selection

\- Recursive scanner

\- Exclusions

\- Fingerprinting

\- Initial index

\- Incremental update

\- Deleted-file cleanup

\- Cancellation

\- Progress reporting



Deliverable:



\- End-to-end indexing through a basic UI



\## Phase 4 — Search



\- Basic query

\- File name/content scope

\- Result ranking

\- Snippets

\- Thai and English tests

\- Exact phrase

\- Match case

\- Wildcards

\- Filters

\- Result limits



Deliverable:



\- Stable local search behavior with documented semantics



\## Phase 5 — Main UI



\- Modern light theme

\- Search root selection

\- Index state

\- Search bar

\- Advanced filters

\- Result model/table

\- Details panel

\- Progress view

\- Error summary

\- Full-screen/resizable support



Deliverable:



\- Feature-complete desktop workflow



\## Phase 6 — Windows integration



\- Open file

\- Reveal in Explorer

\- Copy path

\- Single-instance guard

\- Local drive validation

\- Long-path handling where possible



Deliverable:



\- Usable Windows-native interactions



\## Phase 7 — Packaging and hardening



\- PyInstaller `onedir`

\- Clean-machine test

\- Offline test

\- Network-monitoring test

\- Log/privacy review

\- Dependency review

\- Corrupt-input tests

\- Performance profiling

\- Documentation



Deliverable:



\- Release candidate directory containing `AdvanceFileSearch.exe`



\---



\# 23. Decisions that must be documented during implementation



Claude Code should record major decisions in `docs/decisions/` or an equivalent ADR format.



At minimum, document:



1\. SQLite FTS5 schema design

2\. Thai search strategy and limitations

3\. Wildcard semantics

4\. Incremental fingerprint strategy

5\. Database location and backup behavior

6\. Parser-specific source-location representation

7\. Network-path detection on Windows

8\. Symlink/junction handling

9\. File-size safety limits

10\. Release-build privacy verification

11\. PyInstaller packaging approach

12\. Whether and how index deletion securely removes local data



\---



\# 24. Open implementation questions



Resolve these with small prototypes before final UI polish:



1\. Does bundled SQLite reliably support FTS5?

2\. What FTS tokenizer behavior is acceptable for real Thai text?

3\. Is a substring verification layer needed for all Thai queries?

4\. Should search rows represent files or individual matches?

5\. What is the best XLSX indexing granularity: cell, row, or both?

6\. How should DOCX table order be represented relative to paragraphs?

7\. What maximum file size provides a reasonable safety default?

8\. How should mapped remote drives be detected reliably on Windows?

9\. How should root indexes be separated: one database or one database per root?

10\. What database-backup strategy is safest during schema migration?

11\. What PyInstaller hidden imports are required for all parsers?

12\. How should highlighted snippets be rendered without HTML injection risk?



Recommended starting decisions:



\- One SQLite database containing multiple roots

\- One content unit per PDF page

\- One unit per DOCX paragraph and table cell

\- One unit per non-empty XLSX cell, with row context generated for snippets

\- One unit per TXT line or small line block

\- File-grouped search results with expandable locations



These can be changed if prototypes show a better design.



\---



\# 25. Privacy statement for the application



Display a concise statement in About, first-run guidance, and documentation:



> Advance File Search processes documents and search queries entirely on this computer. It does not upload files, use cloud services, send telemetry, or require an Internet connection.



Thai version:



> Advance File Search ประมวลผลเอกสารและคำค้นหาภายในเครื่องนี้เท่านั้น โปรแกรมจะไม่อัปโหลดไฟล์ ไม่ใช้บริการคลาวด์ ไม่ส่งข้อมูลการใช้งาน และไม่จำเป็นต้องเชื่อมต่ออินเทอร์เน็ต



Do not make this statement unless the release build has passed the network/privacy acceptance tests.



\---



\# 26. Instructions for Claude Code



Implement this project incrementally.



Rules:



1\. Do not attempt the whole application in a single large change.

2\. Start with repository setup, architecture, tests, and security constraints.

3\. Present a short plan before each phase.

4\. Keep commits or change sets small and reviewable.

5\. Run tests after each meaningful change.

6\. Never add a network-enabled dependency without explicit approval.

7\. Never introduce telemetry, update checks, analytics, remote fonts, CDN assets, WebViews, or cloud APIs.

8\. Never log document content or search queries.

9\. Never execute or render untrusted document scripts.

10\. Use parameterized SQL.

11\. Treat all file paths and document contents as untrusted input.

12\. Keep the UI responsive by moving indexing work off the UI thread.

13\. Preserve the last valid index if an update is interrupted.

14\. Use synthetic test files only.

15\. Document known limitations honestly.

16\. Prefer maintainability and data safety over cleverness.

17\. Build a basic vertical slice before polishing:

&#x20;   - Select local folder

&#x20;   - Index TXT

&#x20;   - Search

&#x20;   - Show snippet and line

&#x20;   - Reveal file in Explorer

18\. Then add PDF, DOCX, and XLSX one format at a time.

19\. Validate offline operation continuously, not only at the end.

20\. Stop and request clarification if a proposed feature would require networking, cloud processing, OCR, legacy Office support, or execution of external applications during indexing.



\---



\# 27. Final MVP summary



Advance File Search version 1 is a single-user Windows desktop full-text search application.



It will:



\- Run locally and offline

\- Index local PDF, DOCX, XLSX, and TXT files

\- Support approximately 2,000–3,000 files

\- Search Thai and English content

\- Update indexes incrementally

\- Show matching snippets and source locations

\- Show file metadata

\- Open original files

\- Reveal files in Windows File Explorer

\- Provide practical advanced search and filters

\- Use a modern light-themed UI

\- Launch through a packaged `.exe`



It will not:



\- Use OCR

\- Support DOC/XLS

\- Search NAS or network shares

\- Use cloud services

\- Use AI or LLMs

\- Perform semantic search

\- Upload or transmit documents

\- Send telemetry

\- Require Internet access



\*\*The primary release requirement is that user documents, extracted text, metadata, and queries remain on the local computer at all times.\*\*

