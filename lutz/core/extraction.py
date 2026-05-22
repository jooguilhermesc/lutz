"""Pluggable PDF extraction strategies for PDFProcessor.

Two concrete strategies are provided out-of-the-box:

PyMuPDFStrategy (default, no extra deps)
    Cascades pymupdf → pdfplumber → pypdf.  Fast, no system dependencies.

MarkerStrategy (optional, requires ``[marker]`` extra)
    Uses marker-pdf for OCR and multi-column layout detection.  Ideal for
    scanned PDFs and IEEE/Elsevier/ACM two-column layouts.  Model weights
    (~500 MB) are downloaded lazily on first use.

    Install::

        pip install "lutz-research[marker]"

    Configuration via .env::

        EXTRACTION_BACKEND=auto|pymupdf|marker
        MARKER_LANGUAGES=pt,en
        MARKER_DEVICE=cpu|cuda
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lutz.core.section_parser import Section

logger = logging.getLogger(__name__)

# Chars-per-page below which a PDF is considered likely scanned
_SPARSE_CHARS_PER_PAGE = 100


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ExtractionStrategy(Protocol):
    """Protocol for PDF text extraction backends.

    Implementations must provide :meth:`extract_pages` and
    :meth:`extract_sections`.  The latter may return ``None`` when the
    backend does not support structured section output — in that case
    :class:`~lutz.core.section_parser.SectionParser` is used instead.
    """

    def extract_pages(self, pdf_path: Path) -> list[tuple[int, str]]:
        """Return ``[(page_number, text), ...]`` in reading order."""
        ...

    def extract_sections(self, pdf_path: Path) -> "list[Section] | None":
        """Return structured sections or ``None`` if not supported."""
        ...


# ---------------------------------------------------------------------------
# PyMuPDF strategy (default)
# ---------------------------------------------------------------------------


class PyMuPDFStrategy:
    """Default strategy: pymupdf → pdfplumber → pypdf cascade.

    All three libraries operate on the PDF's existing text layer, so this
    strategy returns empty pages for scanned documents.  Use
    :class:`MarkerStrategy` for OCR.
    """

    def extract_pages(self, pdf_path: Path) -> list[tuple[int, str]]:
        """Extract text using pymupdf with pdfplumber / pypdf fallbacks."""
        # 1. pymupdf (MuPDF C binding — fastest, best layout handling)
        try:
            import fitz  # pymupdf

            doc = fitz.open(str(pdf_path))
            pages = [(i + 1, page.get_text("text") or "") for i, page in enumerate(doc)]
            doc.close()
            return pages
        except Exception as exc:
            logger.debug("pymupdf failed for %s: %s — trying pdfplumber", pdf_path.name, exc)

        # 2. pdfplumber (better quality than pypdf, pure Python)
        try:
            import pdfplumber

            with pdfplumber.open(str(pdf_path)) as pdf:
                return [(i, page.extract_text() or "") for i, page in enumerate(pdf.pages, 1)]
        except Exception as exc:
            logger.debug("pdfplumber failed for %s: %s — trying pypdf", pdf_path.name, exc)

        # 3. pypdf (last resort)
        try:
            import pypdf

            reader = pypdf.PdfReader(str(pdf_path))
            return [(i, page.extract_text() or "") for i, page in enumerate(reader.pages, 1)]
        except Exception as exc:
            logger.error("Could not extract text from %s: %s", pdf_path.name, exc)
            return []

    def extract_sections(self, pdf_path: Path) -> None:  # noqa: ARG002
        """PyMuPDF strategy does not provide structured sections."""
        return None


# ---------------------------------------------------------------------------
# Sparse-text heuristic (used by auto mode)
# ---------------------------------------------------------------------------


def is_sparse(pages: list[tuple[int, str]]) -> bool:
    """Return ``True`` if the extracted text is suspiciously sparse.

    A PDF is considered sparse when the average extracted text is fewer than
    :data:`_SPARSE_CHARS_PER_PAGE` characters per page, which typically
    indicates a scanned document with no embedded text layer.
    """
    if not pages:
        return False
    total_chars = sum(len(text) for _, text in pages)
    return (total_chars / len(pages)) < _SPARSE_CHARS_PER_PAGE


# ---------------------------------------------------------------------------
# Marker strategy (optional)
# ---------------------------------------------------------------------------


class MarkerStrategy:
    """Extraction backend powered by `marker-pdf`.

    Handles multi-column layouts (IEEE, Elsevier, ACM) and performs OCR on
    scanned PDFs via surya without requiring Poppler or Tesseract.

    Parameters
    ----------
    languages:
        Comma-separated BCP-47 language codes used for OCR, e.g. ``"pt,en"``.
        Passed as the ``langs`` argument to marker's ``convert_single_pdf``.
    device:
        Device for model inference: ``"cpu"`` or ``"cuda"``.
        When ``None`` the device is auto-detected by marker/torch.
    """

    def __init__(
        self,
        languages: str | None = None,
        device: str | None = None,
    ) -> None:
        self._languages = languages
        self._device = device
        self._models = None          # lazy-loaded on first use
        self._cache: dict[str, str] = {}  # resolved_path → markdown

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_installed() -> None:
        try:
            import marker  # noqa: F401  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "marker-pdf is not installed. "
                'Install it with: pip install "lutz-research[marker]"'
            ) from exc

    def _load_models(self):
        if self._models is not None:
            return self._models
        self._check_installed()
        from marker.models import load_all_models  # type: ignore[import]
        logger.info(
            "Loading marker-pdf models — first-time download may take a few minutes…"
        )
        self._models = load_all_models()
        return self._models

    def _get_markdown(self, pdf_path: Path) -> str:
        """Convert *pdf_path* to Markdown via marker; result is cached per file."""
        key = str(pdf_path.resolve())
        if key in self._cache:
            return self._cache[key]

        from marker.convert import convert_single_pdf  # type: ignore[import]

        models = self._load_models()
        kwargs: dict = {}
        if self._languages:
            kwargs["langs"] = [lang.strip() for lang in self._languages.split(",")]
        if self._device:
            kwargs["device"] = self._device

        logger.debug("marker: converting %s", pdf_path.name)
        full_text, _images, _metadata = convert_single_pdf(str(pdf_path), models, **kwargs)
        self._cache[key] = full_text
        return full_text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_pages(self, pdf_path: Path) -> list[tuple[int, str]]:
        """Convert PDF via marker and split Markdown output by page breaks."""
        markdown = self._get_markdown(pdf_path)
        # marker inserts form-feed (\x0c) between pages
        raw_pages = markdown.split("\x0c")
        return [
            (i + 1, page_text)
            for i, page_text in enumerate(raw_pages)
            if page_text.strip()
        ]

    def extract_sections(self, pdf_path: Path) -> "list[Section] | None":
        """Parse marker's Markdown headings into :class:`~lutz.core.section_parser.Section` objects.

        Returns ``None`` when no recognisable academic section headers are
        found in the Markdown output (the caller falls back to
        :class:`~lutz.core.section_parser.SectionParser`).
        """
        import re

        # Import the canonical-name matcher from section_parser.
        # _match_header is not part of the public API but is stable; marker
        # headings already give us the text to match against the same patterns.
        from lutz.core.section_parser import Section, _match_header  # type: ignore[attr-defined]

        markdown = self._get_markdown(pdf_path)
        lines = markdown.splitlines()

        sections: list[Section] = []
        state: list = ["body", [], 1, 1]  # [name, lines, page_start, page_end]
        current_page = 1

        def _flush(end_page: int) -> None:
            text = " ".join(state[1]).strip()
            if text:
                sections.append(Section(
                    name=state[0],
                    text=text,
                    page_start=state[2],
                    page_end=end_page,
                ))

        for line in lines:
            if line == "\x0c":
                current_page += 1
                continue

            heading_match = re.match(r"^#{1,3}\s+(.+)$", line)
            if heading_match:
                heading_text = heading_match.group(1).strip()
                canonical = _match_header(heading_text, max_len=200)
                if canonical:
                    _flush(current_page)
                    state[:] = [canonical, [], current_page, current_page]
                    continue

            if line.strip():
                state[1].append(line)
            state[3] = current_page

        _flush(state[3])

        # Only return sections if we found at least one named (non-body) section
        named = [s for s in sections if s.name != "body"]
        if not named:
            return None
        return sections


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_strategy(
    backend: str,
    languages: str | None = None,
    device: str | None = None,
) -> PyMuPDFStrategy | MarkerStrategy:
    """Return the extraction strategy for *backend*.

    Parameters
    ----------
    backend:
        ``"pymupdf"`` — default, no extra deps.
        ``"marker"``  — OCR + multi-column layout (requires ``[marker]``).
        ``"auto"``    — returns a :class:`PyMuPDFStrategy`; the caller
                        should call :func:`is_sparse` on the result and
                        switch to :class:`MarkerStrategy` when appropriate.
    languages:
        Forwarded to :class:`MarkerStrategy` only.
    device:
        Forwarded to :class:`MarkerStrategy` only.
    """
    if backend == "marker":
        return MarkerStrategy(languages=languages, device=device)
    # "pymupdf" and "auto" both start with PyMuPDF
    return PyMuPDFStrategy()
