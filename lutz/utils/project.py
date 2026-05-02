"""Project root detection and environment loading."""

from __future__ import annotations

import os
from pathlib import Path

import click
from dotenv import dotenv_values


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up directory tree looking for a lutz project marker.

    A lutz project is identified by the presence of an 'articles' directory
    or a '.lutz' directory at the project root.
    """
    current = (start or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        if (path / "articles").is_dir() or (path / ".lutz").is_dir():
            return path
    return None


def require_project_root() -> Path:
    """Return the project root or abort with a helpful error message."""
    root = find_project_root()
    if root is None:
        raise click.ClickException(
            "No lutz project found in the current directory or any parent directory.\n"
            "Run [bold]lutz init[/] to create a new project."
        )
    return root


def load_env(project_root: Path | None = None) -> dict[str, str]:
    """Load environment variables from .env file, merged with os.environ."""
    root = project_root or find_project_root() or Path.cwd()
    env_file = root / ".env"

    file_values: dict[str, str] = {}
    if env_file.exists():
        file_values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}

    # os.environ takes precedence over .env file
    merged = {**file_values, **os.environ}
    return merged
