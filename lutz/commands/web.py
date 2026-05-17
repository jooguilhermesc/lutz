"""lutz web — inicia a interface visual de pesquisa."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()

_APP_HOME = Path(__file__).parent.parent / "ui" / "Home.py"


@click.command()
@click.option(
    "--port",
    default=8501,
    show_default=True,
    type=click.IntRange(1024, 65535),
    help="Porta onde o servidor Streamlit irá escutar.",
)
@click.option(
    "--host",
    default="localhost",
    show_default=True,
    help="Endereço de rede ao qual o servidor irá se vincular.",
)
@click.option(
    "--browser/--no-browser",
    default=True,
    show_default=True,
    help="Abrir o navegador automaticamente ao iniciar.",
)
def web(port: int, host: str, browser: bool) -> None:
    """Inicia a interface visual de pesquisa no navegador.

    \b
    Inicia um servidor Streamlit local e abre a interface automaticamente.
    Requer que o Streamlit esteja instalado:

        pip install 'lutz-research[ui]'

    \b
    Exemplos:
      lutz web
      lutz web --port 8080
      lutz web --host 0.0.0.0 --port 8888
      lutz web --no-browser
    """
    try:
        import streamlit  # noqa: F401
    except ImportError:
        console.print(
            "[bold red]Erro:[/] Streamlit não está instalado.\n"
            "Reinstale o pacote: [bold]uv pip install -e .[/]"
        )
        raise click.Abort()

    if not _APP_HOME.exists():
        console.print(
            f"[bold red]Erro:[/] Arquivos da interface não encontrados em:\n"
            f"  [dim]{_APP_HOME}[/]\n"
            "Reinstale o pacote lutz-research."
        )
        raise click.Abort()

    console.print(
        f"[bold cyan]Lutz UI[/] iniciando em "
        f"[bold]http://{host}:{port}[/]\n"
        "[dim]Pressione Ctrl+C para encerrar.[/]\n"
    )

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(_APP_HOME),
        "--server.port", str(port),
        "--server.address", host,
    ]
    if not browser:
        cmd += ["--server.headless", "true"]

    subprocess.run(cmd)
