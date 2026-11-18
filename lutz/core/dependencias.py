"""Lazy loading of PyMuPDF with a message the researcher can act on.

PyMuPDF is imported only where a PDF is read or written, never when the CLI, the web server or the
MCP server start. On a Windows machine without the Microsoft Visual C++ Redistributable,
``import pymupdf`` fails with "DLL load failed" because MSVCP140.dll is missing; ``lutz web`` and
``lutz doctor`` must still open and say what to install.
"""

from __future__ import annotations

import ctypes
import functools
import importlib
import sys
from types import ModuleType

from lutz.core.errors import LutzError

URL_VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
WINGET_VCREDIST = "winget install --id Microsoft.VCRedist.2015+.x64 -e"


class DependenciaAusente(LutzError):
    """A library the Lutz needs cannot be loaded on this machine."""


def _msvcp140_ausente() -> bool:
    """True when the C++ runtime of the Visual C++ Redistributable cannot be loaded."""
    try:
        ctypes.WinDLL("msvcp140.dll")  # type: ignore[attr-defined]
    except OSError:
        return True
    return False


def _plataforma() -> str:
    return sys.platform


def mensagem_pymupdf(exc: BaseException) -> str:
    if _plataforma() == "win32" and "DLL load failed" in str(exc) and _msvcp140_ausente():
        return ("O PyMuPDF, que o Lutz usa para ler e gerar PDFs, não carregou porque falta o Microsoft "
                "Visual C++ Redistributable (MSVCP140.dll) neste Windows. Instale-o com "
                f"'{WINGET_VCREDIST}' ou pelo instalador {URL_VCREDIST}, abra um terminal novo e "
                f"tente de novo. Erro original: {exc}")
    return (f"O PyMuPDF, que o Lutz usa para ler e gerar PDFs, não carregou: {exc}. "
            "Reinstale-o com 'pip install --force-reinstall pymupdf'.")


@functools.cache
def carregar_pymupdf() -> ModuleType:
    """Return the pymupdf module or raise DependenciaAusente with instructions."""
    try:
        return importlib.import_module("pymupdf")
    except ImportError as exc:
        raise DependenciaAusente(mensagem_pymupdf(exc)) from exc


def versao_pymupdf() -> str:
    m = carregar_pymupdf()
    return getattr(m, "__version__", None) or getattr(m, "VersionBind", "?")
