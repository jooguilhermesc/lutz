"""Tests for real tool integration and SSE streaming — Sprint 4.

TDD: tests written BEFORE implementation.

Covers:
  1. analyze_corpus with/without job_manager
  2. extract_citations with job_manager
  3. generate_roadmap with job_manager
  4. ExecutionEngine.execute_step passes job_manager to registry
  5. POST /api/agent/chat/stream returns text/event-stream
  6. First SSE event has type=session with session_id
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job_manager(job_id: str = "test-job-id-1234") -> MagicMock:
    """Return a mock JobManager whose create() returns a Job-like mock."""
    jm = MagicMock()
    job = MagicMock()
    job.id = job_id
    jm.create.return_value = job
    return jm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\nOPENAI_API_KEY=test-key\n"
        "EMBEDDING_PROVIDER=openai\nEMBEDDING_MODEL=text-embedding-3-small\n",
        encoding="utf-8",
    )
    from lutz.server import db as _db
    _db.init_db(tmp_path)
    return tmp_path


@pytest.fixture()
def client(project_root: Path) -> TestClient:
    import os
    from lutz.server.app import app

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


# ---------------------------------------------------------------------------
# 1. analyze_corpus with job_manager
# ---------------------------------------------------------------------------


def test_analyze_corpus_with_job_manager():
    """When job_manager is provided, analyze_corpus calls create('analysis', ...) and returns job_id."""
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    jm = _make_job_manager("job-analysis-123")

    result = registry.execute(
        "analyze_corpus",
        {"prompt": "Qual o impacto do RAG em LLMs?", "mode": "rag", "top_k": 5},
        job_manager=jm,
    )

    assert isinstance(result, dict)
    assert result.get("status") == "queued"
    assert result.get("job_id") == "job-analysis-123"
    assert result.get("job_type") == "analysis"
    jm.create.assert_called_once()
    call_args = jm.create.call_args
    assert call_args[0][0] == "analysis"  # first positional arg is "analysis"


# ---------------------------------------------------------------------------
# 2. analyze_corpus without job_manager
# ---------------------------------------------------------------------------


def test_analyze_corpus_without_job_manager():
    """Without job_manager, analyze_corpus returns queued status without crashing."""
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()

    result = registry.execute(
        "analyze_corpus",
        {"prompt": "some prompt"},
    )

    assert isinstance(result, dict)
    assert result.get("status") == "queued"
    assert "job_id" in result


# ---------------------------------------------------------------------------
# 3. extract_citations with job_manager
# ---------------------------------------------------------------------------


def test_extract_citations_with_job_manager():
    """When job_manager is provided, extract_citations calls create('citations', ...) and returns job_id."""
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    jm = _make_job_manager("job-citations-456")

    result = registry.execute(
        "extract_citations",
        {"report_path": "/tmp/report.json"},
        job_manager=jm,
    )

    assert isinstance(result, dict)
    assert result.get("status") == "queued"
    assert result.get("job_id") == "job-citations-456"
    assert result.get("job_type") == "citations"
    jm.create.assert_called_once()
    call_args = jm.create.call_args
    assert call_args[0][0] == "citations"


# ---------------------------------------------------------------------------
# 4. generate_roadmap with job_manager
# ---------------------------------------------------------------------------


def test_generate_roadmap_with_job_manager():
    """When job_manager is provided, generate_roadmap calls create('roadmap', ...) and returns job_id."""
    from lutz.agent.tools import get_tool_registry

    registry = get_tool_registry()
    jm = _make_job_manager("job-roadmap-789")

    result = registry.execute(
        "generate_roadmap",
        {"report_path": "/tmp/report.json"},
        job_manager=jm,
    )

    assert isinstance(result, dict)
    assert result.get("status") == "queued"
    assert result.get("job_id") == "job-roadmap-789"
    assert result.get("job_type") == "roadmap"
    jm.create.assert_called_once()
    call_args = jm.create.call_args
    assert call_args[0][0] == "roadmap"


# ---------------------------------------------------------------------------
# 5. ExecutionEngine.execute_step passes job_manager to registry
# ---------------------------------------------------------------------------


def test_execute_step_passes_job_manager():
    """ExecutionEngine.execute_step with job_manager= forwards it to the tool handler."""
    from lutz.agent.orchestrator import ExecutionEngine
    from lutz.agent.tools import get_tool_registry, ToolRegistry
    from lutz.agent.model_router import ModelRouter

    registry = get_tool_registry()
    router = ModelRouter()
    engine = ExecutionEngine(registry, router)

    jm = _make_job_manager("job-step-abc")

    step = {
        "step": 1,
        "tool": "analyze_corpus",
        "arguments": {"prompt": "test", "mode": "rag"},
        "rationale": "test",
        "status": "pending",
    }

    result = engine.execute_step(step, vector_store=None, job_manager=jm)

    assert result.get("status") == "queued"
    assert result.get("job_id") == "job-step-abc"
    jm.create.assert_called_once()


# ---------------------------------------------------------------------------
# 6. POST /api/agent/chat/stream returns text/event-stream
# ---------------------------------------------------------------------------


def test_agent_chat_stream_endpoint(client: TestClient):
    """POST /api/agent/chat/stream returns 200 with Content-Type text/event-stream."""
    from lutz.agent.orchestrator import AgentOrchestrator

    mock_result = {
        "response": "Olá! Posso ajudar.",
        "state": "idle",
        "plan": None,
        "awaiting_confirmation": False,
        "step_result": None,
    }

    with patch.object(AgentOrchestrator, "process_message", return_value=mock_result):
        with client.stream("POST", "/api/agent/chat/stream", json={"message": "olá"}) as resp:
            assert resp.status_code == 200
            content_type = resp.headers.get("content-type", "")
            assert "text/event-stream" in content_type

            raw = resp.read().decode("utf-8")

    # Must contain a 'done' event
    events = [line for line in raw.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line[len("data: "):]) for line in events]
    done_events = [p for p in payloads if p.get("type") == "done"]
    assert len(done_events) >= 1


# ---------------------------------------------------------------------------
# 7. First SSE event has type=session with session_id
# ---------------------------------------------------------------------------


def test_agent_chat_stream_contains_session_event(client: TestClient):
    """First SSE data event has type='session' and a non-empty session_id."""
    from lutz.agent.orchestrator import AgentOrchestrator

    mock_result = {
        "response": "Tudo bem.",
        "state": "awaiting_confirmation",
        "plan": {"steps": [], "current_step": 0, "goal": "test", "inclusion_criterion": None},
        "awaiting_confirmation": True,
        "step_result": None,
    }

    with patch.object(AgentOrchestrator, "process_message", return_value=mock_result):
        with client.stream(
            "POST",
            "/api/agent/chat/stream",
            json={"message": "analisa meu corpus", "session_id": "fixed-session-999"},
        ) as resp:
            assert resp.status_code == 200
            raw = resp.read().decode("utf-8")

    data_lines = [line for line in raw.splitlines() if line.startswith("data: ")]
    assert len(data_lines) >= 1
    first_payload = json.loads(data_lines[0][len("data: "):])
    assert first_payload.get("type") == "session"
    assert first_payload.get("session_id") == "fixed-session-999"
