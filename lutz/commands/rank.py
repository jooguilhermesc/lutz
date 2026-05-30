"""lutz rank — rank articles by relevance to a research question."""

from __future__ import annotations

import csv
import io
import json

import click
from rich.console import Console
from rich.table import Table

from lutz.core.embedding_client import EmbeddingClient
from lutz.core.vector_store import VectorStore
from lutz.utils.project import load_env, require_project_root
from lutz.utils.ranking import rank_articles_by_relevance

console = Console()


@click.command()
@click.option(
    "--question",
    required=True,
    metavar="TEXT",
    help="Research question to rank articles against.",
)
@click.option(
    "--aggregation",
    default="mean",
    show_default=True,
    type=click.Choice(["mean", "max"]),
    help=(
        "How to aggregate chunk-level cosine similarities into an article score. "
        "'mean' averages all chunk similarities; 'max' takes the best-matching chunk."
    ),
)
@click.option(
    "--filter-sections",
    default=None,
    metavar="SECTIONS",
    help=(
        "Comma-separated list of section names to consider when scoring. "
        "Only chunks whose section label matches are used. "
        "Example: --filter-sections abstract,introduction"
    ),
)
@click.option(
    "--top",
    "top_n",
    default=None,
    type=click.IntRange(1),
    help="Show only the top N articles. Default: show all.",
)
@click.option(
    "--format",
    "output_format",
    default="table",
    show_default=True,
    type=click.Choice(["table", "json", "csv"]),
    help="Output format.",
)
def rank(
    question: str,
    aggregation: str,
    filter_sections: str | None,
    top_n: int | None,
    output_format: str,
) -> None:
    """Rank vectorised articles by cosine similarity to a research question.

    \b
    The question is embedded with the same model used for the corpus.
    Scores are cosine similarities in [-1, 1] — higher means more relevant.
    No LLM is involved; ranking is purely embedding-based.

    \b
    Examples:
      lutz rank --question "machine learning for medical diagnosis"
      lutz rank --question "climate change adaptation" --aggregation max --top 10
      lutz rank --question "deep learning" --filter-sections abstract,introduction
      lutz rank --question "neural networks" --format json
      lutz rank --question "NLP survey" --format csv > ranking.csv
    """
    question = question.strip()
    if not question:
        raise click.UsageError("--question must not be empty.")

    env = load_env()
    project_root = require_project_root()

    section_filter: list[str] | None = None
    if filter_sections:
        section_filter = [s.strip() for s in filter_sections.split(",") if s.strip()]

    store = VectorStore(project_root / ".lutz" / "vector_store")
    store_info = store.info()

    if store_info["total_records"] == 0:
        console.print(
            "[bold red]Error:[/] vector store is empty.\n"
            "Run [bold]lutz vectorize[/] first."
        )
        raise click.Abort()

    # Embed the question
    embedding_client = EmbeddingClient.from_env(env)

    # Warn if embedding model might differ from corpus model
    corpus_model = store_info.get("embedding_model") or ""
    if corpus_model and corpus_model != embedding_client.model_id:
        console.print(
            f"[bold yellow]Warning:[/] Corpus was embedded with '{corpus_model}' but "
            f"current EMBEDDING_MODEL is '{embedding_client.model_id}'. "
            "Scores may not be comparable. Set EMBEDDING_MODEL in your .env to match.",
            err=True,
        )

    query_embeddings, _ = embedding_client.embed([question])
    question_embedding = __import__("numpy").array(query_embeddings[0], dtype="float32")

    # Retrieve chunk embeddings grouped by article
    article_chunk_embeddings = store.get_chunk_embeddings_by_article(sections=section_filter)

    if not article_chunk_embeddings:
        console.print(
            "[bold red]Error:[/] No articles found in vector store"
            + (f" for sections {section_filter}." if section_filter else "."),
        )
        raise click.Abort()

    # Rank
    results = rank_articles_by_relevance(article_chunk_embeddings, question_embedding, aggregation)

    if top_n is not None:
        results = results[:top_n]

    sections_label = ",".join(section_filter) if section_filter else "all"

    # ---- Output ----------------------------------------------------------------
    if output_format == "json":
        payload = [
            {
                "rank": i + 1,
                "filename": r["filename"],
                "score": round(r["score"], 6),
                "chunks_used": r["chunks_used"],
            }
            for i, r in enumerate(results)
        ]
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))

    elif output_format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["rank", "filename", "score", "chunks_used"])
        for i, r in enumerate(results):
            writer.writerow([i + 1, r["filename"], round(r["score"], 6), r["chunks_used"]])
        click.echo(buf.getvalue().rstrip())

    else:
        # table (default)
        table = Table(show_header=True, header_style="bold cyan", show_lines=False)
        table.add_column("Rank", justify="right", style="bold", width=6)
        table.add_column("Filename", no_wrap=False)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Sections used")
        for i, r in enumerate(results):
            table.add_row(
                str(i + 1),
                r["filename"],
                f"{r['score']:.4f}",
                sections_label,
            )
        console.print(table)

    n_total = len(results)
    summary = f"\nRanked {n_total} articles. Cutoff decision is yours — no automatic exclusions."
    if output_format in ("json", "csv"):
        # Machine-readable formats: summary goes to stderr to keep stdout parseable
        click.echo(summary, err=True)
    else:
        console.print(summary)
