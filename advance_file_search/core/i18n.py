"""Centralized user-facing strings for Thai and English.

Business logic never hard-codes user-visible text: it raises an error *code*
and the UI resolves it here.  Keeping every string in one table also makes the
privacy review tractable — there is exactly one place where document-derived
data could leak into a message, and none of these templates accept content.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from advance_file_search.core import constants as C

LANG_THAI: Final[str] = "th"
LANG_ENGLISH: Final[str] = "en"
AVAILABLE_LANGUAGES: Final[tuple[tuple[str, str], ...]] = (
    (LANG_THAI, "ไทย"),
    (LANG_ENGLISH, "English"),
)

_EN: Final[dict[str, str]] = {
    # --- window / chrome -------------------------------------------------
    "app.title": "Advance File Search",
    "app.version": "Version {version}",
    "menu.settings": "Settings",
    "menu.help": "Help",
    "menu.about": "About",
    "menu.manual": "User Manual",
    "menu.manual_tooltip": "Open the step-by-step user manual",
    "menu.language": "Language",
    # --- root selection --------------------------------------------------
    "root.label": "Search root:",
    "root.select": "Select Folder…",
    "root.placeholder": "No folder selected",
    "root.recent": "Recent roots",
    "root.dialog_title": "Select a local folder or drive to index",
    "root.forget": "Remove from list",
    "root.unavailable": "(unavailable)",
    # --- index status ----------------------------------------------------
    "index.status_label": "Index status:",
    "index.status_none": "No index yet",
    "index.status_ready": "Ready",
    "index.status_running": "Indexing…",
    "index.status_cancelled": "Last run cancelled",
    "index.status_failed": "Last run failed",
    "index.files_count": "{count:,} files",
    "index.updated": "Updated {when}",
    "index.never": "never",
    "index.create": "Create / Update Index",
    "index.update": "Update Index",
    "index.auto_building": "Building the search index…",
    "index.auto_checking": "Checking for changed files…",
    "index.auto_updated": "Index updated: {changed:,} file(s) changed.",
    "index.auto_hint": "Searching builds or refreshes the index automatically.",
    "index.auto_first_run": (
        "This folder has not been indexed yet. It will be indexed now; "
        "the first run can take a while."
    ),
    "index.rebuild": "Rebuild Index",
    "index.delete": "Delete Index",
    "index.open_data_folder": "Open Application Data Folder",
    "index.cancel": "Cancel",
    "index.close": "Close",
    "index.title": "Indexing",
    "index.phase": "Phase:",
    "index.current": "Current file:",
    "index.elapsed": "Elapsed:",
    "index.discovered": "Discovered",
    "index.processed": "Processed",
    "index.indexed": "Indexed",
    "index.unchanged": "Unchanged",
    "index.skipped": "Skipped",
    "index.failed": "Failed",
    "index.no_text": "No text",
    "index.deleted": "Removed",
    "index.errors_heading": "Problems ({count})",
    "index.no_errors": "No problems were reported.",
    "index.skips_heading": "Skipped items",
    "index.done": "Indexing finished.",
    "index.done_cancelled": "Indexing was cancelled. Previously indexed files remain searchable.",
    "index.done_failed": "Indexing stopped because of an error. The previous index is unchanged.",
    # --- phases ----------------------------------------------------------
    "phase.idle": "Idle",
    "phase.preparing": "Preparing",
    "phase.scanning": "Scanning folders",
    "phase.extracting": "Reading documents",
    "phase.removing_deleted": "Removing deleted files",
    "phase.finalizing": "Finalizing",
    "phase.done": "Completed",
    "phase.cancelled": "Cancelled",
    "phase.failed": "Failed",
    # --- search ----------------------------------------------------------
    "search.placeholder": "Search file names and contents…",
    "search.button": "Search",
    "search.stop": "Stop",
    "search.advanced": "Advanced filters",
    "search.scope": "Search in:",
    "search.scope_both": "File names and contents",
    "search.scope_name": "File names only",
    "search.scope_content": "Contents only",
    "search.match_case": "Match case",
    "search.exact_phrase": "Exact phrase",
    "search.whole_word": "Whole word",
    "search.file_types": "File types:",
    "search.modified_from": "Modified from:",
    "search.modified_to": "to:",
    "search.size_min": "Size from (KB):",
    "search.size_max": "to (KB):",
    "search.subfolder": "Subfolder:",
    "search.clear_filters": "Clear filters",
    "search.results_count": "Results: {count:,}",
    "search.results_truncated": "Results: {shown:,} of {total:,} files",
    "search.load_more": "Load more",
    "search.sort": "Sort:",
    "search.sort_relevance": "Relevance",
    "search.sort_name": "File name",
    "search.sort_type": "File type",
    "search.sort_size": "File size",
    "search.sort_modified": "Date modified",
    "search.sort_path": "Full path",
    "search.elapsed": "{ms:,.0f} ms",
    "search.empty": "No results found.",
    "search.no_index": "This folder has not been indexed yet. Choose Create / Update Index.",
    "search.wildcard_help": (
        "Wildcards: * matches any number of characters, ? matches exactly one. "
        'Use "quotes" for an exact phrase.'
    ),
    # --- result table ----------------------------------------------------
    "col.name": "Name",
    "col.location": "Location",
    "col.type": "Type",
    "col.size": "Size",
    "col.modified": "Modified",
    "col.snippet": "Match",
    "col.matches": "Matches",
    "col.open": "Open",
    "result.match_source_name": "File name",
    "result.match_source_content": "Content",
    "result.match_source_both": "Name + content",
    "result.more_locations": "{count} more locations",
    "result.missing": "File is missing",
    "result.match_count": "{count:,} matches",
    "result.match_count_one": "1 match",
    # --- details panel ---------------------------------------------------
    "details.heading": "Details",
    "details.none": "Select a result to see its details.",
    "details.full_path": "Full path",
    "details.relative_path": "Relative path",
    "details.type": "Type",
    "details.size": "Size",
    "details.created": "Created",
    "details.modified": "Modified",
    "details.match_source": "Match source",
    "details.status": "Index status",
    "details.locations": "Matching locations",
    "details.match_preview": "Matching text",
    "details.no_match_preview": "This result matched on the file name.",
    "details.no_selection_preview": "Select a result to preview the matching text.",
    # --- actions ---------------------------------------------------------
    "action.open_file": "Open File",
    "action.open_folder": "Open Folder",
    "action.open_folder_short": "Open folder",
    "action.open_folder_tooltip": "Open the folder containing this file",
    "action.copy_path": "Copy Path",
    "action.copy_folder_path": "Copy Folder Path",
    "action.copy_name": "Copy File Name",
    "action.update_index": "Update Index",
    # --- locations -------------------------------------------------------
    "loc.page": "Page {page}",
    "loc.paragraph": "Paragraph {paragraph}",
    "loc.table_cell": "Table {table}, row {row}, column {column}",
    "loc.sheet_cell": "Sheet: {sheet}, Cell: {cell}",
    "loc.line": "Line {line}",
    "loc.header": "Header",
    "loc.footer": "Footer",
    "loc.file_name": "File name",
    # --- first run -------------------------------------------------------
    "firstrun.heading": "Welcome to Advance File Search",
    "firstrun.body": (
        "Select a local folder or drive to create a private search index. "
        "Files and search data remain on this computer."
    ),
    "firstrun.step1": "1.  Choose a local folder or drive.",
    "firstrun.step2": "2.  Create the search index.",
    "firstrun.step3": "3.  Search file names and document contents.",
    # --- privacy ---------------------------------------------------------
    "privacy.statement": (
        "Advance File Search processes documents and search queries entirely on "
        "this computer. It does not upload files, use cloud services, send usage "
        "data, or require an Internet connection."
    ),
    # --- settings --------------------------------------------------------
    "settings.title": "Settings",
    "settings.tab_indexing": "Indexing",
    "settings.tab_search": "Search",
    "settings.tab_privacy": "Privacy & Logs",
    "settings.max_file_size": "Skip files larger than (MB):",
    "settings.include_hidden": "Index hidden files (system files are always skipped)",
    "settings.optional_formats": "Also index .md, .csv and .log files",
    "settings.docx_headers": "Index DOCX headers and footers",
    "settings.result_limit": "Results loaded per page:",
    "settings.snippets_per_file": "Maximum match locations shown per file:",
    "settings.remember_filters": "Remember the advanced filters",
    "settings.log_paths": "Include file paths in the log (helps troubleshooting)",
    "settings.log_level": "Log level:",
    "settings.language": "Language:",
    "settings.open_logs": "Open Log Folder",
    "settings.clear_logs": "Clear Logs",
    "settings.save": "Save",
    "settings.cancel": "Cancel",
    "settings.restart_note": "Language changes apply immediately to new windows.",
    # --- confirmations ---------------------------------------------------
    "confirm.rebuild_title": "Rebuild index?",
    "confirm.rebuild_body": (
        "The existing index for this folder will be deleted and rebuilt from "
        "scratch. {count:,} indexed files will be re-read. Continue?"
    ),
    "confirm.delete_title": "Delete index?",
    "confirm.delete_body": (
        "The index for this folder will be removed, including {count:,} indexed "
        "files. Your documents are not affected. Continue?"
    ),
    "confirm.yes": "Continue",
    "confirm.no": "Cancel",
    "confirm.drive_scan_title": "Index an entire drive?",
    "confirm.drive_scan_body": (
        "You selected the whole drive {drive}. Scanning may take a long time and "
        "some protected system folders will be skipped. Continue?"
    ),
    # --- errors ----------------------------------------------------------
    "error.title": "Advance File Search",
    "error.network_path": "Advance File Search version 1 supports local drives and folders only.",
    "error.remote_drive": (
        "{path} is a network drive. Advance File Search version 1 supports local "
        "drives and folders only."
    ),
    "error.device_path": "That location cannot be indexed.",
    "error.not_found": "The selected folder no longer exists.",
    "error.not_a_directory": "Please select a folder, not a file.",
    "error.cdrom": "Optical drives are not supported.",
    "error.unknown_drive": "That drive is not available.",
    "error.no_drive": "Please select a full local path, for example D:\\Documents.",
    "error.already_running": "Advance File Search is already running.",
    "error.db_locked": (
        "The search index is in use by another operation. Please try again in a "
        "moment."
    ),
    "error.db_corrupt": (
        "The search index could not be opened and may be damaged. You can rebuild "
        "it from the index menu."
    ),
    "error.disk_full": "There is not enough free disk space to update the index.",
    "error.query_too_long": "The search text is too long (maximum {max} characters).",
    "error.query_too_complex": "The search pattern is too complex. Please simplify it.",
    "error.query_empty": "Enter something to search for.",
    "error.no_root": "Select a local folder or drive first.",
    "error.file_missing_title": "File not found",
    "error.file_missing_body": (
        "The file was moved or deleted after it was indexed. Update the index to "
        "refresh the results."
    ),
    "error.open_failed": "Windows could not open this file.",
    "error.no_association": "No program on this computer is registered for this file type.",
    "action.row_buttons_tooltip": "Left: open the folder that holds this file\nRight: open the file",
    "action.open_file_tooltip": "Open this file",
    "error.unexpected": "An unexpected problem occurred. Details were written to the log.",
    "error.manual_missing": (
        "The user manual was not found. It should be in the Manual folder next "
        "to the program."
    ),
    "error.manual_failed": "Windows could not open the user manual.",
    # --- per-file index errors ------------------------------------------
    f"filestatus.{C.ERR_NO_TEXT}": (
        "No searchable text was found. The PDF may be scanned or image-only."
    ),
    f"filestatus.{C.ERR_PASSWORD_PROTECTED}": "This file is password-protected and was not indexed.",
    f"filestatus.{C.ERR_ACCESS_DENIED}": (
        "Advance File Search does not have permission to read this file."
    ),
    f"filestatus.{C.ERR_FILE_MISSING}": "The file was moved or deleted before indexing completed.",
    f"filestatus.{C.ERR_TOO_LARGE}": "The file is larger than the configured size limit.",
    f"filestatus.{C.ERR_CORRUPT}": "The file could not be read and may be damaged.",
    f"filestatus.{C.ERR_UNSUPPORTED}": "This file type is not supported in version 1.",
    f"filestatus.{C.ERR_ENCODING}": "The text encoding could not be detected reliably.",
    f"filestatus.{C.ERR_DISK_FULL}": "There is not enough free disk space to update the index.",
    f"filestatus.{C.ERR_LIMIT}": "The file exceeded a safety limit and was only partly indexed.",
    f"filestatus.{C.ERR_UNKNOWN}": "The file could not be indexed.",
    f"filestatus.{C.STATUS_INDEXED}": "Indexed",
    f"filestatus.{C.STATUS_STALE}": "Needs re-indexing",
    f"filestatus.{C.STATUS_SKIPPED}": "Skipped",
    f"filestatus.{C.STATUS_FAILED}": "Failed",
    # --- skip reasons ----------------------------------------------------
    "skip.not_supported": "Unsupported file type",
    "skip.executable": "Program or script file",
    "skip.temp_file": "Temporary Office file",
    "skip.hidden": "Hidden file",
    "skip.system": "System file",
    "skip.reparse_point": "Shortcut, symbolic link or junction",
    "skip.cloud_placeholder": "Online-only file (not downloaded)",
    "skip.too_large": "Larger than the size limit",
    "skip.excluded_dir": "Excluded folder",
    "skip.app_data": "Advance File Search data folder",
    "skip.outside_root": "Outside the selected folder",
    "skip.access_denied": "Permission denied",
    "skip.vanished": "File disappeared during the scan",
    "skip.empty_file": "Empty file",
    # --- about -----------------------------------------------------------
    "about.title": "About Advance File Search",
    "about.offline": "Offline · local processing only",
    "about.licenses": "Third-party licenses",
    "about.data_folder": "Application data folder",
    "about.close": "Close",
    "about.limitations": "Known limitations",
    "about.limitations_body": (
        "• Scanned or image-only PDFs are not read; there is no OCR.\n"
        "• Legacy .doc and .xls files are not supported.\n"
        "• Word page numbers cannot be determined without rendering, so DOCX "
        "matches report paragraph and table positions instead.\n"
        "• Excel formulas are not recalculated; the value stored in the file is "
        "indexed.\n"
        "• Network, NAS and cloud locations are not supported in version 1."
    ),
}

_TH: Final[dict[str, str]] = {
    "app.title": "Advance File Search",
    "app.version": "เวอร์ชัน {version}",
    "menu.settings": "ตั้งค่า",
    "menu.help": "ช่วยเหลือ",
    "menu.about": "เกี่ยวกับโปรแกรม",
    "menu.manual": "คู่มือการใช้งาน",
    "menu.manual_tooltip": "เปิดคู่มือการใช้งานแบบทีละขั้นตอน",
    "menu.language": "ภาษา",
    "root.label": "โฟลเดอร์ที่ค้นหา:",
    "root.select": "เลือกโฟลเดอร์…",
    "root.placeholder": "ยังไม่ได้เลือกโฟลเดอร์",
    "root.recent": "โฟลเดอร์ที่ใช้ล่าสุด",
    "root.dialog_title": "เลือกโฟลเดอร์หรือไดรฟ์ภายในเครื่องเพื่อสร้างดัชนี",
    "root.forget": "ลบออกจากรายการ",
    "root.unavailable": "(ไม่พบ)",
    "index.status_label": "สถานะดัชนี:",
    "index.status_none": "ยังไม่มีดัชนี",
    "index.status_ready": "พร้อมใช้งาน",
    "index.status_running": "กำลังสร้างดัชนี…",
    "index.status_cancelled": "การสร้างดัชนีครั้งก่อนถูกยกเลิก",
    "index.status_failed": "การสร้างดัชนีครั้งก่อนไม่สำเร็จ",
    "index.files_count": "{count:,} ไฟล์",
    "index.updated": "อัปเดต {when}",
    "index.never": "ยังไม่เคย",
    "index.create": "สร้าง / อัปเดตดัชนี",
    "index.update": "อัปเดตดัชนี",
    "index.auto_building": "กำลังสร้างดัชนีค้นหา…",
    "index.auto_checking": "กำลังตรวจสอบไฟล์ที่เปลี่ยนแปลง…",
    "index.auto_updated": "อัปเดตดัชนีแล้ว: เปลี่ยนแปลง {changed:,} ไฟล์",
    "index.auto_hint": "เมื่อกดค้นหา ระบบจะสร้างหรืออัปเดตดัชนีให้อัตโนมัติ",
    "index.auto_first_run": (
        "โฟลเดอร์นี้ยังไม่ได้สร้างดัชนี ระบบจะสร้างให้ตอนนี้ "
        "การสร้างครั้งแรกอาจใช้เวลาสักครู่"
    ),
    "index.rebuild": "สร้างดัชนีใหม่ทั้งหมด",
    "index.delete": "ลบดัชนี",
    "index.open_data_folder": "เปิดโฟลเดอร์ข้อมูลโปรแกรม",
    "index.cancel": "ยกเลิก",
    "index.close": "ปิด",
    "index.title": "การสร้างดัชนี",
    "index.phase": "ขั้นตอน:",
    "index.current": "ไฟล์ปัจจุบัน:",
    "index.elapsed": "เวลาที่ใช้:",
    "index.discovered": "พบไฟล์",
    "index.processed": "ดำเนินการแล้ว",
    "index.indexed": "จัดดัชนีสำเร็จ",
    "index.unchanged": "ไม่มีการเปลี่ยนแปลง",
    "index.skipped": "ข้าม",
    "index.failed": "ไม่สำเร็จ",
    "index.no_text": "ไม่มีข้อความ",
    "index.deleted": "ลบออกจากดัชนี",
    "index.errors_heading": "ปัญหาที่พบ ({count})",
    "index.no_errors": "ไม่พบปัญหา",
    "index.skips_heading": "รายการที่ข้าม",
    "index.done": "สร้างดัชนีเสร็จสิ้น",
    "index.done_cancelled": "ยกเลิกการสร้างดัชนีแล้ว ไฟล์ที่จัดดัชนีไว้ก่อนหน้ายังค้นหาได้",
    "index.done_failed": "การสร้างดัชนีหยุดเพราะเกิดข้อผิดพลาด ดัชนีเดิมไม่ถูกเปลี่ยนแปลง",
    "phase.idle": "ว่าง",
    "phase.preparing": "กำลังเตรียม",
    "phase.scanning": "กำลังสำรวจโฟลเดอร์",
    "phase.extracting": "กำลังอ่านเอกสาร",
    "phase.removing_deleted": "กำลังลบไฟล์ที่ถูกลบไปแล้ว",
    "phase.finalizing": "กำลังปิดงาน",
    "phase.done": "เสร็จสิ้น",
    "phase.cancelled": "ยกเลิกแล้ว",
    "phase.failed": "ไม่สำเร็จ",
    "search.placeholder": "ค้นหาชื่อไฟล์และเนื้อหาเอกสาร…",
    "search.button": "ค้นหา",
    "search.stop": "หยุด",
    "search.advanced": "ตัวกรองขั้นสูง",
    "search.scope": "ค้นหาใน:",
    "search.scope_both": "ชื่อไฟล์และเนื้อหา",
    "search.scope_name": "ชื่อไฟล์เท่านั้น",
    "search.scope_content": "เนื้อหาเท่านั้น",
    "search.match_case": "ตรงตามตัวพิมพ์เล็ก/ใหญ่",
    "search.exact_phrase": "ตรงทั้งวลี",
    "search.whole_word": "ตรงทั้งคำ",
    "search.file_types": "ชนิดไฟล์:",
    "search.modified_from": "แก้ไขตั้งแต่:",
    "search.modified_to": "ถึง:",
    "search.size_min": "ขนาดตั้งแต่ (KB):",
    "search.size_max": "ถึง (KB):",
    "search.subfolder": "โฟลเดอร์ย่อย:",
    "search.clear_filters": "ล้างตัวกรอง",
    "search.results_count": "ผลลัพธ์: {count:,}",
    "search.results_truncated": "ผลลัพธ์: {shown:,} จาก {total:,} ไฟล์",
    "search.load_more": "โหลดเพิ่ม",
    "search.sort": "เรียงตาม:",
    "search.sort_relevance": "ความเกี่ยวข้อง",
    "search.sort_name": "ชื่อไฟล์",
    "search.sort_type": "ชนิดไฟล์",
    "search.sort_size": "ขนาดไฟล์",
    "search.sort_modified": "วันที่แก้ไข",
    "search.sort_path": "พาธเต็ม",
    "search.elapsed": "{ms:,.0f} มิลลิวินาที",
    "search.empty": "ไม่พบผลลัพธ์",
    "search.no_index": "โฟลเดอร์นี้ยังไม่ได้สร้างดัชนี กรุณากด สร้าง / อัปเดตดัชนี",
    "search.wildcard_help": (
        "สัญลักษณ์แทน: * แทนอักขระจำนวนเท่าใดก็ได้, ? แทนอักขระหนึ่งตัว "
        'ใช้เครื่องหมาย "คำพูด" เพื่อค้นหาทั้งวลี'
    ),
    "col.name": "ชื่อไฟล์",
    "col.location": "ตำแหน่ง",
    "col.type": "ชนิด",
    "col.size": "ขนาด",
    "col.modified": "วันที่แก้ไข",
    "col.snippet": "ข้อความที่ตรงกัน",
    "col.matches": "จำนวนที่ตรง",
    "col.open": "เปิด",
    "result.match_source_name": "ชื่อไฟล์",
    "result.match_source_content": "เนื้อหา",
    "result.match_source_both": "ชื่อไฟล์ + เนื้อหา",
    "result.more_locations": "อีก {count} ตำแหน่ง",
    "result.missing": "ไม่พบไฟล์",
    "result.match_count": "ตรงกัน {count:,} แห่ง",
    "result.match_count_one": "ตรงกัน 1 แห่ง",
    "details.heading": "รายละเอียด",
    "details.none": "เลือกผลลัพธ์เพื่อดูรายละเอียด",
    "details.full_path": "พาธเต็ม",
    "details.relative_path": "พาธสัมพัทธ์",
    "details.type": "ชนิดไฟล์",
    "details.size": "ขนาด",
    "details.created": "วันที่สร้าง",
    "details.modified": "วันที่แก้ไข",
    "details.match_source": "แหล่งที่ตรงกัน",
    "details.status": "สถานะดัชนี",
    "details.locations": "ตำแหน่งที่ตรงกัน",
    "details.match_preview": "ข้อความที่ตรงกัน",
    "details.no_match_preview": "ผลลัพธ์นี้ตรงกับชื่อไฟล์",
    "details.no_selection_preview": "เลือกผลลัพธ์เพื่อดูข้อความที่ตรงกัน",
    "action.open_file": "เปิดไฟล์",
    "action.open_folder": "เปิดโฟลเดอร์",
    "action.open_folder_short": "เปิดโฟลเดอร์",
    "action.open_folder_tooltip": "เปิดโฟลเดอร์ที่เก็บไฟล์นี้",
    "action.copy_path": "คัดลอกพาธ",
    "action.copy_folder_path": "คัดลอกพาธโฟลเดอร์",
    "action.copy_name": "คัดลอกชื่อไฟล์",
    "action.update_index": "อัปเดตดัชนี",
    "loc.page": "หน้า {page}",
    "loc.paragraph": "ย่อหน้า {paragraph}",
    "loc.table_cell": "ตาราง {table} แถว {row} คอลัมน์ {column}",
    "loc.sheet_cell": "ชีต: {sheet}, เซลล์: {cell}",
    "loc.line": "บรรทัด {line}",
    "loc.header": "หัวกระดาษ",
    "loc.footer": "ท้ายกระดาษ",
    "loc.file_name": "ชื่อไฟล์",
    "firstrun.heading": "ยินดีต้อนรับสู่ Advance File Search",
    "firstrun.body": (
        "เลือกโฟลเดอร์หรือไดรฟ์ภายในเครื่องเพื่อสร้างดัชนีค้นหา "
        "ไฟล์และข้อมูลการค้นหาจะอยู่ภายในเครื่องนี้เท่านั้น"
    ),
    "firstrun.step1": "1.  เลือกโฟลเดอร์หรือไดรฟ์ภายในเครื่อง",
    "firstrun.step2": "2.  สร้างดัชนีค้นหา",
    "firstrun.step3": "3.  ค้นหาชื่อไฟล์และเนื้อหาเอกสาร",
    "privacy.statement": (
        "Advance File Search ประมวลผลเอกสารและคำค้นหาภายในเครื่องนี้เท่านั้น "
        "โปรแกรมจะไม่อัปโหลดไฟล์ ไม่ใช้บริการคลาวด์ ไม่ส่งข้อมูลการใช้งาน "
        "และไม่จำเป็นต้องเชื่อมต่ออินเทอร์เน็ต"
    ),
    "settings.title": "ตั้งค่า",
    "settings.tab_indexing": "การสร้างดัชนี",
    "settings.tab_search": "การค้นหา",
    "settings.tab_privacy": "ความเป็นส่วนตัวและบันทึก",
    "settings.max_file_size": "ข้ามไฟล์ที่ใหญ่กว่า (MB):",
    "settings.include_hidden": "จัดดัชนีไฟล์ที่ซ่อนอยู่ (ไฟล์ระบบจะถูกข้ามเสมอ)",
    "settings.optional_formats": "จัดดัชนีไฟล์ .md, .csv และ .log ด้วย",
    "settings.docx_headers": "จัดดัชนีหัวกระดาษและท้ายกระดาษของ DOCX",
    "settings.result_limit": "จำนวนผลลัพธ์ที่โหลดต่อครั้ง:",
    "settings.snippets_per_file": "จำนวนตำแหน่งที่แสดงต่อไฟล์:",
    "settings.remember_filters": "จดจำตัวกรองขั้นสูงไว้ใช้ครั้งถัดไป",
    "settings.log_paths": "บันทึกพาธไฟล์ลงในบันทึก (ช่วยในการแก้ปัญหา)",
    "settings.log_level": "ระดับการบันทึก:",
    "settings.language": "ภาษา:",
    "settings.open_logs": "เปิดโฟลเดอร์บันทึก",
    "settings.clear_logs": "ลบบันทึก",
    "settings.save": "บันทึก",
    "settings.cancel": "ยกเลิก",
    "settings.restart_note": "การเปลี่ยนภาษาจะมีผลทันที",
    "confirm.rebuild_title": "สร้างดัชนีใหม่ทั้งหมด?",
    "confirm.rebuild_body": (
        "ดัชนีเดิมของโฟลเดอร์นี้จะถูกลบและสร้างใหม่ทั้งหมด "
        "ไฟล์ที่จัดดัชนีไว้ {count:,} ไฟล์จะถูกอ่านซ้ำ ดำเนินการต่อ?"
    ),
    "confirm.delete_title": "ลบดัชนี?",
    "confirm.delete_body": (
        "ดัชนีของโฟลเดอร์นี้จะถูกลบ รวมถึงข้อมูลของไฟล์ {count:,} ไฟล์ "
        "เอกสารต้นฉบับจะไม่ได้รับผลกระทบ ดำเนินการต่อ?"
    ),
    "confirm.yes": "ดำเนินการต่อ",
    "confirm.no": "ยกเลิก",
    "confirm.drive_scan_title": "จัดดัชนีทั้งไดรฟ์?",
    "confirm.drive_scan_body": (
        "คุณเลือกไดรฟ์ {drive} ทั้งไดรฟ์ การสำรวจอาจใช้เวลานาน "
        "และโฟลเดอร์ระบบบางส่วนจะถูกข้าม ดำเนินการต่อ?"
    ),
    "error.title": "Advance File Search",
    "error.network_path": "Advance File Search เวอร์ชัน 1 รองรับไดรฟ์และโฟลเดอร์ภายในเครื่องเท่านั้น",
    "error.remote_drive": (
        "{path} เป็นไดรฟ์เครือข่าย Advance File Search เวอร์ชัน 1 "
        "รองรับไดรฟ์และโฟลเดอร์ภายในเครื่องเท่านั้น"
    ),
    "error.device_path": "ไม่สามารถจัดดัชนีตำแหน่งนี้ได้",
    "error.not_found": "ไม่พบโฟลเดอร์ที่เลือก",
    "error.not_a_directory": "กรุณาเลือกโฟลเดอร์ ไม่ใช่ไฟล์",
    "error.cdrom": "ไม่รองรับไดรฟ์ออปติคัล",
    "error.unknown_drive": "ไดรฟ์นี้ไม่พร้อมใช้งาน",
    "error.no_drive": "กรุณาระบุพาธภายในเครื่องแบบเต็ม เช่น D:\\Documents",
    "error.already_running": "Advance File Search กำลังทำงานอยู่แล้ว",
    "error.db_locked": "ดัชนีค้นหากำลังถูกใช้งานอยู่ กรุณาลองอีกครั้งในอีกสักครู่",
    "error.db_corrupt": "ไม่สามารถเปิดดัชนีค้นหาได้ ดัชนีอาจเสียหาย คุณสามารถสร้างดัชนีใหม่ได้จากเมนูดัชนี",
    "error.disk_full": "พื้นที่ดิสก์ไม่เพียงพอสำหรับการอัปเดตดัชนี",
    "error.query_too_long": "คำค้นหายาวเกินไป (ไม่เกิน {max} อักขระ)",
    "error.query_too_complex": "รูปแบบการค้นหาซับซ้อนเกินไป กรุณาลดความซับซ้อน",
    "error.query_empty": "กรุณาระบุคำค้นหา",
    "error.no_root": "กรุณาเลือกโฟลเดอร์หรือไดรฟ์ภายในเครื่องก่อน",
    "error.file_missing_title": "ไม่พบไฟล์",
    "error.file_missing_body": "ไฟล์ถูกย้ายหรือลบหลังจากจัดดัชนี กรุณาอัปเดตดัชนีเพื่อรีเฟรชผลลัพธ์",
    "error.open_failed": "Windows ไม่สามารถเปิดไฟล์นี้ได้",
    "error.no_association": "เครื่องนี้ยังไม่มีโปรแกรมที่ตั้งไว้สำหรับเปิดไฟล์ชนิดนี้",
    "action.row_buttons_tooltip": "ซ้าย: เปิดโฟลเดอร์ที่เก็บไฟล์นี้\nขวา: เปิดไฟล์นี้",
    "action.open_file_tooltip": "เปิดไฟล์นี้",
    "error.unexpected": "เกิดปัญหาที่ไม่คาดคิด รายละเอียดถูกบันทึกไว้ในไฟล์บันทึก",
    "error.manual_missing": "ไม่พบคู่มือการใช้งาน คู่มือควรอยู่ในโฟลเดอร์ Manual ข้างโปรแกรม",
    "error.manual_failed": "Windows ไม่สามารถเปิดคู่มือการใช้งานได้",
    f"filestatus.{C.ERR_NO_TEXT}": "ไม่พบข้อความที่ค้นหาได้ ไฟล์ PDF นี้อาจเป็นภาพสแกน",
    f"filestatus.{C.ERR_PASSWORD_PROTECTED}": "ไฟล์นี้มีรหัสผ่านป้องกัน จึงไม่ได้จัดดัชนี",
    f"filestatus.{C.ERR_ACCESS_DENIED}": "Advance File Search ไม่มีสิทธิ์อ่านไฟล์นี้",
    f"filestatus.{C.ERR_FILE_MISSING}": "ไฟล์ถูกย้ายหรือลบก่อนที่การจัดดัชนีจะเสร็จ",
    f"filestatus.{C.ERR_TOO_LARGE}": "ไฟล์มีขนาดใหญ่กว่าขีดจำกัดที่ตั้งไว้",
    f"filestatus.{C.ERR_CORRUPT}": "ไม่สามารถอ่านไฟล์ได้ ไฟล์อาจเสียหาย",
    f"filestatus.{C.ERR_UNSUPPORTED}": "เวอร์ชัน 1 ไม่รองรับไฟล์ชนิดนี้",
    f"filestatus.{C.ERR_ENCODING}": "ตรวจหาการเข้ารหัสข้อความได้ไม่แน่ชัด",
    f"filestatus.{C.ERR_DISK_FULL}": "พื้นที่ดิสก์ไม่เพียงพอสำหรับการอัปเดตดัชนี",
    f"filestatus.{C.ERR_LIMIT}": "ไฟล์เกินขีดจำกัดความปลอดภัย จึงจัดดัชนีได้เพียงบางส่วน",
    f"filestatus.{C.ERR_UNKNOWN}": "ไม่สามารถจัดดัชนีไฟล์นี้ได้",
    f"filestatus.{C.STATUS_INDEXED}": "จัดดัชนีแล้ว",
    f"filestatus.{C.STATUS_STALE}": "ต้องจัดดัชนีใหม่",
    f"filestatus.{C.STATUS_SKIPPED}": "ข้าม",
    f"filestatus.{C.STATUS_FAILED}": "ไม่สำเร็จ",
    "skip.not_supported": "ชนิดไฟล์ที่ไม่รองรับ",
    "skip.executable": "ไฟล์โปรแกรมหรือสคริปต์",
    "skip.temp_file": "ไฟล์ชั่วคราวของ Office",
    "skip.hidden": "ไฟล์ที่ซ่อนอยู่",
    "skip.system": "ไฟล์ระบบ",
    "skip.reparse_point": "ทางลัด ลิงก์สัญลักษณ์ หรือ junction",
    "skip.cloud_placeholder": "ไฟล์ออนไลน์เท่านั้น (ยังไม่ดาวน์โหลด)",
    "skip.too_large": "ใหญ่กว่าขีดจำกัดขนาด",
    "skip.excluded_dir": "โฟลเดอร์ที่ยกเว้น",
    "skip.app_data": "โฟลเดอร์ข้อมูลของ Advance File Search",
    "skip.outside_root": "อยู่นอกโฟลเดอร์ที่เลือก",
    "skip.access_denied": "ไม่มีสิทธิ์เข้าถึง",
    "skip.vanished": "ไฟล์หายไประหว่างการสำรวจ",
    "skip.empty_file": "ไฟล์ว่าง",
    "about.title": "เกี่ยวกับ Advance File Search",
    "about.offline": "ออฟไลน์ · ประมวลผลภายในเครื่องเท่านั้น",
    "about.licenses": "สัญญาอนุญาตของไลบรารีภายนอก",
    "about.data_folder": "โฟลเดอร์ข้อมูลโปรแกรม",
    "about.close": "ปิด",
    "about.limitations": "ข้อจำกัดที่ทราบ",
    "about.limitations_body": (
        "• ไม่อ่าน PDF ที่เป็นภาพสแกน เพราะไม่มีระบบ OCR\n"
        "• ไม่รองรับไฟล์ .doc และ .xls รูปแบบเก่า\n"
        "• ไม่สามารถระบุเลขหน้าของ Word ได้หากไม่เรนเดอร์เอกสาร "
        "จึงรายงานตำแหน่งเป็นย่อหน้าและตารางแทน\n"
        "• ไม่คำนวณสูตรของ Excel ใหม่ ระบบจัดดัชนีค่าที่บันทึกไว้ในไฟล์\n"
        "• เวอร์ชัน 1 ไม่รองรับตำแหน่งบนเครือข่าย NAS หรือคลาวด์"
    ),
}

_TABLES: Final[Mapping[str, Mapping[str, str]]] = {LANG_ENGLISH: _EN, LANG_THAI: _TH}

_current_language: str = LANG_THAI


def set_language(language: str) -> None:
    global _current_language
    _current_language = language if language in _TABLES else LANG_ENGLISH


def current_language() -> str:
    return _current_language


def tr(key: str, /, **kwargs: Any) -> str:
    """Return the localized string for ``key``.

    Falls back to English and finally to the key itself, so a missing
    translation degrades gracefully rather than raising in the UI.  Formatting
    errors are swallowed for the same reason.
    """
    table = _TABLES.get(_current_language, _EN)
    text = table.get(key)
    if text is None:
        text = _EN.get(key, key)
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):  # pragma: no cover - defensive
        return text


def location_label(location_type: str, location_data: Mapping[str, Any]) -> str:
    """Render a localized source-location label.

    Only integer/short-string positional data is interpolated.  Sheet names
    come from the document, so they are length-capped before display; the UI
    escapes them when rendering rich text.
    """
    data = dict(location_data or {})
    sheet = data.get("sheet")
    if isinstance(sheet, str) and len(sheet) > 60:
        data["sheet"] = sheet[:59] + "…"
    key = f"loc.{location_type}"
    if key not in _EN:
        return str(data.get("label", location_type))
    return tr(key, **data)


def skip_reason_label(reason: str) -> str:
    return tr(f"skip.{reason}")


def file_status_label(code: str) -> str:
    return tr(f"filestatus.{code}")
