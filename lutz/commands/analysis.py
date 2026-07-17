"""lutz analysis — run an LLM-based analysis over vectorised articles."""

from __future__ import annotations

import json
import re
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
from lutz.core.context_store import ContextStore
from lutz.core.llm_client import LLMClient
from lutz.core.embedding_client import EmbeddingClient
from lutz.utils.html_report import generate_html_report

console = Console()

_SYSTEM_PROMPT = (
    "You are an expert academic researcher performing a systematic literature review. "
    "Your task is to analyse the provided article excerpts and produce a structured, "
    "evidence-based response following the researcher's instructions. "
    "Always cite the source article filename when referencing specific content. "
    "Be objective, concise, and academically rigorous."
)

_LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "pt": "Respond in Portuguese (pt-BR). All text in your response must be in Portuguese.",
    "en": "Respond in English. All text in your response must be in English.",
    "es": "Respond in Spanish (es). All text in your response must be in Spanish.",
}


def _build_system_prompt(language: str = "pt") -> str:
    lang_instr = _LANGUAGE_INSTRUCTIONS.get(language, _LANGUAGE_INSTRUCTIONS["pt"])
    return _SYSTEM_PROMPT + f"\n\n## Language\n\n{lang_instr}"

# ---------------------------------------------------------------------------
# Relevance verdict — labels, injection, and extraction
# ---------------------------------------------------------------------------

def _build_relevance_instruction(
    criteria_text: str | None = None,
    verdict_categories: list[dict] | None = None,
) -> str:
    criteria_block = f"\n{criteria_text.strip()}\n\n" if criteria_text and criteria_text.strip() else ""

    if verdict_categories:
        codes = [c["code"] for c in verdict_categories]
        labels_bold = ", ".join(f"**{c}**" for c in codes)
        include_codes = [c["code"] for c in verdict_categories if c.get("extractCitations")]
        cat_lines = ""
        for c in verdict_categories:
            code = c["code"]
            if code in include_codes:
                desc = "the article meets the criteria for inclusion."
            else:
                desc = "the article does not meet the criteria."
            cat_lines += f"- **{code}** ({c.get('label', code)}) — {desc}\n"
        return (
            "\n\n## Relevance Verdict\n\n"
            "After completing your analysis you MUST end your response with the following block "
            "(no extra text after it):\n\n"
            "```\n---VERDICT---\nRELEVANCE: <label>\n```\n\n"
            f"Replace `<label>` with EXACTLY one of: {labels_bold}.\n"
            f"{criteria_block}"
            f"{cat_lines}"
        )

    if criteria_text and criteria_text.strip():
        verdict_guidance = (
            "Based on the criteria above, classify the article as:\n"
            "- **INCLUDE** — the article clearly meets the specified criteria.\n"
            "- **EXCLUDE** — the article clearly fails one or more criteria.\n"
            "- **UNCERTAIN** — the excerpts do not provide enough information to evaluate.\n"
        )
    else:
        verdict_guidance = (
            "- **INCLUDE** — the article meets the relevance criterion stated in the instructions above.\n"
            "- **EXCLUDE** — the article does NOT meet the relevance criterion.\n"
            "- **UNCERTAIN** — the excerpts do not contain enough information to decide.\n"
        )
    return (
        "\n\n## Relevance Verdict\n\n"
        "After completing your analysis you MUST end your response with the following block "
        "(no extra text after it):\n\n"
        "```\n"
        "---VERDICT---\n"
        "RELEVANCE: <label>\n"
        "```\n\n"
        f"Replace `<label>` with EXACTLY one of: **INCLUDE**, **EXCLUDE**, or **UNCERTAIN**.\n"
        f"{criteria_block}"
        f"{verdict_guidance}"
    )

_VERDICT_RE = re.compile(
    r"---VERDICT---\s*\n\s*RELEVANCE:\s*([A-Z_]+)", re.IGNORECASE
)

# Patterns that suggest the prompt contains a relevance criterion.
_CRITERION_KEYWORDS = re.compile(
    r"\b(relevance|relevance criterion|inclusion criteria|exclusion criteria|"
    r"eligibility criteria|eligible|must (report|include|contain|address)|"
    r"should (report|include|contain)|study criterion|screening criterion|"
    r"include only|exclude if)\b",
    re.IGNORECASE,
)


