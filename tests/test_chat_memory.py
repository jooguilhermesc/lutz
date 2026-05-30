"""Tests for F3 Memory Improvements.

Covers:
  - PUT /api/chat/memory/{id} — inline editing
  - db.update_memory() function
  - db.get_memories() with project_path filter
  - db.add_memory() with project_path param
  - project_path column migration (idempotent)
  - GET /api/chat/sessions/{id}/memory — count + estimated_tokens
  - _compact_memories() auto-compaction logic
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


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


# ---------------------------------------------------------------------------
# Test 1: db.update_memory() — updates content and returns updated record
# ---------------------------------------------------------------------------

def test_update_memory_db_function(project_root: Path) -> None:
    from lutz.server import db as _db

    entry = _db.add_memory(project_root, "original text", None, "manual")
    mid = entry["id"]

    updated = _db.update_memory(project_root, mid, "updated text")

    assert updated["id"] == mid
    assert updated["content"] == "updated text"
    assert "updated_at" in updated

    # Verify persistence — re-read from DB
    memories = _db.list_memory(project_root)
    found = next((m for m in memories if m["id"] == mid), None)
    assert found is not None
    assert found["content"] == "updated text"


# ---------------------------------------------------------------------------
# Test 2: PUT /api/chat/memory/{id} endpoint — success
# ---------------------------------------------------------------------------

def test_put_chat_memory_endpoint(client: TestClient, project_root: Path) -> None:
    from lutz.server import db as _db

    entry = _db.add_memory(project_root, "original", None, "manual")
    mid = entry["id"]

    resp = client.put(f"/api/chat/memory/{mid}", json={"content": "edited text"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == mid
    assert body["content"] == "edited text"
    assert "updated_at" in body


# ---------------------------------------------------------------------------
# Test 3: PUT /api/chat/memory/{id} — 404 for unknown id
# ---------------------------------------------------------------------------

def test_put_chat_memory_not_found(client: TestClient) -> None:
    resp = client.put(f"/api/chat/memory/{uuid.uuid4()}", json={"content": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: PUT /api/chat/memory/{id} — 400 when content is empty
# ---------------------------------------------------------------------------

def test_put_chat_memory_empty_content(client: TestClient, project_root: Path) -> None:
    from lutz.server import db as _db

    entry = _db.add_memory(project_root, "original", None, "manual")
    mid = entry["id"]

    resp = client.put(f"/api/chat/memory/{mid}", json={"content": "   "})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 5: project_path column exists and add_memory accepts project_path param
# ---------------------------------------------------------------------------

def test_add_memory_with_project_path(project_root: Path) -> None:
    from lutz.server import db as _db

    entry = _db.add_memory(
        project_root, "scoped fact", None, "manual", project_path="/home/user/proj"
    )
    assert entry["id"]

    # Re-read and verify the column is stored
    memories = _db.get_memories(project_root, session_id=None, project_path="/home/user/proj")
    texts = [m["content"] for m in memories]
    assert "scoped fact" in texts


# ---------------------------------------------------------------------------
# Test 6: get_memories() filters by project_path
# ---------------------------------------------------------------------------

def test_get_memories_filters_by_project_path(project_root: Path) -> None:
    from lutz.server import db as _db

    _db.add_memory(project_root, "proj A fact", None, "manual", project_path="/proj/a")
    _db.add_memory(project_root, "proj B fact", None, "manual", project_path="/proj/b")
    _db.add_memory(project_root, "global fact", None, "manual")

    proj_a = _db.get_memories(project_root, session_id=None, project_path="/proj/a")
    proj_b = _db.get_memories(project_root, session_id=None, project_path="/proj/b")

    proj_a_texts = [m["content"] for m in proj_a]
    proj_b_texts = [m["content"] for m in proj_b]

    assert "proj A fact" in proj_a_texts
    assert "proj B fact" not in proj_a_texts
    assert "proj B fact" in proj_b_texts
    assert "proj A fact" not in proj_b_texts


# ---------------------------------------------------------------------------
# Test 7: GET /api/chat/sessions/{id}/memory returns count + estimated_tokens
# ---------------------------------------------------------------------------

def test_session_memory_endpoint_returns_stats(client: TestClient, project_root: Path) -> None:
    from lutz.server import db as _db

    session = _db.create_session(project_root, "test session")
    sid = session["id"]

    _db.add_memory(project_root, "fact one about research", sid, "manual")
    _db.add_memory(project_root, "fact two about methodology", sid, "manual")

    resp = client.get(f"/api/chat/sessions/{sid}/memory")
    assert resp.status_code == 200

    body = resp.json()
    assert "memories" in body
    assert "count" in body
    assert "estimated_tokens" in body
    assert body["count"] == len(body["memories"])
    assert isinstance(body["estimated_tokens"], int)
    assert body["estimated_tokens"] > 0


# ---------------------------------------------------------------------------
# Test 8: _compact_memories skips when token count is below threshold
# ---------------------------------------------------------------------------

def test_compact_memories_skips_when_below_threshold(project_root: Path) -> None:
    from lutz.server import db as _db
    from lutz.server.app import _compact_memories

    session = _db.create_session(project_root, "compact test")
    sid = session["id"]

    # Add a small memory — well below 1500 tokens
    _db.add_memory(project_root, "short fact", sid, "manual")

    # Should return False (no compaction performed)
    result = _compact_memories(project_root, sid)
    assert result is False


# ---------------------------------------------------------------------------
# Test 9: _compact_memories triggers LLM and replaces memories when above threshold
# ---------------------------------------------------------------------------

def test_compact_memories_triggers_when_above_threshold(project_root: Path) -> None:
    from lutz.server import db as _db
    from lutz.server.app import _compact_memories

    session = _db.create_session(project_root, "compact trigger test")
    sid = session["id"]

    # Add many long memories to exceed 1500 tokens (rough: words * 1.3)
    # 400 words * 1.3 = 520 tokens each, 3 entries = 1560 tokens total (> 1500)
    long_text = "research finding about methodology analysis " * 80
    for _ in range(3):
        _db.add_memory(project_root, long_text, sid, "manual")

    mock_llm = MagicMock()
    mock_llm.complete.return_value = (
        "- Key research finding\n- Important methodology note\n- Researcher preference noted",
        {"total_tokens": 50},
    )

    with patch("lutz.server.app._get_llm_for_compaction", return_value=mock_llm):
        result = _compact_memories(project_root, sid)

    assert result is True
    # After compaction, memories should be replaced with bullet points
    memories_after = _db.list_memory(project_root)
    session_mems = [m for m in memories_after if m.get("session_id") == sid]
    assert len(session_mems) >= 1
    # The long original texts should be gone
    for m in session_mems:
        assert m["content"] != long_text


# ---------------------------------------------------------------------------
# Test 10: project_path migration is idempotent (safe to call init_db twice)
# ---------------------------------------------------------------------------

def test_project_path_column_migration_is_idempotent(project_root: Path) -> None:
    from lutz.server import db as _db

    # Calling init_db a second time must not raise
    _db.init_db(project_root)
    _db.init_db(project_root)

    # Should still be able to write with project_path
    entry = _db.add_memory(project_root, "idempotent test", None, "manual", project_path="/test")
    assert entry["id"]
