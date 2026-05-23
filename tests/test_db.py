"""Tests for lutz.server.db — SQLite persistence layer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from lutz.server import db


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path: Path, monkeypatch) -> Path:
    """Isolated project root with db path pointing to a temp file."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)

    # Patch get_db_path so all db calls use the temp directory.
    monkeypatch.setattr(db, "get_db_path", lambda r: r / ".lutz" / "lutz.db")

    db.init_db(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


def test_init_db_creates_tables(root: Path) -> None:
    with db.get_db(root) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    expected = {
        "projects",
        "article_projects",
        "datasets",
        "chat_sessions",
        "chat_messages",
        "chat_memory",
    }
    assert expected.issubset(tables)


def test_init_db_idempotent(root: Path) -> None:
    """Calling init_db twice must not raise."""
    db.init_db(root)
    db.init_db(root)


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_projects(root: Path) -> None:
    p = db.create_project(root, "My project", "#ff0000", "flask")
    assert p["id"]
    assert p["name"] == "My project"
    assert p["color"] == "#ff0000"
    assert p["icon"] == "flask"

    projects = db.list_projects(root)
    assert len(projects) == 1
    assert projects[0]["id"] == p["id"]


def test_get_project(root: Path) -> None:
    p = db.create_project(root, "P1", "#000", "folder")
    fetched = db.get_project(root, p["id"])
    assert fetched is not None
    assert fetched["name"] == "P1"


def test_get_project_not_found(root: Path) -> None:
    assert db.get_project(root, "nonexistent") is None


def test_update_project(root: Path) -> None:
    p = db.create_project(root, "Old name", "#aaa", "folder")
    updated = db.update_project(root, p["id"], "New name", "#bbb", "star")
    assert updated["name"] == "New name"
    assert updated["color"] == "#bbb"
    assert updated["icon"] == "star"

    fetched = db.get_project(root, p["id"])
    assert fetched["name"] == "New name"


def test_update_project_not_found(root: Path) -> None:
    with pytest.raises(Exception):
        db.update_project(root, "bad-id", "x", "#000", "folder")


def test_delete_project(root: Path) -> None:
    p = db.create_project(root, "ToDelete", "#000", "folder")
    db.delete_project(root, p["id"])
    assert db.get_project(root, p["id"]) is None
    assert db.list_projects(root) == []


def test_list_projects_counts(root: Path) -> None:
    p = db.create_project(root, "P", "#000", "folder")
    db.add_article_to_project(root, p["id"], "article1.pdf")
    db.add_article_to_project(root, p["id"], "article2.pdf")

    projects = db.list_projects(root)
    assert projects[0]["article_count"] == 2
    assert projects[0]["dataset_count"] == 0


# ---------------------------------------------------------------------------
# Article-project association
# ---------------------------------------------------------------------------


def test_add_and_list_project_articles(root: Path) -> None:
    p = db.create_project(root, "P", "#000", "folder")
    db.add_article_to_project(root, p["id"], "a.pdf")
    db.add_article_to_project(root, p["id"], "b.pdf")

    articles = db.list_project_articles(root, p["id"])
    assert set(articles) == {"a.pdf", "b.pdf"}


def test_remove_article_from_project(root: Path) -> None:
    p = db.create_project(root, "P", "#000", "folder")
    db.add_article_to_project(root, p["id"], "a.pdf")
    db.remove_article_from_project(root, p["id"], "a.pdf")

    assert db.list_project_articles(root, p["id"]) == []


def test_article_project_cascade_delete(root: Path) -> None:
    p = db.create_project(root, "P", "#000", "folder")
    db.add_article_to_project(root, p["id"], "x.pdf")
    db.delete_project(root, p["id"])

    # Foreign key cascade should have removed the association row
    with db.get_db(root) as conn:
        rows = conn.execute(
            "SELECT * FROM article_projects WHERE project_id=?", (p["id"],)
        ).fetchall()
    assert rows == []


# ---------------------------------------------------------------------------
# Datasets CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_datasets(root: Path) -> None:
    d = db.create_dataset(
        root,
        name="DS1",
        source="query",
        project_id=None,
        query="SELECT 1",
        columns=["col1", "col2"],
        rows=[[1, "a"], [2, "b"]],
        row_count=2,
        metadata={"note": "test"},
    )
    assert d["id"]
    assert d["name"] == "DS1"
    assert d["row_count"] == 2

    datasets = db.list_datasets(root)
    assert len(datasets) == 1
    # list must NOT include rows_json data for performance
    assert "rows" not in datasets[0]


def test_get_dataset_includes_rows(root: Path) -> None:
    d = db.create_dataset(
        root,
        name="DS2",
        source="upload",
        project_id=None,
        query=None,
        columns=["x"],
        rows=[[42]],
        row_count=1,
        metadata=None,
    )
    fetched = db.get_dataset(root, d["id"])
    assert fetched is not None
    assert fetched["rows"] == [[42]]
    assert fetched["columns"] == ["x"]


def test_get_dataset_not_found(root: Path) -> None:
    assert db.get_dataset(root, "missing") is None


def test_delete_dataset(root: Path) -> None:
    d = db.create_dataset(root, "D", "q", None, None, [], [], 0, None)
    db.delete_dataset(root, d["id"])
    assert db.get_dataset(root, d["id"]) is None


def test_list_datasets_filter_by_project(root: Path) -> None:
    p = db.create_project(root, "P", "#000", "folder")
    db.create_dataset(root, "D1", "q", p["id"], None, [], [], 0, None)
    db.create_dataset(root, "D2", "q", None, None, [], [], 0, None)

    filtered = db.list_datasets(root, project_id=p["id"])
    assert len(filtered) == 1
    assert filtered[0]["name"] == "D1"


# ---------------------------------------------------------------------------
# Chat sessions CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_sessions(root: Path) -> None:
    s = db.create_session(root, "Test session")
    assert s["id"]
    assert s["title"] == "Test session"

    sessions = db.list_sessions(root)
    assert len(sessions) == 1
    assert "message_count" in sessions[0]


def test_get_session_includes_messages(root: Path) -> None:
    s = db.create_session(root, "S1")
    db.add_message(root, s["id"], "user", "hello")
    db.add_message(root, s["id"], "assistant", "world")

    fetched = db.get_session(root, s["id"])
    assert fetched is not None
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][0]["role"] == "user"
    assert fetched["messages"][1]["content"] == "world"


