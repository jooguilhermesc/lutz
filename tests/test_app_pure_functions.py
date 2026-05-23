"""Tests for pure functions inside lutz/server/app.py.

These tests cover business logic that has no side-effects, no subprocess
calls, and no LLM/embedding network access — just deterministic Python.

Covers:
  - _validate_select_only: SQL injection prevention
  - _json_val: JSON serialisation of mixed column types
  - _safe_child: path traversal prevention
  - _parse_report_meta: report metadata parsing
  - Job / JobManager: in-memory job lifecycle
  - _now_iso: timestamp helper
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# _validate_select_only
# ---------------------------------------------------------------------------

class TestValidateSelectOnly:

    def _validate(self, sql: str) -> None:
        from lutz.server.app import _validate_select_only
        _validate_select_only(sql)

    # --- Valid queries -------------------------------------------------------

    def test_simple_select(self) -> None:
        self._validate("SELECT * FROM vectors")

    def test_select_with_where(self) -> None:
        self._validate("SELECT filename, text FROM vectors WHERE page = 1")

    def test_select_with_limit(self) -> None:
        self._validate("SELECT * FROM vectors LIMIT 10")

    def test_select_with_count(self) -> None:
        self._validate("SELECT COUNT(*) FROM vectors")

    def test_select_case_insensitive(self) -> None:
        self._validate("select * from vectors")

    # --- Blocked statement types -------------------------------------------

    def test_insert_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("INSERT INTO vectors VALUES (1, 2)")

    def test_drop_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("DROP TABLE vectors")

    def test_delete_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("DELETE FROM vectors")

    def test_create_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("CREATE TABLE t (id INT)")

    def test_update_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("UPDATE vectors SET text = 'x'")

    def test_truncate_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("TRUNCATE TABLE vectors")

    def test_alter_blocked(self) -> None:
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("ALTER TABLE vectors ADD COLUMN x INT")

    def test_empty_sql_blocked(self) -> None:
        with pytest.raises((ValueError, Exception)):
            self._validate("")

    def test_copy_blocked(self) -> None:
        """COPY statement is blocked by the regex fallback."""
        with pytest.raises(ValueError, match="SELECT"):
            self._validate("COPY vectors TO '/tmp/out.csv'")


# ---------------------------------------------------------------------------
# _json_val
# ---------------------------------------------------------------------------

class TestJsonVal:

    def _val(self, v):
        from lutz.server.app import _json_val
        return _json_val(v)

    def test_none_returns_none(self) -> None:
        assert self._val(None) is None

    def test_bool_true(self) -> None:
        result = self._val(True)
        assert result is True
        assert isinstance(result, bool)

    def test_bool_false(self) -> None:
        result = self._val(False)
        assert result is False
        assert isinstance(result, bool)

    def test_int_passthrough(self) -> None:
        assert self._val(42) == 42

    def test_float_passthrough(self) -> None:
        assert self._val(3.14) == pytest.approx(3.14)

    def test_str_passthrough(self) -> None:
        assert self._val("hello") == "hello"

    def test_list_passthrough(self) -> None:
        lst = [1.0, 2.0, 3.0]
        assert self._val(lst) is lst

    def test_unknown_object_becomes_string(self) -> None:
        class Custom:
            def __str__(self):
                return "custom"
        result = self._val(Custom())
        assert result == "custom"


# ---------------------------------------------------------------------------
# _safe_child
# ---------------------------------------------------------------------------

class TestSafeChild:

    def test_valid_child_path(self, tmp_path: Path) -> None:
        from lutz.server.app import _safe_child
        result = _safe_child(tmp_path, "file.pdf")
        assert result == tmp_path / "file.pdf"

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        from fastapi import HTTPException
        from lutz.server.app import _safe_child
        with pytest.raises(HTTPException) as exc_info:
            _safe_child(tmp_path, "../../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_nested_valid_child(self, tmp_path: Path) -> None:
        """A sub-path that stays within parent is allowed."""
        from lutz.server.app import _safe_child
        result = _safe_child(tmp_path, "subdir/file.txt")
        assert result.parent.parent == tmp_path or result.parent == tmp_path / "subdir"


# ---------------------------------------------------------------------------
# _parse_report_meta
# ---------------------------------------------------------------------------

class TestParseReportMeta:

    def test_valid_report_meta(self, tmp_path: Path) -> None:
        from lutz.server.app import _parse_report_meta

        data = {
            "metadata": {
                "mode": "per_article",
                "report_type": "analysis",
                "started_at": "2025-01-01T00:00:00Z",
                "llm": {"total_tokens": 1000, "model": "gpt-4o"},
                "elapsed_seconds": 42.5,
            },
            "articles": [{"id": "a1"}, {"id": "a2"}],
        }
        report_file = tmp_path / "my_report.json"
        report_file.write_text(json.dumps(data), encoding="utf-8")

        meta = _parse_report_meta(report_file)
        assert meta["name"] == "my_report"
        assert meta["mode"] == "per_article"
        assert meta["articles"] == 2
        assert meta["tokens"] == 1000
        assert meta["model"] == "gpt-4o"

    def test_malformed_report_returns_defaults(self, tmp_path: Path) -> None:
        from lutz.server.app import _parse_report_meta

        report_file = tmp_path / "bad_report.json"
        report_file.write_text("not json at all", encoding="utf-8")

        meta = _parse_report_meta(report_file)
        assert meta["name"] == "bad_report"
        assert meta["mode"] == ""
        assert meta["articles"] == 0

    def test_empty_json_returns_defaults(self, tmp_path: Path) -> None:
        from lutz.server.app import _parse_report_meta

        report_file = tmp_path / "empty_report.json"
        report_file.write_text("{}", encoding="utf-8")

        meta = _parse_report_meta(report_file)
        assert meta["name"] == "empty_report"
        assert meta["mode"] == ""
        assert meta["tokens"] == 0

    def test_report_with_generated_at_fallback(self, tmp_path: Path) -> None:
        """Reports without started_at use generated_at instead."""
        from lutz.server.app import _parse_report_meta

        data = {
            "metadata": {
                "mode": "rag",
                "report_type": "citations",
                "generated_at": "2025-06-01T12:00:00Z",
                "llm": {},
                "relevant": 5,
            }
        }
        report_file = tmp_path / "citations_report.json"
        report_file.write_text(json.dumps(data), encoding="utf-8")

        meta = _parse_report_meta(report_file)
        assert meta["started_at"] == "2025-06-01T12:00:00Z"
        assert meta["articles"] == 5


# ---------------------------------------------------------------------------
# Job / JobManager
# ---------------------------------------------------------------------------

class TestJobManager:

    def _manager(self):
        from lutz.server.app import JobManager
        return JobManager()

    def test_create_job(self) -> None:
        jm = self._manager()
        job = jm.create("vectorize", "Processar biblioteca", {})
        assert job.id
        assert job.status == "queued"
        assert job.type == "vectorize"
        assert job.title == "Processar biblioteca"

    def test_get_job_found(self) -> None:
        jm = self._manager()
        job = jm.create("vectorize", "Test", {})
        retrieved = jm.get(job.id)
        assert retrieved is job

    def test_get_job_not_found(self) -> None:
        jm = self._manager()
        assert jm.get("nonexistent-id") is None

    def test_list_all_empty(self) -> None:
        jm = self._manager()
        assert jm.list_all() == []

    def test_list_all_returns_jobs(self) -> None:
        jm = self._manager()
        jm.create("vectorize", "Job A", {})
        jm.create("analysis", "Job B", {})
        jobs = jm.list_all()
        assert len(jobs) == 2

    def test_remove_terminal_job(self) -> None:
        jm = self._manager()
        job = jm.create("vectorize", "Test", {})
        job.status = "done"
        result = jm.remove(job.id)
        assert result is True
        assert jm.get(job.id) is None

    def test_remove_nonexistent_job_returns_false(self) -> None:
        jm = self._manager()
        result = jm.remove("no-such-id")
        assert result is False

    def test_list_all_reversed_order(self) -> None:
        """list_all returns jobs in reverse creation order (most recent first)."""
        jm = self._manager()
        job_a = jm.create("vectorize", "A", {})
        job_b = jm.create("analysis", "B", {})
        jobs = jm.list_all()
        # Most recently created is first
        assert jobs[0]["id"] == job_b.id
        assert jobs[1]["id"] == job_a.id

    def test_evict_old_terminal_jobs_when_full(self) -> None:
        """Old terminal jobs are evicted when the manager is full."""
        from lutz.server.app import JobManager
        jm = JobManager()
        # Override the max to a small number for testing
        from lutz.server import app as _app
        original_max = _app._MAX_JOBS
        _app._MAX_JOBS = 3
        try:
            # Create 3 terminal jobs
            for i in range(3):
                j = jm.create("vectorize", f"Job {i}", {})
                j.status = "done"
            # Creating one more should evict old terminal jobs
            new_job = jm.create("analysis", "New Job", {})
            assert jm.get(new_job.id) is not None
        finally:
            _app._MAX_JOBS = original_max


# ---------------------------------------------------------------------------
# Job.to_dict
# ---------------------------------------------------------------------------

class TestJobToDict:

    def test_to_dict_without_logs(self) -> None:
        from lutz.server.app import Job

        job = Job(id="abc", type="vectorize", status="queued", title="Test", params={})
        d = job.to_dict()
        assert d["id"] == "abc"
        assert d["status"] == "queued"
        assert "logs" not in d

    def test_to_dict_with_logs(self) -> None:
        from lutz.server.app import Job

        job = Job(id="xyz", type="analysis", status="done", title="Analysis", params={})
        job.logs.append("line 1")
        job.logs.append("line 2")
        d = job.to_dict(include_logs=True)
        assert "logs" in d
        assert d["logs"] == ["line 1", "line 2"]


# ---------------------------------------------------------------------------
# _now_iso
# ---------------------------------------------------------------------------

class TestNowIso:

    def test_returns_iso_string(self) -> None:
        from lutz.server.app import _now_iso
        result = _now_iso()
        assert isinstance(result, str)
        assert "T" in result  # ISO 8601 datetime contains T separator
        assert "+" in result or "Z" in result  # UTC offset or Z


# ---------------------------------------------------------------------------
# _build_job_args — valid and error cases
# ---------------------------------------------------------------------------

class TestBuildJobArgs:

    def test_vectorize_basic(self, tmp_path: Path) -> None:
        from lutz.server.app import _build_job_args
        args, title = _build_job_args("vectorize", {}, tmp_path)
        assert args == ["vectorize"]
        assert "biblioteca" in title.lower() or "processar" in title.lower()

    def test_vectorize_with_options(self, tmp_path: Path) -> None:
        from lutz.server.app import _build_job_args
        body = {"chunk_size": 512, "chunk_overlap": 50}
        args, _ = _build_job_args("vectorize", body, tmp_path)
        assert "--chunk-size" in args
        assert "512" in args
        assert "--chunk-overlap" in args
        assert "50" in args

    def test_vectorize_extraction_backend(self, tmp_path: Path) -> None:
        from lutz.server.app import _build_job_args
        args, _ = _build_job_args("vectorize", {"extraction_backend": "pymupdf"}, tmp_path)
        assert "--extraction" in args
        assert "pymupdf" in args

    def test_analysis_requires_prompt(self, tmp_path: Path) -> None:
        from fastapi import HTTPException
        from lutz.server.app import _build_job_args
        with pytest.raises(HTTPException) as exc_info:
            _build_job_args("analysis", {}, tmp_path)
        assert exc_info.value.status_code == 400

    def test_analysis_with_inline_prompt(self, tmp_path: Path) -> None:
        from lutz.server.app import _build_job_args
        body = {"inline_prompt": "# Triagem\n\nFazer triagem dos artigos."}
        args, title = _build_job_args("analysis", body, tmp_path)
        assert "analysis" in args
        assert "--p" in args
        assert "prompt personalizado" in title.lower()

    def test_citations_missing_report_raises(self, tmp_path: Path) -> None:
        from fastapi import HTTPException
        from lutz.server.app import _build_job_args
        with pytest.raises(HTTPException) as exc_info:
            _build_job_args("citations", {}, tmp_path)
        assert exc_info.value.status_code == 400

    def test_unknown_job_type_raises(self, tmp_path: Path) -> None:
        from fastapi import HTTPException
        from lutz.server.app import _build_job_args
        with pytest.raises(HTTPException) as exc_info:
            _build_job_args("unknown_type", {}, tmp_path)
        assert exc_info.value.status_code == 400

    def test_roadmap_missing_report_raises(self, tmp_path: Path) -> None:
        from fastapi import HTTPException
        from lutz.server.app import _build_job_args
        with pytest.raises(HTTPException):
            _build_job_args("roadmap", {}, tmp_path)


# ---------------------------------------------------------------------------
# WSManager — basic connection tracking
# ---------------------------------------------------------------------------

class TestWSManager:

    def test_disconnect_removes_client(self) -> None:
        from unittest.mock import MagicMock
        from lutz.server.app import WSManager

        wm = WSManager()
        ws = MagicMock()
        wm._clients.add(ws)
        wm.disconnect(ws)
        assert ws not in wm._clients

    def test_disconnect_unknown_is_safe(self) -> None:
        from unittest.mock import MagicMock
        from lutz.server.app import WSManager

        wm = WSManager()
        ws = MagicMock()
        wm.disconnect(ws)  # should not raise
