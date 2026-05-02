"""lutz analysis — run an LLM-based analysis over vectorised articles."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from lutz.utils.project import require_project_root, load_env
from lutz.core.vector_store import VectorStore
from lutz.core.llm_client import LLMClient
from lutz.core.embedding_client import EmbeddingClient

console = Console()

_SYSTEM_PROMPT = (
    "You are an expert academic researcher performing a systematic literature review. "
    "Your task is to analyse the provided article excerpts and produce a structured, "
    "evidence-based response following the researcher's instructions. "
    "Always cite the source article filename when referencing specific content. "
    "Be objective, concise, and academically rigorous."
)


class _TopKType(click.ParamType):
    """Click type that accepts a positive integer or '*' (meaning all chunks)."""

    name = "top_k"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        if str(value).strip() == "*":
            return None  # None signals "retrieve everything"
        try:
            n = int(value)
            if n <= 0:
                self.fail(f"top-k must be a positive integer or '*'.", param, ctx)
            return n
        except (ValueError, TypeError):
            self.fail(
                f"'{value}' is not valid. Use a positive integer or '*' to retrieve all chunks.",
                param,
                ctx,
            )


_TOP_K_TYPE = _TopKType()


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"--- Excerpt {i} (from: {chunk['filename']}, page {chunk.get('page', '?')}) ---\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(parts)


def _user_message(prompt_content: str, context: str) -> str:
    return (
        f"## Researcher Instructions\n\n{prompt_content}\n\n"
        f"## Article Excerpts\n\n{context}\n\n"
        f"## Your Analysis\n\n"
        f"Based on the excerpts above, provide a detailed response following the instructions."
    )


@click.command()
@click.option(
    "--p", "prompt_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Path to the Markdown (.md) prompt file that instructs the LLM. "
        "The file content becomes the researcher instructions section of the LLM request. "
        "Use the templates in prompts/ created by 'lutz init' as a starting point."
    ),
)
@click.option(
    "--top-k",
    default=10,
    show_default=True,
    type=_TOP_K_TYPE,
    help=(
        "RAG mode only. Number of most-relevant chunks to retrieve from the vector store. "
        "Chunks are ranked by cosine similarity to the embedded prompt. "
        "Use '*' (quoted in shell: --top-k '*') to retrieve every chunk in the store, "
        "ranked by relevance. Large values may exceed the model's context window."
    ),
)
@click.option(
    "--per-article",
    is_flag=True,
    default=False,
    help=(
        "Switch to per-article mode: one LLM call per article in the vector store. "
        "Each article's chunks are fetched directly (no embedding or similarity search). "
        "Produces one analysis entry per article in the output JSON. "
        "Recommended for systematic inclusion/exclusion screening. "
        "Ignores --top-k."
    ),
)
@click.option(
    "--workers",
    default=1,
    show_default=True,
    type=click.IntRange(1, 32),
    help=(
        "Per-article mode only. Number of concurrent LLM calls (ThreadPoolExecutor). "
        "Effective for remote APIs (OpenAI, Anthropic, OpenRouter) where the bottleneck "
        "is network I/O. For local models (Docker Model Runner), keep at 1 — requests "
        "queue on the GPU anyway. Increase carefully to avoid API rate-limit errors (429)."
    ),
)
@click.option(
    "--max-chunks-per-article",
    default=None,
    type=click.IntRange(1),
    help=(
        "Per-article mode only. Maximum number of chunks sent to the LLM per article. "
        "Chunks are taken from the beginning of the document (document order). "
        "Use this to cap context size when articles exceed the model's context window. "
        "Example: --max-chunks-per-article 10 sends at most 10 × 512 words ≈ 7 000 LLM tokens. "
        "Default: no limit (all chunks for the article are sent)."
    ),
)
@click.option(
    "--output-name", default=None,
    help=(
        "Custom base name for the output JSON file saved in analysis/execution_reports/. "
        "Default: <prompt_stem>_<YYYYMMDD_HHMMSS>.json."
    ),
)
def analysis(
    prompt_path: Path,
    top_k: int | None,
    per_article: bool,
    workers: int,
    max_chunks_per_article: int | None,
    output_name: str | None,
) -> None:
    """Analyse vectorised articles using a Markdown prompt.

    \b
    RAG mode (default)
      Embeds the prompt into a vector, searches the store for the top-k most
      similar chunks, and sends them all in a single LLM call. Best for open-ended
      synthesis questions where the most relevant passages are unknown in advance.

      Context window estimate:
        top-k=10 chunks × 512 words × 1.33 ≈ 6 800 LLM tokens of article text,
        plus system prompt (~60 tokens) and researcher prompt (variable).

    \b
    Per-article mode (--per-article)
      Fetches all chunks for each article from the vector store (no embedding step)
      and makes one LLM call per article. Best for systematic screening where you
      need an inclusion/exclusion decision for every article.

      Context window estimate per call:
        ~23 chunks (corpus average) × 512 words × 1.33 ≈ 15 700 LLM tokens.
        Use --max-chunks-per-article to cap this for models with smaller windows.

      Performance tip:
        --workers 4 cuts runtime from ~43 min to ~11 min for 52 articles at 50 s/call.
        The vector store is read once (bulk load) before workers start.

    \b
    Output
      A single JSON file in analysis/execution_reports/ containing metadata
      (mode, prompt, timestamps, token counts) and the analysis body.
      The per-article JSON output can be fed directly to 'lutz citations'.

    \b
    Examples:
      lutz analysis --p prompts/systematic_review.md
      lutz analysis --p prompts/screening.md --top-k 25
      lutz analysis --p prompts/screening.md --top-k '*'
      lutz analysis --p prompts/screening.md --per-article
      lutz analysis --p prompts/screening.md --per-article --workers 4
      lutz analysis --p prompts/screening.md --per-article --workers 4 --max-chunks-per-article 10
      lutz analysis --p prompts/screening.md --output-name screening_pilot_v1
    """
    env = load_env()
    project_root = require_project_root()

    reports_dir = project_root / "analysis" / "execution_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    prompt_content = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_content:
        console.print("[bold red]Error:[/] prompt file is empty.")
        raise click.Abort()

    mode = "per_article" if per_article else "rag"
    top_k_display = "*" if (not per_article and top_k is None) else (top_k if not per_article else "—")

    panel_lines = [
        f"[bold cyan]Analysis run[/]",
        f"Prompt:  [dim]{prompt_path}[/]",
        f"Mode:    {mode}",
    ]
    if not per_article:
        panel_lines.append(f"Top-K:   {top_k_display}")
    else:
        panel_lines.append(f"Workers: {workers}")
        if max_chunks_per_article:
            panel_lines.append(f"Max chunks/article: {max_chunks_per_article}")

    console.print(Panel.fit("\n".join(panel_lines), border_style="cyan"))

    store = VectorStore(project_root / ".lutz" / "vector_store")
    store_info = store.info()

    if store_info["total_records"] == 0:
        console.print(
            "[bold red]Error:[/] vector store is empty.\n"
            "Run [bold]lutz vectorize[/] first."
        )
        raise click.Abort()

    console.print(
        f"Vector store: [cyan]{store_info['total_records']}[/] chunks from "
        f"[cyan]{store_info['unique_documents']}[/] article(s).\n"
    )

    embedding_client = EmbeddingClient.from_env(env)
    llm_client = LLMClient.from_env(env)

    started_at = datetime.now(timezone.utc)
    start_ts = time.time()

    if per_article:
        output = _run_per_article(
            store, llm_client, prompt_content, store_info,
            embedding_client, workers, max_chunks_per_article,
        )
    else:
        output = _run_rag(
            store, llm_client, embedding_client, prompt_content,
            top_k, store_info,
        )

    finished_at = datetime.now(timezone.utc)
    elapsed_seconds = round(time.time() - start_ts, 2)

    console.print(f"[green]✓[/] Analysis complete in {elapsed_seconds:.1f}s.\n")

    # ---- assemble final JSON -----------------------------------------------
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    base_name = output_name or f"{prompt_path.stem}_{timestamp}"
    report_path = reports_dir / f"{base_name}.json"

    report = {
        "metadata": {
            "mode": mode,
            "prompt_path": str(prompt_path),
            "prompt_content": prompt_content,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "vector_store": {
                "total_records": store_info["total_records"],
                "unique_documents": store_info["unique_documents"],
                "last_updated": store_info.get("last_updated"),
            },
            **output["metadata"],
        },
        **output["body"],
    }

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---- summary panel -------------------------------------------------------
    llm_meta = report["metadata"]["llm"]
    embed_meta = report["metadata"]["embedding"]

    if per_article:
        articles_covered = len(output["body"].get("articles", []))
        extra = f"Articles covered: [cyan]{articles_covered}[/]"
    else:
        articles_covered = len(output["body"].get("articles_covered", []))
        chunks = output["body"].get("chunks_retrieved", 0)
        extra = (
            f"Articles covered: [cyan]{articles_covered}[/]\n"
            f"Chunks retrieved: [cyan]{chunks}[/]"
        )

    console.print(
        Panel.fit(
            f"[bold green]Report saved![/]\n\n"
            f"{report_path.relative_to(project_root)}\n\n"
            f"{extra}\n"
            f"LLM model:        [cyan]{llm_client.model_id}[/]\n"
            f"LLM tokens:       [cyan]{llm_meta['total_tokens']:,}[/] "
            f"(prompt {llm_meta['prompt_tokens']:,} + completion {llm_meta['completion_tokens']:,})\n"
            f"Embed tokens:     [cyan]{embed_meta['tokens']:,}[/] "
            f"[dim]({'estimated' if embedding_client.provider == 'sentence_transformers' else 'API-reported'})[/]\n"
            f"Duration:         [cyan]{elapsed_seconds:.1f}s[/]",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# RAG mode
# ---------------------------------------------------------------------------

def _run_rag(
    store: VectorStore,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    prompt_content: str,
    top_k: int | None,
    store_info: dict,
) -> dict:
    console.print("[bold]Step 1/2 — Retrieving relevant context[/]")
    with Progress(SpinnerColumn(), TextColumn("Embedding prompt..."), console=console, transient=True) as p:
        p.add_task("", total=None)
        query_embeddings, embed_tokens = embedding_client.embed([prompt_content])

    query_embedding = query_embeddings[0]
    chunks = store.search(query_embedding, top_k=top_k)
    unique_docs = sorted({c["filename"] for c in chunks})

    top_k_label = "*" if top_k is None else top_k
    console.print(
        f"[green]✓[/] Retrieved {len(chunks)} chunk(s) from {len(unique_docs)} article(s) "
        f"(top-k={top_k_label}).\n"
    )

    context = _build_context(chunks)
    user_msg = _user_message(prompt_content, context)

    console.print("[bold]Step 2/2 — Running LLM analysis[/]")
    with Progress(SpinnerColumn(), TextColumn("Analysing with LLM..."), console=console, transient=True) as p:
        p.add_task("", total=None)
        llm_text, llm_usage = llm_client.complete(system=_SYSTEM_PROMPT, user=user_msg)

    return {
        "metadata": {
            "top_k": top_k_label,
            "embedding": {
                "provider": embedding_client.provider,
                "model": embedding_client.model_id,
                "tokens": embed_tokens,
            },
            "llm": {
                "provider": llm_client.provider,
                "model": llm_client.model_id,
                **llm_usage,
            },
        },
        "body": {
            "articles_covered": unique_docs,
            "chunks_retrieved": len(chunks),
            "analysis": llm_text,
        },
    }


# ---------------------------------------------------------------------------
# Per-article mode
# ---------------------------------------------------------------------------

def _run_per_article(
    store: VectorStore,
    llm_client: LLMClient,
    prompt_content: str,
    store_info: dict,
    embedding_client: EmbeddingClient,
    workers: int,
    max_chunks: int | None,
) -> dict:
    # Single bulk read — avoids N full table scans
    console.print("[dim]Loading vector store into memory...[/]")
    all_chunks = store.get_all_grouped()
    filenames = sorted(all_chunks.keys())

    if not filenames:
        console.print("[bold red]No articles found in vector store.[/]")
        raise click.Abort()

    console.print(
        f"[bold]Per-article analysis — {len(filenames)} article(s)"
        f"{f', {workers} workers' if workers > 1 else ''}[/]\n"
    )

    def _analyse_one(filename: str) -> dict:
        chunks = all_chunks[filename]
        if max_chunks:
            chunks = chunks[:max_chunks]

        if not chunks:
            return {
                "filename": filename,
                "chunks_used": 0,
                "llm_prompt_tokens": 0,
                "llm_completion_tokens": 0,
                "llm_total_tokens": 0,
                "analysis": None,
                "error": "No chunks found in store.",
            }

        context = _build_context(chunks)
        user_msg = _user_message(prompt_content, context)
        llm_text, llm_usage = llm_client.complete(system=_SYSTEM_PROMPT, user=user_msg)

        return {
            "filename": filename,
            "chunks_used": len(chunks),
            "llm_prompt_tokens": llm_usage["prompt_tokens"],
            "llm_completion_tokens": llm_usage["completion_tokens"],
            "llm_total_tokens": llm_usage["total_tokens"],
            "analysis": llm_text,
        }

    results_map: dict[str, dict] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]0/{len(filenames)}[/] articles done", total=len(filenames)
        )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_analyse_one, fn): fn for fn in filenames}
            for future in as_completed(futures):
                filename = futures[future]
                try:
                    results_map[filename] = future.result()
                except Exception as exc:
                    results_map[filename] = {
                        "filename": filename,
                        "chunks_used": 0,
                        "llm_prompt_tokens": 0,
                        "llm_completion_tokens": 0,
                        "llm_total_tokens": 0,
                        "analysis": None,
                        "error": str(exc),
                    }
                done = len(results_map)
                progress.update(
                    task,
                    advance=1,
                    description=f"[cyan]{done}/{len(filenames)}[/] articles done",
                )

    # Preserve sorted order in output
    articles_results = [results_map[fn] for fn in filenames]

    total_prompt_tokens = sum(r["llm_prompt_tokens"] for r in articles_results)
    total_completion_tokens = sum(r["llm_completion_tokens"] for r in articles_results)

    # Summary table
    table = Table(title="Per-article results", show_lines=False, header_style="bold cyan")
    table.add_column("Article", style="dim", no_wrap=False)
    table.add_column("Chunks", justify="right")
    table.add_column("LLM tokens", justify="right")
    table.add_column("Status")
    for r in articles_results:
        if r.get("error"):
            status = f"[red]✗ {r['error']}[/]"
        else:
            status = "[green]✓[/]"
        table.add_row(
            r["filename"],
            str(r["chunks_used"]),
            f"{r['llm_total_tokens']:,}",
            status,
        )
    console.print(table)
    console.print()

    return {
        "metadata": {
            "workers": workers,
            "max_chunks_per_article": max_chunks,
            "embedding": {
                "provider": embedding_client.provider,
                "model": embedding_client.model_id,
                "tokens": 0,  # no embedding needed in per-article mode
            },
            "llm": {
                "provider": llm_client.provider,
                "model": llm_client.model_id,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
            },
        },
        "body": {
            "articles": articles_results,
        },
    }
