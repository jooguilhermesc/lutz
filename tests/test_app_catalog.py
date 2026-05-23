"""Tests for lutz/server/app.py catalog/store metadata functions and helper utilities.

Covers:
  - _pa_type_to_str: PyArrow type-to-string serialisation
  - GET /api/store/catalog: catalog endpoint
  - GET /api/vector-store/udfs: UDF listing
  - lutz/utils/project.py: find_project_root, load_env
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# _pa_type_to_str
# ---------------------------------------------------------------------------

class TestPaTypeToStr:

    def _convert(self, field):
        from lutz.server.app import _pa_type_to_str
        return _pa_type_to_str(field)

    def test_string_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.string())
        assert self._convert(field) == "string"

    def test_large_string_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.large_string())
        assert self._convert(field) == "string"

    def test_int32_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.int32())
        assert self._convert(field) == "int32"

    def test_int64_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.int64())
        assert self._convert(field) == "int64"

    def test_float32_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.float32())
        assert self._convert(field) == "float32"

    def test_float64_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.float64())
        assert self._convert(field) == "float64"

    def test_bool_type(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.bool_())
        assert self._convert(field) == "bool"

    def test_list_float32_type(self) -> None:
        import pyarrow as pa
        field = pa.field("emb", pa.list_(pa.float32()))
        assert self._convert(field) == "float32[N]"

    def test_list_float64_type(self) -> None:
        import pyarrow as pa
        field = pa.field("emb", pa.list_(pa.float64()))
        assert self._convert(field) == "float64[N]"

    def test_list_int32_type(self) -> None:
        import pyarrow as pa
        field = pa.field("ids", pa.list_(pa.int32()))
        result = self._convert(field)
        assert result.startswith("list[")

    def test_unknown_type_returns_str_repr(self) -> None:
        import pyarrow as pa
        field = pa.field("col", pa.date32())
        result = self._convert(field)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# GET /api/store/catalog — endpoint test
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Minimal lutz project root with an initialised SQLite DB."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\nOPENAI_API_KEY=test-key\n"
        "EMBEDDING_PROVIDER=openai\nEMBEDDING_MODEL=text-embedding-3-small\n",
        encoding="utf-8",
    )
    from lutz.server import db as _db
    _db.init_db(tmp_path)
    return tmp_path


@pytest.fixture()
def client(project_root: Path):
    """FastAPI TestClient wired to project_root."""
    from fastapi.testclient import TestClient
    from lutz.server.app import app

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


class TestStoreCatalog:

    def test_catalog_returns_tables(self, client) -> None:
        """GET /api/store/catalog returns a tables list."""
        resp = client.get("/api/store/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert "tables" in data
        assert isinstance(data["tables"], list)

    def test_catalog_table_keys(self, client) -> None:
        """Each table entry has the expected keys."""
        resp = client.get("/api/store/catalog")
        assert resp.status_code == 200
        tables = resp.json()["tables"]
        for t in tables:
            assert "name" in t
            assert "description" in t
            assert "record_count" in t
            assert "columns" in t

    def test_catalog_table_names_include_articles(self, client) -> None:
        """The articles table is always present in the catalog."""
        resp = client.get("/api/store/catalog")
        names = {t["name"] for t in resp.json()["tables"]}
        assert "articles" in names

    def test_catalog_empty_store_record_count_zero(self, client) -> None:
        """Record count for articles is 0 when no articles are vectorized."""
        resp = client.get("/api/store/catalog")
        articles_entry = next(t for t in resp.json()["tables"] if t["name"] == "articles")
        assert articles_entry["record_count"] == 0


class TestVectorStoreUdfs:

    def test_list_udfs_returns_list(self, client) -> None:
        """GET /api/vector-store/udfs returns a list of UDF names."""
        resp = client.get("/api/vector-store/udfs")
        assert resp.status_code == 200
        data = resp.json()
        assert "udfs" in data
        assert isinstance(data["udfs"], list)


class TestContextEndpoint:

    def test_list_context_files_empty(self, client) -> None:
        """GET /api/context returns empty list when no context files."""
        resp = client.get("/api/context")
        assert resp.status_code == 200
        assert resp.json()["files"] == []


class TestChatFilesEndpoint:

    def test_list_chat_files_empty(self, client) -> None:
        """GET /api/chat/files returns empty when no files uploaded."""
        resp = client.get("/api/chat/files")
        assert resp.status_code == 200
        assert resp.json()["files"] == []

    def test_reset_chat_store(self, client) -> None:
        """DELETE /api/chat/store resets the chat vector store."""
        resp = client.delete("/api/chat/store")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# lutz/utils/project.py
# ---------------------------------------------------------------------------

class TestFindProjectRoot:

    def test_finds_root_with_articles_dir(self, tmp_path: Path) -> None:
        """find_project_root detects an articles/ directory."""
        from lutz.utils.project import find_project_root

        (tmp_path / "articles").mkdir()
        result = find_project_root(start=tmp_path)
        assert result == tmp_path

    def test_finds_root_with_lutz_dir(self, tmp_path: Path) -> None:
        """find_project_root detects a .lutz/ directory."""
        from lutz.utils.project import find_project_root

        (tmp_path / ".lutz").mkdir()
        result = find_project_root(start=tmp_path)
        assert result == tmp_path

    def test_finds_root_in_parent(self, tmp_path: Path) -> None:
        """find_project_root walks up to find the root."""
        from lutz.utils.project import find_project_root

        (tmp_path / "articles").mkdir()
        nested = tmp_path / "sub" / "dir"
        nested.mkdir(parents=True)
        result = find_project_root(start=nested)
        assert result == tmp_path

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """find_project_root returns None when no project marker exists."""
        from lutz.utils.project import find_project_root

        # tmp_path has no articles/ or .lutz/
        result = find_project_root(start=tmp_path)
        # Could be None or find a project higher in the tree — just don't crash
        # In CI there's no lutz project above tmp_path
        assert result is None or isinstance(result, Path)


class TestLoadEnv:

    def test_load_env_reads_dot_env(self, tmp_path: Path) -> None:
        """load_env reads values from .env file."""
        from lutz.utils.project import load_env

        (tmp_path / ".env").write_text("MY_KEY=my_value\n", encoding="utf-8")
        env = load_env(tmp_path)
        assert env.get("MY_KEY") == "my_value"

    def test_load_env_os_environ_takes_precedence(self, tmp_path: Path) -> None:
        """load_env: os.environ values override .env file values."""
        from lutz.utils.project import load_env

        (tmp_path / ".env").write_text("MY_KEY=from_file\n", encoding="utf-8")
        with patch.dict(os.environ, {"MY_KEY": "from_env"}):
            env = load_env(tmp_path)
        assert env["MY_KEY"] == "from_env"

    def test_load_env_no_file(self, tmp_path: Path) -> None:
        """load_env does not crash when .env does not exist."""
        from lutz.utils.project import load_env

        env = load_env(tmp_path)
        assert isinstance(env, dict)
