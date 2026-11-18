# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Lutz 1.0.
#
#   cd web && npm ci && npm run build && cd ..
#   rm -rf lutz/web && cp -r web/dist lutz/web
#   pip install . pyinstaller && pyinstaller lutz.spec
#
# Output: dist/lutz(.exe). No PyTorch, no OCR models, no GTK runtime: PDF reports are made with
# PyMuPDF, so the binary stays self-contained.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)

datas = [
    (str(HERE / "lutz" / "web"), "lutz/web"),
    (str(HERE / "lutz" / "data"), "lutz/data"),
]
datas += collect_data_files("certifi")

hidden_imports = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "anyio._backends._asyncio", "multipart", "python_multipart",
    "pymupdf", "krippendorff", "rapidfuzz", "openai", "yaml", "dotenv",
]
hidden_imports += collect_submodules("lutz")
hidden_imports += collect_submodules("mcp")

excludes = [
    "matplotlib", "IPython", "jupyter", "notebook", "tkinter", "PyQt5", "wx",
    "torch", "transformers", "sklearn", "statsmodels", "pandas", "pingouin",
    "pytest", "test", "tests", "doctest",
]

a = Analysis(
    [str(HERE / "lutz" / "__main__.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# PyMuPDF on Windows needs the Visual C++ runtime (MSVCP140.dll, VCRUNTIME140*.dll). PyInstaller
# copies these DLLs from the build machine into the binary (app-local deployment, allowed by the
# Redistributable licence), so lutz.exe runs where the Redistributable is not installed. A build
# machine without them would ship a lutz.exe that fails on "import pymupdf": stop the build instead.
if sys.platform == "win32":
    _incluidas = {Path(destino).name.lower() for destino, _origem, _tipo in a.binaries}
    _faltam = sorted({"msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"} - _incluidas)
    if _faltam:
        raise SystemExit(f"lutz.spec: {_faltam} não entraram no binário. Instale o Microsoft Visual C++ "
                         "Redistributable (x64) na máquina de build e rode o PyInstaller de novo.")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="lutz",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
