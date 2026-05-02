"""lutz vectorize / lutz unvectorize — manage the local vector store."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

from lutz.utils.project import require_project_root, load_env
from lutz.utils.pdf import is_valid_pdf
from lutz.core.security_checker import SecurityChecker, SecurityReport, detect_corpus_anomalies
from lutz.core.pdf_processor import PDFProcessor
from lutz.core.vector_store import VectorStore
from lutz.core.embedding_client import EmbeddingClient

console = Console()


@click.command()
@click.option(
    "--skip-security/--no-skip-security",
    default=False,
    show_default=True,
    help=(
        "Skip all security checks and index every PDF in articles/ directly. "
        "Not recommended unless you fully trust the source of your PDFs."
    ),
)
@click.option(
    "--chunk-size", default=512, show_default=True,
    help=(
        "Sliding-window size in words (not LLM tokens). "
        "512 words ≈ 680 LLM tokens. "
        "Smaller values increase retrieval granularity but raise chunk count and embedding cost."
    ),
)
@click.option(
    "--chunk-overlap", default=64, show_default=True,
    help=(
        "Number of words shared between consecutive chunks. "
        "Overlap preserves context at chunk boundaries. "
        "Must be smaller than --chunk-size."
    ),
)
@click.option(
    "--quarantine",
    is_flag=True,
    default=False,
    help=(
        "Process PDFs from articles/_quarantine/ instead of articles/. "
        "The security scan is skipped — use only after manually reviewing the quarantined files."
    ),
)
def vectorize(skip_security: bool, chunk_size: int, chunk_overlap: int, quarantine: bool) -> None:
    """Index PDF articles into the local vector database (.lutz/vector_store/).

    \b
    Workflow (normal mode):
      1. Security scan  — structural PDF analysis, prompt-injection detection,
                          academic-structure validation, and corpus-level anomaly
                          detection (IsolationForest, applied when >= 5 PDFs).
         Suspicious files are moved to articles/_quarantine/ and excluded.
      2. Text extraction — pdfplumber (primary), pypdf (fallback).
      3. Chunking        — sliding window over words (not LLM tokens).
                          chunk-size=512 words ≈ 680 LLM tokens.
      4. Embedding       — one embedding API call per article; provider and model
                          are read from .env (EMBEDDING_PROVIDER, EMBEDDING_MODEL).
      5. Storage         — chunks are upserted into LanceDB.

    \b
    Quarantine mode (--quarantine):
      Targets articles/_quarantine/ instead of articles/.
      The security scan is skipped because the researcher is explicitly choosing
      to include these files after manual review.
      Run 'lutz vector-store --summarize' afterwards to confirm indexing.

    \b
    Chunk size and overlap:
      Both --chunk-size and --chunk-overlap are measured in words (whitespace-
      split tokens), not in LLM tokens. A chunk of 512 words is approximately
      680 LLM tokens for English text (ratio ≈ 1.33).
      Reducing chunk-size increases retrieval granularity but raises the total
      number of chunks and embedding cost.

    \b
    Re-running vectorize appends new chunks; it does not deduplicate.
    Use 'lutz unvectorize' first if you want to rebuild the index from scratch.

    \b
    Examples:
      lutz vectorize
      lutz vectorize --skip-security
      lutz vectorize --chunk-size 256 --chunk-overlap 32
      lutz vectorize --quarantine
    """
    env = load_env()
    project_root = require_project_root()
    articles_dir = project_root / "articles"

    if quarantine:
        source_dir = articles_dir / "_quarantine"
        if not source_dir.exists():
            console.print("[yellow]No quarantine directory found at articles/_quarantine/.[/]")
            return
        console.print(
            f"[bold yellow]Quarantine mode:[/] processing files from "
            f"[dim]articles/_quarantine/[/] (security check skipped).\n"
        )
        skip_security = True
    else:
        source_dir = articles_dir

    pdf_files = [
        p for p in source_dir.glob("*.pdf")
        if p.name != ".gitkeep" and is_valid_pdf(p)
    ]
    pdf_files += [
        p for p in source_dir.glob("*.PDF")
        if p.name != ".gitkeep" and is_valid_pdf(p)
    ]

    if not pdf_files:
        console.print(f"[yellow]No valid PDF files found in {source_dir.relative_to(project_root)}/.[/]")
        console.print("Add PDFs with [bold]lutz load[/] or copy them manually to [dim]articles/[/].")
        return

    console.print(f"Found [bold cyan]{len(pdf_files)}[/] PDF(s) to process.\n")

    # ------------------------------------------------------------------
    # Security phase
    # ------------------------------------------------------------------
    approved: list[Path] = []

    if skip_security:
        if not quarantine:
            console.print("[yellow]Warning:[/] security check skipped.\n")
        approved = pdf_files
    else:
        console.print("[bold]Phase 1/3 — Security scan[/]")
        checker = SecurityChecker()
        quarantine_dir = articles_dir / "_quarantine"

        reports: list[SecurityReport] = []
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"),
            BarColumn(), TaskProgressColumn(), console=console,
        ) as progress:
            task = progress.add_task("Scanning PDFs...", total=len(pdf_files))
            for pdf in pdf_files:
                report = checker.check(pdf)
                reports.append(report)
                progress.advance(task)

        # Corpus-level anomaly detection (applied when >= 5 docs)
        reports = detect_corpus_anomalies(reports)

        safe = [r for r in reports if r.is_safe]
        flagged = [r for r in reports if not r.is_safe]

        if flagged:
            quarantine_dir.mkdir(exist_ok=True)
            console.print(
                f"\n[bold red]Security alert![/] "
                f"{len(flagged)} file(s) flagged and moved to [dim]articles/_quarantine/[/]:\n"
            )
            for rep in flagged:
                import shutil
                dest = quarantine_dir / rep.path.name
                shutil.move(str(rep.path), str(dest))
                console.print(f"  [red]quarantined[/] {rep.path.name}")
                for reason in rep.reasons:
                    console.print(f"    [dim]→ {reason}[/]")
        else:
            console.print(f"[green]✓[/] All {len(safe)} file(s) passed the security scan.\n")

        approved = [r.path for r in safe]

    if not approved:
        console.print("[bold red]No files remain after security check.[/] Aborting.")
        return

    # ------------------------------------------------------------------
    # Extraction phase
    # ------------------------------------------------------------------
    console.print("[bold]Phase 2/3 — Text extraction[/]")
    processor = PDFProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks_by_file: dict[str, list[dict]] = {}

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console,
    ) as progress:
        task = progress.add_task("Extracting text...", total=len(approved))
        for pdf in approved:
            chunks = processor.extract_chunks(pdf)
            chunks_by_file[pdf.stem] = chunks
            progress.advance(task)

    total_chunks = sum(len(c) for c in chunks_by_file.values())
    console.print(f"[green]✓[/] Extracted {total_chunks} chunk(s) from {len(approved)} file(s).\n")

    # ------------------------------------------------------------------
    # Embedding + storage phase
    # ------------------------------------------------------------------
    console.print("[bold]Phase 3/3 — Embedding and indexing[/]")
    embedding_client = EmbeddingClient.from_env(env)
    vector_store = VectorStore(project_root / ".lutz" / "vector_store")

    vectorized_at = datetime.now(timezone.utc).isoformat()
    all_records: list[dict] = []
    total_embedding_tokens = 0

    for filename, chunks in chunks_by_file.items():
        texts = [c["text"] for c in chunks]
        with Progress(
            SpinnerColumn(), TextColumn(f"Embedding [cyan]{filename}[/]..."),
            console=console, transient=True,
        ) as progress:
            progress.add_task("", total=None)
            embeddings, embed_tokens = embedding_client.embed(texts)

        total_embedding_tokens += embed_tokens

        for chunk, embedding in zip(chunks, embeddings):
            all_records.append({
                **chunk,
                "filename": filename,
                "embedding": embedding,
                "vectorized_at": vectorized_at,
                "embedding_model": embedding_client.model_id,
                "embedding_provider": embedding_client.provider,
            })

    vector_store.upsert(all_records)

    console.print(
        Panel.fit(
            f"[bold green]Vectorization complete![/]\n\n"
            f"Articles indexed:  [cyan]{len(approved)}[/]\n"
            f"Total chunks:      [cyan]{total_chunks}[/]\n"
            f"Embedding model:   [cyan]{embedding_client.model_id}[/]\n"
            f"Embedding tokens:  [cyan]{total_embedding_tokens:,}[/]\n"
            f"Timestamp:         [dim]{vectorized_at}[/]",
            border_style="green",
        )
    )
    console.print("Run [bold]lutz analysis --p prompts/<your_prompt>.md[/] to start analysing.")


# ---------------------------------------------------------------------------


@click.command()
@click.confirmation_option(
    prompt="This will delete all vectorised data. Are you sure?"
)
def unvectorize() -> None:
    """Delete all records from the local vector database.

    \b
    This removes every chunk stored in .lutz/vector_store/ but does NOT
    touch your PDF files in articles/. Use this command when you want to
    rebuild the index from scratch — for example after changing the embedding
    model or chunk size, which would otherwise mix incompatible vectors in
    the same store.

    \b
    After unvectorize, run 'lutz vectorize' to rebuild the index.
    """
    project_root = require_project_root()
    store = VectorStore(project_root / ".lutz" / "vector_store")
    deleted = store.drop_all()
    console.print(f"[bold green]Done.[/] Removed {deleted} record(s) from the vector store.")
