"""lutz vector-store — inspect and manage the local vector store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lutz.utils.project import require_project_root
from lutz.core.vector_store import VectorStore

console = Console()


def _dir_size_mb(path: Path) -> float:
    """Return the total size of a directory tree in megabytes."""
    total = sum(
        f.stat().st_size
        for f in path.rglob("*")
        if f.is_file()
    )
    return total / (1024 * 1024)


def _build_payload(info: dict, db_path: Path, project_root: Path, db_size_mb: float) -> dict:
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path.relative_to(project_root)),
        "db_size_mb": round(db_size_mb, 3),
        "total_records": info["total_records"],
        "unique_documents": info["unique_documents"],
        "last_updated": info["last_updated"],
        "embedding_model": info["embedding_model"],
        "embedding_provider": info["embedding_provider"],
        "articles": info["articles"],
    }


@click.command(name="vector-store")
@click.option(
    "--summarize",
    is_flag=True,
    default=False,
    help=(
        "Print a summary to the terminal: total chunks, total articles, last updated, "
        "embedding model and provider, database path and size on disk, "
        "and a per-article table with chunk count and vectorization timestamp."
    ),
)
@click.option(
    "--sections",
    is_flag=True,
    default=False,
    help=(
        "Show a per-article section breakdown: how many chunks each article has in "
        "each section (abstract, introduction, methodology, …). "
        "Articles vectorized without --section-parse will appear under '(no section)'. "
        "Useful to verify that section-aware vectorization worked correctly."
    ),
)
@click.option(
    "--export",
    "export_path",
    # flag_value="" → used as bare flag (--export, no filename)
    # default=None  → option not passed at all
    is_flag=False,
    flag_value="",
    default=None,
    metavar="FILE",
    help=(
        "Export the store summary as a JSON file. "
        "Omit FILE to auto-generate the filename (.lutz/vector_store_export_<timestamp>.json). "
        "Provide a FILE path (relative to project root or absolute) to choose the destination. "
        "Use '-' to print the JSON to stdout."
    ),
)
def vector_store(summarize: bool, sections: bool, export_path: str | None) -> None:
    """Inspect the local vector store (.lutz/vector_store/).

    \b
    Flags can be combined freely, e.g. --summarize --sections --export.

    \b
    Exported JSON fields:
      exported_at        ISO-8601 timestamp of the export.
      db_path            Relative path to the vector store directory.
      db_size_mb         Total size of database files on disk.
      total_records      Number of chunks indexed.
      unique_documents   Number of distinct articles.
      last_updated       Timestamp of the most recent vectorization.
      embedding_model    Model used for embeddings (most frequent in store).
      embedding_provider Provider (docker_model_runner, openai, sentence_transformers).
      articles[]         Per-article: filename, chunk_count, vectorized_at,
                         embedding_model, embedding_provider.

    \b
    Examples:
      lutz vector-store --summarize
      lutz vector-store --sections
      lutz vector-store --summarize --sections
      lutz vector-store --export
      lutz vector-store --export summary.json
      lutz vector-store --export -
      lutz vector-store --summarize --export summary.json
    """
    if not summarize and not sections and export_path is None:
        console.print(
            "Use [bold]lutz vector-store --summarize[/] to display store details,\n"
            "    [bold]lutz vector-store --sections[/] to inspect section breakdown, or\n"
            "    [bold]lutz vector-store --export[/] to save a JSON summary."
        )
        return

    project_root = require_project_root()
    db_path = project_root / ".lutz" / "vector_store"
    store = VectorStore(db_path)
    info = store.summarize()

    if info["total_records"] == 0:
        console.print(
            "[yellow]Vector store is empty.[/] "
            "Run [bold]lutz vectorize[/] to index your articles."
        )
        return

    db_size_mb = _dir_size_mb(db_path) if db_path.exists() else 0.0

    # --summarize: print to terminal
    if summarize:
        console.print(
            Panel.fit(
                f"[bold cyan]Vector Store Summary[/]\n\n"
                f"Total chunks:      [cyan]{info['total_records']:,}[/]\n"
                f"Total articles:    [cyan]{info['unique_documents']}[/]\n"
                f"Last updated:      [dim]{info['last_updated']}[/]\n"
                f"Embedding model:   [cyan]{info['embedding_model']}[/] "
                f"[dim]({info['embedding_provider']})[/]\n"
                f"DB path:           [dim]{db_path.relative_to(project_root)}[/]\n"
                f"DB size on disk:   [cyan]{db_size_mb:.1f} MB[/]",
                border_style="cyan",
            )
        )

        table = Table(
            title="Articles in store",
            show_lines=False,
            header_style="bold cyan",
        )
        table.add_column("Article", style="dim", no_wrap=False)
        table.add_column("Chunks", justify="right")
        table.add_column("Vectorized at", justify="left", style="dim")

        for article in info["articles"]:
            table.add_row(
                article["filename"],
                str(article["chunk_count"]),
                article["vectorized_at"],
            )

        console.print(table)

    # --sections: section breakdown per article
    if sections:
        breakdown = store.section_breakdown()

        if not breakdown:
            console.print("[yellow]No section data found.[/]")
        else:
            # Collect all distinct section names across all articles, sorted
            all_sections: list[str] = sorted(
                {s for counts in breakdown.values() for s in counts if s},
                key=lambda s: [
                    "abstract", "introduction", "background", "methodology",
                    "results", "discussion", "conclusion", "references",
                    "acknowledgements", "appendix",
                ].index(s) if s in [
                    "abstract", "introduction", "background", "methodology",
                    "results", "discussion", "conclusion", "references",
                    "acknowledgements", "appendix",
                ] else 99,
            )
            has_unlabeled = any("" in counts for counts in breakdown.values())

            sec_table = Table(
                title="Section breakdown",
                show_lines=True,
                header_style="bold cyan",
            )
            sec_table.add_column("Article", style="dim", no_wrap=False, min_width=20)
            for sec in all_sections:
                sec_table.add_column(sec, justify="right")
            if has_unlabeled:
                sec_table.add_column("(no section)", justify="right", style="dim")

            for filename in sorted(breakdown.keys()):
                counts = breakdown[filename]
                row = [filename]
                for sec in all_sections:
                    n = counts.get(sec, 0)
                    row.append(str(n) if n else "[dim]—[/]")
                if has_unlabeled:
                    n = counts.get("", 0)
                    row.append(str(n) if n else "[dim]—[/]")
                sec_table.add_row(*row)

            console.print(sec_table)

            if has_unlabeled:
                console.print(
                    "[dim]Articles under '(no section)' were vectorized without "
                    "--section-parse. Re-run 'lutz unvectorize' then "
                    "'lutz vectorize --section-parse' to add section labels.[/]"
                )

    # --export: write JSON
    if export_path is not None:
        payload = _build_payload(info, db_path, project_root, db_size_mb)
        json_text = json.dumps(payload, ensure_ascii=False, indent=2)

        if export_path == "-":
            console.print(json_text)
            return

        if export_path == "":
            # bare --export: auto-generate path
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            resolved = project_root / ".lutz" / f"vector_store_export_{timestamp}.json"
        else:
            resolved = Path(export_path)
            if not resolved.is_absolute():
                resolved = project_root / resolved

        resolved.write_text(json_text, encoding="utf-8")
        console.print(
            f"[green]✓[/] Exported to [cyan]{resolved.relative_to(project_root)}[/] "
            f"({info['unique_documents']} articles, {info['total_records']:,} chunks)."
        )
