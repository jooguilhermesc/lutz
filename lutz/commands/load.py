"""lutz load — copy PDF articles into the project's articles/ directory."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from lutz.utils.project import require_project_root
from lutz.utils.pdf import is_valid_pdf

console = Console()

_OS_TYPES = ("linux", "windows", "mac", "docker")


@click.command()
@click.option(
    "--f", "folder",
    required=True,
    help="Source folder path containing PDF files.",
)
@click.option(
    "--so", "source_os",
    default="docker",
    type=click.Choice(_OS_TYPES, case_sensitive=False),
    show_default=True,
    help=(
        "Operating system convention for the source path. "
        "Use 'docker' (default) when running inside a container with a mounted volume; "
        "'linux', 'windows', or 'mac' when running on a local machine."
    ),
)
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Overwrite existing files in articles/.",
)
def load(folder: str, source_os: str, overwrite: bool) -> None:
    """Copy PDF files from a source folder into the project's articles/ directory.

    \b
    Only files with a .pdf or .PDF extension are copied. Files that fail a
    basic validity check (magic bytes) are skipped and reported as invalid.
    Sub-directories in the source folder are searched recursively.

    \b
    The --so flag tells lutz which path convention the source path uses.
    This is necessary because the path separator and expansion rules differ
    across operating systems and Docker volumes:
      linux / mac   Standard POSIX paths. ~ is expanded.
      windows       Backslash-separated paths (e.g. C:\\Users\\...).
      docker        Default. Use when running lutz inside a container and the
                    source folder is a mounted volume path (e.g. /data/papers).

    \b
    Examples:
      lutz load --f /data/my-articles
      lutz load --f ~/Downloads/papers --so linux
      lutz load --f ~/Desktop/papers --so mac
      lutz load --f "C:\\Users\\researcher\\papers" --so windows
      lutz load --f /workspace/papers --overwrite
    """
    project_root = require_project_root()
    articles_dir = project_root / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    source_path = _resolve_path(folder, source_os)
    if not source_path.exists():
        console.print(f"[bold red]Error:[/] source path does not exist: {source_path}")
        raise click.Abort()
    if not source_path.is_dir():
        console.print(f"[bold red]Error:[/] source path is not a directory: {source_path}")
        raise click.Abort()

    pdf_files = list(source_path.rglob("*.pdf")) + list(source_path.rglob("*.PDF"))
    if not pdf_files:
        console.print(f"[yellow]No PDF files found in[/] {source_path}")
        return

    console.print(f"Found [bold cyan]{len(pdf_files)}[/] PDF candidate(s) in [dim]{source_path}[/]")

    copied = skipped = invalid = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Copying articles...", total=len(pdf_files))

        for pdf in pdf_files:
            progress.advance(task)
            dest = articles_dir / pdf.name

            if dest.exists() and not overwrite:
                console.print(f"  [dim]skip[/] {pdf.name} (already exists, use --overwrite)")
                skipped += 1
                continue

            if not is_valid_pdf(pdf):
                console.print(f"  [red]invalid[/] {pdf.name} — not a valid PDF, skipping")
                invalid += 1
                continue

            shutil.copy2(pdf, dest)
            console.print(f"  [green]copied[/] {pdf.name}")
            copied += 1

    console.print(
        f"\n[bold green]Done.[/] "
        f"Copied: {copied}  |  Skipped: {skipped}  |  Invalid: {invalid}"
    )
    if copied > 0:
        console.print("Run [bold]lutz vectorize[/] to index the new articles.")


def _resolve_path(raw: str, source_os: str) -> Path:
    """Normalise a raw path string according to the source OS convention."""
    match source_os.lower():
        case "windows":
            # Convert Windows backslash path to a local Path
            pure = PureWindowsPath(raw)
            return Path(*pure.parts)
        case "mac" | "linux" | "docker":
            return Path(raw).expanduser().resolve()
        case _:  # pragma: no cover
            return Path(raw)
