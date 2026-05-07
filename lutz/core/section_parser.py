"""Section-aware layout parsing for academic PDFs.

Two detection strategies are supported:

heuristic (default, no extra deps)
    Scans pdfplumber-extracted text line-by-line looking for short lines that
    match known academic section header patterns (e.g. "Abstract",
    "1. Introduction", "Materials and Methods").

layout-parser enhanced (optional)
    Uses layoutparser + pdf2image to render pages and detect Title blocks via
    a Detectron2 model trained on PubLayNet.  Title block positions are mapped
    back to the text lines already extracted by pdfplumber, then the same
    header patterns are applied — but with a more lenient line-length limit
    inside detected Title bands.

    Requires::

        pip install "lutz-research[layout]"

    Which installs ``layoutparser[layoutmodels]`` and ``pdf2image``.
    The PubLayNet Detectron2 model weights are downloaded on first use (~250 MB).
    Poppler must also be available on the system (``apt install poppler-utils``
    on Debian/Ubuntu; ``brew install poppler`` on macOS).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section header patterns
# ---------------------------------------------------------------------------

# Each entry is (canonical_name, compiled_regex).
# Patterns are anchored and allow an optional leading section number
# (e.g. "1.", "2.1", "II.").
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("abstract",         re.compile(r"^\s*(?:[\divxIVX]+[.\s]*)?\babstract\b\s*$", re.I)),
    ("introduction",     re.compile(r"^\s*(?:[\divxIVX]+[.\s]*)?\bintroduction\b\s*$", re.I)),
    ("background",       re.compile(
        r"^\s*(?:[\divxIVX]+[.\s]*)?\b(?:related\s+work|background|"
        r"literature\s+review)\b\s*$",
        re.I,
    )),
    ("methodology",      re.compile(
        r"^\s*(?:[\divxIVX]+[.\s]*)?\b(?:methodology|methods?|"
        r"materials\s+and\s+methods?|experimental\s+(?:setup|design)|"
        r"procedures?)\b\s*$",
        re.I,
    )),
    ("results",          re.compile(
        r"^\s*(?:[\divxIVX]+[.\s]*)?\b(?:results?|findings|"
        r"experiments?|evaluation|empirical\s+(?:study|results?))\b\s*$",
        re.I,
    )),
    ("discussion",       re.compile(r"^\s*(?:[\divxIVX]+[.\s]*)?\bdiscussion\b\s*$", re.I)),
    ("conclusion",       re.compile(
        r"^\s*(?:[\divxIVX]+[.\s]*)?\b(?:conclusions?|concluding\s+remarks?|summary)\b\s*$",
        re.I,
    )),
    ("references",       re.compile(
        r"^\s*(?:[\divxIVX]+[.\s]*)?\b(?:references?|bibliography)\b\s*$", re.I
    )),
    ("acknowledgements", re.compile(
        r"^\s*(?:[\divxIVX]+[.\s]*)?\backnowledgements?\b\s*$", re.I
    )),
    ("appendix",         re.compile(r"^\s*(?:[\divxIVX]+[.\s]*)?\bappendix\b\s*$", re.I)),
]

_STRICT_MAX_LEN = 80    # for heuristic-only lines
_LENIENT_MAX_LEN = 120  # for lines inside layout-detected Title bands


def _match_header(line: str, max_len: int = _STRICT_MAX_LEN) -> str | None:
    """Return a canonical section name if *line* looks like a section header."""
    stripped = line.strip()
    if not stripped or len(stripped) > max_len:
        return None
    for name, pattern in _PATTERNS:
        if pattern.match(stripped):
            return name
    return None


# ---------------------------------------------------------------------------
# Section dataclass
# ---------------------------------------------------------------------------


@dataclass
class Section:
    """A labeled segment of an academic paper."""

    name: str        # canonical name: 'abstract', 'introduction', 'body', …
    text: str        # full text content (space-joined lines)
    page_start: int  # first page (1-indexed)
    page_end: int    # last page  (1-indexed)


# ---------------------------------------------------------------------------
# SectionParser
# ---------------------------------------------------------------------------


class SectionParser:
    """Parse academic PDFs into labeled :class:`Section` objects.

    Parameters
    ----------
    use_layout_parser:
        When ``True`` (default), attempt to use layout-parser for visual block
        detection.  Falls back to text heuristics automatically if the library
        is not installed or if detection fails for a specific file.
    """

    def __init__(self, use_layout_parser: bool = True) -> None:
        self._lp_available = False
        if use_layout_parser:
            self._lp_available = _probe_layout_parser()
            if self._lp_available:
                logger.info("layout-parser detected — using visual layout detection.")
            else:
                logger.warning(
                    "layout-parser is installed but detectron2 is not available. "
                    "Falling back to text-heuristic section detection. "
                    "detectron2 is not on PyPI and must be installed manually — see: "
                    "https://detectron2.readthedocs.io/en/latest/tutorials/install.html"
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, pdf_path: Path, pages: list[tuple[int, str]]) -> list[Section]:
        """Return ordered :class:`Section` objects for *pdf_path*.

        Parameters
        ----------
        pdf_path:
            Source PDF (used only when layout-parser is active for rendering).
        pages:
            ``(page_number, text)`` pairs as produced by
            :meth:`~lutz.core.pdf_processor.PDFProcessor._extract_pages`.
        """
        if not pages:
            return []

        if self._lp_available:
            try:
                return self._parse_with_lp(pdf_path, pages)
            except Exception as exc:
                logger.warning(
                    "layout-parser failed for %s (%s) — falling back to heuristics.",
                    pdf_path.name,
                    exc,
                )

        return self._parse_heuristic(pages)

    # ------------------------------------------------------------------
    # Text-heuristic strategy (no extra deps)
    # ------------------------------------------------------------------

    def _parse_heuristic(self, pages: list[tuple[int, str]]) -> list[Section]:
        sections: list[Section] = []
        # Mutable state: [current_name, accumulated_lines, page_start, page_end]
        state: list = ["body", [], pages[0][0], pages[0][0]]

        def _flush(end_page: int) -> None:
            text = " ".join(state[1]).strip()
            if text:
                sections.append(Section(
                    name=state[0],
                    text=text,
                    page_start=state[2],
                    page_end=end_page,
                ))

        for page_num, page_text in pages:
            for line in page_text.splitlines():
                matched = _match_header(line, max_len=_STRICT_MAX_LEN)
                if matched:
                    _flush(page_num)
                    state[0] = matched
                    state[1] = []
                    state[2] = page_num
                    state[3] = page_num
                else:
                    if line.strip():
                        state[1].append(line)
                    state[3] = page_num

        _flush(state[3])

        if not sections:
            return [Section(
                name="body",
                text=" ".join(t for _, t in pages).strip(),
                page_start=pages[0][0],
                page_end=pages[-1][0],
            )]
        return sections

    # ------------------------------------------------------------------
    # layout-parser strategy (requires layoutparser + pdf2image)
    # ------------------------------------------------------------------

    def _parse_with_lp(self, pdf_path: Path, pages: list[tuple[int, str]]) -> list[Section]:
        import layoutparser as lp  # type: ignore[import]
        import numpy as np
        from pdf2image import convert_from_path  # type: ignore[import]

        model = lp.Detectron2LayoutModel(
            "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
            label_map={0: "Text", 1: "Title", 2: "List", 3: "Figure", 4: "Table"},
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
        )

        images = convert_from_path(str(pdf_path), dpi=150)

        # Collect Title-block vertical bands per page: {page_num: [(y0_frac, y1_frac), ...]}
        title_bands: dict[int, list[tuple[float, float]]] = {}
        for img, (page_num, _) in zip(images, pages):
            arr = np.array(img)
            h = arr.shape[0]
            if h == 0:
                continue
            layout = model.detect(arr)
            bands = [
                (block.block.y_1 / h, block.block.y_2 / h)
                for block in layout
                if block.type == "Title"
            ]
            if bands:
                title_bands[page_num] = bands

        if not title_bands:
            logger.debug(
                "No Title blocks detected by layout-parser for %s — using heuristics.",
                pdf_path.name,
            )
            return self._parse_heuristic(pages)

        # Scan lines: lines inside detected Title bands get lenient matching;
        # other lines still get strict heuristic matching.
        sections: list[Section] = []
        state: list = ["body", [], pages[0][0], pages[0][0]]

        def _flush(end_page: int) -> None:
            text = " ".join(state[1]).strip()
            if text:
                sections.append(Section(
                    name=state[0],
                    text=text,
                    page_start=state[2],
                    page_end=end_page,
                ))

        for page_num, page_text in pages:
            lines = page_text.splitlines()
            n = len(lines)
            bands = title_bands.get(page_num, [])

            for idx, line in enumerate(lines):
                # Estimate the vertical fraction of the page this line occupies
                line_frac = idx / max(n - 1, 1)
                in_title_band = any(
                    (y0 - 0.02) <= line_frac <= (y1 + 0.02)
                    for y0, y1 in bands
                )

                max_len = _LENIENT_MAX_LEN if in_title_band else _STRICT_MAX_LEN
                matched = _match_header(line, max_len=max_len)

                if matched:
                    _flush(page_num)
                    state[0] = matched
                    state[1] = []
                    state[2] = page_num
                    state[3] = page_num
                else:
                    if line.strip():
                        state[1].append(line)
                    state[3] = page_num

        _flush(state[3])

        if not sections or {s.name for s in sections} == {"body"}:
            # No meaningful sections found with layout-parser aid → heuristics
            return self._parse_heuristic(pages)

        return sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _probe_layout_parser() -> bool:
    """Return True if layoutparser, pdf2image, and detectron2 are all available."""
    try:
        import layoutparser as lp
        import pdf2image  # noqa: F401
        return lp.is_detectron2_available()
    except ImportError:
        return False
