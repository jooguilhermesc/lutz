"""lutz citations — extract structured citations from a per-article analysis report."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click
import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from lutz.utils.project import require_project_root, load_env
from lutz.utils.html_report import generate_html_citations_report, generate_html_reading_roadmap_report
from lutz.core.vector_store import VectorStore
from lutz.core.llm_client import LLMClient

console = Console()

# ---------------------------------------------------------------------------
# Relevance parsing (regex, no LLM cost)
# ---------------------------------------------------------------------------

_RELEVANT_PATTERNS = [
    re.compile(r'Relevance\s*:\s*RELEVANT', re.IGNORECASE),
    re.compile(r'Relevance\s*:\s*INCLUDED', re.IGNORECASE),
    re.compile(r'"decision"\s*:\s*"included"', re.IGNORECASE),
    re.compile(r'decision\s*:\s*included', re.IGNORECASE),
]

_NOT_RELEVANT_PATTERNS = [
    re.compile(r'Relevance\s*:\s*NOT\s+RELEVANT', re.IGNORECASE),
    re.compile(r'Relevance\s*:\s*IRRELEVANT', re.IGNORECASE),
    re.compile(r'Relevance\s*:\s*EXCLUDED', re.IGNORECASE),
    re.compile(r'"decision"\s*:\s*"excluded"', re.IGNORECASE),
    re.compile(r'decision\s*:\s*excluded', re.IGNORECASE),
]


def _parse_relevance(text: str) -> str:
    """Return 'relevant', 'not_relevant', or 'unknown'."""
    if not text:
        return "unknown"
    for p in _RELEVANT_PATTERNS:
        if p.search(text):
            return "relevant"
    for p in _NOT_RELEVANT_PATTERNS:
        if p.search(text):
            return "not_relevant"
    return "unknown"


# ---------------------------------------------------------------------------
# LLM-based citation extraction
# ---------------------------------------------------------------------------

_LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "pt": "All narrative text (reasoning, reading_note, overview, description, stage_name, etc.) must be written in Portuguese (pt-BR). JSON keys must remain in English as specified.",
    "en": "All narrative text must be written in English. JSON keys must remain in English as specified.",
    "es": "All narrative text (reasoning, reading_note, overview, description, stage_name, etc.) must be written in Spanish (es). JSON keys must remain in English as specified.",
}

_CITATIONS_SYSTEM = (
    "You are a systematic review assistant. "
    "Your task is to extract the key passages from an academic article that most strongly "
    "support its relevance classification. "
    "Respond with valid JSON only — no markdown, no extra text."
)


def _citations_user_message(
    prompt_content: str,
    filename: str,
    analysis_text: str,
    context: str,
) -> str:
    return (
        f"## Screening Criteria\n\n{prompt_content}\n\n"
        f"## Analysis of \"{filename}\"\n\n{analysis_text}\n\n"
        f"## Original Article Excerpts\n\n{context}\n\n"
        "## Task\n\n"
        "Extract the 3 to 5 passages from the article excerpts that most strongly support "
        "the relevance classification. Prefer exact quotes; always include the page number.\n\n"
        "Respond with JSON only, in this exact format:\n"
        "{\n"
        '  "label": "classification label or null",\n'
        '  "confidence": integer_0_to_100_or_null,\n'
        '  "reasoning": "1-2 sentence summary of why this article is relevant",\n'
        '  "citations": [\n'
        '    {"text": "exact passage from the excerpts", "page": page_number}\n'
        "  ]\n"
        "}"
    )


def _parse_llm_json(text: str) -> dict | None:
    """Try to extract a JSON object from an LLM response."""
    # Direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # JSON inside markdown code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # First JSON object in the response
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"--- Excerpt {i} (page {chunk.get('page', '?')}) ---\n{chunk['text']}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Reading roadmap helpers
# ---------------------------------------------------------------------------

def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine distance between two vectors (1 − cosine_similarity)."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - float(np.dot(a, b) / (norm_a * norm_b))


def _rank_articles_by_centrality(
    relevant: list[dict],
    embeddings_by_article: "dict[str, np.ndarray]",
) -> list[dict]:
    """Return relevant articles sorted by cosine distance from the corpus centroid.

    Articles closer to the centroid (distance ≈ 0) are the most 'foundational'
    (representative of the central research theme). Articles farther away are
    more specialised or peripheral — recommended for reading later.

    Returns a list of dicts with keys: filename, distance, rank, analysis.
    Articles not found in the vector store are appended at the end with
    distance=None.
    """
    # Compute per-article mean embeddings (already done in store, re-use here)
    vecs: list[tuple[str, np.ndarray]] = []
    missing: list[str] = []

    for a in relevant:
        fn = a["filename"]
        if fn in embeddings_by_article:
            vecs.append((fn, embeddings_by_article[fn]))
        else:
            missing.append(fn)

    ranked: list[dict] = []

    if vecs:
        # Global centroid = mean of per-article centroids (unweighted by chunk count)
        centroid = np.stack([v for _, v in vecs]).mean(axis=0)

        distances = [(fn, _cosine_distance(vec, centroid)) for fn, vec in vecs]
        distances.sort(key=lambda x: x[1])

        article_analysis = {a["filename"]: a.get("analysis", "") for a in relevant}
        for rank, (fn, dist) in enumerate(distances, 1):
            ranked.append({
                "filename": fn,
                "distance": round(dist, 6),
                "rank": rank,
                "analysis": article_analysis.get(fn, ""),
            })

    for fn in missing:
        ranked.append({
            "filename": fn,
            "distance": None,
            "rank": len(ranked) + 1,
            "analysis": next((a.get("analysis", "") for a in relevant if a["filename"] == fn), ""),
        })

    return ranked


_ROADMAP_SYSTEM = (
    "You are a systematic review specialist. "
    "Your task is to create a structured reading guide for researchers based on "
    "the semantic distance of articles from the center of the research corpus. "
    "Respond with valid JSON only — no markdown, no extra text."
)


def _roadmap_user_message(
    prompt_content: str,
    ranked_articles: list[dict],
    user_instructions: str = "",
) -> str:
    article_list = "\n".join(
        f"{a['rank']}. **{a['filename']}**"
        + (f" (semantic distance from centroid: {a['distance']:.4f})" if a["distance"] is not None else " (embedding not found)")
        + (f"\n   Article assessment: {a['analysis'][:600].strip()}" if a.get("analysis") else "")
        for a in ranked_articles
    )
    extra = (
        f"\n\n## Additional Instructions from Researcher\n\n{user_instructions.strip()}"
        if user_instructions and user_instructions.strip()
        else ""
    )
    return (
        f"## Research Screening Criteria\n\n{prompt_content}\n\n"
        f"## Articles ordered from most foundational to most specialised\n\n"
        f"These articles are sorted by their cosine distance from the centroid of the relevant "
        f"articles' embedding space. A distance near 0 means the article sits at the centre of "
        f"the research theme (foundational); a larger distance means it is more specialised or "
        f"peripheral — recommended for reading after the core articles.\n\n"
        f"{article_list}"
        f"{extra}\n\n"
        f"## Task\n\n"
        f"Create a structured reading guide in JSON. Group the articles into 2-4 logical stages "
        f"(e.g. Foundations, Core Methods, Advanced Topics). For each article provide a short "
        f"reading note explaining what to focus on and why it fits that stage.\n\n"
        f"Respond with JSON only, exactly in this format:\n"
        f'{{\n'
        f'  "overview": "2-3 sentence overview of the recommended reading strategy",\n'
        f'  "stages": [\n'
        f'    {{\n'
        f'      "stage_number": 1,\n'
        f'      "stage_name": "Foundations",\n'
        f'      "description": "What this stage covers and why to read it first",\n'
        f'      "articles": [\n'
        f'        {{\n'
        f'          "filename": "exact filename from the list above",\n'
        f'          "reading_note": "What to focus on and how this article builds understanding"\n'
        f'        }}\n'
        f'      ]\n'
        f'    }}\n'
        f'  ]\n'
        f'}}'
    )


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--analysis",
    "analysis_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Path to a JSON report produced by 'lutz analysis --per-article'. "
        "The file must have mode='per_article' in its metadata. "
        "Legacy .md or .csv files from older runs are not accepted."
    ),
)
@click.option(
    "--workers",
    default=1,
    show_default=True,
    type=click.IntRange(1, 32),
    help=(
        "Number of concurrent LLM calls for citation extraction (ThreadPoolExecutor). "
        "Only relevant articles trigger LLM calls, so the effective workload is "
        "smaller than the total article count. "
        "Increase for remote APIs; keep at 1 for local models."
    ),
)
@click.option(
    "--only-relevant",
    is_flag=True,
    default=False,
    help=(
        "Omit not-relevant and unknown articles from the output JSON. "
        "By default all articles appear in the report under their respective keys "
        "(relevant_articles, not_relevant_articles, unknown_articles)."
    ),
)
@click.option(
    "--output-name",
    default=None,
    help=(
        "Custom base name for the output JSON saved in analysis/execution_reports/. "
        "Default: <analysis_filename>_citations_<YYYYMMDD_HHMMSS>.json."
    ),
)
@click.option(
    "--language",
    default="pt",
    show_default=True,
    type=click.Choice(["pt", "en", "es"]),
    help="Language for LLM responses (pt = Portuguese, en = English, es = Spanish).",
)
@click.option(
    "--reading-roadmap",
    "reading_roadmap",
    is_flag=True,
    default=False,
    help=(
        "Generate a reading roadmap instead of a citation report. "
        "Articles are ranked by cosine distance from the corpus centroid — "
        "those closest to the centre are foundational; those farthest are specialised. "
        "An LLM then produces a structured reading guide with stages and per-article notes. "
        "Requires the vector store to still be available."
    ),
)
@click.option(
    "--user-instructions",
    "user_instructions",
    default="",
    help=(
        "Additional free-text instructions for the reading roadmap generator. "
        "Use this to specify the desired number of stages, focus areas, depth level, "
        "target audience, or any other guidance for the LLM. Only used with --reading-roadmap."
    ),
)
def citations(
    analysis_path: Path,
    workers: int,
    only_relevant: bool,
    output_name: str | None,
    language: str,
    reading_roadmap: bool,
    user_instructions: str,
) -> None:
    """Extract structured citations from a per-article analysis report.

    \b
    Requires a JSON report produced by 'lutz analysis --per-article'.
    The vector store (.lutz/vector_store/) must still be available since
    citations are extracted from the original article chunks, not from the
    analysis text alone.

    \b
    Workflow:
      1. Load the per-article JSON report and read the original screening prompt.
      2. Classify each article as relevant, not_relevant, or unknown by scanning
         the analysis text with regex patterns (no LLM cost at this step).
         Detected patterns include 'Relevance: RELEVANT / NOT RELEVANT / EXCLUDED',
         'decision: included / excluded', and similar variants.
      3. Load all article chunks from the vector store in a single bulk read.
      4. For each relevant article: send the analysis text + original chunks to
         the LLM and ask it to return a JSON with label, confidence, reasoning,
         and the 3-5 most relevant citation passages (exact quotes with page numbers).
      5. Save a citations report JSON in analysis/execution_reports/.

    \b
    Output JSON structure:
      metadata{}           Run info: source file, timestamps, token counts, counts.
      relevant_articles[]  Per-article: label, confidence, reasoning, citations[].
      not_relevant_articles[]  Compact list (filename only) — omitted with --only-relevant.
      unknown_articles[]   Articles where relevance could not be determined.

    \b
    Each citation entry:
      text    Exact passage extracted from the article.
      page    Page number where the passage appears.

    \b
    Examples:
      lutz citations --analysis analysis/execution_reports/screening_20260501.json
      lutz citations --analysis analysis/execution_reports/screening_20260501.json --workers 4
      lutz citations --analysis analysis/execution_reports/screening_20260501.json --only-relevant
      lutz citations --analysis analysis/execution_reports/screening_20260501.json \\
        --workers 4 --only-relevant --output-name review_citations_v1
    """
    env = load_env()
    project_root = require_project_root()

    # ---- load analysis JSON -------------------------------------------------
    if analysis_path.suffix.lower() != ".json":
        console.print(
            f"[bold red]Error:[/] expected a .json file, got [dim]{analysis_path.name}[/].\n"
            "Pass the JSON report produced by [bold]lutz analysis --per-article[/], "
            "not the legacy .md or .csv files."
        )
        raise click.Abort()

    try:
        report = json.loads(analysis_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        console.print(
            f"[bold red]Error:[/] [dim]{analysis_path.name}[/] is not valid JSON.\n"
            "Pass the JSON report produced by [bold]lutz analysis --per-article[/]."
        )
        raise click.Abort()

    if report.get("metadata", {}).get("mode") != "per_article":
        console.print(
            "[bold red]Error:[/] 'lutz citations' requires a report produced by "
            "[bold]lutz analysis --per-article[/]. "
            f"This report has mode=[bold]{report.get('metadata', {}).get('mode', 'unknown')}[/]."
        )
        raise click.Abort()

    articles: list[dict] = report.get("articles", [])
    prompt_content: str = report["metadata"].get("prompt_content", "")

    if not articles:
        console.print("[yellow]No articles found in the analysis report.[/]")
        return

    # ---- classify relevance -------------------------------------------------
    for a in articles:
        a["_relevance"] = _parse_relevance(a.get("analysis") or "")

    relevant = [a for a in articles if a["_relevance"] == "relevant"]
    not_relevant = [a for a in articles if a["_relevance"] == "not_relevant"]
    unknown = [a for a in articles if a["_relevance"] == "unknown"]

    mode_label = "Reading roadmap" if reading_roadmap else "Citations extraction"
    console.print(
        Panel.fit(
            f"[bold cyan]{mode_label}[/]\n\n"
            f"Analysis file:  [dim]{analysis_path.name}[/]\n"
            f"Total articles: [cyan]{len(articles)}[/]\n"
            f"Relevant:       [green]{len(relevant)}[/]\n"
            f"Not relevant:   [dim]{len(not_relevant)}[/]\n"
            f"Unknown:        [yellow]{len(unknown)}[/]\n"
            + (f"Workers:        {workers}" if not reading_roadmap else ""),
            border_style="cyan",
        )
    )

    if not relevant:
        console.print(
            "[yellow]No relevant articles detected.[/] "
            "Check that the analysis prompt produces a clear relevance signal\n"
            "(e.g. 'Relevance: RELEVANT' or 'Relevance: NOT RELEVANT')."
        )
        raise click.Abort()

    # ---- load vector store --------------------------------------------------
    store = VectorStore(project_root / ".lutz" / "vector_store")
    store_info = store.info()

    if store_info["total_records"] == 0:
        console.print(
            "[bold red]Error:[/] vector store is empty. "
            "Run [bold]lutz vectorize[/] to rebuild the index."
        )
        raise click.Abort()

    llm_client = LLMClient.from_env(env)
    reports_dir = project_root / "analysis" / "execution_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # BRANCH A — Reading roadmap
    # =========================================================================
    if reading_roadmap:
        console.print(
            f"\nLoading embeddings from vector store ({store_info['total_records']:,} chunks)... ",
            end="",
        )
        embeddings_by_article = store.get_embeddings_by_article()
        console.print("[green]done.[/]\n")

        console.print("[bold]Ranking articles by semantic centrality...[/]")
        ranked = _rank_articles_by_centrality(relevant, embeddings_by_article)

        table = Table(title="Article ranking (foundational → specialised)", show_lines=False, header_style="bold cyan")
        table.add_column("Rank", justify="right", style="dim")
        table.add_column("Article", no_wrap=False)
        table.add_column("Distance", justify="right")
        for r in ranked:
            dist_str = f"{r['distance']:.4f}" if r["distance"] is not None else "—"
            table.add_row(str(r["rank"]), r["filename"], dist_str)
        console.print(table)
        console.print()

        console.print("[bold]Generating reading roadmap via LLM...[/]\n")
        started_at = datetime.now(timezone.utc)
        start_ts = time.time()

        lang_instr = _LANGUAGE_INSTRUCTIONS.get(language, _LANGUAGE_INSTRUCTIONS["pt"])
        roadmap_system = _ROADMAP_SYSTEM + f"\n\n## Language\n\n{lang_instr}"
        user_msg = _roadmap_user_message(prompt_content, ranked, user_instructions=user_instructions)
        llm_text, llm_usage = llm_client.complete(system=roadmap_system, user=user_msg)
        parsed_roadmap = _parse_llm_json(llm_text)

        finished_at = datetime.now(timezone.utc)
        elapsed_seconds = round(time.time() - start_ts, 2)

        if parsed_roadmap is None:
            console.print("[bold red]Warning:[/] could not parse LLM response as JSON. Storing raw text.")
            parsed_roadmap = {"overview": llm_text, "stages": []}

        # ---- assemble roadmap report JSON -----------------------------------
        not_relevant_entries = [
            {"filename": a["filename"], "relevance": "not_relevant"}
            for a in not_relevant
        ]
        unknown_entries = [
            {"filename": a["filename"], "relevance": "unknown"}
            for a in unknown
        ]

        output_report = {
            "metadata": {
                "report_type": "reading_roadmap",
                "analysis_file": str(analysis_path),
                "generated_at": finished_at.isoformat(),
                "elapsed_seconds": elapsed_seconds,
                "original_prompt_path": report["metadata"].get("prompt_path"),
                "prompt_content": prompt_content,
                "total_articles": len(articles),
                "relevant": len(relevant),
                "not_relevant": len(not_relevant),
                "unknown": len(unknown),
                "llm": {
                    "provider": llm_client.provider,
                    "model": llm_client.model_id,
                    "prompt_tokens": llm_usage["prompt_tokens"],
                    "completion_tokens": llm_usage["completion_tokens"],
                    "total_tokens": llm_usage["total_tokens"],
                },
            },
            "roadmap": {
                **parsed_roadmap,
                "article_distances": [
                    {"filename": r["filename"], "distance": r["distance"], "rank": r["rank"]}
                    for r in ranked
                ],
            },
        }
        if not only_relevant:
            output_report["not_relevant_articles"] = not_relevant_entries
            if unknown_entries:
                output_report["unknown_articles"] = unknown_entries

        # ---- save -----------------------------------------------------------
        timestamp = finished_at.strftime("%Y%m%d_%H%M%S")
        base_name = output_name or f"{analysis_path.stem}_roadmap_{timestamp}"
        out_path = reports_dir / f"{base_name}.json"
        out_path.write_text(json.dumps(output_report, ensure_ascii=False, indent=2), encoding="utf-8")

        html_path = out_path.with_suffix(".html")
        html_path.write_text(generate_html_reading_roadmap_report(output_report), encoding="utf-8")

        n_stages = len((parsed_roadmap or {}).get("stages", []))
        console.print(
            Panel.fit(
                f"[bold green]Reading roadmap saved![/]\n\n"
                f"{out_path.relative_to(project_root)}\n\n"
                f"Relevant articles: [cyan]{len(relevant)}[/]\n"
                f"Stages generated:  [cyan]{n_stages}[/]\n"
                f"LLM tokens:        [cyan]{llm_usage['total_tokens']:,}[/]\n"
                f"Duration:          [cyan]{elapsed_seconds:.1f}s[/]",
                border_style="green",
            )
        )
        return

    # =========================================================================
    # BRANCH B — Citations (original behaviour)
    # =========================================================================
    console.print(
        f"\nLoading vector store ({store_info['total_records']:,} chunks)... ",
        end="",
    )
    all_chunks = store.get_all_grouped()
    console.print("[green]done.[/]\n")

    console.print(
        f"[bold]Extracting citations — {len(relevant)} relevant article(s)[/]\n"
    )

    started_at = datetime.now(timezone.utc)
    start_ts = time.time()

    def _process_one(article: dict) -> dict:
        filename = article["filename"]
        chunks = all_chunks.get(filename, [])
        analysis_text = article.get("analysis") or ""

        if not chunks:
            return {
                "filename": filename,
                "relevance": "relevant",
                "error": "Article not found in vector store.",
                "label": None,
                "confidence": None,
                "reasoning": None,
                "citations": [],
                "llm_prompt_tokens": 0,
                "llm_completion_tokens": 0,
                "llm_total_tokens": 0,
            }

        context = _build_context(chunks)
        user_msg = _citations_user_message(prompt_content, filename, analysis_text, context)
        lang_instr = _LANGUAGE_INSTRUCTIONS.get(language, _LANGUAGE_INSTRUCTIONS["pt"])
        citations_system = _CITATIONS_SYSTEM + f"\n\n## Language\n\n{lang_instr}"
        llm_text, llm_usage = llm_client.complete(system=citations_system, user=user_msg)
        parsed = _parse_llm_json(llm_text)

        if parsed is None:
            return {
                "filename": filename,
                "relevance": "relevant",
                "parse_error": "LLM response could not be parsed as JSON.",
                "raw_response": llm_text,
                "label": None,
                "confidence": None,
                "reasoning": None,
                "citations": [],
                "llm_prompt_tokens": llm_usage["prompt_tokens"],
                "llm_completion_tokens": llm_usage["completion_tokens"],
                "llm_total_tokens": llm_usage["total_tokens"],
            }

        return {
            "filename": filename,
            "relevance": "relevant",
            "label": parsed.get("label"),
            "confidence": parsed.get("confidence"),
            "reasoning": parsed.get("reasoning"),
            "citations": parsed.get("citations", []),
            "llm_prompt_tokens": llm_usage["prompt_tokens"],
            "llm_completion_tokens": llm_usage["completion_tokens"],
            "llm_total_tokens": llm_usage["total_tokens"],
        }

    relevant_results: dict[str, dict] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]0/{len(relevant)}[/] articles done", total=len(relevant)
        )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_one, a): a["filename"] for a in relevant}
            for future in as_completed(futures):
                filename = futures[future]
                try:
                    relevant_results[filename] = future.result()
                except Exception as exc:
                    relevant_results[filename] = {
                        "filename": filename,
                        "relevance": "relevant",
                        "error": str(exc),
                        "citations": [],
                        "llm_prompt_tokens": 0,
                        "llm_completion_tokens": 0,
                        "llm_total_tokens": 0,
                    }
                done = len(relevant_results)
                progress.update(
                    task,
                    advance=1,
                    description=f"[cyan]{done}/{len(relevant)}[/] articles done",
                )

    finished_at = datetime.now(timezone.utc)
    elapsed_seconds = round(time.time() - start_ts, 2)

    # Preserve sorted order
    relevant_entries = [relevant_results[a["filename"]] for a in relevant]

    total_prompt_tokens = sum(r.get("llm_prompt_tokens", 0) for r in relevant_entries)
    total_completion_tokens = sum(r.get("llm_completion_tokens", 0) for r in relevant_entries)

    # ---- summary table ------------------------------------------------------
    table = Table(title="Citations extracted", show_lines=False, header_style="bold cyan")
    table.add_column("Article", style="dim", no_wrap=False)
    table.add_column("Label", justify="center")
    table.add_column("Conf.", justify="right")
    table.add_column("Citations", justify="right")
    table.add_column("Status")

    for r in relevant_entries:
        status = "[green]✓[/]" if not r.get("error") and not r.get("parse_error") else "[red]✗[/]"
        table.add_row(
            r["filename"],
            str(r.get("label") or "—"),
            str(r.get("confidence") or "—"),
            str(len(r.get("citations") or [])),
            status,
        )

    console.print(table)
    console.print()

    # ---- assemble report JSON -----------------------------------------------
    not_relevant_entries = [
        {
            "filename": a["filename"],
            "relevance": "not_relevant",
            "reasoning": None,
            "citations": [],
        }
        for a in not_relevant
    ]
    unknown_entries = [
        {
            "filename": a["filename"],
            "relevance": "unknown",
            "raw_analysis": a.get("analysis"),
            "citations": [],
        }
        for a in unknown
    ]

    report_body: dict = {"relevant_articles": relevant_entries}
    if not only_relevant:
        report_body["not_relevant_articles"] = not_relevant_entries
        if unknown_entries:
            report_body["unknown_articles"] = unknown_entries

    output_report = {
        "metadata": {
            "report_type": "citations",
            "analysis_file": str(analysis_path),
            "generated_at": finished_at.isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "workers": workers,
            "original_prompt_path": report["metadata"].get("prompt_path"),
            "prompt_content": prompt_content,
            "total_articles": len(articles),
            "relevant": len(relevant),
            "not_relevant": len(not_relevant),
            "unknown": len(unknown),
            "llm": {
                "provider": llm_client.provider,
                "model": llm_client.model_id,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
            },
        },
        **report_body,
    }

    # ---- save ---------------------------------------------------------------
    timestamp = finished_at.strftime("%Y%m%d_%H%M%S")
    base_name = output_name or f"{analysis_path.stem}_citations_{timestamp}"
    out_path = reports_dir / f"{base_name}.json"

    out_path.write_text(
        json.dumps(output_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    html_path = out_path.with_suffix(".html")
    html_path.write_text(generate_html_citations_report(output_report), encoding="utf-8")

    console.print(
        Panel.fit(
            f"[bold green]Citations report saved![/]\n\n"
            f"{out_path.relative_to(project_root)}\n\n"
            f"Relevant articles:  [cyan]{len(relevant)}[/]\n"
            f"Citations extracted:[cyan]{sum(len(r.get('citations') or []) for r in relevant_entries)}[/]\n"
            f"LLM tokens:         [cyan]{total_prompt_tokens + total_completion_tokens:,}[/] "
            f"(prompt {total_prompt_tokens:,} + completion {total_completion_tokens:,})\n"
            f"Duration:           [cyan]{elapsed_seconds:.1f}s[/]",
            border_style="green",
        )
    )
