"""Lutz — AI-powered academic article screening tool."""

# Windows legacy consoles (cmd.exe / PowerShell 5) report cp1252 as
# sys.stdout.encoding, which cannot encode the Unicode glyphs Rich prints
# (→, ✓, —) and used to abort `lutz vectorize` with UnicodeEncodeError.
#
# The reconfiguration is triggered here, at *package* import, because
# `lutz.cli` and every `lutz.commands.*` module build their `Console()` at
# module level: importing any of them executes this file first, so stdio is
# already UTF-8 by the time those consoles are created — regardless of the
# entry point used (`lutz.cli:cli`, `python -m lutz`, or the FastAPI app).
from lutz.utils.console import force_utf8_stdio

force_utf8_stdio()

__version__ = "0.5.0"
__author__ = "Lutz Contributors"
