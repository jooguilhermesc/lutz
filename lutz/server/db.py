"""SQLite persistence layer for Lutz web server."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path(root: Path) -> Path:
    return root / ".lutz" / "lutz.db"


@contextmanager
def get_db(root: Path):
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(get_db_path(root)), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#6366f1',
    icon TEXT NOT NULL DEFAULT 'folder',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_projects (
    article_path TEXT NOT NULL,
    project_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (article_path, project_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    project_id TEXT,
    query TEXT,
    columns_json TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Nova conversa',
    project_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_memory (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    session_id TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    extracted_at_count INTEGER,
    created_at TEXT NOT NULL
);
"""


def init_db(root: Path) -> None:
    """Create tables and migrate existing JSON data."""
    db_path = get_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db(root) as conn:
        for statement in _SCHEMA.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(stmt)

        migrate_sessions(root, conn)
        migrate_memory(root, conn)


def migrate_sessions(root: Path, conn: sqlite3.Connection) -> None:
    """Migrate .lutz/chat_sessions/*.json into chat_sessions + chat_messages tables."""
    # Only migrate when table is empty
    count = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
    if count > 0:
        return

    sessions_dir = root / ".lutz" / "chat_sessions"
    if not sessions_dir.exists():
        return

    for f in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sid = data.get("id", f.stem)
            title = data.get("title", "Nova conversa")
            created_at = data.get("created_at", _now())
            updated_at = data.get("updated_at", _now())

            conn.execute(
                "INSERT OR IGNORE INTO chat_sessions (id, title, project_id, created_at, updated_at) "
                "VALUES (?, ?, NULL, ?, ?)",
                (sid, title, created_at, updated_at),
            )

            for msg in data.get("messages", []):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                sources = msg.get("sources")
                sources_json = json.dumps(sources) if sources is not None else None
                msg_created_at = msg.get("created_at", created_at)
                conn.execute(
                    "INSERT OR IGNORE INTO chat_messages "
                    "(id, session_id, role, content, sources_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), sid, role, content, sources_json, msg_created_at),
                )
        except Exception:
            pass  # skip malformed files


