"""PDF text extraction and chunking."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lutz.core.section_parser import SectionParser

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Extract text from PDFs and split into overlapping chunks."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_chunks(
        self,
        pdf_path: Path,
        pre_extracted_pages: list[tuple[int, str]] | None = None,
    ) -> list[dict]:
        """Return a list of chunk dicts ready for embedding.

        Parameters
        ----------
        pdf_path:
            Path to the PDF file. Used only when ``pre_extracted_pages`` is
            ``None``.
        pre_extracted_pages:
            Optional list of ``(page_number, text)`` tuples already extracted
            by a previous step (e.g. ``SecurityChecker.check``).  When
            provided the PDF is not opened again, eliminating redundant I/O.

        Each dict contains:
            text        — the chunk text
            page        — source page number (1-indexed)
            chunk_index — sequential index within the document
            char_start  — character offset within the page text
            section     — always empty string (use extract_chunks_with_sections
                          when section metadata is needed)
        """
        pages = pre_extracted_pages if pre_extracted_pages is not None \
            else self._extract_pages(pdf_path)
        chunks: list[dict] = []
        chunk_index = 0

        for page_num, page_text in pages:
            words = page_text.split()
            if not words:
                continue

            start = 0
            while start < len(words):
                end = min(start + self.chunk_size, len(words))
                chunk_text = " ".join(words[start:end]).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "page": page_num,
                            "chunk_index": chunk_index,
                            "char_start": start,
                            "section": "",
                        }
                    )
                    chunk_index += 1
                if end == len(words):
                    break
                start = end - self.chunk_overlap

        return chunks

    def extract_chunks_with_sections(
        self,
        pdf_path: Path,
        section_parser: "SectionParser",
        pre_extracted_pages: list[tuple[int, str]] | None = None,
    ) -> list[dict]:
        """Return chunks annotated with a ``section`` field.

        The sliding-window chunking runs within each detected section so that
        chunks never span section boundaries.  This preserves the semantic
        coherence of each section and allows downstream filtering by section
        name (e.g. retrieve only *abstract* or *methodology* chunks).

        Parameters
        ----------
        pdf_path:
            Path to the PDF file.
        section_parser:
            Configured ``SectionParser`` instance.
        pre_extracted_pages:
            Optional pre-extracted pages (see ``extract_chunks`` for details).

        Each dict contains:
            text        — the chunk text
            page        — first page of the section this chunk belongs to
            chunk_index — sequential index across the whole document
            char_start  — word offset within the section text
            section     — canonical section name ('abstract', 'introduction', …)
                          or 'body' / 'unknown' when no header was detected
        """
        pages = pre_extracted_pages if pre_extracted_pages is not None \
            else self._extract_pages(pdf_path)
        sections = section_parser.parse(pdf_path, pages)

        chunks: list[dict] = []
        chunk_index = 0

        for section in sections:
            words = section.text.split()
            if not words:
                continue

            start = 0
            while start < len(words):
                end = min(start + self.chunk_size, len(words))
                chunk_text = " ".join(words[start:end]).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "page": section.page_start,
                            "chunk_index": chunk_index,
                            "char_start": start,
                            "section": section.name,
                        }
                    )
                    chunk_index += 1
                if end == len(words):
                    break
                start = end - self.chunk_overlap

        return chunks

    def _extract_pages(self, pdf_path: Path) -> list[tuple[int, str]]:
        """Extract (page_number, text) pairs from a PDF.

        Extractor priority:
            1. pymupdf  — binding C para MuPDF (10-50x mais rápido)
            2. pdfplumber — fallback Python puro
            3. pypdf    — último recurso
        """
        # 1. pymupdf (MuPDF C binding — fastest, best layout handling)
        try:
            import fitz  # pymupdf

            doc = fitz.open(str(pdf_path))
            pages = [(i + 1, page.get_text("text") or "") for i, page in enumerate(doc)]
            doc.close()
            return pages
        except Exception as exc:
            logger.debug("pymupdf failed for %s: %s — trying pdfplumber", pdf_path.name, exc)

        # 2. pdfplumber (better text quality than pypdf, pure Python)
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
