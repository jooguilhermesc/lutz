"""Multi-experiment runner — parses a YAML file and executes each experiment."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from lutz.utils.project import require_project_root, load_env
from lutz.core.vector_store import VectorStore
from lutz.core.llm_client import LLMClient
from lutz.core.embedding_client import EmbeddingClient
from lutz.utils.html_report import generate_html_report

console = Console()

# ---------------------------------------------------------------------------
# YAML schema
# ---------------------------------------------------------------------------

_VALID_MODES = {"per_article", "top_k"}
_VALID_SECTIONS = {
    "abstract", "introduction", "background", "methodology",
    "results", "discussion", "conclusion", "references",
    "acknowledgements", "appendix",
}


def _parse_yaml(path: Path) -> dict[str, dict]:
    """Load and perform basic validation on the experiments YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise click.UsageError(f"Invalid YAML in {path.name}: {exc}")

    if not isinstance(raw, dict) or not raw:
        raise click.UsageError(
            f"{path.name} must be a non-empty YAML mapping of "
            "experiment names to configuration blocks."
        )
    return raw


def _validate_experiment(name: str, cfg: Any, project_root: Path) -> dict:
    """Validate and normalise a single experiment config dict.

    Returns a clean config dict with all optional fields filled with defaults.
    Raises ValueError with a descriptive message on any validation failure.
    """
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be a YAML mapping.")

    # ----- required ----------------------------------------------------------
    if "prompt" not in cfg:
        raise ValueError("'prompt' is required.")
    prompt_path = Path(cfg["prompt"])
    if not prompt_path.is_absolute():
        prompt_path = project_root / prompt_path
    if not prompt_path.exists():
        raise ValueError(f"prompt file not found: {cfg['prompt']}")

    mode_raw = cfg.get("mode", "")
    if mode_raw not in _VALID_MODES:
        raise ValueError(
            f"'mode' must be one of {sorted(_VALID_MODES)}, got: {mode_raw!r}"
        )

    # ----- optional ----------------------------------------------------------
    top_k: int | None = None
    if mode_raw == "top_k":
        raw_top_k = cfg.get("top_k", 10)
        if str(raw_top_k).strip() == "*":
            top_k = None
        else:
            try:
                top_k = int(raw_top_k)
                if top_k <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(
                    f"'top_k' must be a positive integer or '*', got: {raw_top_k!r}"
                )

    workers = cfg.get("workers", 1)
    try:
        workers = int(workers)
        if not (1 <= workers <= 32):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(f"'workers' must be an integer between 1 and 32, got: {workers!r}")

    filter_sections: list[str] | None = None
    if "filter_sections" in cfg and cfg["filter_sections"]:
        raw_sections = cfg["filter_sections"]
        if isinstance(raw_sections, str):
            raw_sections = [s.strip() for s in raw_sections.split(",")]
        if not isinstance(raw_sections, list):
            raise ValueError("'filter_sections' must be a list or comma-separated string.")
        invalid = [s for s in raw_sections if s not in _VALID_SECTIONS]
        if invalid:
            raise ValueError(
                f"Unknown section(s) in 'filter_sections': {invalid}. "
                f"Valid values: {sorted(_VALID_SECTIONS)}"
            )
        filter_sections = raw_sections

    main_model: str | None = cfg.get("main_model") or None
    only_relevant: bool = bool(cfg.get("only_relevant", False))
    output_name_analysis: str | None = cfg.get("output_name_analysis") or None
    # Citations run if and only if the key is explicitly present in the YAML.
    run_citations: bool = "output_name_citations" in cfg
    output_name_citations: str | None = cfg.get("output_name_citations") or None

    return {
        "prompt_path": prompt_path,
        "mode": mode_raw,
        "top_k": top_k,
        "workers": workers,
        "filter_sections": filter_sections,
        "main_model": main_model,
        "only_relevant": only_relevant,
        "output_name_analysis": output_name_analysis,
        "run_citations": run_citations,
        "output_name_citations": output_name_citations,
    }


# ---------------------------------------------------------------------------
# Per-experiment execution
# ---------------------------------------------------------------------------

