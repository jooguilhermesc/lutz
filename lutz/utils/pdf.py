"""PDF validation utilities."""

from __future__ import annotations

from pathlib import Path

_PDF_MAGIC = b"%PDF-"


def is_valid_pdf(path: Path) -> bool:
    """Return True if the file starts with the PDF magic bytes."""
    try:
        with path.open("rb") as f:
            header = f.read(5)
        return header == _PDF_MAGIC
    except OSError:
        return False