def _extract_relevance(text: str) -> str:
    """Parse the RELEVANCE verdict from an LLM response. Returns 'UNKNOWN' if absent."""
    if not text:
        return "UNKNOWN"
    m = _VERDICT_RE.search(text)
    if m:
        return m.group(1).upper()
    return "UNKNOWN"


def _validate_prompt_relevance(prompt_content: str) -> None:
    """Emit a console warning when no relevance criterion is detected in the prompt."""
    if not _CRITERION_KEYWORDS.search(prompt_content):
        console.print(
            "[bold yellow]Warning:[/] No relevance criterion detected in the prompt. "
            "The LLM will still emit a RELEVANCE verdict, but it may be unreliable "
            "without a clear criterion. Consider adding an "
            "'## Relevance Criterion' section to your prompt.\n"
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
        section = chunk.get("section", "")
        section_label = f", section: {section}" if section else ""
        parts.append(
            f"--- Excerpt {i} "
            f"(from: {chunk['filename']}, page {chunk.get('page', '?')}{section_label}) ---\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(parts)


def _build_reference_context(chunks: list[dict]) -> str:
    """Build the reference context block from context file chunks."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"--- Reference {i} (from: {chunk['filename']}, page {chunk.get('page', '?')}) ---\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(parts)


def _user_message(
    prompt_content: str,
    context: str,
    *,
    reference_context: str = "",
    include_verdict: bool = False,
    relevance_instruction: str = "",
) -> str:
    verdict_section = (relevance_instruction or _build_relevance_instruction()) if include_verdict else ""
    ref_block = (
        f"## Reference Context\n\n"
        f"The following documents provide additional context for your analysis:\n\n"
        f"{reference_context}\n\n"
        if reference_context else ""
    )
    return (
        f"## Researcher Instructions\n\n{prompt_content}\n\n"
        f"{ref_block}"
        f"## Article Excerpts\n\n{context}\n\n"
        f"## Your Analysis\n\n"
        f"Based on the excerpts above, provide a detailed response following the instructions."
        f"{verdict_section}"
    )


@click.command()
@click.option(
    "--p", "prompt_path",
    required=False,
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Path to the Markdown (.md) prompt file that instructs the LLM. "
        "The file content becomes the researcher instructions section of the LLM request. "
        "Use the templates in prompts/ created by 'lutz init' as a starting point. "
        "Required unless --multiple is used."
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
    "--filter-sections",
    default=None,
    metavar="SECTIONS",
    help=(
        "Comma-separated list of section names to include in the analysis. "
        "Only chunks whose section label matches one of the given names are "
        "retrieved or sent to the LLM. "
        "Example: --filter-sections abstract,methodology,results "
        "Valid names: abstract, introduction, background, methodology, results, "
        "discussion, conclusion, references, acknowledgements, appendix. "
        "Has no effect on articles vectorized without --section-parse (those chunks "
        "have no section label and will be excluded when this filter is active). "
        "Use 'lutz vector-store --sections' to check what sections are available."
    ),
)
@click.option(
    "--output-name", default=None,
    help=(
        "Custom base name for the output JSON file saved in analysis/execution_reports/. "
        "Default: <prompt_stem>_<YYYYMMDD_HHMMSS>.json."
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
    "--multiple", "experiments_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Path to a YAML file defining multiple experiments to run sequentially. "
        "When this option is used all other flags are ignored — each experiment "
        "defines its own parameters inside the YAML file. "
        "A summary JSON is saved alongside the individual experiment reports. "
        "See 'lutz analysis --multiple experiments.yaml' for the expected YAML schema."
    ),
)
@click.option(
    "--analysis-criteria",
    "analysis_criteria",
    default=None,
    help=(
        "Compiled classification criteria text injected into the LLM relevance instruction. "
        "Typically generated by the web UI from a researcher-defined list of named criteria."
    ),
)
@click.option(
    "--verdict-categories",
    "verdict_categories_json",
    default=None,
    help=(
        "JSON array defining custom verdict categories. Each item has 'code', 'label', "
        "and 'extractCitations' fields. When provided, the LLM is instructed to use "
        "these codes instead of the default INCLUDE/EXCLUDE/UNCERTAIN labels."
    ),
)
def analysis(
    prompt_path: Path | None,
    top_k: int | None,
    per_article: bool,
    workers: int,
    max_chunks_per_article: int | None,
    filter_sections: str | None,
    output_name: str | None,
    language: str,
    experiments_path: Path | None,
    analysis_criteria: str | None,
    verdict_categories_json: str | None,
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
    Multiple experiments mode (--multiple)
      Run several experiments defined in a YAML file in a single command.
      Each experiment specifies its own prompt, mode, and optional parameters.
      A consolidated summary JSON is produced alongside the individual reports.

      YAML schema (one block per experiment):

        exp_name:
          prompt: prompts/screening.md        # required
          mode: per_article                   # required: per_article | top_k
          main_model: claude-haiku-4-5        # optional: override LLM_MODEL from .env
          workers: 4                          # optional: default 1
          top_k: 10                           # optional: only for mode=top_k
          filter_sections:                    # optional
            - abstract
            - methodology
          only_relevant: false                # optional: default false
          output_name_analysis: exp_analysis  # optional: default <name>_analysis_<ts>.json
          output_name_citations: exp_cit      # optional: presence triggers citations step

    \b
    Section filter (--filter-sections)
      Restricts the analysis to specific sections of the articles. Only chunks
      whose section label matches one of the given names are retrieved.
      Works in both RAG and per-article modes.
      Requires articles to have been vectorized with --section-parse.
      Use 'lutz vector-store --sections' to see what sections are available.

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
      lutz analysis --p prompts/methodology.md --filter-sections methodology,results
      lutz analysis --p prompts/screening.md --per-article --filter-sections abstract
      lutz analysis --multiple experiments/pilot.yaml
    """
    # --multiple: delegate entirely to the experiments runner
    if experiments_path is not None:
        from lutz.commands.experiments import run_experiments
        run_experiments(experiments_path)
        return

    if prompt_path is None:
        raise click.UsageError(
            "Missing option '--p'. "
            "Provide a prompt file with --p or run multiple experiments with --multiple."
        )

    env = load_env()
    project_root = require_project_root()

    reports_dir = project_root / "analysis" / "execution_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    prompt_content = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_content:
        console.print("[bold red]Error:[/] prompt file is empty.")
        raise click.Abort()

    if per_article:
        _validate_prompt_relevance(prompt_content)

    # Parse section filter
    section_filter: list[str] | None = None
    if filter_sections:
        section_filter = [s.strip() for s in filter_sections.split(",") if s.strip()]

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
    if section_filter:
        panel_lines.append(f"Sections: [cyan]{', '.join(section_filter)}[/]")

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

    # Load context store (reference files) — optional, silently absent
    ctx_store = ContextStore(project_root / ".lutz" / "context_store")

    embedding_client = EmbeddingClient.from_env(env)
    llm_client = LLMClient.from_env(env)

    started_at = datetime.now(timezone.utc)
    start_ts = time.time()

    if per_article:
        verdict_categories: list[dict] | None = None
        if verdict_categories_json:
            try:
                verdict_categories = json.loads(verdict_categories_json)
            except (json.JSONDecodeError, TypeError):
                verdict_categories = None
        rel_instruction = _build_relevance_instruction(analysis_criteria, verdict_categories)
        output = _run_per_article(
            store, llm_client, prompt_content, store_info,
            embedding_client, workers, max_chunks_per_article,
            section_filter=section_filter,
            ctx_store=ctx_store,
            language=language,
            relevance_instruction=rel_instruction,
        )
    else:
        output = _run_rag(
            store, llm_client, embedding_client, prompt_content,
            top_k, store_info,
            section_filter=section_filter,
            language=language,
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
            "filter_sections": section_filter,
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

    # ---- HTML report (per-article only) -------------------------------------
    html_path: Path | None = None
    if per_article:
        html_path = report_path.with_suffix(".html")
        html_path.write_text(generate_html_report(report), encoding="utf-8")

    # ---- summary panel -------------------------------------------------------
    llm_meta = report["metadata"]["llm"]
    embed_meta = report["metadata"]["embedding"]

    if per_article:
        articles_list = output["body"].get("articles", [])
        articles_covered = len(articles_list)
        relevance_counts: dict[str, int] = {}
        for a in articles_list:
            lbl = a.get("relevance", "UNKNOWN")
            relevance_counts[lbl] = relevance_counts.get(lbl, 0) + 1
        relevance_summary = "  ".join(
            f"[cyan]{lbl}[/]: {cnt}" for lbl, cnt in sorted(relevance_counts.items())
        )
        extra = (
            f"Articles covered: [cyan]{articles_covered}[/]\n"
            f"Relevance:        {relevance_summary}"
        )
    else:
        articles_covered = len(output["body"].get("articles_covered", []))
        chunks = output["body"].get("chunks_retrieved", 0)
        extra = (
            f"Articles covered: [cyan]{articles_covered}[/]\n"
            f"Chunks retrieved: [cyan]{chunks}[/]"
        )

    saved_files = str(report_path.relative_to(project_root))
    if html_path:
        saved_files += f"\n{html_path.relative_to(project_root)}"

    console.print(
        Panel.fit(
            f"[bold green]Report saved![/]\n\n"
            f"{saved_files}\n\n"
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
    section_filter: list[str] | None = None,
    language: str = "pt",
) -> dict:
    console.print("[bold]Step 1/2 — Retrieving relevant context[/]")
    with Progress(SpinnerColumn(), TextColumn("Embedding prompt..."), console=console, transient=True) as p:
        p.add_task("", total=None)
        query_embeddings, embed_tokens = embedding_client.embed([prompt_content])

    query_embedding = query_embeddings[0]
    chunks = store.search(query_embedding, top_k=top_k, sections=section_filter)
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
        llm_text, llm_usage = llm_client.complete(system=_build_system_prompt(language), user=user_msg)

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
    section_filter: list[str] | None = None,
    ctx_store: ContextStore | None = None,
    language: str = "pt",
    relevance_instruction: str = "",
) -> dict:
    # Single bulk read — avoids N full table scans
    console.print("[dim]Loading vector store into memory...[/]")
    all_chunks = store.get_all_grouped(sections=section_filter)
    filenames = sorted(all_chunks.keys())

    if not filenames:
        console.print("[bold red]No articles found in vector store.[/]")
        raise click.Abort()

    # Load reference context once — shared across all articles
    reference_context = ""
    if ctx_store and not ctx_store.is_empty():
        ref_chunks = ctx_store.get_all_chunks()
        # If large (>20 chunks), retrieve top-K by similarity to the prompt
        if len(ref_chunks) > 20:
            with Progress(
                SpinnerColumn(), TextColumn("Embedding prompt for context retrieval..."),
                console=console, transient=True,
            ) as p:
                p.add_task("", total=None)
                prompt_embeddings, _ = embedding_client.embed([prompt_content])
            ref_chunks = ctx_store.search(prompt_embeddings[0], top_k=20)
        reference_context = _build_reference_context(ref_chunks)
        console.print(
            f"[dim]Reference context: {len(ref_chunks)} chunk(s) from "
            f"{len({c['filename'] for c in ref_chunks})} file(s) will be included in each call.[/]"
        )

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
                "relevance": "UNKNOWN",
                "analysis": None,
                "error": "No chunks found in store.",
            }

        context = _build_context(chunks)
        user_msg = _user_message(
            prompt_content, context,
            reference_context=reference_context,
            include_verdict=True,
            relevance_instruction=relevance_instruction,
        )
        llm_text, llm_usage = llm_client.complete(system=_build_system_prompt(language), user=user_msg)

        return {
            "filename": filename,
            "chunks_used": len(chunks),
            "llm_prompt_tokens": llm_usage["prompt_tokens"],
            "llm_completion_tokens": llm_usage["completion_tokens"],
            "llm_total_tokens": llm_usage["total_tokens"],
            "relevance": _extract_relevance(llm_text),
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
                        "relevance": "UNKNOWN",
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
    _RELEVANCE_COLOR = {"INCLUDE": "green", "EXCLUDE": "red", "UNCERTAIN": "yellow"}
    table = Table(title="Per-article results", show_lines=False, header_style="bold cyan")
    table.add_column("Article", style="dim", no_wrap=False)
    table.add_column("Chunks", justify="right")
    table.add_column("LLM tokens", justify="right")
    table.add_column("Relevance")
    table.add_column("Status")
    for r in articles_results:
        if r.get("error"):
            status = f"[red]✗ {r['error']}[/]"
        else:
            status = "[green]✓[/]"
        relevance_label = r.get("relevance", "UNKNOWN")
        color = _RELEVANCE_COLOR.get(relevance_label, "dim")
        table.add_row(
            r["filename"],
            str(r["chunks_used"]),
            f"{r['llm_total_tokens']:,}",
            f"[{color}]{relevance_label}[/]",
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
