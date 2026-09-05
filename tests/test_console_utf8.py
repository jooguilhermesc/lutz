"""Tests for lutz.utils.console — UTF-8 stdio forcing and ASCII-safe symbols.

Regression coverage for the Windows legacy-console crash:

    UnicodeEncodeError: 'charmap' codec can't encode character '→'

raised from ``console.print(f"    [dim]-> {reason}[/]")`` in
``lutz/commands/vectorize.py`` while quarantining flagged PDFs.

Every test runs on Linux (CI) by monkeypatching ``sys.platform`` / ``sys.stdout``.
"""

from __future__ import annotations

import importlib
import io
import sys

import pytest
from rich.console import Console

import lutz.utils.console as console_mod


class FakeStream:
    """Minimal stdout/stderr stand-in that records reconfigure() calls."""

    def __init__(self, encoding: str = "cp1252", raises: BaseException | None = None) -> None:
        self.encoding = encoding
        self.calls: list[dict[str, str]] = []
        self._raises = raises

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        if "encoding" in kwargs:
            self.encoding = kwargs["encoding"]

    def write(self, text: str) -> int:  # pragma: no cover - not exercised
        return len(text)


class NoReconfigureStream:
    """Stream without .reconfigure (e.g. a plain object wrapping a pipe)."""

    encoding = "cp1252"


# ---------------------------------------------------------------------------
# force_utf8_stdio
# ---------------------------------------------------------------------------


def test_force_utf8_stdio_is_noop_outside_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    out, err = FakeStream(), FakeStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    console_mod.force_utf8_stdio()

    assert out.calls == []
    assert err.calls == []


def test_force_utf8_stdio_reconfigures_stdout_and_stderr_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    out, err = FakeStream(), FakeStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    console_mod.force_utf8_stdio()

    expected = {"encoding": "utf-8", "errors": "replace"}
    assert out.calls == [expected]
    assert err.calls == [expected]
    assert out.encoding == "utf-8"
    assert err.encoding == "utf-8"


def test_force_utf8_stdio_survives_stream_without_reconfigure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", NoReconfigureStream())
    monkeypatch.setattr(sys, "stderr", NoReconfigureStream())

    console_mod.force_utf8_stdio()  # must not raise AttributeError


def test_force_utf8_stdio_survives_reconfigure_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    out = FakeStream(raises=ValueError("underlying buffer has been detached"))
    err = FakeStream(raises=ValueError("underlying buffer has been detached"))
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    console_mod.force_utf8_stdio()  # must not raise

    assert len(out.calls) == 1
    assert len(err.calls) == 1


def test_force_utf8_stdio_survives_none_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    """pythonw.exe / frozen builds can leave sys.stdout as None."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    console_mod.force_utf8_stdio()  # must not raise


# ---------------------------------------------------------------------------
# _supports / symbol fallbacks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("char", ["→", "✓", "✗", "•", "—"])
def test_supports_false_under_cp1252(monkeypatch: pytest.MonkeyPatch, char: str) -> None:
    """cp1252 has no arrow/check glyph, and its dash/bullet render as mojibake.

    The user report shows ``Phase 1/3 ?`` — U+2014 *is* encodable in cp1252
    (0x97) but the console draws it with the active OEM code page.  Non-UTF
    stdout encodings therefore never get a Unicode glyph.
    """
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="cp1252"))
    assert console_mod._supports(char) is False


@pytest.mark.parametrize("char", ["→", "✓", "✗", "•", "—"])
def test_supports_false_under_oem_code_page(monkeypatch: pytest.MonkeyPatch, char: str) -> None:
    """cp850 (chcp default on many Windows installs) has none of the glyphs."""
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="cp850"))
    assert console_mod._supports(char) is False


@pytest.mark.parametrize("char", ["→", "✓", "•", "—"])
def test_supports_true_under_utf8(monkeypatch: pytest.MonkeyPatch, char: str) -> None:
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="utf-8"))
    assert console_mod._supports(char) is True


def test_supports_handles_missing_and_unknown_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding=None))  # type: ignore[arg-type]
    assert console_mod._supports("→") is False

    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="not-a-real-codec"))
    assert console_mod._supports("→") is False


@pytest.mark.parametrize("encoding", ["utf-8", "UTF8", "utf_8", "utf-16"])
def test_supports_accepts_utf_codec_aliases(
    monkeypatch: pytest.MonkeyPatch, encoding: str
) -> None:
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding=encoding))
    assert console_mod._supports("→") is True


def test_symbol_prefers_unicode_then_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="utf-8"))
    assert console_mod._symbol("→", "->") == "→"

    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="cp1252"))
    assert console_mod._symbol("→", "->") == "->"


def _reload_with_stdout(monkeypatch: pytest.MonkeyPatch, stream: object):
    monkeypatch.setattr(sys, "stdout", stream)
    return importlib.reload(console_mod)


def test_symbols_degrade_to_ascii_on_legacy_code_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_with_stdout(monkeypatch, FakeStream(encoding="cp850"))
    try:
        assert mod.ARROW == "->"
        assert mod.CHECK == "OK"
        assert mod.CROSS == "x"
        assert mod.BULLET == "*"
        assert mod.DASH == "-"
        for symbol in (mod.ARROW, mod.CHECK, mod.CROSS, mod.BULLET, mod.DASH):
            symbol.encode("cp850")  # must not raise
    finally:
        importlib.reload(mod)


def test_symbols_are_encodable_under_cp1252(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every symbol must survive the exact encoding of the reported crash."""
    mod = _reload_with_stdout(monkeypatch, FakeStream(encoding="cp1252"))
    try:
        assert mod.ARROW == "->"
        assert mod.CHECK == "OK"
        assert mod.DASH == "-"
        assert mod.BULLET == "*"
        for symbol in (mod.ARROW, mod.CHECK, mod.CROSS, mod.BULLET, mod.DASH):
            symbol.encode("ascii")  # must not raise
    finally:
        importlib.reload(mod)


