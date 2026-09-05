"""Click help text must stay ASCII-only.

``--help`` is rendered by ``click.echo`` straight into ``sys.stdout``: it never
goes through Rich and cannot use the runtime symbol fallbacks in
``lutz.utils.console``.  A single ``≈`` in an option help string is therefore
enough to raise ``UnicodeEncodeError`` whenever stdout is not UTF-8 — a legacy
Windows console, or any redirection where ``reconfigure()`` fails.
"""

from __future__ import annotations

import click
import pytest

from lutz.cli import cli
from lutz.commands.analysis import analysis
from lutz.commands.init import init
from lutz.commands.load import load
from lutz.commands.vectorize import unvectorize, vectorize

FLOW_COMMANDS = [cli, init, load, vectorize, unvectorize, analysis]


def _non_ascii(text: str) -> list[str]:
    return sorted({ch for ch in text if ord(ch) > 127})


@pytest.mark.parametrize("command", FLOW_COMMANDS, ids=lambda c: c.name)
def test_command_docstring_is_ascii(command: click.Command) -> None:
    offenders = _non_ascii(command.help or "")
    assert offenders == [], f"{command.name} help text has non-ASCII: {offenders}"


@pytest.mark.parametrize("command", FLOW_COMMANDS, ids=lambda c: c.name)
def test_command_option_help_is_ascii(command: click.Command) -> None:
    for param in command.params:
        offenders = _non_ascii(getattr(param, "help", None) or "")
        assert offenders == [], f"{command.name} --{param.name} help has non-ASCII: {offenders}"


@pytest.mark.parametrize("command", FLOW_COMMANDS, ids=lambda c: c.name)
def test_rendered_help_encodes_on_legacy_code_page(command: click.Command) -> None:
    ctx = click.Context(command, info_name=command.name)
    command.get_help(ctx).encode("cp1252")  # must not raise
