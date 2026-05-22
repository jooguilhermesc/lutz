"""lutz web — inicia a interface visual de pesquisa."""
from __future__ import annotations

import os
import subprocess
import threading
import warnings
import webbrowser
from pathlib import Path

# Suppress LanceDB fork-safety warning — irrelevant for a single-process web server
warnings.filterwarnings("ignore", message="lance is not fork-safe")

import click
from rich.console import Console

console = Console()


@click.command()
@click.option(
    "--port",
    default=8765,
    show_default=True,
    type=click.IntRange(1024, 65535),
    help="Porta onde o servidor irá escutar.",
)
@click.option(
    "--host",
    default="localhost",
    show_default=True,
    help="Endereço de rede ao qual o servidor irá se vincular.",
)
@click.option(
    "--project",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Diretório do projeto lutz. Padrão: diretório atual.",
)
@click.option(
    "--browser/--no-browser",
    default=True,
    show_default=True,
    help="Abrir o navegador automaticamente ao iniciar.",
)
def web(port: int, host: str, project: Path | None, browser: bool) -> None:
    """Inicia a interface visual de pesquisa no navegador.

    \b
    Sobe um servidor local e abre a interface automaticamente.
    Não requer dependências adicionais — tudo já está incluído no pacote.

    \b
    Exemplos:
      lutz web
      lutz web --port 8080
      lutz web --host 0.0.0.0
      lutz web --no-browser
      lutz web --project /caminho/para/projeto
    """
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        console.print(
            "[bold red]Erro:[/] uvicorn não está instalado.\n"
            "Reinstale o pacote: [bold]pip install lutz-research[/]"
        )
        raise click.Abort()

    from lutz.utils.project import find_project_root

    # Resolve project root now, before uvicorn takes over the process.
    # Storing it in an env var makes it available regardless of what
    # uvicorn does with the working directory later.
    if project is not None:
        project_root = project.resolve()
    else:
        project_root = find_project_root()

    if project_root is None:
        console.print(
            "[bold red]Erro:[/] Nenhum projeto lutz encontrado neste diretório "
            "ou nos pais.\nExecute [bold]lutz init[/] para criar um projeto, "
            "ou use [bold]--project /caminho/para/projeto[/]."
        )
        raise click.Abort()

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)

    url = f"http://{host}:{port}"
    console.print(
        f"[bold cyan]Lutz[/] iniciando em [bold]{url}[/]\n"
        "[dim]Pressione Ctrl+C para encerrar.[/]\n"
    )

    if browser:
        def _open() -> None:
            import time
            time.sleep(1.2)
            # Use xdg-open with stderr suppressed to avoid GTK module warnings.
            # Fall back to webbrowser if xdg-open is not available.
            import shutil
            if shutil.which("xdg-open"):
                subprocess.Popen(
                    ["xdg-open", url],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            else:
                webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    import uvicorn
    uvicorn.run(
        "lutz.server.app:app",
        host=host,
        port=port,
        log_level="warning",
    )
