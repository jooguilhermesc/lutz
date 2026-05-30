"""Tests for F6 — file activate/deactivate in the chat system.

Covers:
  - db.set_file_active (true / false)
  - db.list_session_files includes active column
  - PATCH /api/chat/sessions/{session_id}/files/{file_id} (200)
  - PATCH with invalid value (422 / 400)
  - PATCH for non-existent file (404)
  - PATCH for file belonging to another session (404)
  - inactive file excluded from RAG post-filter
  - active file included in RAG post-filter
"""
from __future__ import annotations

import os
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
    from lutz.server.app import app
    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


def _create_session_and_file(root: Path, filename: str = "paper.pdf") -> tuple[str, int]:
    """Helper: create a session and a chat_file record, return (session_id, file_id)."""
    from lutz.server import db as _db
    session = _db.create_session(root, "test session")
    file_id = _db.add_chat_file(root, session["id"], filename)
    return session["id"], file_id


# ---------------------------------------------------------------------------
# db.set_file_active — True
# ---------------------------------------------------------------------------

def test_set_file_active_true(project_root: Path) -> None:
    from lutz.server import db as _db

    session_id, file_id = _create_session_and_file(project_root, "doc.pdf")

    # Deactivate first
    _db.set_file_active(project_root, file_id, False)
    files = _db.list_session_files(project_root, session_id)
    assert files[0]["active"] == 0 or files[0]["active"] is False

    # Reactivate
    _db.set_file_active(project_root, file_id, True)
    files = _db.list_session_files(project_root, session_id)
    assert files[0]["active"] in (1, True)


# ---------------------------------------------------------------------------
# db.set_file_active — False
# ---------------------------------------------------------------------------

def test_set_file_active_false(project_root: Path) -> None:
    from lutz.server import db as _db

    session_id, file_id = _create_session_and_file(project_root, "report.docx")

    # By default active=1; set to inactive
    _db.set_file_active(project_root, file_id, False)
    files = _db.list_session_files(project_root, session_id)
    assert files[0]["active"] == 0 or files[0]["active"] is False


# ---------------------------------------------------------------------------
# db.list_session_files includes active column
# ---------------------------------------------------------------------------

def test_list_files_includes_active_column(project_root: Path) -> None:
    from lutz.server import db as _db

    session_id, _ = _create_session_and_file(project_root, "thesis.pdf")
    files = _db.list_session_files(project_root, session_id)
    assert len(files) == 1
    assert "active" in files[0], "active column must be present in list_session_files result"
    # Default value must be truthy
    assert files[0]["active"] in (1, True)


# ---------------------------------------------------------------------------
# PATCH /api/chat/sessions/{session_id}/files/{file_id} — 200
# ---------------------------------------------------------------------------

def test_patch_file_active_endpoint(client: TestClient, project_root: Path) -> None:
    from lutz.server import db as _db

    session_id, file_id = _create_session_and_file(project_root, "active_test.pdf")

    resp = client.patch(
        f"/api/chat/sessions/{session_id}/files/{file_id}",
        json={"active": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == file_id
    assert body["active"] in (0, False)

    # Verify persisted
    files = _db.list_session_files(project_root, session_id)
    assert files[0]["active"] in (0, False)


# ---------------------------------------------------------------------------
# PATCH with invalid value → 422 or 400
# ---------------------------------------------------------------------------

def test_patch_file_active_invalid_value(client: TestClient, project_root: Path) -> None:
    session_id, file_id = _create_session_and_file(project_root, "badval.pdf")

    resp = client.patch(
        f"/api/chat/sessions/{session_id}/files/{file_id}",
        json={"active": "maybe"},
    )
    assert resp.status_code in (400, 422), f"Expected 400 or 422, got {resp.status_code}"


# ---------------------------------------------------------------------------
# PATCH for non-existent file → 404
# ---------------------------------------------------------------------------

def test_patch_file_active_not_found(client: TestClient, project_root: Path) -> None:
    from lutz.server import db as _db
    session = _db.create_session(project_root, "empty session")

    resp = client.patch(
        f"/api/chat/sessions/{session['id']}/files/99999",
        json={"active": False},
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# PATCH for file belonging to another session → 404
# ---------------------------------------------------------------------------

def test_patch_file_wrong_session(client: TestClient, project_root: Path) -> None:
    from lutz.server import db as _db

    session_id, file_id = _create_session_and_file(project_root, "other.pdf")
    other_session = _db.create_session(project_root, "other session")

    resp = client.patch(
        f"/api/chat/sessions/{other_session['id']}/files/{file_id}",
        json={"active": False},
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# RAG retrieval: inactive file excluded
# ---------------------------------------------------------------------------

def test_inactive_file_excluded_from_rag(project_root: Path) -> None:
    """Chunks from inactive files must not appear in RAG retrieval results."""
    from lutz.server import db as _db
    from lutz.server.app import _filter_chunks_by_active_files

    session_id, file_id = _create_session_and_file(project_root, "inactive.pdf")
    _db.set_file_active(project_root, file_id, False)

    active_names = _db.get_active_filenames(project_root, session_id)

    chunks = [
        {"filename": "inactive.pdf", "page": 1, "text": "secret"},
        {"filename": "active.pdf", "page": 1, "text": "visible"},
    ]
    # active.pdf is not in the DB for this session, so treat all-files-not-in-DB as active
    # Only inactive.pdf is explicitly inactive
    filtered = _filter_chunks_by_active_files(chunks, active_names)
    filenames = {c["filename"] for c in filtered}
    assert "inactive.pdf" not in filenames, "inactive file chunks must be excluded"


# ---------------------------------------------------------------------------
# RAG retrieval: active file included
# ---------------------------------------------------------------------------

def test_active_file_included_in_rag(project_root: Path) -> None:
    """Chunks from active files must pass through RAG post-filter."""
    from lutz.server import db as _db
    from lutz.server.app import _filter_chunks_by_active_files

    session_id, file_id = _create_session_and_file(project_root, "active.pdf")
    _db.set_file_active(project_root, file_id, True)

    active_names = _db.get_active_filenames(project_root, session_id)

    chunks = [{"filename": "active.pdf", "page": 1, "text": "important finding"}]
    filtered = _filter_chunks_by_active_files(chunks, active_names)
    assert len(filtered) == 1
    assert filtered[0]["filename"] == "active.pdf"


# ---------------------------------------------------------------------------
# Edge case: empty active_names set allows unknown files through
# ---------------------------------------------------------------------------

def test_filter_with_no_session_files_passes_all(project_root: Path) -> None:
    """When no files are registered for a session, get_active_filenames returns None
    and all chunks pass through the filter unchanged."""
    from lutz.server import db as _db
    from lutz.server.app import _filter_chunks_by_active_files

    session = _db.create_session(project_root, "no files session")
    active_names = _db.get_active_filenames(project_root, session["id"])

    assert active_names is None, "no registered files → None sentinel"

    chunks = [
        {"filename": "unregistered.pdf", "page": 1, "text": "some text"},
    ]
    filtered = _filter_chunks_by_active_files(chunks, active_names)
    assert len(filtered) == 1, "chunks from unregistered files should not be filtered out"
