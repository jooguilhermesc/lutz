"""Tests for lutz/agent/tools.py — Tool Registry (Sprint 1).

TDD: these tests are written BEFORE the implementation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vector_store(article_count: int = 5, chunk_count: int = 20):
    """Return a mock VectorStore with predictable responses."""
    vs = MagicMock()
    vs.info.return_value = {
        "total_records": chunk_count,
        "unique_documents": article_count,
        "last_updated": "2026-05-23T00:00:00",
    }
    vs.section_breakdown.return_value = {
        f"article_{i}.pdf": {"abstract": 2, "methodology": 3}
        for i in range(article_count)
    }
    vs.search.return_value = [
        {
            "filename": "article_0.pdf",
            "page": 1,
            "chunk_index": 0,
            "section": "abstract",
            "text": "Sample text",
            "score": 0.12,
        }
    ]
    vs.get_by_filename.return_value = [
        {
            "filename": "article_0.pdf",
            "page": 1,
            "chunk_index": 0,
            "section": "abstract",
            "text": "Sample text",
        }
    ]
    return vs


# ---------------------------------------------------------------------------
# Test 1 — Registry has exactly 8 tools
# ---------------------------------------------------------------------------


def test_tool_registry_has_8_tools():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    assert len(registry.list_tools()) == 8


# ---------------------------------------------------------------------------
# Test 2 — inspect_corpus returns expected shape
# ---------------------------------------------------------------------------


def test_inspect_corpus_returns_dict():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    vs = _make_vector_store(article_count=3, chunk_count=12)

    result = registry.execute("inspect_corpus", {}, vector_store=vs)

    assert isinstance(result, dict)
    assert "article_count" in result
    assert "chunk_count" in result
    assert "sections" in result
    assert result["article_count"] == 3
    assert result["chunk_count"] == 12


# ---------------------------------------------------------------------------
# Test 3 — search_corpus calls VectorStore.search and returns chunks
# ---------------------------------------------------------------------------


def test_search_corpus_calls_vector_store():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    vs = _make_vector_store()

    result = registry.execute(
        "search_corpus",
        {"query_embedding": [0.1] * 768, "top_k": 5},
        vector_store=vs,
    )

    vs.search.assert_called_once()
    assert isinstance(result, list)
    assert len(result) >= 1
    first = result[0]
    assert "filename" in first
    assert "text" in first
    assert "score" in first


# ---------------------------------------------------------------------------
# Test 4 — get_article_chunks filters by filename
# ---------------------------------------------------------------------------


def test_get_article_chunks_filters_by_filename():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    vs = _make_vector_store()

    result = registry.execute(
        "get_article_chunks",
        {"filename": "article_0.pdf"},
        vector_store=vs,
    )

    vs.get_by_filename.assert_called_once_with("article_0.pdf")
    assert isinstance(result, list)
    assert result[0]["filename"] == "article_0.pdf"


# ---------------------------------------------------------------------------
# Test 5 — get_section_breakdown returns breakdown dict
# ---------------------------------------------------------------------------


def test_get_section_breakdown_returns_breakdown():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    vs = _make_vector_store(article_count=2)

    result = registry.execute("get_section_breakdown", {}, vector_store=vs)

    vs.section_breakdown.assert_called_once()
    assert isinstance(result, dict)
    # must contain at least the articles from our mock
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 6 — analyze_corpus returns queued status
# ---------------------------------------------------------------------------


def test_analyze_corpus_returns_queued():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()

    result = registry.execute(
        "analyze_corpus",
        {"prompt": "Is this article relevant?", "mode": "per_article", "top_k": 10},
    )

    assert isinstance(result, dict)
    assert result.get("status") == "queued"
    assert "job_id" in result


# ---------------------------------------------------------------------------
# Test 7 — execute with unknown tool raises KeyError or ToolNotFoundError
# ---------------------------------------------------------------------------


def test_execute_unknown_tool_raises():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()

    with pytest.raises((KeyError, Exception)):
        registry.execute("nonexistent_tool_xyz", {})


# ---------------------------------------------------------------------------
# Test 8 — every tool schema is a valid JSON-Schema object
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Additional coverage tests for stub tools
# ---------------------------------------------------------------------------


def test_extract_citations_returns_queued():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute(
        "extract_citations",
        {"report_path": "/some/report.json", "article_count": 5},
    )
    assert result.get("status") == "queued"
    assert "job_id" in result


def test_generate_roadmap_returns_queued():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute(
        "generate_roadmap",
        {"report_path": "/some/report.json"},
    )
    assert result.get("status") == "queued"
    assert "job_id" in result


def test_query_analytics_blocks_non_select():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute(
        "query_analytics",
        {"sql_query": "DROP TABLE articles"},
    )
    assert "error" in result
    assert result["error"] != "DuckDB integration pending"


def test_query_analytics_returns_stub_for_select():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute(
        "query_analytics",
        {"sql_query": "SELECT * FROM articles LIMIT 10"},
    )
    assert "error" in result
    assert result["error"] == "DuckDB integration pending"


def test_inspect_corpus_no_vector_store():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute("inspect_corpus", {}, vector_store=None)
    assert result["article_count"] == 0
    assert result["chunk_count"] == 0


def test_get_article_chunks_no_vector_store():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute("get_article_chunks", {"filename": "x.pdf"}, vector_store=None)
    assert result == []


def test_get_section_breakdown_no_vector_store():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute("get_section_breakdown", {}, vector_store=None)
    assert result == {}


def test_tool_schemas_are_valid_json_schema():
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()

    schemas = registry.list_tools()
    assert len(schemas) == 8

    for schema in schemas:
        assert "name" in schema, f"Missing 'name' in {schema}"
        assert "description" in schema, f"Missing 'description' in {schema}"
        assert "parameters" in schema, f"Missing 'parameters' in {schema}"

        params = schema["parameters"]
        assert isinstance(params, dict), f"'parameters' is not a dict in {schema['name']}"
        assert params.get("type") == "object", (
            f"'parameters.type' must be 'object' in {schema['name']}, got {params.get('type')}"
        )
        # properties is optional if no params, but type:object must be present