def _run_analysis_for_experiment(
    cfg: dict,
    exp_name: str,
    store: VectorStore,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    store_info: dict,
    reports_dir: Path,
    project_root: Path,
    started_at: datetime,
) -> tuple[dict, Path]:
    """Run the analysis step for one experiment. Returns (report_dict, report_path)."""
    from lutz.commands.analysis import (
        _run_per_article,
        _run_rag,
        _validate_prompt_relevance,
    )

    prompt_path: Path = cfg["prompt_path"]
    mode: str = cfg["mode"]
    prompt_content = prompt_path.read_text(encoding="utf-8").strip()

    if mode == "per_article":
        _validate_prompt_relevance(prompt_content)
        output = _run_per_article(
            store=store,
            llm_client=llm_client,
            prompt_content=prompt_content,
            store_info=store_info,
            embedding_client=embedding_client,
            workers=cfg["workers"],
            max_chunks=None,
            section_filter=cfg["filter_sections"],
        )
        internal_mode = "per_article"
    else:  # top_k
        output = _run_rag(
            store=store,
            llm_client=llm_client,
            embedding_client=embedding_client,
            prompt_content=prompt_content,
            top_k=cfg["top_k"],
            store_info=store_info,
            section_filter=cfg["filter_sections"],
        )
        internal_mode = "rag"

    finished_at = datetime.now(timezone.utc)
    elapsed = round((finished_at - started_at).total_seconds(), 2)

    report = {
        "metadata": {
            "mode": internal_mode,
            "experiment": exp_name,
            "prompt_path": str(prompt_path),
            "prompt_content": prompt_content,
            "filter_sections": cfg["filter_sections"],
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "elapsed_seconds": elapsed,
            "vector_store": {
                "total_records": store_info["total_records"],
                "unique_documents": store_info["unique_documents"],
                "last_updated": store_info.get("last_updated"),
            },
            **output["metadata"],
        },
        **output["body"],
    }

    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    base_name = cfg["output_name_analysis"] or f"{exp_name}_analysis_{timestamp}"
    report_path = reports_dir / f"{base_name}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if internal_mode == "per_article":
        html_path = report_path.with_suffix(".html")
        html_path.write_text(generate_html_report(report), encoding="utf-8")

    return report, report_path


