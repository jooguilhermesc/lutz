"""Tests for agent web endpoints — Sprint 4.

Covers:
  - GET /api/agent/tools
  - GET /api/agent/model-profiles
  - POST /api/agent/chat (basic, session_id generation, session reuse)
  - GET /api/agent/sessions
  - CRUD for researcher_profile via db functions
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Isolated lutz project root with initialised SQLite DB."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\nOPENAI_API_KEY=test-key\n"  # pragma: allowlist secret
        "EMBEDDING_PROVIDER=openai\nEMBEDDING_MODEL=text-embedding-3-small\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    from lutz.server import db as _db
    _db.init_db(tmp_path)
    return tmp_path


@pytest.fixture()
def client(project_root: Path) -> TestClient:
    """FastAPI TestClient wired to project_root."""
    import os
    from lutz.server.app import app

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


# ---------------------------------------------------------------------------
# GET /api/agent/tools
# ---------------------------------------------------------------------------


class TestAgentToolsEndpoint:

    def test_agent_tools_endpoint_returns_tools_key(self, client: TestClient) -> None:
        """GET /api/agent/tools returns a JSON object with a 'tools' key."""
        resp = client.get("/api/agent/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data

    def test_agent_tools_endpoint_has_8_tools(self, client: TestClient) -> None:
        """GET /api/agent/tools returns exactly 8 tool definitions."""
        resp = client.get("/api/agent/tools")
        tools = resp.json()["tools"]
        assert len(tools) == 8

    def test_agent_tools_have_required_fields(self, client: TestClient) -> None:
        """Each tool dict contains name, description, parameters."""
        resp = client.get("/api/agent/tools")
        for tool in resp.json()["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool


# ---------------------------------------------------------------------------
# GET /api/agent/model-profiles
# ---------------------------------------------------------------------------


class TestAgentModelProfilesEndpoint:

    def test_model_profiles_returns_profiles_key(self, client: TestClient) -> None:
        """GET /api/agent/model-profiles returns a JSON object with 'profiles'."""
        resp = client.get("/api/agent/model-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data

    def test_model_profiles_has_at_least_3_profiles(self, client: TestClient) -> None:
        """GET /api/agent/model-profiles returns at least 3 model profiles."""
        resp = client.get("/api/agent/model-profiles")
        profiles = resp.json()["profiles"]
        assert len(profiles) >= 3


# ---------------------------------------------------------------------------
# POST /api/agent/chat
# ---------------------------------------------------------------------------


class TestAgentChatEndpoint:

    def _mock_orchestrator_result(self) -> dict:
        return {
            "response": "Olá! Como posso ajudar?",
            "state": "idle",
            "plan": None,
            "awaiting_confirmation": False,
            "step_result": None,
        }

    def test_agent_chat_basic_returns_required_fields(self, client: TestClient) -> None:
        """POST /api/agent/chat with 'message' returns session_id, response, state."""
        from lutz.agent.orchestrator import AgentOrchestrator

        with patch.object(
            AgentOrchestrator,
            "process_message",
            return_value=self._mock_orchestrator_result(),
        ):
            resp = client.post("/api/agent/chat", json={"message": "olá"})

        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "response" in data
        assert "state" in data

    def test_agent_chat_creates_session_id_when_absent(self, client: TestClient) -> None:
        """Without session_id in body, a new UUID is generated."""
        from lutz.agent.orchestrator import AgentOrchestrator

        with patch.object(
            AgentOrchestrator,
            "process_message",
            return_value=self._mock_orchestrator_result(),
        ):
            resp = client.post("/api/agent/chat", json={"message": "novo"})

        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID4 length with hyphens

    def test_agent_chat_accepts_provided_session_id(self, client: TestClient) -> None:
        """When session_id is in body, the same value is echoed back."""
        from lutz.agent.orchestrator import AgentOrchestrator

        session_id = "my-custom-session-123"
        with patch.object(
            AgentOrchestrator,
            "process_message",
            return_value=self._mock_orchestrator_result(),
        ):
            resp = client.post(
                "/api/agent/chat",
                json={"message": "oi", "session_id": session_id},
            )

        assert resp.json()["session_id"] == session_id

    def test_agent_chat_missing_message_returns_400(self, client: TestClient) -> None:
        """POST /api/agent/chat without 'message' returns 400."""
        resp = client.post("/api/agent/chat", json={})
        assert resp.status_code == 400

    def test_agent_chat_reuses_session_state(self, client: TestClient) -> None:
        """Two calls with the same session_id both echo it back correctly."""
        from lutz.agent.orchestrator import AgentOrchestrator

        session_id = "persistent-session-abc"
        call_count = []

        def fake_process_message(
            self_or_sid, sid_or_msg=None, msg_or_vs=None, vector_store=None, job_manager=None
        ):
            # patch.object on a class passes (self, session_id, user_message, ...)
            # We just need to track calls and return a valid result.
            call_count.append(1)
            return {
                "response": f"Chamada {len(call_count)}",
                "state": "idle",
                "plan": None,
                "awaiting_confirmation": False,
                "step_result": None,
            }

        with patch.object(AgentOrchestrator, "process_message", fake_process_message):
            resp1 = client.post(
                "/api/agent/chat",
                json={"message": "primeira", "session_id": session_id},
            )
            resp2 = client.post(
                "/api/agent/chat",
                json={"message": "segunda", "session_id": session_id},
            )

        # Two calls were processed
        assert len(call_count) == 2
        # Both responses echo the same session_id
        assert resp1.json()["session_id"] == session_id
        assert resp2.json()["session_id"] == session_id


# ---------------------------------------------------------------------------
# GET /api/agent/sessions
# ---------------------------------------------------------------------------


class TestAgentSessionsEndpoint:

    def test_agent_sessions_returns_sessions_key(self, client: TestClient) -> None:
        """GET /api/agent/sessions returns a JSON object with 'sessions'."""
        resp = client.get("/api/agent/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data

    def test_agent_sessions_returns_list(self, client: TestClient) -> None:
        """GET /api/agent/sessions returns a list (may be empty)."""
        resp = client.get("/api/agent/sessions")
        assert isinstance(resp.json()["sessions"], list)


# ---------------------------------------------------------------------------
# GET /api/agent/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestAgentSessionDetailEndpoint:

    def test_agent_session_detail_not_found(self, client: TestClient) -> None:
        """GET /api/agent/sessions/{id} returns 404 for unknown session."""
        resp = client.get("/api/agent/sessions/nonexistent-agent-session")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# researcher_profile CRUD (direct DB)
# ---------------------------------------------------------------------------


class TestResearcherProfileCrud:

    def test_set_and_get_researcher_profile(self, project_root: Path) -> None:
        """set_researcher_profile_key stores and get_researcher_profile retrieves."""
        from lutz.server import db as _db

        _db.set_researcher_profile_key(project_root, "preferred_language", "pt")
        profile = _db.get_researcher_profile(project_root)
        assert profile["preferred_language"] == "pt"

    def test_researcher_profile_upsert_no_duplicates(self, project_root: Path) -> None:
        """Setting the same key twice upserts — only one row per key."""
        from lutz.server import db as _db

        _db.set_researcher_profile_key(project_root, "domain", "NLP")
        _db.set_researcher_profile_key(project_root, "domain", "IA")
        profile = _db.get_researcher_profile(project_root)
        assert profile["domain"] == "IA"

    def test_get_researcher_profile_empty_dict(self, project_root: Path) -> None:
        """get_researcher_profile returns {} when table is empty."""
        from lutz.server import db as _db

        assert _db.get_researcher_profile(project_root) == {}