def test_get_session_not_found(root: Path) -> None:
    assert db.get_session(root, "nope") is None


def test_update_session_title(root: Path) -> None:
    s = db.create_session(root, "Old")
    db.update_session_title(root, s["id"], "New title")
    assert db.get_session(root, s["id"])["title"] == "New title"


def test_delete_session_cascades_messages(root: Path) -> None:
    s = db.create_session(root, "S")
    db.add_message(root, s["id"], "user", "hi")
    db.delete_session(root, s["id"])

    assert db.get_session(root, s["id"]) is None
    assert db.get_messages(root, s["id"]) == []


def test_add_message_with_sources(root: Path) -> None:
    s = db.create_session(root, "S")
    sources = [{"filename": "paper.pdf", "page": 1}]
    msg = db.add_message(root, s["id"], "assistant", "answer", sources=sources)
    assert msg["id"]

    messages = db.get_messages(root, s["id"])
    assert messages[0]["sources"] == sources


def test_update_session_updated_at(root: Path) -> None:
    import time

    s = db.create_session(root, "S")
    old_ts = s["updated_at"]
    time.sleep(0.01)
    db.update_session_updated_at(root, s["id"])

    fetched = db.get_session(root, s["id"])
    assert fetched["updated_at"] >= old_ts


# ---------------------------------------------------------------------------
# Chat memory CRUD
# ---------------------------------------------------------------------------


def test_add_and_list_memory(root: Path) -> None:
    m = db.add_memory(root, "Important fact", None, "manual")
    assert m["id"]
    assert m["text"] == "Important fact"
    assert m["source"] == "manual"

    memories = db.list_memory(root)
    assert len(memories) == 1


def test_delete_memory(root: Path) -> None:
    m = db.add_memory(root, "Fact", None, "manual")
    db.delete_memory(root, m["id"])
    assert db.list_memory(root) == []