def migrate_memory(root: Path, conn: sqlite3.Connection) -> None:
    """Migrate .lutz/chat_memory.json into chat_memory table."""
    # Only migrate when table is empty
    count = conn.execute("SELECT COUNT(*) FROM chat_memory").fetchone()[0]
    if count > 0:
        return

    memory_path = root / ".lutz" / "chat_memory.json"
    if not memory_path.exists():
        return

    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
        memories = data.get("memories", [])
        for m in memories:
            mid = m.get("id", str(uuid.uuid4()))
            text = m.get("text", "")
            session_id = m.get("session_id") or None
            source = m.get("source", "manual")
            extracted_at_count = m.get("extracted_at_count")
            created_at = m.get("created_at", _now())
            conn.execute(
                "INSERT OR IGNORE INTO chat_memory "
                "(id, text, session_id, source, extracted_at_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mid, text, session_id, source, extracted_at_count, created_at),
            )
    except Exception:
        pass  # skip malformed file


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def list_projects(root: Path) -> list[dict]:
    with get_db(root) as conn:
        rows = conn.execute(
            """
            SELECT
                p.*,
                COUNT(DISTINCT ap.article_path) AS article_count,
                COUNT(DISTINCT d.id)             AS dataset_count
            FROM projects p
            LEFT JOIN article_projects ap ON ap.project_id = p.id
            LEFT JOIN datasets d          ON d.project_id  = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_project(root: Path, name: str, color: str, icon: str) -> dict:
    now = _now()
    pid = str(uuid.uuid4())
    with get_db(root) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, color, icon, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, color, icon, now, now),
        )
    return get_project(root, pid)  # type: ignore[return-value]


def update_project(root: Path, project_id: str, name: str, color: str, icon: str) -> dict:
    now = _now()
    with get_db(root) as conn:
        result = conn.execute(
            "UPDATE projects SET name=?, color=?, icon=?, updated_at=? WHERE id=?",
            (name, color, icon, now, project_id),
        )
        if result.rowcount == 0:
            raise ValueError(f"Project {project_id!r} not found")
    fetched = get_project(root, project_id)
    if fetched is None:
        raise ValueError(f"Project {project_id!r} not found after update")
    return fetched


def delete_project(root: Path, project_id: str) -> None:
    with get_db(root) as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))


def get_project(root: Path, project_id: str) -> dict | None:
    with get_db(root) as conn:
        row = conn.execute(
            """
            SELECT
                p.*,
                COUNT(DISTINCT ap.article_path) AS article_count,
                COUNT(DISTINCT d.id)             AS dataset_count
            FROM projects p
            LEFT JOIN article_projects ap ON ap.project_id = p.id
            LEFT JOIN datasets d          ON d.project_id  = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (project_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_project_articles(root: Path, project_id: str) -> list[str]:
    with get_db(root) as conn:
        rows = conn.execute(
            "SELECT article_path FROM article_projects WHERE project_id=? ORDER BY added_at",
            (project_id,),
        ).fetchall()
    return [r["article_path"] for r in rows]


def add_article_to_project(root: Path, project_id: str, article_path: str) -> None:
    now = _now()
    with get_db(root) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO article_projects (article_path, project_id, added_at) "
            "VALUES (?, ?, ?)",
            (article_path, project_id, now),
        )


def remove_article_from_project(root: Path, project_id: str, article_path: str) -> None:
    with get_db(root) as conn:
        conn.execute(
            "DELETE FROM article_projects WHERE project_id=? AND article_path=?",
            (project_id, article_path),
        )


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


def list_datasets(root: Path, project_id: str | None = None) -> list[dict]:
    query = (
        "SELECT id, name, source, project_id, query, columns_json, row_count, "
        "metadata_json, created_at FROM datasets"
    )
    params: list[Any] = []
    if project_id is not None:
        query += " WHERE project_id=?"
        params.append(project_id)
    query += " ORDER BY created_at DESC"

    with get_db(root) as conn:
        rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        d = _row_to_dict(r)
        d["columns"] = json.loads(d.pop("columns_json", "[]") or "[]")
        if d.get("metadata_json"):
            d["metadata"] = json.loads(d["metadata_json"])
        else:
            d["metadata"] = None
        d.pop("metadata_json", None)
        result.append(d)
    return result


def create_dataset(
    root: Path,
    name: str,
    source: str,
    project_id: str | None,
    query: str | None,
    columns: list,
    rows: list,
    row_count: int,
    metadata: dict | None,
) -> dict:
    now = _now()
    did = str(uuid.uuid4())
    columns_json = json.dumps(columns)
    rows_json = json.dumps(rows)
    metadata_json = json.dumps(metadata) if metadata is not None else None

    with get_db(root) as conn:
        conn.execute(
            "INSERT INTO datasets "
            "(id, name, source, project_id, query, columns_json, rows_json, row_count, metadata_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (did, name, source, project_id, query, columns_json, rows_json, row_count, metadata_json, now),
        )

    fetched = get_dataset(root, did)
    if fetched is None:
        raise RuntimeError("Dataset creation failed")
    return fetched


def get_dataset(root: Path, dataset_id: str) -> dict | None:
    with get_db(root) as conn:
        row = conn.execute(
            "SELECT * FROM datasets WHERE id=?", (dataset_id,)
        ).fetchone()
    if row is None:
        return None
    d = _row_to_dict(row)
    d["columns"] = json.loads(d.pop("columns_json", "[]") or "[]")
    d["rows"] = json.loads(d.pop("rows_json", "[]") or "[]")
    if d.get("metadata_json"):
        d["metadata"] = json.loads(d["metadata_json"])
    else:
        d["metadata"] = None
    d.pop("metadata_json", None)
    return d


def delete_dataset(root: Path, dataset_id: str) -> None:
    with get_db(root) as conn:
        conn.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))


# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------