def _run_citations_for_experiment(
    cfg: dict,
    exp_name: str,
    analysis_report: dict,
    store: VectorStore,
    llm_client: LLMClient,
    reports_dir: Path,
    project_root: Path,
) -> tuple[dict, Path]:
    """Run citations extraction for one experiment. Returns (citations_report, path)."""
    from lutz.commands.citations import (
        _build_context as _cit_build_context,
        _citations_user_message,
        _CITATIONS_SYSTEM,
        _parse_llm_json,
    )

    articles: list[dict] = analysis_report.get("articles", [])
    prompt_content: str = analysis_report["metadata"].get("prompt_content", "")
    only_relevant: bool = cfg["only_relevant"]

    # Use the structured relevance field from issue #13 (INCLUDE/EXCLUDE/UNCERTAIN).
    # Fall back to old text-based detection for reports without the field.
    def _is_relevant(a: dict) -> bool:
        rel = a.get("relevance")
        if rel is not None:
            return rel.upper() == "INCLUDE"
        # Legacy fallback: check analysis text for old patterns
        from lutz.commands.citations import _parse_relevance as _old_parse
        return _old_parse(a.get("analysis") or "") == "relevant"

    relevant = [a for a in articles if _is_relevant(a)]
    not_relevant = [a for a in articles if not _is_relevant(a) and (a.get("relevance") or "").upper() == "EXCLUDE"]
    unknown = [a for a in articles if a not in relevant and a not in not_relevant]

    if not relevant:
        console.print(
            f"[yellow]  No INCLUDE articles for citations in '{exp_name}'.[/]"
        )
        return {}, None

    console.print(
        f"  Citations: [green]{len(relevant)}[/] relevant "
        f"/ [dim]{len(not_relevant)}[/] excluded "
        f"/ [yellow]{len(unknown)}[/] uncertain"
    )

    all_chunks = store.get_all_grouped()

    cit_started_ts = time.time()

    def _process_one(article: dict) -> dict:
        filename = article["filename"]
        chunks = all_chunks.get(filename, [])
        analysis_text = article.get("analysis") or ""

        if not chunks:
            return {
                "filename": filename,
                "error": "Article not found in vector store.",
                "label": None, "confidence": None,
                "reasoning": None, "citations": [],
                "llm_prompt_tokens": 0, "llm_completion_tokens": 0, "llm_total_tokens": 0,
            }

        context = _cit_build_context(chunks)
        user_msg = _citations_user_message(prompt_content, filename, analysis_text, context)
        llm_text, llm_usage = llm_client.complete(system=_CITATIONS_SYSTEM, user=user_msg)
        parsed = _parse_llm_json(llm_text)

        if parsed is None:
            return {
                "filename": filename,
                "parse_error": "LLM response could not be parsed as JSON.",
                "raw_response": llm_text,
                "label": None, "confidence": None, "reasoning": None, "citations": [],
                **llm_usage,
            }

        return {
            "filename": filename,
            "label": parsed.get("label"),
            "confidence": parsed.get("confidence"),
            "reasoning": parsed.get("reasoning"),
            "citations": parsed.get("citations", []),
            **{f"llm_{k}": v for k, v in llm_usage.items()},
        }

    workers = cfg["workers"]
    results_map: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_one, a): a["filename"] for a in relevant}
        for future in as_completed(futures):
            fn = futures[future]
            try:
                results_map[fn] = future.result()
            except Exception as exc:
                results_map[fn] = {
                    "filename": fn, "error": str(exc),
                    "citations": [],
                    "llm_prompt_tokens": 0, "llm_completion_tokens": 0, "llm_total_tokens": 0,
                }

    cit_elapsed = round(time.time() - cit_started_ts, 2)
    relevant_entries = [results_map[a["filename"]] for a in relevant]

    total_pt = sum(r.get("llm_prompt_tokens", 0) for r in relevant_entries)
    total_ct = sum(r.get("llm_completion_tokens", 0) for r in relevant_entries)

    report_body: dict = {"relevant_articles": relevant_entries}
    if not only_relevant:
        report_body["not_relevant_articles"] = [
            {"filename": a["filename"], "relevance": a.get("relevance", "EXCLUDE")}
            for a in not_relevant
        ]
        if unknown:
            report_body["unknown_articles"] = [
                {"filename": a["filename"], "relevance": a.get("relevance", "UNCERTAIN")}
                for a in unknown
            ]

    cit_report = {
        "metadata": {
            "experiment": exp_name,
            "analysis_file": str(analysis_report["metadata"].get("prompt_path", "")),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": cit_elapsed,
            "workers": workers,
            "only_relevant": only_relevant,
            "total_articles": len(articles),
            "relevant": len(relevant),
            "not_relevant": len(not_relevant),
            "unknown": len(unknown),
            "llm": {
                "provider": llm_client.provider,
                "model": llm_client.model_id,
                "prompt_tokens": total_pt,
                "completion_tokens": total_ct,
                "total_tokens": total_pt + total_ct,
            },
        },
        **report_body,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = cfg["output_name_citations"] or f"{exp_name}_citations_{timestamp}"
    cit_path = reports_dir / f"{base_name}.json"
    cit_path.write_text(json.dumps(cit_report, ensure_ascii=False, indent=2), encoding="utf-8")

    return cit_report, cit_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_experiments(experiments_path: Path) -> None:
    """Parse a YAML experiments file and run each experiment sequentially."""
    env = load_env()
    project_root = require_project_root()
    reports_dir = project_root / "analysis" / "execution_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    raw = _parse_yaml(experiments_path)

    # Validate all experiments before starting any
    experiments: dict[str, dict] = {}
    for name, cfg_raw in raw.items():
        try:
            experiments[name] = _validate_experiment(name, cfg_raw, project_root)
        except (ValueError, click.UsageError) as exc:
            console.print(f"[bold red]Error in experiment '{name}':[/] {exc}")
            raise click.Abort()

    console.print(
        Panel.fit(
            f"[bold cyan]Experiments file:[/] {experiments_path.name}\n"
            f"[bold cyan]Experiments to run:[/] {len(experiments)}\n"
            + "\n".join(
                f"  [dim]•[/] [bold]{name}[/]  "
                f"[dim](mode={cfg['mode']}, prompt={cfg['prompt_path'].name})[/]"
                for name, cfg in experiments.items()
            ),
            border_style="cyan",
            title="lutz experiments",
        )
    )

    store = VectorStore(project_root / ".lutz" / "vector_store")
    store_info = store.info()

    if store_info["total_records"] == 0:
        console.print(
            "[bold red]Error:[/] vector store is empty. "
            "Run [bold]lutz vectorize[/] first."
        )
        raise click.Abort()

    embedding_client = EmbeddingClient.from_env(env)

    overall_started = datetime.now(timezone.utc)
    overall_start_ts = time.time()

    summary: dict[str, Any] = {}

    for idx, (exp_name, cfg) in enumerate(experiments.items(), 1):
        console.print(
            Rule(
                f"[bold cyan]{idx}/{len(experiments)}[/]  [bold]{exp_name}[/]"
                f"  [dim]({cfg['mode']})[/]"
            )
        )

        # Build LLM client, optionally overriding the model
        exp_env = dict(env)
        if cfg["main_model"]:
            exp_env["LLM_MODEL"] = cfg["main_model"]
        llm_client = LLMClient.from_env(exp_env)

        exp_started = datetime.now(timezone.utc)
        exp_start_ts = time.time()
        analysis_report: dict | None = None
        analysis_path: Path | None = None
        citations_path: Path | None = None
        exp_error: str | None = None

        try:
            analysis_report, analysis_path = _run_analysis_for_experiment(
                cfg=cfg,
                exp_name=exp_name,
                store=store,
                llm_client=llm_client,
                embedding_client=embedding_client,
                store_info=store_info,
                reports_dir=reports_dir,
                project_root=project_root,
                started_at=exp_started,
            )
            console.print(
                f"[green]✓[/] Analysis saved: "
                f"[dim]{analysis_path.relative_to(project_root)}[/]"
            )
        except Exception as exc:
            exp_error = str(exc)
            console.print(f"[bold red]✗ Analysis failed:[/] {exc}")

        if analysis_report and cfg["run_citations"] and cfg["mode"] == "per_article":
            try:
                _, citations_path = _run_citations_for_experiment(
                    cfg=cfg,
                    exp_name=exp_name,
                    analysis_report=analysis_report,
                    store=store,
                    llm_client=llm_client,
                    reports_dir=reports_dir,
                    project_root=project_root,
                )
                if citations_path:
                    console.print(
                        f"[green]✓[/] Citations saved: "
                        f"[dim]{citations_path.relative_to(project_root)}[/]"
                    )
            except Exception as exc:
                console.print(f"[yellow]Citations failed:[/] {exc}")

        exp_elapsed = round(time.time() - exp_start_ts, 2)

        # Build the summary entry
        entry: dict[str, Any] = {"tempo_de_execução": exp_elapsed}

        if exp_error:
            entry["status"] = "error"
            entry["error"] = exp_error
            entry["nr_relevant_articles"] = None
            entry["tokens"] = None
        else:
            llm_meta = analysis_report["metadata"].get("llm", {})
            entry["status"] = "ok"
            entry["tokens"] = llm_meta.get("total_tokens", 0)

            if cfg["mode"] == "per_article":
                articles = analysis_report.get("articles", [])
                entry["nr_relevant_articles"] = sum(
                    1 for a in articles
                    if (a.get("relevance") or "").upper() == "INCLUDE"
                )
            else:
                entry["nr_relevant_articles"] = None  # not applicable for top_k/RAG mode

            entry["analysis_file"] = str(analysis_path.relative_to(project_root))
            if citations_path:
                entry["citations_file"] = str(citations_path.relative_to(project_root))

        summary[exp_name] = entry

    overall_elapsed = round(time.time() - overall_start_ts, 2)

    # Save the summary JSON
    timestamp = overall_started.strftime("%Y%m%d_%H%M%S")
    summary_path = reports_dir / f"experiments_{timestamp}.json"

    full_summary: dict[str, Any] = {
        "metadata": {
            "experiments_file": str(experiments_path),
            "started_at": overall_started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_elapsed_seconds": overall_elapsed,
            "total_experiments": len(experiments),
        },
        **summary,
    }

    summary_path.write_text(
        json.dumps(full_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Final panel
    ok_count = sum(1 for e in summary.values() if e.get("status") == "ok")
    err_count = len(summary) - ok_count

    status_line = f"[green]{ok_count} succeeded[/]"
    if err_count:
        status_line += f"  [red]{err_count} failed[/]"

    console.print(Rule())
    console.print(
        Panel.fit(
            f"[bold green]All experiments done![/]\n\n"
            f"Summary: [dim]{summary_path.relative_to(project_root)}[/]\n"
            f"Results: {status_line}\n"
            f"Duration: [cyan]{overall_elapsed:.1f}s[/]",
            border_style="green",
        )
    )