def test_replace_auto_memory(root: Path) -> None:
    s = db.create_session(root, "S")
    # Seed some manual and some auto memories
    db.add_memory(root, "manual fact", None, "manual")
    db.add_memory(root, "old auto", s["id"], "auto", extracted_at_count=2)

    # Replace auto memories for this session
    db.replace_auto_memory(root, s["id"], ["new fact 1", "new fact 2"], message_count=4)

    memories = db.list_memory(root)
    # Manual memory should survive; old auto should be gone; 2 new ones added
    texts = {m["text"] for m in memories}
    assert "manual fact" in texts
    assert "old auto" not in texts
    assert "new fact 1" in texts
    assert "new fact 2" in texts


def test_replace_auto_memory_does_not_duplicate(root: Path) -> None:
    """Calling replace_auto_memory twice replaces, not appends."""
    s = db.create_session(root, "S")
    db.replace_auto_memory(root, s["id"], ["fact A"], message_count=4)
    db.replace_auto_memory(root, s["id"], ["fact B"], message_count=4)

    auto = [m for m in db.list_memory(root) if m["source"] == "auto"]
    assert len(auto) == 1
    assert auto[0]["text"] == "fact B"


# ---------------------------------------------------------------------------
# JSON migration
# ---------------------------------------------------------------------------


def test_migrate_sessions_from_json(tmp_path: Path, monkeypatch) -> None:
    """migrate_sessions imports existing *.json files into chat_sessions table."""
    lutz_dir = tmp_path / ".lutz"
    sessions_dir = lutz_dir / "chat_sessions"
    sessions_dir.mkdir(parents=True)

    session_data = {
        "id": "20240101_120000_000000",
        "title": "Migrated session",
        "created_at": "2024-01-01T12:00:00+00:00",
        "updated_at": "2024-01-01T12:05:00+00:00",
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    }
    (sessions_dir / "20240101_120000_000000.json").write_text(
        json.dumps(session_data), encoding="utf-8"
    )

    monkeypatch.setattr(db, "get_db_path", lambda r: r / ".lutz" / "lutz.db")
    db.init_db(tmp_path)

    sessions = db.list_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0]["title"] == "Migrated session"
    assert sessions[0]["message_count"] == 2

    fetched = db.get_session(tmp_path, "20240101_120000_000000")
    assert fetched is not None
    assert len(fetched["messages"]) == 2


def test_migrate_memory_from_json(tmp_path: Path, monkeypatch) -> None:
    """migrate_memory imports existing chat_memory.json into chat_memory table."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)

    memory_data = {
        "memories": [
            {
                "id": "mem_001",
                "text": "User likes python",
                "session_id": "",
                "created_at": "2024-01-01T10:00:00+00:00",
                "source": "manual",
            }
        ]
    }
    (lutz_dir / "chat_memory.json").write_text(
        json.dumps(memory_data), encoding="utf-8"
    )

    monkeypatch.setattr(db, "get_db_path", lambda r: r / ".lutz" / "lutz.db")
    db.init_db(tmp_path)

    memories = db.list_memory(tmp_path)
    assert len(memories) == 1
    assert memories[0]["text"] == "User likes python"
    assert memories[0]["id"] == "mem_001"


def test_migrate_sessions_skipped_when_table_not_empty(tmp_path: Path, monkeypatch) -> None:
    """Migration must not insert duplicates if table already has data."""
    lutz_dir = tmp_path / ".lutz"
    sessions_dir = lutz_dir / "chat_sessions"
    sessions_dir.mkdir(parents=True)

    session_data = {
        "id": "sess_1",
        "title": "Already there",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "messages": [],
    }
    (sessions_dir / "sess_1.json").write_text(json.dumps(session_data), encoding="utf-8")

    monkeypatch.setattr(db, "get_db_path", lambda r: r / ".lutz" / "lutz.db")
    db.init_db(tmp_path)

    # init_db again (simulates server restart)
    db.init_db(tmp_path)

    sessions = db.list_sessions(tmp_path)
    assert len(sessions) == 1  # no duplicates
