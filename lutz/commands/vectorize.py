"""lutz vectorize / lutz unvectorize — manage the local vector store."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

from lutz.utils.project import require_project_root, load_env
from lutz.utils.pdf import is_valid_pdf
from lutz.core.security_checker import SecurityChecker, SecurityReport, detect_corpus_anomalies
from lutz.core.extraction import (
    ExtractionStrategy,
    PyMuPDFStrategy,
    MarkerStrategy,
    get_strategy,
    is_sparse,
)
from lutz.core.pdf_processor import PDFProcessor
from lutz.core.vector_store import VectorStore
from lutz.core.embedding_client import EmbeddingClient
from lutz.core.section_parser import SectionParser

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
@click.option(
    "--section-parse/--no-section-parse",
    default=False,
    show_default=True,
    help=(
        "Split each article into sections (abstract, introduction, methodology, …) "
        "before chunking.  Each chunk is annotated with its section name so the LLM "
        "receives richer context.  Chunks never cross section boundaries. "
        "When --extraction marker is active, sections are parsed directly from the "
        "Markdown headings output by marker, bypassing layoutparser entirely."
    ),
)
@click.option(
    "--layout-parse/--no-layout-parse",
    default=True,
    show_default=True,
    help=(
        "When --section-parse is active, attempt to use layout-parser for visual "
        "layout detection of section headers (requires 'lutz-research[layout]'). "
        "If layout-parser is not installed the flag is ignored and text heuristics "
        "are used instead.  Has no effect without --section-parse. "
        "Ignored when --extraction marker is active."
    ),
)
@click.option(
    "--extraction",
    type=click.Choice(["pymupdf", "marker", "auto"], case_sensitive=False),
    default=None,
    show_default=False,
    metavar="BACKEND",
    help=(
        "PDF text extraction backend.  "
        "pymupdf (default): fast, no extra deps, works only on PDFs with text layers.  "
        "marker: OCR + multi-column layout detection via marker-pdf "
        "(requires pip install 'lutz-research[marker]').  "
        "auto: tries pymupdf first; switches to marker automatically for scanned PDFs "
        "(emits a warning if marker is not installed)."
    ),
)
def vectorize(
    skip_security: bool,
    chunk_size: int,
    chunk_overlap: int,
    quarantine: bool,
    section_parse: bool,
    layout_parse: bool,
    extraction: str | None,
) -> None:
    """Index PDF articles into the local vector database (.lutz/vector_store/).

    \b
    Workflow (normal mode):
      1. Security scan  — structural PDF analysis, prompt-injection detection,
                          academic-structure validation, and corpus-level anomaly
                          detection (IsolationForest, applied when >= 5 PDFs).
         Suspicious files are moved to articles/_quarantine/ and excluded.
      2. Text extraction — configurable backend (see --extraction).
      3. Section parsing — (optional, --section-parse) splits each article into
                          sections (abstract, introduction, methodology, results,
                          discussion, conclusion, references …) before chunking.
                          When --extraction marker is active, sections come from
                          Markdown headings; otherwise layout-parser or heuristics.
                          Each chunk is tagged with its section name.
      4. Chunking        — sliding window over words (not LLM tokens).
                          chunk-size=512 words ≈ 680 LLM tokens.
                          With --section-parse, chunks never cross section boundaries.
      5. Embedding       — one embedding API call per article; provider and model
                          are read from .env (EMBEDDING_PROVIDER, EMBEDDING_MODEL).
      6. Storage         — chunks are upserted into LanceDB.

    \b
    Quarantine mode (--quarantine):
      Targets articles/_quarantine/ instead of articles/.
      The security scan is skipped because the researcher is explicitly choosing
      to include these files after manual review.
      Run 'lutz vector-store --summarize' afterwards to confirm indexing.

    \b
    Extraction backends (--extraction):
      pymupdf  Fast, zero extra deps. Fails silently on scanned PDFs.
      marker   OCR + multi-column layout via marker-pdf. Requires:
                 pip install "lutz-research[marker]"
               Model weights (~500 MB) are downloaded once to ~/.cache/.
      auto     Tries pymupdf; detects scanned PDFs and warns (or switches to
               marker if installed).

    \b
    Section parsing (--section-parse):
      Splits the document into semantic sections before chunking. With
      --extraction marker the Markdown headings are used directly (fast, no
      layoutparser needed). Otherwise layout-parser or regex heuristics are
      tried in order.

    \b
    Re-running vectorize appends new chunks; it does not deduplicate.
    Use 'lutz unvectorize' first if you want to rebuild the index from scratch.

    \b
    Examples:
      lutz vectorize
      lutz vectorize --skip-security
      lutz vectorize --chunk-size 256 --chunk-overlap 32
      lutz vectorize --quarantine
      lutz vectorize --section-parse
      lutz vectorize --extraction marker
      lutz vectorize --extraction marker --section-parse
      lutz vectorize --extraction auto
    """
    env = load_env()
    project_root = require_project_root()
    articles_dir = project_root / "articles"

    # Resolve extraction backend: CLI flag > env var > default "pymupdf"
    backend = (extraction or env.get("EXTRACTION_BACKEND") or "pymupdf").lower()
    marker_languages = env.get("MARKER_LANGUAGES")
    marker_device = env.get("MARKER_DEVICE")

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
    # Security phase — parallel scan using ThreadPoolExecutor
    # ------------------------------------------------------------------
    approved: list[Path] = []
    # Map from PDF path to its SecurityReport (for cached_pages access later)
    security_reports: dict[Path, SecurityReport] = {}

    if skip_security:
        if not quarantine:
            console.print("[yellow]Warning:[/] security check skipped.\n")
        approved = pdf_files
    else:
        console.print("[bold]Phase 1/3 — Security scan[/]")
        checker = SecurityChecker()
        quarantine_dir = articles_dir / "_quarantine"

        scan_workers = min(len(pdf_files), os.cpu_count() or 4)

        reports_map: dict[Path, SecurityReport] = {}
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"),
            BarColumn(), TaskProgressColumn(), console=console,
        ) as progress:
            task = progress.add_task(
                f"Scanning PDFs... (workers={scan_workers})", total=len(pdf_files)
            )
            with ThreadPoolExecutor(max_workers=scan_workers) as pool:
                future_to_pdf = {pool.submit(checker.check, pdf): pdf for pdf in pdf_files}
                for future in as_completed(future_to_pdf):
                    pdf = future_to_pdf[future]
                    reports_map[pdf] = future.result()
                    progress.advance(task)

        reports: list[SecurityReport] = [reports_map[pdf] for pdf in pdf_files]
        reports = detect_corpus_anomalies(reports)

        safe = [r for r in reports if r.is_safe]
        flagged = [r for r in reports if not r.is_safe]
        security_reports = {r.path: r for r in safe}

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
    # Strategy selection
    # ------------------------------------------------------------------
    strategy: ExtractionStrategy = get_strategy(
        backend, languages=marker_languages, device=marker_device
    )
    effective_backend = backend  # may be updated per-file in auto mode

    if backend == "marker":
        console.print(
            f"[bold]Extraction backend:[/] [cyan]marker[/] "
            f"(OCR + multi-column layout)\n"
        )
    elif backend == "auto":
        console.print(
            "[bold]Extraction backend:[/] [cyan]auto[/] "
            "(pymupdf first, switches to marker for scanned PDFs)\n"
        )

    # ------------------------------------------------------------------
    # Extraction phase — parallel extraction using ThreadPoolExecutor
    # ------------------------------------------------------------------
    phase_label = "Phase 2/3" if not section_parse else "Phase 2–3/4"
    console.print(f"[bold]{phase_label} — Text extraction[/]")

    processor = PDFProcessor(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        strategy=strategy,
    )
    section_parser: SectionParser | None = None

    if section_parse:
        # When using marker, layoutparser is not needed — sections come from
        # the Markdown headings via MarkerStrategy.extract_sections().
        use_lp = layout_parse and backend != "marker"
        section_parser = SectionParser(use_layout_parser=use_lp)

    # Per-file extraction results: stem → (chunks, actual_backend)
    chunks_by_file: dict[str, list[dict]] = {}
    backend_by_file: dict[str, str] = {}

    # layout-parser (Detectron2) is not thread-safe — limit to 1 worker when active
    lp_active = section_parse and getattr(section_parser, "_lp_available", False)
    # marker is also not thread-safe (GPU model) — 1 worker when active
    marker_active = backend == "marker"
    extract_workers = 1 if (lp_active or marker_active) else min(len(approved), os.cpu_count() or 4)

    # Track sparse PDFs detected in auto mode
    sparse_pdfs: list[str] = []
    marker_available_for_auto = False
    if backend == "auto":
        try:
            MarkerStrategy._check_installed()  # type: ignore[attr-defined]
            marker_available_for_auto = True
        except ImportError:
            pass

    def _extract_one(pdf: Path) -> tuple[str, list[dict], str]:
        """Extract chunks from a single PDF; returns (stem, chunks, used_backend)."""
        cached = security_reports.get(pdf)
        pre_pages = cached.cached_pages if cached is not None else None

        used_backend = backend

        if backend == "auto":
            # First pass with pymupdf
            pymupdf_pages = pre_pages if pre_pages is not None else PyMuPDFStrategy().extract_pages(pdf)
            if is_sparse(pymupdf_pages):
                sparse_pdfs.append(pdf.name)
                if marker_available_for_auto:
                    # Switch to marker for this file
                    marker_strategy = MarkerStrategy(languages=marker_languages, device=marker_device)
                    auto_processor = PDFProcessor(
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        strategy=marker_strategy,
                    )
                    used_backend = "marker"
                    if section_parser is not None:
                        return pdf.stem, auto_processor.extract_chunks_with_sections(
                            pdf, section_parser
                        ), used_backend
                    return pdf.stem, auto_processor.extract_chunks(pdf), used_backend
                else:
                    # Warn later; proceed with sparse pymupdf output
                    used_backend = "pymupdf"
                    if section_parser is not None:
                        return pdf.stem, processor.extract_chunks_with_sections(
                            pdf, section_parser, pre_extracted_pages=pymupdf_pages
                        ), used_backend
                    return pdf.stem, processor.extract_chunks(pdf, pre_extracted_pages=pymupdf_pages), used_backend
            else:
                # Not sparse — use the cached pymupdf pages
                if section_parser is not None:
                    return pdf.stem, processor.extract_chunks_with_sections(
                        pdf, section_parser, pre_extracted_pages=pymupdf_pages
                    ), used_backend
                return pdf.stem, processor.extract_chunks(pdf, pre_extracted_pages=pymupdf_pages), used_backend

        # pymupdf or marker (no auto)
        if section_parser is not None:
            return pdf.stem, processor.extract_chunks_with_sections(
                pdf, section_parser, pre_extracted_pages=pre_pages
            ), used_backend
        return pdf.stem, processor.extract_chunks(pdf, pre_extracted_pages=pre_pages), used_backend

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console,
    ) as progress:
        label = "Extracting & parsing sections..." if section_parse else "Extracting text..."
        if extract_workers > 1:
            label += f" (workers={extract_workers})"
        task = progress.add_task(label, total=len(approved))

        with ThreadPoolExecutor(max_workers=extract_workers) as pool:
            futures = {pool.submit(_extract_one, pdf): pdf for pdf in approved}
            for future in as_completed(futures):
                stem, chunks, used_backend = future.result()
                chunks_by_file[stem] = chunks
                backend_by_file[stem] = used_backend
                progress.advance(task)

    total_chunks = sum(len(c) for c in chunks_by_file.values())
    section_note = " (section-aware)" if section_parse else ""
    console.print(
        f"[green]✓[/] Extracted {total_chunks} chunk(s){section_note} "
        f"from {len(approved)} file(s).\n"
    )

    # Warn about sparse PDFs detected in auto mode
    if sparse_pdfs and backend == "auto":
        if not marker_available_for_auto:
            console.print(
                f"[bold yellow]Warning:[/] {len(sparse_pdfs)} PDF(s) appear to be scanned "
                f"(very little text extracted):\n"
            )
            for name in sparse_pdfs:
                console.print(f"  [dim]{name}[/]")
            console.print(
                "\n  Install marker for automatic OCR: "
                "[cyan]pip install \"lutz-research[marker]\"[/]\n"
                "  Or re-run with: [cyan]lutz vectorize --extraction marker[/]\n"
            )
        else:
            console.print(
                f"[dim]{len(sparse_pdfs)} PDF(s) detected as scanned → processed with marker.[/]\n"
            )

    if section_parse:
        from collections import Counter
        section_counts: Counter[str] = Counter()
        for chunks in chunks_by_file.values():
            for c in chunks:
                section_counts[c.get("section", "") or "unknown"] += 1
        top = section_counts.most_common(8)
        breakdown = "  ".join(f"[cyan]{s}[/]={n}" for s, n in top)
        console.print(f"  Sections detected: {breakdown}\n")

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
        file_backend = backend_by_file.get(filename, backend)

        for chunk, embedding in zip(chunks, embeddings):
            all_records.append({
                **chunk,
                "filename": filename,
                "embedding": embedding,
                "vectorized_at": vectorized_at,
                "embedding_model": embedding_client.model_id,
                "embedding_provider": embedding_client.provider,
                "extraction_backend": file_backend,
            })

    vector_store.upsert(all_records)

    # Build backend summary line for the completion panel
    backend_counts: dict[str, int] = {}
    for b in backend_by_file.values():
        backend_counts[b] = backend_counts.get(b, 0) + 1
    backend_summary = ", ".join(
        f"{b} ({n})" for b, n in sorted(backend_counts.items())
    )

    console.print(
        Panel.fit(
            f"[bold green]Vectorization complete![/]\n\n"
            f"Articles indexed:     [cyan]{len(approved)}[/]\n"
            f"Total chunks:         [cyan]{total_chunks}[/]\n"
            f"Extraction backend:   [cyan]{backend_summary}[/]\n"
            f"Embedding model:      [cyan]{embedding_client.model_id}[/]\n"
            f"Embedding tokens:     [cyan]{total_embedding_tokens:,}[/]\n"
            f"Timestamp:            [dim]{vectorized_at}[/]",
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
