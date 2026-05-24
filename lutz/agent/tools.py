"""Tool Registry for the Lutz agentic layer.

Each tool wraps an internal Lutz function (VectorStore, analysis pipeline, etc.)
with a JSON Schema definition for function calling.

Sprint 1 stubs: analyze_corpus, extract_citations, generate_roadmap return
{"status": "queued", "job_id": ...} — real integration is Sprint 4.
query_analytics returns a safe error stub until DuckDB integration lands.

Security: all tool inputs are validated against their JSON Schema before
execution. No user input is ever interpolated into subprocess calls here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class ToolNotFoundError(KeyError):
    """Raised when an unknown tool name is requested from the registry."""


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema (type: object)
    tier: int         # 0-3 default; may be overridden by TierClassifier
    handler: Callable[..., Any]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _handle_inspect_corpus(arguments: dict, vector_store=None) -> dict:
    """Return corpus overview: article_count, chunk_count, sections."""
    if vector_store is None:
        return {"article_count": 0, "chunk_count": 0, "sections": {}}
    info = vector_store.info()
    breakdown = vector_store.section_breakdown()
    return {
        "article_count": info.get("unique_documents", 0),
        "chunk_count": info.get("total_records", 0),
        "sections": breakdown,
    }


def _handle_search_corpus(arguments: dict, vector_store=None) -> list[dict]:
    """Semantic search against the corpus."""
    if vector_store is None:
        return []
    query_embedding = arguments.get("query_embedding", [])
    top_k = int(arguments.get("top_k", 10))
    sections = arguments.get("sections", None)
    kwargs: dict[str, Any] = {"query_embedding": query_embedding, "top_k": top_k}
    if sections:
        kwargs["sections"] = sections
    results = vector_store.search(**kwargs)
    return [
        {
            "filename": r.get("filename", ""),
            "page": r.get("page", 0),
            "chunk_index": r.get("chunk_index", 0),
            "section": r.get("section", ""),
            "text": r.get("text", ""),
            "score": r.get("score", None),
        }
        for r in results
    ]


def _handle_analyze_corpus(arguments: dict, vector_store=None, job_manager=None) -> dict:
    """Queue a corpus analysis job via JobManager when available."""
    if job_manager is None:
        return {"status": "queued", "job_id": str(uuid.uuid4()), "note": "no job_manager"}

    prompt = arguments.get("prompt", "")
    mode = arguments.get("mode", "rag")
    top_k = int(arguments.get("top_k", 5))
    workers = int(arguments.get("workers", 2))
    language = arguments.get("language", "pt")

    body = {
        "prompt": prompt,
        "mode": mode,
        "top_k": top_k,
        "workers": workers,
        "language": language,
        "output_name": f"agent_{uuid.uuid4().hex[:8]}",
    }
    job = job_manager.create("analysis", f"Análise: {prompt[:40]}", body)
    return {"status": "queued", "job_id": job.id, "job_type": "analysis"}


def _handle_extract_citations(arguments: dict, vector_store=None, job_manager=None) -> dict:
    """Queue a citation extraction job via JobManager when available."""
    if job_manager is None:
        return {"status": "queued", "job_id": str(uuid.uuid4()), "note": "no job_manager"}

    body = {
        "report_path": arguments.get("report_path", ""),
        "language": arguments.get("language", "pt"),
    }
    job = job_manager.create("citations", "Extração de citações", body)
    return {"status": "queued", "job_id": job.id, "job_type": "citations"}


def _handle_generate_roadmap(arguments: dict, vector_store=None, job_manager=None) -> dict:
    """Queue a reading roadmap generation job via JobManager when available."""
    if job_manager is None:
        return {"status": "queued", "job_id": str(uuid.uuid4()), "note": "no job_manager"}

    body = {
        "report_path": arguments.get("report_path", ""),
        "language": arguments.get("language", "pt"),
    }
    job = job_manager.create("roadmap", "Geração de roadmap", body)
    return {"status": "queued", "job_id": job.id, "job_type": "roadmap"}


def _handle_query_analytics(arguments: dict, vector_store=None) -> dict:
    """Execute an analytics SQL query against DuckDB (stub — integration pending)."""
    sql = arguments.get("sql_query", "")
    # Security: only SELECT statements are allowed
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return {"error": "Only SELECT queries are permitted"}
    return {"error": "DuckDB integration pending"}


def _handle_get_article_chunks(arguments: dict, vector_store=None) -> list[dict]:
    """Return all chunks for a specific article."""
    if vector_store is None:
        return []
    filename = arguments.get("filename", "")
    return vector_store.get_by_filename(filename)


def _handle_get_section_breakdown(arguments: dict, vector_store=None) -> dict:
    """Return per-article section chunk counts."""
    if vector_store is None:
        return {}
    return vector_store.section_breakdown()


# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="inspect_corpus",
        description=(
            "Inspect the current corpus: returns article count, total chunk count, "
            "and a breakdown of sections per article. Tier L0 — no LLM required."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        tier=0,
        handler=_handle_inspect_corpus,
    ),
    ToolDefinition(
        name="search_corpus",
        description=(
            "Semantic search against the corpus using an embedding vector. "
            "Returns the top_k most similar chunks with filename, page, section, text and score."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query_embedding": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Dense embedding vector for the query.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 10,
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional section filter (e.g. ['abstract', 'methodology']).",
                },
            },
            "required": ["query_embedding"],
        },
        tier=1,
        handler=_handle_search_corpus,
    ),
    ToolDefinition(
        name="analyze_corpus",
        description=(
            "Execute corpus analysis with the given prompt and mode. "
            "mode: 'rag' for open synthesis, 'per_article' for individual screening. "
            "Returns a queued job reference (integration with analysis pipeline is Sprint 4)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Analysis prompt or screening criterion.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["rag", "per_article"],
                    "description": "Analysis mode.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of chunks to retrieve per query.",
                    "default": 10,
                },
                "workers": {
                    "type": "integer",
                    "description": "Number of parallel workers.",
                    "default": 4,
                },
                "article_count": {
                    "type": "integer",
                    "description": "Total articles to analyse (used for tier routing).",
                },
                "has_relevance_criterion": {
                    "type": "boolean",
                    "description": "Whether a formal INCLUDE/EXCLUDE criterion is provided.",
                },
            },
            "required": ["prompt"],
        },
        tier=2,
        handler=_handle_analyze_corpus,
    ),
    ToolDefinition(
        name="extract_citations",
        description=(
            "Extract citations from a per-article analysis report. "
            "Returns a queued job reference (integration is Sprint 4)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "report_path": {
                    "type": "string",
                    "description": "Path to the per-article analysis report.",
                },
                "article_count": {
                    "type": "integer",
                    "description": "Number of INCLUDE articles (used for tier routing).",
                },
            },
            "required": ["report_path"],
        },
        tier=2,
        handler=_handle_extract_citations,
    ),
    ToolDefinition(
        name="generate_roadmap",
        description=(
            "Generate a reading roadmap from a per-article analysis report, "
            "ranking articles by centrality and synthesising a structured reading plan. "
            "Returns a queued job reference (integration is Sprint 4)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "report_path": {
                    "type": "string",
                    "description": "Path to the per-article analysis report.",
                },
            },
            "required": ["report_path"],
        },
        tier=3,
        handler=_handle_generate_roadmap,
    ),
    ToolDefinition(
        name="query_analytics",
        description=(
            "Execute a read-only SQL SELECT query against the DuckDB analytics store. "
            "Only SELECT statements are permitted. "
            "Returns an error stub until DuckDB integration is complete (Sprint 4)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": "A read-only SQL SELECT query.",
                },
            },
            "required": ["sql_query"],
        },
        tier=1,
        handler=_handle_query_analytics,
    ),
    ToolDefinition(
        name="get_article_chunks",
        description=(
            "Return all chunks for a specific article ordered by chunk index. "
            "Tier L0 — no LLM required."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename of the article (e.g. 'my_paper.pdf').",
                },
            },
            "required": ["filename"],
        },
        tier=0,
        handler=_handle_get_article_chunks,
    ),
    ToolDefinition(
        name="get_section_breakdown",
        description=(
            "Return a per-article breakdown of section chunk counts. "
            "Tier L0 — no LLM required."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        tier=0,
        handler=_handle_get_section_breakdown,
    ),
]


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Registry of all available agent tools."""

    def __init__(self, tools: list[ToolDefinition]) -> None:
        self._tools: dict[str, ToolDefinition] = {t.name: t for t in tools}

    def get(self, name: str) -> ToolDefinition:
        """Return tool definition by name, raising ToolNotFoundError if absent."""
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"Tool '{name}' not found in registry") from None

    def list_tools(self) -> list[dict]:
        """Return OpenAI-compatible function schemas for all registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict, vector_store=None, job_manager=None) -> Any:
        """Execute a tool by name with the given arguments.

        Parameters
        ----------
        name:
            Tool name.
        arguments:
            Tool input dict (validated against the tool's JSON Schema by the caller).
        vector_store:
            Optional VectorStore instance injected at call time.
        job_manager:
            Optional JobManager instance injected at call time (Sprint 4).

        Raises
        ------
        ToolNotFoundError
            When `name` is not registered.
        """
        tool = self.get(name)  # raises ToolNotFoundError on miss
        import inspect
        sig = inspect.signature(tool.handler)
        params = sig.parameters
        kwargs: dict[str, Any] = {"vector_store": vector_store}
        if "job_manager" in params:
            kwargs["job_manager"] = job_manager
        return tool.handler(arguments, **kwargs)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Return the singleton ToolRegistry, creating it on first call."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry(_TOOL_DEFINITIONS)
    return _registry
