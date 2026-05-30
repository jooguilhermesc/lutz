"""Tests for basic chat API endpoints and LLM client paths.

Covers:
  - GET /api/chat/sessions (empty and with data)
  - POST /api/chat/sessions (create session)
  - GET /api/chat/memory (empty and with data)
  - POST /api/chat/memory (add and retrieve)
  - DELETE /api/chat/memory/{id}
  - GET /api/chat/sessions/{id} (not found)
  - DELETE /api/chat/sessions/{id}
  - LLMClient temperature fallback behaviour
  - LLMClient.from_env for docker_model_runner and anthropic providers
  - server/db.py functions directly
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — fixture that builds an isolated project root with a .lutz DB
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a minimal lutz project root with an initialised SQLite DB."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)
    # Write a minimal .env so load_env() doesn't fail
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\nOPENAI_API_KEY=test-key\n"  # pragma: allowlist secret
        "EMBEDDING_PROVIDER=openai\nEMBEDDING_MODEL=text-embedding-3-small\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    # Initialise the DB schema
    from lutz.server import db as _db
    _db.init_db(tmp_path)
    return tmp_path


@pytest.fixture()
def client(project_root: Path) -> TestClient:
    """Return a FastAPI TestClient wired to the project_root."""
    import os
    from lutz.server.app import app

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    # Clean up env var so it doesn't bleed into other tests
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


# ---------------------------------------------------------------------------
# GET /api/chat/sessions — empty
# ---------------------------------------------------------------------------

class TestGetSessionsEmpty:

    def test_returns_empty_list(self, client: TestClient) -> None:
        """GET /api/chat/sessions returns [] when no sessions exist."""
        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert data["sessions"] == []


# ---------------------------------------------------------------------------
# POST /api/chat/sessions + GET /api/chat/sessions
# ---------------------------------------------------------------------------

class TestCreateAndListSessions:

    def test_create_session_returns_id(self, client: TestClient) -> None:
        """POST /api/chat/sessions creates a session and returns its id."""
        resp = client.post("/api/chat/sessions", json={"title": "Minha sessão"})
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert "id" in data["session"]
        assert data["session"]["title"] == "Minha sessão"

    def test_list_sessions_after_create(self, client: TestClient) -> None:
        """After creating a session, list returns it."""
        client.post("/api/chat/sessions", json={"title": "Sessão 1"})
        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["title"] == "Sessão 1"

    def test_get_session_not_found(self, client: TestClient) -> None:
        """GET /api/chat/sessions/{id} returns 404 for unknown id."""
        resp = client.get("/api/chat/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_session(self, client: TestClient) -> None:
        """DELETE /api/chat/sessions/{id} removes the session."""
        create_resp = client.post("/api/chat/sessions", json={})
        session_id = create_resp.json()["session"]["id"]

        del_resp = client.delete(f"/api/chat/sessions/{session_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["ok"] is True

        # Session should no longer appear
        list_resp = client.get("/api/chat/sessions")
        assert list_resp.json()["sessions"] == []

    def test_rename_session(self, client: TestClient) -> None:
        """PUT /api/chat/sessions/{id}/title updates the session title."""
        create_resp = client.post("/api/chat/sessions", json={"title": "Antigo"})
        session_id = create_resp.json()["session"]["id"]

        put_resp = client.put(
            f"/api/chat/sessions/{session_id}/title",
            json={"title": "Novo título"},
        )
        assert put_resp.status_code == 200

        get_resp = client.get(f"/api/chat/sessions/{session_id}")
        assert get_resp.json()["session"]["title"] == "Novo título"


# ---------------------------------------------------------------------------
# GET /api/chat/memory — empty
# ---------------------------------------------------------------------------

class TestGetMemoryEmpty:

    def test_returns_empty_list(self, client: TestClient) -> None:
        """GET /api/chat/memory returns [] when no memories exist."""
        resp = client.get("/api/chat/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert data["memories"] == []


# ---------------------------------------------------------------------------
# POST /api/chat/memory + GET /api/chat/memory
# ---------------------------------------------------------------------------

class TestPostAndRetrieveMemory:

    def test_post_memory_returns_entry(self, client: TestClient) -> None:
        """POST /api/chat/memory returns the created memory entry."""
        resp = client.post("/api/chat/memory", json={"text": "Pesquisador foca em NLP"})
        assert resp.status_code == 200
        data = resp.json()
        assert "memory" in data
        assert data["memory"]["text"] == "Pesquisador foca em NLP"
        assert "id" in data["memory"]

    def test_post_memory_appears_in_list(self, client: TestClient) -> None:
        """After POST /api/chat/memory, GET returns the same entry."""
        client.post("/api/chat/memory", json={"text": "Fato importante"})
        resp = client.get("/api/chat/memory")
        memories = resp.json()["memories"]
        assert len(memories) == 1
        assert memories[0]["text"] == "Fato importante"

    def test_post_memory_empty_text_returns_400(self, client: TestClient) -> None:
        """POST /api/chat/memory with empty text returns 400."""
        resp = client.post("/api/chat/memory", json={"text": "   "})
        assert resp.status_code == 400

    def test_delete_memory(self, client: TestClient) -> None:
        """DELETE /api/chat/memory/{id} removes the memory."""
        create_resp = client.post("/api/chat/memory", json={"text": "Para deletar"})
        memory_id = create_resp.json()["memory"]["id"]

        del_resp = client.delete(f"/api/chat/memory/{memory_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["ok"] is True

        list_resp = client.get("/api/chat/memory")
        assert list_resp.json()["memories"] == []

    def test_multiple_memories_returned(self, client: TestClient) -> None:
        """Multiple POST /api/chat/memory calls all appear in GET."""
        client.post("/api/chat/memory", json={"text": "Fato A"})
        client.post("/api/chat/memory", json={"text": "Fato B"})
        resp = client.get("/api/chat/memory")
        texts = {m["text"] for m in resp.json()["memories"]}
        assert texts == {"Fato A", "Fato B"}


# ---------------------------------------------------------------------------
# server/db.py — direct unit tests
# ---------------------------------------------------------------------------

class TestDbDirect:

    def test_create_and_get_session(self, project_root: Path) -> None:
        """db.create_session and db.get_session round-trip correctly."""
        from lutz.server import db as _db

        session = _db.create_session(project_root, "Título direto")
        assert session["title"] == "Título direto"
        assert "id" in session

        retrieved = _db.get_session(project_root, session["id"])
        assert retrieved is not None
        assert retrieved["title"] == "Título direto"
        assert retrieved["messages"] == []

    def test_get_session_not_found_returns_none(self, project_root: Path) -> None:
        """db.get_session returns None for an unknown id."""
        from lutz.server import db as _db
        assert _db.get_session(project_root, "no-such-id") is None

    def test_add_and_list_memory(self, project_root: Path) -> None:
        """db.add_memory and db.list_memory round-trip correctly."""
        from lutz.server import db as _db

        entry = _db.add_memory(project_root, "Facto de teste", None, "manual")
        assert entry["text"] == "Facto de teste"
        assert entry["source"] == "manual"

        memories = _db.list_memory(project_root)
        assert len(memories) == 1
        assert memories[0]["id"] == entry["id"]

    def test_delete_memory_direct(self, project_root: Path) -> None:
        """db.delete_memory removes the entry from the DB."""
        from lutz.server import db as _db

        entry = _db.add_memory(project_root, "Para deletar", None, "manual")
        _db.delete_memory(project_root, entry["id"])
        assert _db.list_memory(project_root) == []

    def test_add_message_to_session(self, project_root: Path) -> None:
        """db.add_message persists a message that db.get_messages returns."""
        from lutz.server import db as _db

        session = _db.create_session(project_root, "Chat")
        _db.add_message(project_root, session["id"], "user", "Olá")
        _db.add_message(project_root, session["id"], "assistant", "Tudo bem!")

        messages = _db.get_messages(project_root, session["id"])
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Olá"
        assert messages[1]["role"] == "assistant"

    def test_update_session_title(self, project_root: Path) -> None:
        """db.update_session_title changes the stored title."""
        from lutz.server import db as _db

        session = _db.create_session(project_root, "Original")
        _db.update_session_title(project_root, session["id"], "Atualizado")
        retrieved = _db.get_session(project_root, session["id"])
        assert retrieved["title"] == "Atualizado"

    def test_delete_session_removes_messages(self, project_root: Path) -> None:
        """db.delete_session cascades to messages (FK ON DELETE CASCADE)."""
        from lutz.server import db as _db

        session = _db.create_session(project_root, "Deletar")
        _db.add_message(project_root, session["id"], "user", "msg")
        _db.delete_session(project_root, session["id"])

        assert _db.get_session(project_root, session["id"]) is None
        assert _db.get_messages(project_root, session["id"]) == []

    def test_replace_auto_memory(self, project_root: Path) -> None:
        """db.replace_auto_memory removes previous auto entries and inserts new ones."""
        from lutz.server import db as _db

        session = _db.create_session(project_root, "Auto")
        sid = session["id"]

        _db.replace_auto_memory(project_root, sid, ["fact 1", "fact 2"], 4)
        memories = _db.list_memory(project_root)
        assert len(memories) == 2
        texts = {m["text"] for m in memories}
        assert texts == {"fact 1", "fact 2"}

        # Replace with new facts — old auto ones must be gone
        _db.replace_auto_memory(project_root, sid, ["fact 3"], 8)
        memories = _db.list_memory(project_root)
        assert len(memories) == 1
        assert memories[0]["text"] == "fact 3"


# ---------------------------------------------------------------------------
# LLMClient — temperature fallback and from_env providers
# ---------------------------------------------------------------------------

class TestLLMClientTemperatureFallback:

    def test_temperature_none_uses_instance_default(self) -> None:
        """complete_messages with temperature=None falls back to instance temperature."""
        from lutz.core.llm_client import LLMClient

        client = LLMClient(
            provider="openai",
            model_id="gpt-4o-mini",
            api_key="dummy",  # pragma: allowlist secret
            max_tokens=100,
            temperature=0.7,
        )

        openai_mock = MagicMock()
        choice = MagicMock()
        choice.message.content = "hello"
        response = MagicMock()
        response.choices = [choice]
        response.usage.prompt_tokens = 5
        response.usage.completion_tokens = 5
        response.usage.total_tokens = 10
        openai_mock.chat.completions.create.return_value = response

        with patch.object(client, "_get_client", return_value=openai_mock):
            client.complete_messages(
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                temperature=None,  # must use instance default 0.7
            )

        call_kwargs = openai_mock.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7

    def test_temperature_kwarg_overrides_instance(self) -> None:
        """Explicit temperature kwarg overrides instance-level temperature."""
        from lutz.core.llm_client import LLMClient

        client = LLMClient(
            provider="openai",
            model_id="gpt-4o-mini",
            api_key="dummy",  # pragma: allowlist secret
            max_tokens=100,
            temperature=0.9,
        )

        openai_mock = MagicMock()
        choice = MagicMock()
        choice.message.content = "hi"
        response = MagicMock()
        response.choices = [choice]
        response.usage.prompt_tokens = 1
        response.usage.completion_tokens = 1
        response.usage.total_tokens = 2
        openai_mock.chat.completions.create.return_value = response

        with patch.object(client, "_get_client", return_value=openai_mock):
            client.complete_messages(
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.1,
            )

        call_kwargs = openai_mock.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.1


class TestLLMClientFromEnv:

    def test_from_env_openai(self) -> None:
        """LLMClient.from_env returns an openai-provider client."""
        from lutz.core.llm_client import LLMClient

        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o",
            "OPENAI_API_KEY": "sk-test",  # pragma: allowlist secret
        }
        client = LLMClient.from_env(env)
        assert client.provider == "openai"
        assert client.model_id == "gpt-4o"

    def test_from_env_openai_missing_key_raises(self) -> None:
        """from_env raises ValueError when OPENAI_API_KEY is absent."""
        from lutz.core.llm_client import LLMClient

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMClient.from_env({"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o"})

    def test_from_env_docker_model_runner(self) -> None:
        """from_env returns a docker_model_runner-provider client with correct defaults."""
        from lutz.core.llm_client import LLMClient

        env = {
            "LLM_PROVIDER": "docker_model_runner",
            "LLM_MODEL": "ai/llama3.2",
        }
        client = LLMClient.from_env(env)
        assert client.provider == "docker_model_runner"
        assert client.model_id == "ai/llama3.2"
        # Default base_url should point to Docker Model Runner
        assert "model-runner.docker.internal" in client._kwargs.get("base_url", "")

    def test_from_env_anthropic(self) -> None:
        """from_env returns an anthropic-provider client."""
        from lutz.core.llm_client import LLMClient

        env = {
            "LLM_PROVIDER": "anthropic",
            "LLM_MODEL": "claude-haiku-4-5-20251001",
            "ANTHROPIC_API_KEY": "test-key",  # pragma: allowlist secret
        }
        client = LLMClient.from_env(env)
        assert client.provider == "anthropic"

    def test_from_env_anthropic_missing_key_raises(self) -> None:
        """from_env raises ValueError when ANTHROPIC_API_KEY is absent."""
        from lutz.core.llm_client import LLMClient

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            LLMClient.from_env({"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-x"})

    def test_from_env_unknown_provider_raises(self) -> None:
        """from_env raises ValueError for an unknown provider."""
        from lutz.core.llm_client import LLMClient

        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            LLMClient.from_env({"LLM_PROVIDER": "unicorn", "LLM_MODEL": "magic"})

    def test_from_env_temperature_defaults(self) -> None:
        """from_env reads LLM_TEMPERATURE from env, defaulting to 0.2."""
        from lutz.core.llm_client import LLMClient

        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o-mini",
            "OPENAI_API_KEY": "sk-test",  # pragma: allowlist secret
        }
        client = LLMClient.from_env(env)
        assert client._kwargs["temperature"] == 0.2

        env["LLM_TEMPERATURE"] = "0.7"
        client2 = LLMClient.from_env(env)
        assert client2._kwargs["temperature"] == 0.7


# ---------------------------------------------------------------------------
# LLMClient — Anthropic complete_messages path
# ---------------------------------------------------------------------------

class TestLLMClientAnthropic:

    def _make_anthropic_client(self) -> object:
        from lutz.core.llm_client import LLMClient
        return LLMClient(
            provider="anthropic",
            model_id="claude-haiku-4-5-20251001",
            api_key="dummy",  # pragma: allowlist secret
            max_tokens=100,
            temperature=0.2,
        )

    def test_anthropic_complete_messages_basic(self) -> None:
        """complete_messages routes to anthropic path and returns text + usage."""
        from lutz.core.llm_client import LLMClient

        client = LLMClient(
            provider="anthropic",
            model_id="claude-haiku",
            api_key="dummy",  # pragma: allowlist secret
            max_tokens=100,
            temperature=0.2,
        )

        anthropic_mock = MagicMock()
        block = MagicMock()
        block.text = "resposta"
        response = MagicMock()
        response.content = [block]
        response.usage.input_tokens = 10
        response.usage.output_tokens = 5
        anthropic_mock.messages.create.return_value = response

        with patch.object(client, "_get_client", return_value=anthropic_mock):
            text, usage = client.complete_messages(
                system="sys",
                messages=[{"role": "user", "content": "oi"}],
            )

        assert text == "resposta"
        assert usage["prompt_tokens"] == 10
        assert usage["completion_tokens"] == 5
        assert usage["total_tokens"] == 15

    def test_anthropic_complete_basic(self) -> None:
        """complete() routes to anthropic path correctly."""
        from lutz.core.llm_client import LLMClient

        client = LLMClient(
            provider="anthropic",
            model_id="claude-haiku",
            api_key="dummy",  # pragma: allowlist secret
            max_tokens=100,
            temperature=0.2,
        )

        anthropic_mock = MagicMock()
        block = MagicMock()
        block.text = "resposta simples"
        response = MagicMock()
        response.content = [block]
        response.usage.input_tokens = 8
        response.usage.output_tokens = 3
        anthropic_mock.messages.create.return_value = response

        with patch.object(client, "_get_client", return_value=anthropic_mock):
            text, usage = client.complete(system="sys", user="pergunta")

        assert text == "resposta simples"
        assert usage["total_tokens"] == 11


# ---------------------------------------------------------------------------
# server/app.py — additional simple API endpoints
# ---------------------------------------------------------------------------

class TestProjectEndpoint:

    def test_get_project(self, client: TestClient, project_root: Path) -> None:
        """GET /api/project returns root path and article/report counts."""
        # Create articles dir with one PDF stub
        arts_dir = project_root / "articles"
        arts_dir.mkdir()
        (arts_dir / "test.pdf").write_bytes(b"%PDF-1.4 stub")

        resp = client.get("/api/project")
        assert resp.status_code == 200
        data = resp.json()
        assert "root" in data
        assert data["articles"] == 1
        assert data["reports"] == 0


class TestArticlesEndpoint:

    def test_list_articles_empty(self, client: TestClient, project_root: Path) -> None:
        """GET /api/articles returns empty list when no articles dir."""
        resp = client.get("/api/articles")
        assert resp.status_code == 200
        assert resp.json()["articles"] == []

    def test_list_articles_with_pdf(self, client: TestClient, project_root: Path) -> None:
        """GET /api/articles lists PDF files in articles/."""
        arts_dir = project_root / "articles"
        arts_dir.mkdir()
        (arts_dir / "paper.pdf").write_bytes(b"%PDF-1.4")

        resp = client.get("/api/articles")
        assert resp.status_code == 200
        arts = resp.json()["articles"]
        assert len(arts) == 1
        assert arts[0]["name"] == "paper.pdf"

    def test_delete_article_not_found(self, client: TestClient) -> None:
        """DELETE /api/articles/{name} returns 404 for a non-existent file."""
        resp = client.delete("/api/articles/nonexistent.pdf")
        assert resp.status_code == 404


class TestPromptsEndpoint:

    def test_list_prompts_empty(self, client: TestClient, project_root: Path) -> None:
        """GET /api/prompts returns empty list when no prompts dir."""
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        assert resp.json()["prompts"] == []

    def test_save_and_get_prompt(self, client: TestClient, project_root: Path) -> None:
        """PUT /api/prompts/{name} saves and GET retrieves the prompt."""
        put_resp = client.put("/api/prompts/triagem", json={"content": "# Triagem\n\nFiltrar..."})
        assert put_resp.status_code == 200

        get_resp = client.get("/api/prompts/triagem")
        assert get_resp.status_code == 200
        assert get_resp.json()["content"] == "# Triagem\n\nFiltrar..."

    def test_get_prompt_not_found(self, client: TestClient) -> None:
        """GET /api/prompts/{name} returns 404 for unknown prompt."""
        resp = client.get("/api/prompts/nao-existe")
        assert resp.status_code == 404


class TestReportsEndpoint:

    def test_list_reports_empty(self, client: TestClient) -> None:
        """GET /api/reports returns empty list when no reports dir."""
        resp = client.get("/api/reports")
        assert resp.status_code == 200
        assert resp.json()["reports"] == []


class TestConfigEndpoint:

    def test_get_config_returns_keys(self, client: TestClient) -> None:
        """GET /api/config returns expected config keys."""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "LLM_PROVIDER" in data
        assert "EMBEDDING_PROVIDER" in data
        assert "has_openai_key" in data


class TestJobsEndpoint:

    def test_list_jobs_empty(self, client: TestClient) -> None:
        """GET /api/jobs returns empty list when no jobs have been created."""
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        assert resp.json()["jobs"] == []

    def test_get_job_not_found(self, client: TestClient) -> None:
        """GET /api/jobs/{id} returns 404 for unknown job."""
        resp = client.get("/api/jobs/nonexistent-job-id")
        assert resp.status_code == 404