def list_sessions(root: Path) -> list[dict]:
    with get_db(root) as conn:
        rows = conn.execute(
            """
            SELECT
                s.id, s.title, s.project_id, s.created_at, s.updated_at,
                COUNT(m.id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            """
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_session(root: Path, title: str) -> dict:
    now = _now()
    sid = str(uuid.uuid4())
    with get_db(root) as conn:
        conn.execute(
            "INSERT INTO chat_sessions (id, title, project_id, created_at, updated_at) "
            "VALUES (?, ?, NULL, ?, ?)",
            (sid, title, now, now),
        )
    return {
        "id": sid,
        "title": title,
        "project_id": None,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def get_session(root: Path, session_id: str) -> dict | None:
    with get_db(root) as conn:
        row = conn.execute(
            "SELECT id, title, project_id, created_at, updated_at "
            "FROM chat_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        session = _row_to_dict(row)
        msg_rows = conn.execute(
            "SELECT id, role, content, sources_json, created_at "
            "FROM chat_messages WHERE session_id=? ORDER BY created_at, rowid",
            (session_id,),
        ).fetchall()

    messages = []
    for mr in msg_rows:
        md = _row_to_dict(mr)
        raw_sources = md.pop("sources_json", None)
        md["sources"] = json.loads(raw_sources) if raw_sources else None
        messages.append(md)

    session["messages"] = messages
    return session


def update_session_title(root: Path, session_id: str, title: str) -> None:
    now = _now()
    with get_db(root) as conn:
        conn.execute(
            "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=?",
            (title, now, session_id),
        )


def update_session_updated_at(root: Path, session_id: str) -> None:
    now = _now()
    with get_db(root) as conn:
        conn.execute(
            "UPDATE chat_sessions SET updated_at=? WHERE id=?",
            (now, session_id),
        )


def delete_session(root: Path, session_id: str) -> None:
    with get_db(root) as conn:
        conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))


def add_message(
    root: Path,
    session_id: str,
    role: str,
    content: str,
    sources: list | None = None,
) -> dict:
    now = _now()
    mid = str(uuid.uuid4())
    sources_json = json.dumps(sources) if sources is not None else None
    with get_db(root) as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, session_id, role, content, sources_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, session_id, role, content, sources_json, now),
        )
    return {
        "id": mid,
        "session_id": session_id,
        "role": role,
        "content": content,
        "sources": sources,
        "created_at": now,
    }


def get_messages(root: Path, session_id: str) -> list[dict]:
    with get_db(root) as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, sources_json, created_at "
            "FROM chat_messages WHERE session_id=? ORDER BY created_at, rowid",
            (session_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = _row_to_dict(r)
        raw = d.pop("sources_json", None)
        d["sources"] = json.loads(raw) if raw else None
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Chat memory
# ---------------------------------------------------------------------------


def list_memory(root: Path) -> list[dict]:
    with get_db(root) as conn:
        rows = conn.execute(
            "SELECT id, text, session_id, source, extracted_at_count, created_at "
            "FROM chat_memory ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_memory(
    root: Path,
    text: str,
    session_id: str | None,
    source: str,
    extracted_at_count: int | None = None,
) -> dict:
    now = _now()
    mid = str(uuid.uuid4())
    with get_db(root) as conn:
        conn.execute(
            "INSERT INTO chat_memory (id, text, session_id, source, extracted_at_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, text, session_id or None, source, extracted_at_count, now),
        )
    return {
        "id": mid,
        "text": text,
        "session_id": session_id,
        "source": source,
        "extracted_at_count": extracted_at_count,
        "created_at": now,
    }


def delete_memory(root: Path, memory_id: str) -> None:
    with get_db(root) as conn:
        conn.execute("DELETE FROM chat_memory WHERE id=?", (memory_id,))


def replace_auto_memory(
    root: Path,
    session_id: str,
    facts: list[str],
    message_count: int,
) -> None:
    """Remove all auto-memories for session_id, then insert new facts."""
    now = _now()
    with get_db(root) as conn:
        conn.execute(
            "DELETE FROM chat_memory WHERE source='auto' AND session_id=?",
            (session_id,),
        )
        for fact in facts:
            fact = str(fact).strip()[:200]
            if fact:
                conn.execute(
                    "INSERT INTO chat_memory (id, text, session_id, source, extracted_at_count, created_at) "
                    "VALUES (?, ?, ?, 'auto', ?, ?)",
                    (str(uuid.uuid4()), fact, session_id, message_count, now),
                )
