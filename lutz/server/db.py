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
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Nova conversa',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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

    migrate_memory_schema(root)
    migrate_agent_schema(root)
    migrate_chat_files_schema(root)


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
                "INSERT OR IGNORE INTO chat_sessions (id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
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


# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------


def list_sessions(root: Path) -> list[dict]:
    with get_db(root) as conn:
        rows = conn.execute(
            """
            SELECT
                s.id, s.title, s.created_at, s.updated_at,
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
            "INSERT INTO chat_sessions (id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (sid, title, now, now),
        )
    return {
        "id": sid,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def get_session(root: Path, session_id: str) -> dict | None:
    with get_db(root) as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at "
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
            "SELECT id, text, session_id, source, extracted_at_count, created_at, "
            "project_path, COALESCE(content, text) AS content, updated_at "
            "FROM chat_memory ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_memories(
    root: Path,
    session_id: str | None = None,
    project_path: str | None = None,
) -> list[dict]:
    """Return memories, optionally filtered by session_id and/or project_path."""
    clauses: list[str] = []
    params: list[Any] = []
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)
    if project_path is not None:
        clauses.append("project_path = ?")
        params.append(project_path)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db(root) as conn:
        rows = conn.execute(
            f"SELECT id, text, session_id, source, extracted_at_count, created_at, "
            f"project_path, COALESCE(content, text) AS content, updated_at "
            f"FROM chat_memory {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_memory(
    root: Path,
    text: str,
    session_id: str | None,
    source: str,
    extracted_at_count: int | None = None,
    project_path: str | None = None,
) -> dict:
    now = _now()
    mid = str(uuid.uuid4())
    with get_db(root) as conn:
        conn.execute(
            "INSERT INTO chat_memory "
            "(id, text, session_id, source, extracted_at_count, created_at, project_path, content, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, text, session_id or None, source, extracted_at_count, now, project_path, text, now),
        )
    return {
        "id": mid,
        "text": text,
        "content": text,
        "session_id": session_id,
        "source": source,
        "extracted_at_count": extracted_at_count,
        "created_at": now,
        "project_path": project_path,
        "updated_at": now,
    }


def update_memory(root: Path, memory_id: str, content: str) -> dict:
    """Update the content of an existing memory entry. Returns updated record or raises KeyError."""
    now = _now()
    with get_db(root) as conn:
        row = conn.execute(
            "SELECT id, text, session_id, source, extracted_at_count, created_at, project_path "
            "FROM chat_memory WHERE id=?",
            (memory_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Memory {memory_id!r} not found")
        conn.execute(
            "UPDATE chat_memory SET content=?, text=?, updated_at=? WHERE id=?",
            (content, content, now, memory_id),
        )
    d = _row_to_dict(row)
    d["content"] = content
    d["updated_at"] = now
    return d


def delete_memory(root: Path, memory_id: str) -> None:
    with get_db(root) as conn:
        conn.execute("DELETE FROM chat_memory WHERE id=?", (memory_id,))


# ---------------------------------------------------------------------------
# Agent schema migration (Sprint 4 — aditivo, sem DROP)
# ---------------------------------------------------------------------------


def migrate_chat_files_schema(root: Path) -> None:
    """Create chat_files table and add active column (idempotent)."""
    db_path = get_db_path(root)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
            """
        )
        _safe_alter(conn, "ALTER TABLE chat_files ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_memory_schema(root: Path) -> None:
    """Add project_path and content columns to chat_memory (idempotent)."""
    db_path = get_db_path(root)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _safe_alter(conn, "ALTER TABLE chat_memory ADD COLUMN project_path TEXT")
        _safe_alter(conn, "ALTER TABLE chat_memory ADD COLUMN content TEXT")
        _safe_alter(conn, "ALTER TABLE chat_memory ADD COLUMN updated_at TEXT")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_agent_schema(root: Path) -> None:
    """Add agent-related tables and columns to the existing schema (idempotent).

    Each ALTER TABLE is wrapped in try/except so repeated calls are safe.
    """
    db_path = get_db_path(root)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        # New table: researcher preferences
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS researcher_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # Extend chat_sessions with agent state
        _safe_alter(conn, "ALTER TABLE chat_sessions ADD COLUMN agent_plan TEXT")
        _safe_alter(
            conn,
            "ALTER TABLE chat_sessions ADD COLUMN agent_state TEXT DEFAULT 'idle'",
        )

        # Extend chat_messages with agent metadata
        _safe_alter(conn, "ALTER TABLE chat_messages ADD COLUMN tool_calls TEXT")
        _safe_alter(conn, "ALTER TABLE chat_messages ADD COLUMN model_used TEXT")
        _safe_alter(conn, "ALTER TABLE chat_messages ADD COLUMN tier TEXT")
        _safe_alter(conn, "ALTER TABLE chat_messages ADD COLUMN token_cost REAL")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _safe_alter(conn: sqlite3.Connection, sql: str) -> None:
    """Execute an ALTER TABLE statement, silently ignoring 'duplicate column' errors."""
    try:
        conn.execute(sql)
    except sqlite3.OperationalError as exc:
        if "duplicate column" in str(exc).lower():
            return
        raise


# ---------------------------------------------------------------------------
# Researcher profile CRUD
# ---------------------------------------------------------------------------


def get_researcher_profile(root: Path) -> dict:
    """Return all researcher profile key-value pairs as a plain dict."""
    with get_db(root) as conn:
        rows = conn.execute(
            "SELECT key, value FROM researcher_profile"
        ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_researcher_profile_key(root: Path, key: str, value: str) -> None:
    """Insert or update a researcher profile key (upsert by key)."""
    now = _now()
    with get_db(root) as conn:
        conn.execute(
            """
            INSERT INTO researcher_profile (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, now),
        )


# ---------------------------------------------------------------------------
# Chat files — per-session file tracking with active/inactive toggle
# ---------------------------------------------------------------------------


def add_chat_file(root: Path, session_id: str, filename: str) -> int:
    """Insert a chat file record for a session and return its rowid."""
    now = _now()
    with get_db(root) as conn:
        cur = conn.execute(
            "INSERT INTO chat_files (session_id, filename, active, created_at) VALUES (?, ?, 1, ?)",
            (session_id, filename, now),
        )
        return cur.lastrowid  # type: ignore[return-value]


def list_session_files(root: Path, session_id: str) -> list[dict[str, Any]]:
    """Return all chat files for a session, including the active column."""
    with get_db(root) as conn:
        rows = conn.execute(
            "SELECT id, session_id, filename, active, created_at FROM chat_files WHERE session_id=? ORDER BY created_at, id",
            (session_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_chat_file(root: Path, file_id: int, session_id: str) -> dict[str, Any] | None:
    """Return a single chat file record only if it belongs to session_id."""
    with get_db(root) as conn:
        row = conn.execute(
            "SELECT id, session_id, filename, active, created_at FROM chat_files WHERE id=? AND session_id=?",
            (file_id, session_id),
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def set_file_active(root: Path, file_id: int, active: bool) -> None:
    """Set the active flag for a chat file (1=active, 0=inactive)."""
    with get_db(root) as conn:
        conn.execute(
            "UPDATE chat_files SET active=? WHERE id=?",
            (1 if active else 0, file_id),
        )


def get_active_filenames(root: Path, session_id: str) -> set[str] | None:
    """Return the set of active filenames for a session, or None if no files are registered.

    - None  → no files registered for session → caller should not filter (pass all chunks)
    - set() → files registered but all inactive → caller should filter out everything
    - {..}  → the set of active filenames that should pass through the filter
    """
    with get_db(root) as conn:
        rows = conn.execute(
            "SELECT filename, active FROM chat_files WHERE session_id=?",
            (session_id,),
        ).fetchall()
    if not rows:
        return None
    return {r["filename"] for r in rows if r["active"]}


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
                    "INSERT INTO chat_memory "
                    "(id, text, session_id, source, extracted_at_count, created_at, content, updated_at) "
                    "VALUES (?, ?, ?, 'auto', ?, ?, ?, ?)",
                    (str(uuid.uuid4()), fact, session_id, message_count, now, fact, now),
                )
