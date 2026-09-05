"""Console/stdio helpers for cross-platform Unicode output.

Windows legacy consoles (cmd.exe, PowerShell 5) run on the ANSI code page —
usually ``cp1252`` — and CPython follows the locale for ``sys.stdout.encoding``
up to and including 3.14 (UTF-8 only becomes the default in 3.15, PEP 686).
Printing ``→``/``✓``/``—`` on such a console raises::

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

which used to abort ``lutz vectorize`` in the middle of a corpus.

Two layers of defence live here:

1. :func:`force_utf8_stdio` reconfigures ``sys.stdout``/``sys.stderr`` to UTF-8
   with ``errors="replace"``.  It runs at *package* import time (see
   ``lutz/__init__.py``) so it always precedes the module-level ``Console()``
   instances created by ``lutz.cli`` and ``lutz.commands.*``.
2. The symbol constants below probe the *effective* stdout encoding and degrade
   to ASCII when the glyph is not representable — covering redirected pipes and
   files whose encoding cannot be reconfigured.
"""

from __future__ import annotations

import codecs
import sys

__all__ = [
    "ARROW",
    "BULLET",
    "CHECK",
    "CROSS",
    "DASH",
    "force_utf8_stdio",
]


def force_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows.  No-op elsewhere.

    ``errors="replace"`` is deliberate: an unrepresentable glyph must degrade
    visually (``?``) instead of killing a long-running pipeline.  Streams that
    cannot be reconfigured (redirected pipes, detached buffers, ``None`` under
    ``pythonw.exe``) are skipped silently — the ASCII fallbacks below cover them.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            continue


def _supports(ch: str) -> bool:
    """True when ``ch`` can be both encoded *and* rendered by the current stdout.

    Encodability alone is not enough on Windows: cp1252 encodes ``—`` (0x97),
    yet the console draws the byte with the active OEM code page (cp850/cp437),
    which produced the reported ``Phase 1/3 ?`` mojibake.  Unicode glyphs are
    therefore only used when stdout speaks a UTF codec — every other encoding
    gets the ASCII fallback.
    """
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        codec = codecs.lookup(enc).name
    except (LookupError, TypeError):
        return False
    if not codec.startswith("utf"):
        return False
    try:
        ch.encode(codec)
    except UnicodeEncodeError:
        return False
    return True


def _symbol(unicode_ch: str, ascii_fallback: str) -> str:
    """Return ``unicode_ch`` when the console can render it, else the fallback."""
    return unicode_ch if _supports(unicode_ch) else ascii_fallback


# Applied here — and not only in ``lutz/__init__.py`` — so the probes below see
# the reconfigured encoding no matter which module imports this one first.
force_utf8_stdio()

ARROW = _symbol("→", "->")
CHECK = _symbol("✓", "OK")
CROSS = _symbol("✗", "x")
BULLET = _symbol("•", "*")
DASH = _symbol("—", "-")
