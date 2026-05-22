# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for lutz — AI-powered academic article screening tool.
#
# Build:
#   pip install pyinstaller
#   cd web && npm run build && cd ..
#   pyinstaller lutz.spec
#
# Output: dist/lutz  (Linux) or dist/lutz.exe (Windows)

import sys
from pathlib import Path

HERE = Path(SPECPATH)

# Detect platform
IS_WINDOWS = sys.platform == "win32"

# ── Data files to bundle ──────────────────────────────────────────────────────
#
# (source_path, dest_folder_inside_bundle)
#
# lutz/web/  contains the pre-built React SPA (npm run build → web/dist → lutz/web)
# lutz/      is already handled by the Analysis below, but we explicitly add web assets.

datas = [
    # React SPA static files
    (str(HERE / "lutz" / "web"), "lutz/web"),
    # Default prompts shipped with the package (if any)
    # (str(HERE / "lutz" / "prompts"), "lutz/prompts"),
]

# ── Hidden imports ────────────────────────────────────────────────────────────
#
# PyInstaller cannot always detect dynamic imports. List them explicitly.

hidden_imports = [
    # FastAPI / Starlette
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "starlette.routing",
    "starlette.staticfiles",
    "starlette.responses",
    "starlette.middleware.cors",
    "anyio",
    "anyio._backends._asyncio",
    # ML / embeddings
    "sentence_transformers",
    "transformers",
    "torch",
    "sklearn",
    "sklearn.utils._cython_blas",
    # PDF
    "pypdf",
    "pdfplumber",
    "fitz",       # pymupdf
    # DB
    "lancedb",
    "pyarrow",
    "duckdb",
    # LLM clients
    "openai",
    "anthropic",
    # Misc
    "yaml",
    "dotenv",
    "rich",
    "click",
    "pandas",
    "numpy",
    "python_multipart",
    "multipart",
]

# ── Exclusions ────────────────────────────────────────────────────────────────
#
# Reduce binary size by excluding things we don't need at runtime.

excludes = [
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "tkinter",
    "PyQt5",
    "wx",
    "test",
    "tests",
    "unittest",
    "doctest",
]

# ── Analysis ──────────────────────────────────────────────────────────────────

a = Analysis(
    [str(HERE / "lutz" / "cli.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

# ── Single-file executable ────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="lutz",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # CLI tool — keep console open
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
