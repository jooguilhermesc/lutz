"""CLI command: lutz query — execute SQL queries against the vector store."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

console = Console()

_VS_COLUMNS = [
    "filename", "chunk_index", "page", "section", "text",
    "vectorized_at", "embedding_model", "embedding_provider",
]


@click.command()
@click.argument("sql")
@click.option(
    "--include-embeddings", "-e",
    is_flag=True,
    default=False,
    help="Expose the embedding column in the query.",
)
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--db",
    default=None,
    metavar="PATH",
    help="Path to a specific LanceDB vector store (default: <project>/.lutz/vector_store).",
)
@click.option(
    "--limit", "-n",
    default=None,
    type=int,
    metavar="N",
    help="Append LIMIT N to the query (convenience shortcut).",
)
def query(sql: str, include_embeddings: bool, fmt: str, db: str | None, limit: int | None) -> None:
    """Execute a SQL query against the vector store.

    The table is always named ``vectors``.

    Pass --include-embeddings (-e) to expose the raw embedding column.

    \b
    Examples:

      # Count chunks per section
      lutz query "SELECT section, COUNT(*) AS n FROM vectors GROUP BY section"

      # Inspect embeddings
      lutz query -e "SELECT filename, embedding FROM vectors LIMIT 5"
    """
    import duckdb
    from pathlib import Path
    import pyarrow as pa
    from lutz.core.vector_store import VectorStore
    from lutz.utils.project import require_project_root

    root = require_project_root()
    store_path = Path(db) if db else root / ".lutz" / "vector_store"

    vs = VectorStore(store_path)
    if "articles" not in vs._db.list_tables().tables:
        raise click.ClickException(
            "Vector store is empty — run [bold]lutz vectorize[/bold] first."
        )

    tbl = vs._db.open_table("articles")
    arrow_tbl = tbl.to_arrow()
    available = set(arrow_tbl.schema.names)

    cols = [c for c in _VS_COLUMNS if c in available]

    if include_embeddings and "embedding" in available:
        emb_col = arrow_tbl.column("embedding")
        emb_f64 = emb_col.cast(pa.list_(pa.float64()))
        emb_idx = arrow_tbl.schema.get_field_index("embedding")
        arrow_tbl = (
            arrow_tbl
            .remove_column(emb_idx)
            .append_column(pa.field("embedding", pa.list_(pa.float64())), emb_f64)
        )
        cols = cols + ["embedding"]

    arrow_tbl = arrow_tbl.select(cols)

    effective_sql = sql.rstrip("; ")
    if limit is not None:
        effective_sql = f"SELECT * FROM ({effective_sql}) __q LIMIT {limit}"

    con = duckdb.connect()
    con.register("vectors", arrow_tbl)

    try:
        df = con.execute(effective_sql).fetchdf()
    except Exception as exc:
        raise click.ClickException(str(exc))

    if fmt == "json":
        click.echo(df.to_json(orient="records", indent=2, default_handler=str))
        return

    if fmt == "csv":
        click.echo(df.to_csv(index=False))
        return

    # Rich table
    rich_table = Table(show_header=True, header_style="bold magenta")
    for col in df.columns:
        rich_table.add_column(col, overflow="fold", max_width=60)
    for row in df.itertuples(index=False):
        rich_table.add_row(*[_fmt_cell(v) for v in row])
    console.print(rich_table)
    console.print(f"[dim]{len(df)} row{'s' if len(df) != 1 else ''}[/dim]")


def _fmt_cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        preview = ", ".join(f"{x:.4f}" if isinstance(x, float) else str(x) for x in v[:4])
        suffix = ", …" if len(v) > 4 else ""
        return f"[{preview}{suffix}]"
    return str(v)
