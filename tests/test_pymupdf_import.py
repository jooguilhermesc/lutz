"""Every PDF entry point must import the modern `pymupdf` module.

Importing the legacy `fitz` alias emits::

    warning: The 'fitz' API is deprecated and will be removed in future.
             Use 'import pymupdf' instead.

on every `lutz vectorize` run.  The `as fitz` alias is kept so call sites stay
untouched; a fallback to the legacy module preserves pymupdf < 1.24.3 support.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

PDF_MODULES = [
    "lutz/core/security_checker.py",
    "lutz/core/extraction.py",
    "lutz/server/app.py",
    "lutz/utils/document_reader.py",
]


@pytest.mark.parametrize("relpath", PDF_MODULES)
def test_module_imports_pymupdf_not_legacy_fitz(relpath: str) -> None:
    source = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    lines = [line.strip() for line in source.splitlines()]

    assert "import pymupdf as fitz" in lines, f"{relpath} does not import pymupdf"

    bare_imports = [line for line in lines if line == "import fitz"]
    fallbacks = [line for line in lines if line.startswith("except ImportError")]
    assert len(bare_imports) <= len(fallbacks), (
        f"{relpath} imports the deprecated `fitz` module outside an ImportError fallback"
    )
    assert "import fitz  # pymupdf" not in lines, f"{relpath} still uses the deprecated alias"
