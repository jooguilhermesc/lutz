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

    def extract_chunks(self, pdf_path: Path) -> list[dict]:
        """Return a list of chunk dicts ready for embedding.

        Each dict contains:
            text        — the chunk text
            page        — source page number (1-indexed)
            chunk_index — sequential index within the document
            char_start  — character offset within the page text
            section     — always empty string (use extract_chunks_with_sections
                          when section metadata is needed)
        """
        pages = self._extract_pages(pdf_path)
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
        self, pdf_path: Path, section_parser: "SectionParser"
    ) -> list[dict]:
        """Return chunks annotated with a ``section`` field.

        The sliding-window chunking runs within each detected section so that
        chunks never span section boundaries.  This preserves the semantic
        coherence of each section and allows downstream filtering by section
        name (e.g. retrieve only *abstract* or *methodology* chunks).

        Each dict contains:
            text        — the chunk text
            page        — first page of the section this chunk belongs to
            chunk_index — sequential index across the whole document
            char_start  — word offset within the section text
            section     — canonical section name ('abstract', 'introduction', …)
                          or 'body' / 'unknown' when no header was detected
        """
        pages = self._extract_pages(pdf_path)
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
        """Extract (page_number, text) pairs from a PDF."""
        pages: list[tuple[int, str]] = []

        # Try pdfplumber first (better text quality) then fall back to pypdf
        try:
            import pdfplumber

            with pdfplumber.open(str(pdf_path)) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    pages.append((i, text))
            return pages
        except Exception as exc:
            logger.debug("pdfplumber failed for %s: %s — trying pypdf", pdf_path.name, exc)

        try:
            import pypdf

            reader = pypdf.PdfReader(str(pdf_path))
            for i, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                pages.append((i, text))
            return pages
        except Exception as exc:
            logger.error("Could not extract text from %s: %s", pdf_path.name, exc)
            return []
