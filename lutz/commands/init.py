"""lutz init — initialise a new research project."""

from __future__ import annotations

import shutil
from pathlib import Path

import click
import git
from rich.console import Console
from rich.panel import Panel

from lutz.utils.templates import (
    get_gitignore_template,
    get_env_example_template,
    get_readme_template,
    get_prompt_templates,
)

console = Console()

_PROJECT_DIRS = ["articles", "prompts", "analysis/execution_reports"]


@click.command()
@click.argument("project_name", default=".", required=False)
def init(project_name: str) -> None:
    """Initialise a new lutz research project.

    \b
    PROJECT_NAME
      Directory to initialise. Omit to use the current directory.
      If a name is given and the directory does not exist, it is created.
      An error is raised if the directory already exists and is not empty.

    \b
    Creates:
      articles/                     Place your PDF articles here.
      articles/_quarantine/         Created automatically if suspicious files
                                    are detected during 'lutz vectorize'.
      prompts/                      Markdown prompt templates for analysis.
      analysis/execution_reports/   JSON reports produced by 'lutz analysis'
                                    and 'lutz citations'.
      .env.example                  Model configuration reference.
      .gitignore                    Excludes articles/, .lutz/ and .env.
      README.md                     Project notes.

    \b
    After init:
      1. Copy .env.example → .env and set EMBEDDING_PROVIDER, LLM_PROVIDER, etc.
      2. Add PDFs with 'lutz load' or copy them directly to articles/.
      3. Run 'lutz vectorize' to build the vector index.
      4. Run 'lutz analysis --p prompts/<prompt>.md' to analyse.

    \b
    Examples:
      lutz init
      lutz init my-systematic-review
    """
    project_path = Path(project_name).resolve()

    if project_name != "." and project_path.exists() and any(project_path.iterdir()):
        console.print(
            f"[bold red]Error:[/] directory '{project_path}' already exists and is not empty."
        )
        raise click.Abort()

    project_path.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel.fit(
            f"[bold cyan]Initialising lutz project[/]\n[dim]{project_path}[/]",
            border_style="cyan",
        )
    )

    # --- directory structure -------------------------------------------------
    for subdir in _PROJECT_DIRS:
        (project_path / subdir).mkdir(parents=True, exist_ok=True)
        # keep empty dirs tracked in git
        (project_path / subdir / ".gitkeep").touch()
    console.print("[green]✓[/] Directories created")

    # --- static files --------------------------------------------------------
    _write(project_path / ".gitignore", get_gitignore_template())
    _write(project_path / ".env.example", get_env_example_template())
    _write(project_path / "README.md", get_readme_template(project_path.name))
    console.print("[green]✓[/] Configuration files written")

    # --- prompt templates ----------------------------------------------------
    for name, content in get_prompt_templates().items():
        _write(project_path / "prompts" / name, content)
    console.print("[green]✓[/] Prompt templates written to prompts/")

    # --- git repository ------------------------------------------------------
    try:
        repo = git.Repo.init(project_path)
        repo.index.add(["--all"])
        if repo.index.diff("HEAD") or repo.untracked_files:
            repo.index.add(repo.untracked_files)
            repo.index.commit("chore: initialise lutz research project")
        console.print("[green]✓[/] Git repository initialised")
    except Exception as exc:  # pragma: no cover
        console.print(f"[yellow]Warning:[/] could not initialise git repository — {exc}")

    console.print(
        Panel.fit(
            "[bold green]Project ready![/]\n\n"
            "Next steps:\n"
            "  1. Copy [cyan].env.example[/] → [cyan].env[/] and set your model configuration\n"
            "  2. Add PDF articles to [cyan]articles/[/]  (or use [bold]lutz load[/])\n"
            "  3. Run [bold]lutz vectorize[/] to index your articles\n"
            "  4. Run [bold]lutz analysis --p prompts/systematic_review.md[/]",
            border_style="green",
        )
    )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