def test_symbols_are_unicode_when_stdout_is_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_with_stdout(monkeypatch, FakeStream(encoding="utf-8"))
    try:
        assert mod.ARROW == "→"
        assert mod.CHECK == "✓"
        assert mod.BULLET == "•"
        assert mod.DASH == "—"
    finally:
        importlib.reload(mod)


# ---------------------------------------------------------------------------
# Regression: the actual vectorize.py:267 crash
# ---------------------------------------------------------------------------


QUARANTINE_REASON = "prompt injection pattern detected (ATLAS T0051)"


def test_raw_unicode_arrow_still_breaks_cp1252_console() -> None:
    """Documents the original bug: the hard-coded arrow is unencodable in cp1252."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    console = Console(file=stream, force_terminal=False, width=80)

    with pytest.raises(UnicodeEncodeError):
        console.print(f"    [dim]→ {QUARANTINE_REASON}[/]")


def test_quarantine_line_does_not_crash_on_cp1252_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """vectorize.py:267 equivalent must survive a legacy Windows console."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    mod = _reload_with_stdout(monkeypatch, stream)
    try:
        console = Console(file=stream, force_terminal=False, width=80)
        console.print(f"    [dim]{mod.ARROW} {QUARANTINE_REASON}[/]")
        console.print(f"[green]{mod.CHECK}[/] All 16 file(s) passed the security scan.\n")
        console.print(f"[bold]Phase 1/3 {mod.DASH} Security scan[/]")
        stream.flush()
    finally:
        importlib.reload(mod)


def test_vectorize_module_uses_symbol_constants() -> None:
    """The critical path must not hard-code the unencodable glyphs."""
    from pathlib import Path

    commands_pkg = importlib.import_module("lutz.commands")
    source = (Path(commands_pkg.__file__).parent / "vectorize.py").read_text(  # type: ignore[arg-type]
        encoding="utf-8"
    )

    printed = [
        line
        for line in source.splitlines()
        if "console.print(" in line and ("→" in line or "✓" in line)
    ]
    assert printed == [], f"hard-coded Unicode symbols still printed: {printed}"


def test_reload_reconfigures_before_probing_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows the symbols must be probed *after* stdio becomes UTF-8."""
    monkeypatch.setattr(sys, "platform", "win32")
    stream = FakeStream(encoding="cp1252")
    monkeypatch.setattr(sys, "stderr", FakeStream(encoding="cp1252"))
    mod = _reload_with_stdout(monkeypatch, stream)
    try:
        assert stream.calls == [{"encoding": "utf-8", "errors": "replace"}]
        assert mod.ARROW == "→"
        assert mod.CHECK == "✓"
    finally:
        importlib.reload(mod)


def test_importing_lutz_package_wires_utf8_helper() -> None:
    """`import lutz` must load the stdio fix before any Console() is built."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    code = "import sys, lutz; print('lutz.utils.console' in sys.modules)"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == "True"


def test_supports_false_for_unencodable_char_under_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive branch: lone surrogates are rejected even by a UTF codec."""
    monkeypatch.setattr(sys, "stdout", FakeStream(encoding="utf-8"))
    assert console_mod._supports("\ud800") is False
