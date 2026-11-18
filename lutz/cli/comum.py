"""Helpers shared by every CLI command."""

from __future__ import annotations

import functools
import sys
from contextlib import contextmanager
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from lutz.config.settings import carregar_settings
from lutz.core.db import conectar
from lutz.core.errors import LutzError
from lutz.core.lock import bloqueio
from lutz.core.project import Projeto, encontrar_projeto


def _console() -> Console:
    # Legacy Windows consoles (cp1252) cannot print every glyph; never crash on output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    return Console(highlight=False)


console = _console()


def erros(f):
    """Turn domain errors into clean CLI errors (no traceback)."""

    @functools.wraps(f)
    def inner(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except LutzError as exc:
            raise click.ClickException(str(exc)) from None

    return inner


@contextmanager
def abrir(projeto_dir: str | None = None, escrita: str | None = None):
    """Yield (projeto, con). With *escrita*, hold the project write lock."""
    projeto = encontrar_projeto(Path(projeto_dir) if projeto_dir else None)
    if escrita:
        with bloqueio(projeto, escrita):
            con = conectar(projeto)
            try:
                yield projeto, con
            finally:
                con.close()
    else:
        con = conectar(projeto)
        try:
            yield projeto, con
        finally:
            con.close()


def settings_de(projeto: Projeto):
    return carregar_settings(projeto)


def tabela(colunas: list[str], linhas: list[list], titulo: str | None = None) -> None:
    t = Table(title=titulo, show_lines=False, header_style="bold")
    for c in colunas:
        t.add_column(c, overflow="fold")
    for linha in linhas:
        t.add_row(*["" if x is None else str(x) for x in linha])
    console.print(t)


def fmt(x, casas: int = 2) -> str:
    if x is None:
        return "—"
    try:
        import math

        if math.isnan(x):
            return "—"
    except TypeError:
        return str(x)
    return f"{x:.{casas}f}"


def lista_opcao(valor: str | None) -> list[str] | None:
    if not valor:
        return None
    return [x.strip() for x in valor.split(",") if x.strip()]


opcao_projeto = click.option("--projeto", "projeto_dir", default=None, metavar="PASTA",
                             help="Pasta do projeto (padrão: a pasta atual ou uma acima).")
