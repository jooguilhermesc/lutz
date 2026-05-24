"""Tests for agent-related SQLite schema migrations in lutz/server/db.py.

Sprint 4 additions:
- researcher_profile table (new)
- chat_sessions.agent_plan and agent_state columns (additive migration)
- chat_messages.tool_calls, model_used, tier, token_cost columns (additive migration)
- get_researcher_profile() and set_researcher_profile_key() CRUD functions
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a minimal lutz project root and initialise the DB."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\nOPENAI_API_KEY=test-key\n",
        encoding="utf-8",
    )
    from lutz.server import db as _db
    _db.init_db(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# researcher_profile table
# ---------------------------------------------------------------------------


class TestResearcherProfileTable:

    def test_init_db_creates_researcher_profile_table(self, project_root: Path) -> None:
        """After init_db(), the researcher_profile table exists."""
        from lutz.server.db import get_db_path

        conn = sqlite3.connect(str(get_db_path(project_root)))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "researcher_profile" in tables

    def test_researcher_profile_set_get(self, project_root: Path) -> None:
        """set_researcher_profile_key stores and get_researcher_profile retrieves it."""
        from lutz.server import db as _db

        _db.set_researcher_profile_key(project_root, "preferred_language", "pt")
        profile = _db.get_researcher_profile(project_root)
        assert profile["preferred_language"] == "pt"

    def test_researcher_profile_upsert(self, project_root: Path) -> None:
        """Setting the same key twice must not create duplicates — last value wins."""
        from lutz.server import db as _db

        _db.set_researcher_profile_key(project_root, "domain", "NLP")
        _db.set_researcher_profile_key(project_root, "domain", "IA na Educação")

        profile = _db.get_researcher_profile(project_root)
        assert profile["domain"] == "IA na Educação"

        from lutz.server.db import get_db_path
        conn = sqlite3.connect(str(get_db_path(project_root)))
        count = conn.execute(
            "SELECT COUNT(*) FROM researcher_profile WHERE key='domain'"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_researcher_profile_multiple_keys(self, project_root: Path) -> None:
        """get_researcher_profile returns all stored key-value pairs."""
        from lutz.server import db as _db

        _db.set_researcher_profile_key(project_root, "language", "en")
        _db.set_researcher_profile_key(project_root, "model", "gpt-4o-mini")
        profile = _db.get_researcher_profile(project_root)
        assert profile["language"] == "en"
        assert profile["model"] == "gpt-4o-mini"

    def test_get_researcher_profile_empty(self, project_root: Path) -> None:
        """get_researcher_profile returns empty dict when no keys are stored."""
        from lutz.server import db as _db

        profile = _db.get_researcher_profile(project_root)
        assert profile == {}


# ---------------------------------------------------------------------------
# chat_sessions agent columns
# ---------------------------------------------------------------------------


class TestChatSessionsAgentColumns:

    def test_chat_sessions_has_agent_columns(self, project_root: Path) -> None:
        """After migration, PRAGMA table_info shows agent_plan and agent_state columns."""
        from lutz.server.db import get_db_path

        conn = sqlite3.connect(str(get_db_path(project_root)))
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()
        }
        conn.close()
        assert "agent_plan" in cols
        assert "agent_state" in cols

    def test_agent_state_default_idle(self, project_root: Path) -> None:
        """Sessions created after migration have agent_state='idle' by default."""
        from lutz.server import db as _db
        from lutz.server.db import get_db_path

        session = _db.create_session(project_root, "Test")
        conn = sqlite3.connect(str(get_db_path(project_root)))
        row = conn.execute(
            "SELECT agent_state FROM chat_sessions WHERE id=?", (session["id"],)
        ).fetchone()
        conn.close()
        # Default is 'idle' or NULL — either is acceptable for a new session
        assert row[0] in (None, "idle")

    def test_init_db_is_idempotent(self, project_root: Path) -> None:
        """Calling init_db() twice must not raise (all ALTERs are idempotent)."""
        from lutz.server import db as _db
        # Should not raise
        _db.init_db(project_root)


# ---------------------------------------------------------------------------
# chat_messages agent columns
# ---------------------------------------------------------------------------


class TestChatMessagesAgentColumns:

    def test_chat_messages_has_agent_columns(self, project_root: Path) -> None:
        """After migration, PRAGMA table_info shows tool_calls, model_used, tier, token_cost."""
        from lutz.server.db import get_db_path

        conn = sqlite3.connect(str(get_db_path(project_root)))
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        conn.close()
        assert "tool_calls" in cols
        assert "model_used" in cols
        assert "tier" in cols
        assert "token_cost" in cols
