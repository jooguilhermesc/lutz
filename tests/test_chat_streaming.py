"""Tests for SSE streaming chat endpoint and LLMClient.stream_messages().

Covers:
  1. POST /api/chat/sessions/{id}/message/stream → Content-Type: text/event-stream
  2. Response contains at least one event type=token
  3. Response contains event type=done
  4. When RAG returns sources, response contains event type=sources
  5. LLMClient.stream_messages() with OpenAI mock → yields strings
  6. LLMClient.stream_messages() fallback → emits complete text as one token
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

def _parse_sse_events(raw: bytes) -> list[dict]:
    """Parse SSE text/event-stream body into a list of JSON dicts."""
    events = []
    for block in raw.decode().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
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
    import os
    from lutz.server.app import app

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


@pytest.fixture()
def session_id(client: TestClient) -> str:
    resp = client.post("/api/chat/sessions", json={})
    assert resp.status_code == 200
    return resp.json()["session"]["id"]


# ---------------------------------------------------------------------------
# Helpers: mock LLMClient.stream_messages to yield a token
# ---------------------------------------------------------------------------

def _make_stream_mock(tokens: list[str]):
    """Return a generator that yields the given tokens."""
    def _gen(*args, **kwargs):
        yield from tokens
    return _gen


def _fake_context(*args, **kwargs) -> dict:
    """Return a minimal context dict to avoid any real API calls."""
    return {
        "system": "You are a helpful assistant.",
        "temperature": 0.2,
        "sources": [],
        "thinking_config": None,
    }


# ---------------------------------------------------------------------------
# 1. Content-Type is text/event-stream
# ---------------------------------------------------------------------------

class TestStreamEndpointContentType:

    def test_stream_endpoint_returns_event_stream(
        self, client: TestClient, session_id: str
    ) -> None:
        """POST /stream returns Content-Type: text/event-stream."""
        with (
            patch("lutz.server.app._build_chat_context", side_effect=_fake_context),
            patch(
                "lutz.core.llm_client.LLMClient.stream_messages",
                side_effect=_make_stream_mock(["hello"]),
            ),
        ):
            resp = client.post(
                f"/api/chat/sessions/{session_id}/message/stream",
                json={"message": "hi", "options": {}, "language": "pt"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# 2. At least one token event
# ---------------------------------------------------------------------------

class TestStreamEndpointEmitsTokenEvents:

    def test_stream_endpoint_emits_token_events(
        self, client: TestClient, session_id: str
    ) -> None:
        """SSE response includes at least one event with type='token'."""
        with (
            patch("lutz.server.app._build_chat_context", side_effect=_fake_context),
            patch(
                "lutz.core.llm_client.LLMClient.stream_messages",
                side_effect=_make_stream_mock(["Hello", " world"]),
            ),
        ):
            resp = client.post(
                f"/api/chat/sessions/{session_id}/message/stream",
                json={"message": "hi", "options": {}, "language": "pt"},
            )
        events = _parse_sse_events(resp.content)
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) >= 1
        # All token events must have a 'content' key
        assert all("content" in e for e in token_events)


# ---------------------------------------------------------------------------
# 3. Done event at the end
# ---------------------------------------------------------------------------

class TestStreamEndpointEmitsDoneEvent:

    def test_stream_endpoint_emits_done_event(
        self, client: TestClient, session_id: str
    ) -> None:
        """SSE response ends with an event type='done' that carries the session title."""
        with (
            patch("lutz.server.app._build_chat_context", side_effect=_fake_context),
            patch(
                "lutz.core.llm_client.LLMClient.stream_messages",
                side_effect=_make_stream_mock(["answer"]),
            ),
        ):
            resp = client.post(
                f"/api/chat/sessions/{session_id}/message/stream",
                json={"message": "what is gravity?", "options": {}, "language": "pt"},
            )
        events = _parse_sse_events(resp.content)
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert "title" in done_events[0]


# ---------------------------------------------------------------------------
# 4. Sources event when RAG returns results
# ---------------------------------------------------------------------------

class TestStreamEndpointEmitsSourcesEvent:

    def test_stream_endpoint_emits_sources_event(
        self, client: TestClient, session_id: str
    ) -> None:
        """When _build_chat_context returns sources, SSE emits type='sources' event."""
        fake_source = {"filename": "paper.pdf", "page": 1, "text": "Some content here."}

        def _fake_context_with_sources(*args, **kwargs) -> dict:
            return {
                "system": "You are a helpful assistant.",
                "temperature": 0.2,
                "sources": [fake_source],
                "thinking_config": None,
            }

        with (
            patch("lutz.server.app._build_chat_context", side_effect=_fake_context_with_sources),
            patch(
                "lutz.core.llm_client.LLMClient.stream_messages",
                side_effect=_make_stream_mock(["answer with sources"]),
            ),
        ):
            resp = client.post(
                f"/api/chat/sessions/{session_id}/message/stream",
                json={
                    "message": "tell me about paper",
                    "options": {"use_rag": True},
                    "language": "pt",
                },
            )
        events = _parse_sse_events(resp.content)
        sources_events = [e for e in events if e.get("type") == "sources"]
        assert len(sources_events) == 1
        assert isinstance(sources_events[0]["sources"], list)
        assert len(sources_events[0]["sources"]) >= 1


# ---------------------------------------------------------------------------
# 5. LLMClient.stream_messages with OpenAI mock
# ---------------------------------------------------------------------------

class TestLLMClientStreamMessagesOpenAI:

    def test_stream_messages_openai_yields_strings(self) -> None:
        """stream_messages() with OpenAI provider yields string chunks."""
        from lutz.core.llm_client import LLMClient

        llm = LLMClient(
            provider="openai",
            model_id="gpt-4o-mini",
            api_key="test-key",  # pragma: allowlist secret
            max_tokens=100,
            temperature=0.2,
        )

        # Build a mock stream that mimics the OpenAI streaming response
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = None  # last chunk often has None

        mock_stream = MagicMock()
        mock_stream.__iter__ = MagicMock(return_value=iter([chunk1, chunk2, chunk3]))
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream

        with patch.object(llm, "_get_client", return_value=mock_client):
            result = list(llm.stream_messages("system prompt", [{"role": "user", "content": "hi"}]))

        assert result == ["Hello", " world"]


# ---------------------------------------------------------------------------
# 6. LLMClient.stream_messages fallback (unknown provider → complete_messages)
# ---------------------------------------------------------------------------

class TestLLMClientStreamMessagesFallback:

    def test_stream_messages_fallback_emits_full_text(self) -> None:
        """For unsupported providers, stream_messages() yields the full text as one token."""
        from lutz.core.llm_client import LLMClient

        llm = LLMClient(
            provider="openai",  # valid provider so _get_client doesn't fail
            model_id="gpt-4o-mini",
            api_key="test-key",  # pragma: allowlist secret
        )

        with patch.object(llm, "complete_messages", return_value=("full response text", {})):
            # Temporarily force fallback by setting provider to unknown
            llm.provider = "unknown_provider"
            result = list(llm.stream_messages("sys", [{"role": "user", "content": "q"}]))
            llm.provider = "openai"  # restore

        assert result == ["full response text"]
