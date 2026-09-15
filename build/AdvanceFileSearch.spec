# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Advance File Search (onedir).

Build:
    .venv\\Scripts\\python.exe -m PyInstaller build\\AdvanceFileSearch.spec --noconfirm

Debug build with a console attached:
    set AFS_DEBUG_BUILD=1
    .venv\\Scripts\\python.exe -m PyInstaller build\\AdvanceFileSearch.spec --noconfirm

Design decisions (docs/decisions/0006-packaging.md):

* ``onedir``, not ``onefile``.  A onefile build unpacks itself into the user's
  temp directory on every launch, which both slows startup and writes the whole
  application — including its SQLite library — somewhere a privacy-conscious
  user is not expecting.  ``onedir`` keeps everything in the install folder.
* Windowed release build: no console window.  A console-enabled debug variant
  is produced only when ``AFS_DEBUG_BUILD`` is set.
* Qt network, WebEngine, multimedia and 3D modules are explicitly excluded.
  None of them are used, and excluding them makes it impossible for a stray
  import to give the application network reach.
* ``LICENSES``, ``Manual`` and ``README.txt`` ship next to the executable.
"""

import os
import sys
from pathlib import Path

DEBUG_BUILD = bool(os.environ.get("AFS_DEBUG_BUILD"))

SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

APP_NAME = "AdvanceFileSearch"

# ---------------------------------------------------------------------------
# Data files: everything the application needs at runtime, bundled locally.
# Nothing is downloaded, now or later.
# ---------------------------------------------------------------------------
datas = [
    (str(PROJECT_ROOT / "advance_file_search" / "storage" / "schema.sql"),
     "advance_file_search/storage"),
]

for folder in ("LICENSES", "assets", "Manual"):
    source = PROJECT_ROOT / folder
    if source.is_dir() and any(source.iterdir()):
        datas.append((str(source), folder))

for single in ("README.txt", "PRIVACY.txt"):
    source = PROJECT_ROOT / single
    if source.is_file():
        datas.append((str(source), "."))

# ---------------------------------------------------------------------------
# Hidden imports: parser backends are resolved lazily inside the parsers, so
# PyInstaller's static analysis needs to be told about them.
# ---------------------------------------------------------------------------
hiddenimports = [
    "pymupdf",
    "fitz",
    "docx",
    "docx.opc.exceptions",
    "docx.table",
    "docx.text.paragraph",
    "openpyxl",
    "openpyxl.cell._writer",
    "openpyxl.utils.exceptions",
    "openpyxl.worksheet._reader",
    "et_xmlfile",
    "lxml",
    "lxml.etree",
    "lxml._elementpath",
    "sqlite3",
    "encodings.cp874",
    "encodings.tis_620",
    "encodings.utf_16",
    "encodings.utf_32",
    "encodings.cp1252",
    "encodings.idna",
]

# ---------------------------------------------------------------------------
# Exclusions: anything that could reach the network, plus unused weight.
# ---------------------------------------------------------------------------
excludes = [
    # Qt modules with network or remote-content capability.
    "PySide6.QtNetwork",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    "PySide6.QtHttpServer",
    "PySide6.QtNetworkAuth",
    "PySide6.QtRemoteObjects",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    # Unused Qt weight.
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtSensors",
    "PySide6.QtUiTools",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    # Networking and telemetry.
    # multiprocessing is excluded because PyInstaller injects a runtime hook
    # for it that imports socket, which would drag _socket.pyd and OpenSSL
    # back into a build that must not be able to reach the network.  Nothing
    # in this application uses multiprocessing; background work is done with
    # QThread.
    "multiprocessing",
    "multiprocessing.pool",
    "multiprocessing.reduction",
    "concurrent.futures.process",
    "socket",
    "ssl",
    "asyncio",
    "selectors",
    "socketserver",
    "http",
    "urllib.request",
    "ftplib",
    "smtplib",
    "xmlrpc",
    "webbrowser",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "paramiko",
    "sentry_sdk",
    "posthog",
    # Heavy science stack that is not used.
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "sklearn",
    "torch",
    "onnx",
    "onnxruntime",
    "PIL",
    "cv2",
    # Developer tooling.
    "pytest",
    "_pytest",
    "setuptools",
    "pip",
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "IPython",
]

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / "advance_file_search" / "app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries trip antivirus heuristics for no gain.
    # Release builds are windowed: no console window appears.  Only an
    # explicit AFS_DEBUG_BUILD produces a console variant.
    console=DEBUG_BUILD,
    disable_windowed_traceback=not DEBUG_BUILD,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "app.ico")
    if (PROJECT_ROOT / "assets" / "app.ico").is_file()
    else None,
    version=str(PROJECT_ROOT / "build" / "version_info.txt")
    if (PROJECT_ROOT / "build" / "version_info.txt").is_file()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Advance File Search",
)
