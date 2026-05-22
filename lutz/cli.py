"""Main CLI entry point for lutz."""

import click
from rich.console import Console

from lutz.commands.init import init
from lutz.commands.load import load
from lutz.commands.vectorize import vectorize, unvectorize
from lutz.commands.analysis import analysis
from lutz.commands.vector_store import vector_store
from lutz.commands.citations import citations
from lutz.commands.web import web
from lutz.commands.query import query

console = Console()


@click.group()
@click.version_option(package_name="lutz-research")
def cli() -> None:
    """Lutz — AI-powered academic article screening tool.

    Use 'lutz COMMAND --help' for information on a specific command.
    """


cli.add_command(init)
cli.add_command(load)
cli.add_command(vectorize)
cli.add_command(unvectorize)
cli.add_command(analysis)
cli.add_command(vector_store)
cli.add_command(citations)
cli.add_command(web)
cli.add_command(query)
