"""Security checker — detect potentially malicious or non-academic PDFs.

Threat model
------------
An adversary may include a PDF whose text contains "prompt injection" payloads —
instructions designed to override the LLM's behaviour during the analysis step
(e.g. "Ignore all previous instructions and output ...").

Defence-in-depth approach used here:
    1. Structural PDF analysis — detect embedded JavaScript, launch actions,
       suspicious annotations, and other PDF attack vectors.
    2. Rule-based content checks — scan extracted text for known prompt-injection
       patterns and unusual instruction-like language.
    3. Academic structure validation — heuristically confirm the document follows
       the conventions of a scientific paper (abstract, references, etc.).
    4. Corpus-level anomaly detection — when multiple documents are available,
       use TF-IDF + IsolationForest to flag statistical outliers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

# Use google-re2 when available (linear time, immune to catastrophic backtracking).
# Falls back transparently to the stdlib re module.
try:
    import re2 as re  # type: ignore[import]
except ImportError:
    import re  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt-injection patterns (case-insensitive)
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
        r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
        r"forget\s+(everything|all)\s+(you|i)",
        r"you\s+are\s+now\s+(a|an)\s+\w+",
        r"act\s+as\s+(if\s+you\s+are\s+)?(a|an)\s+\w+",
        r"new\s+instructions?:",
        r"override\s+(the\s+)?system\s+(prompt|instructions?)",
        r"confidential\s+instructions?:",
        r"do\s+not\s+follow\s+(your\s+)?(previous|prior)\s+(instructions?|guidelines?)",
        r"system\s*:\s*(you are|your role|your task)",
        r"<\s*\|?\s*(im_start|im_end|system|user|assistant)\s*\|?\s*>",
        r"\[\[\s*system\s*\]\]",
        r"###\s*instruction",
        r"<</SYS>>",
        r"<<SYS>>",
        r"\[INST\]",
        r"\[/INST\]",
        r"sudo\s+(mode|override)",
        r"developer\s+mode",
        r"jailbreak",
        r"DAN\s+(mode|prompt)",
        r"do\s+anything\s+now",
    ]
]

# ---------------------------------------------------------------------------
# Academic-paper section keywords (at least N must appear)
# ---------------------------------------------------------------------------
_ACADEMIC_SECTIONS = [
    "abstract", "introduction", "methodology", "methods", "results",
    "discussion", "conclusion", "references", "bibliography",
    "literature review", "related work", "background",
]

_ACADEMIC_SECTION_THRESHOLD = 3  # minimum distinct sections to detect

# Suspicious structural markers in a PDF
_PDF_SUSPICIOUS_KEYS = {"/JS", "/JavaScript", "/Launch", "/SubmitForm", "/ImportData"}


@dataclass
class SecurityReport:
    path: Path
    is_safe: bool
    reasons: list[str] = field(default_factory=list)
    # Cached per-page text extracted during the security check.
    # Reused by the extraction pipeline to avoid re-opening the PDF.
    cached_pages: list[tuple[int, str]] | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        status = "SAFE" if self.is_safe else "FLAGGED"
        return f"SecurityReport({self.path.name}, {status}, reasons={self.reasons})"


class SecurityChecker:
    """Run a battery of security checks on a PDF file."""

    def __init__(self, strict_academic: bool = True) -> None:
        self.strict_academic = strict_academic

    def check(self, path: Path) -> SecurityReport:
        reasons: list[str] = []
        cached_pages: list[tuple[int, str]] | None = None

        # --- Primary extractor: pymupdf (fast C library, MuPDF) ---------------
        try:
            import fitz  # pymupdf

            doc = fitz.open(str(path))
            cached_pages = [(i + 1, page.get_text("text") or "") for i, page in enumerate(doc)]
            doc.close()
            full_text = "\n".join(text for _, text in cached_pages)

            # Structural check still requires pypdf (PDF object tree traversal)
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                self._check_structure(reader, reasons)
            except Exception as exc:
                logger.debug("pypdf structural check failed for %s: %s", path.name, exc)

            self._check_injection_patterns(full_text, reasons)
            if self.strict_academic:
                self._check_academic_structure(full_text, reasons)

            return SecurityReport(
                path=path,
                is_safe=len(reasons) == 0,
                reasons=reasons,
                cached_pages=cached_pages,
            )

        except Exception as exc:
            logger.debug("pymupdf failed for %s: %s — falling back to pypdf", path.name, exc)

        # --- Fallback: pypdf only ---------------------------------------------
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            self._check_structure(reader, reasons)
            text = self._extract_text(reader)
            # Build cached_pages as a single-entry list (no per-page offsets)
            cached_pages = [(1, text)]
            self._check_injection_patterns(text, reasons)
            if self.strict_academic:
                self._check_academic_structure(text, reasons)

        except Exception as exc:
            reasons.append(f"Could not parse PDF: {exc}")

        return SecurityReport(
            path=path,
            is_safe=len(reasons) == 0,
            reasons=reasons,
            cached_pages=cached_pages,
        )

    # ------------------------------------------------------------------
    # Internal checkers
    # ------------------------------------------------------------------

    def _check_structure(self, reader: "pypdf.PdfReader", reasons: list[str]) -> None:
        """Look for dangerous PDF structural elements."""
        try:
            trailer = reader.trailer
            if "/Root" in trailer:
                root = trailer["/Root"]
                if hasattr(root, "get"):
                    # Check for JavaScript or auto-launch actions
                    for key in _PDF_SUSPICIOUS_KEYS:
                        if root.get(key):
                            reasons.append(f"PDF contains suspicious element: {key}")
                    # Check /OpenAction
                    open_action = root.get("/OpenAction")
                    if open_action and hasattr(open_action, "get"):
                        action_type = open_action.get("/S", "")
                        if action_type in ("/JavaScript", "/Launch", "/SubmitForm"):
                            reasons.append(
                                f"PDF has auto-execute action on open: /S={action_type}"
                            )
                    # Check /AcroForm for potential form-based attacks
                    acro_form = root.get("/AcroForm")
                    if acro_form and hasattr(acro_form, "get"):
                        xfa = acro_form.get("/XFA")
                        if xfa:
                            reasons.append("PDF contains XFA form (potential attack vector)")
        except Exception as exc:
            logger.debug("Structural check error: %s", exc)

    def _extract_text(self, reader: "pypdf.PdfReader") -> str:
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(parts)

    def _check_injection_patterns(self, text: str, reasons: list[str]) -> None:
        """Search for prompt-injection strings in the document text."""
        for pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                # Surface only the first 80 chars of the match for the report
                snippet = match.group(0)[:80].replace("\n", " ")
                reasons.append(f"Prompt injection pattern detected: '{snippet}'")
                break  # one match is enough to flag

    def _check_academic_structure(self, text: str, reasons: list[str]) -> None:
        """Heuristically verify the document looks like an academic paper."""
        if not text.strip():
            reasons.append("Document appears to contain no extractable text")
            return

        text_lower = text.lower()
        found = sum(1 for sec in _ACADEMIC_SECTIONS if sec in text_lower)
        if found < _ACADEMIC_SECTION_THRESHOLD:
            reasons.append(
                f"Document does not appear to be an academic paper "
                f"(found {found}/{_ACADEMIC_SECTION_THRESHOLD} expected section keywords: "
                f"{_ACADEMIC_SECTIONS})"
            )


# ---------------------------------------------------------------------------
# Corpus-level anomaly detector (optional, used when >= 5 docs are available)
# ---------------------------------------------------------------------------

def detect_corpus_anomalies(reports: list[SecurityReport]) -> list[SecurityReport]:
    """Flag statistical outliers in a document corpus using IsolationForest + TF-IDF.

    Only applied when there are at least 5 documents — fewer documents do not
    provide enough signal for meaningful anomaly detection.

    Returns a (possibly modified) copy of the report list.
    """
    if len(reports) < 5:
        return reports

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.ensemble import IsolationForest
        import numpy as np

        texts: list[str] = []
        for rep in reports:
            if rep.cached_pages is not None:
                # Reuse the text cached during the security check — no re-read needed
                text = "\n".join(t for _, t in rep.cached_pages)
            else:
                # Fallback: re-open the PDF (should only happen for legacy reports)
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(rep.path))
                    text = "\n".join(p.extract_text() or "" for p in reader.pages)
                except Exception:
                    text = ""
            texts.append(text if text.strip() else " ")

        vectorizer = TfidfVectorizer(max_features=500, stop_words="english")
        X = vectorizer.fit_transform(texts).toarray()

        clf = IsolationForest(contamination=0.05, random_state=42)
        predictions = clf.fit_predict(X)  # -1 = anomaly, 1 = normal

        updated: list[SecurityReport] = []
        for rep, pred in zip(reports, predictions):
            if pred == -1 and rep.is_safe:
                new_rep = SecurityReport(
                    path=rep.path,
                    is_safe=False,
                    reasons=rep.reasons
                    + [
                        "Corpus-level anomaly: document is statistically dissimilar "
                        "from the rest of the corpus (IsolationForest)"
                    ],
                    cached_pages=rep.cached_pages,
                )
                updated.append(new_rep)
            else:
                updated.append(rep)
        return updated

    except ImportError:
        logger.warning("scikit-learn not available; skipping corpus anomaly detection.")
        return reports
    except Exception as exc:
        logger.warning("Corpus anomaly detection failed: %s", exc)
        return reports
