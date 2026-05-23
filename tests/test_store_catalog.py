"""Tests for GET /api/store/catalog endpoint.

TDD: these tests are written BEFORE the implementation and must fail RED
until the endpoint is added to lutz/server/app.py.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Return a minimal lutz project root backed by a temp directory."""
    (tmp_path / ".lutz").mkdir()
    return tmp_path


@pytest.fixture()
def client(project_root: Path):
    """Return a FastAPI TestClient with LUTZ_PROJECT_ROOT set."""
    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    from lutz.server.app import app
    with TestClient(app) as c:
        yield c
    # Clean up env var so it doesn't leak into other tests
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


class TestStoreCatalogEmpty:
    """Catalog endpoint with no stores created yet."""

    def test_returns_200(self, client):
        resp = client.get("/api/store/catalog")
        assert resp.status_code == 200

    def test_response_has_tables_key(self, client):
        data = client.get("/api/store/catalog").json()
        assert "tables" in data

    def test_returns_three_tables(self, client):
        data = client.get("/api/store/catalog").json()
        assert len(data["tables"]) == 3

    def test_table_names(self, client):
        data = client.get("/api/store/catalog").json()
        names = {t["name"] for t in data["tables"]}
        assert names == {"articles", "context", "chat_files"}

    def test_empty_store_record_count_is_zero(self, client):
        data = client.get("/api/store/catalog").json()
        for table in data["tables"]:
            assert table["record_count"] == 0, f"{table['name']} should have record_count 0"

    def test_empty_store_last_updated_is_null(self, client):
        data = client.get("/api/store/catalog").json()
        for table in data["tables"]:
            assert table["last_updated"] is None, f"{table['name']} should have null last_updated"

    def test_each_table_has_columns(self, client):
        data = client.get("/api/store/catalog").json()
        for table in data["tables"]:
            assert "columns" in table
            assert len(table["columns"]) > 0, f"{table['name']} should have at least one column"

    def test_each_table_has_description(self, client):
        data = client.get("/api/store/catalog").json()
        for table in data["tables"]:
            assert "description" in table
            assert isinstance(table["description"], str)
            assert len(table["description"]) > 0

    def test_column_shape(self, client):
        data = client.get("/api/store/catalog").json()
        articles = next(t for t in data["tables"] if t["name"] == "articles")
        for col in articles["columns"]:
            assert "name" in col
            assert "type" in col
            assert "description" in col

    def test_articles_known_columns_present(self, client):
        data = client.get("/api/store/catalog").json()
        articles = next(t for t in data["tables"] if t["name"] == "articles")
        col_names = {c["name"] for c in articles["columns"]}
        required = {"filename", "chunk_index", "page", "text", "embedding"}
        assert required.issubset(col_names)


class TestStoreCatalogWithData:
    """Catalog endpoint when the articles store actually has data."""

    def test_record_count_reflects_real_data(self, project_root: Path):
        """After inserting records, record_count must be > 0."""
        import lancedb
        import pyarrow as pa

        db_path = project_root / ".lutz" / "vector_store"
        db_path.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(db_path))

        dim = 4
        schema = pa.schema([
            pa.field("filename", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("page", pa.int32()),
            pa.field("char_start", pa.int32()),
            pa.field("section", pa.string()),
            pa.field("text", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), dim)),
            pa.field("vectorized_at", pa.string()),
            pa.field("embedding_model", pa.string()),
            pa.field("embedding_provider", pa.string()),
        ])
        rows = [
            {
                "filename": "paper.pdf",
                "chunk_index": 0,
                "page": 1,
                "char_start": 0,
                "section": "abstract",
                "text": "hello world",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "vectorized_at": "2024-01-15T10:30:00Z",
                "embedding_model": "text-embedding-3-small",
                "embedding_provider": "openai",
            }
        ]
        db.create_table("articles", data=rows, schema=schema)

        os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
        # Re-import to get fresh app state
        import importlib
        import lutz.server.app as app_mod
        importlib.reload(app_mod)
        with TestClient(app_mod.app) as c:
            resp = c.get("/api/store/catalog")
        os.environ.pop("LUTZ_PROJECT_ROOT", None)

        data = resp.json()
        articles = next(t for t in data["tables"] if t["name"] == "articles")
        assert articles["record_count"] == 1
        assert articles["last_updated"] == "2024-01-15T10:30:00Z"

    def test_schema_columns_populated_from_real_table(self, project_root: Path):
        """When the table exists, columns are introspected from its PyArrow schema."""
        import lancedb
        import pyarrow as pa

        db_path = project_root / ".lutz" / "vector_store"
        db_path.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(db_path))

        dim = 4
        schema = pa.schema([
            pa.field("filename", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("page", pa.int32()),
            pa.field("char_start", pa.int32()),
            pa.field("section", pa.string()),
            pa.field("text", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), dim)),
            pa.field("vectorized_at", pa.string()),
            pa.field("embedding_model", pa.string()),
            pa.field("embedding_provider", pa.string()),
        ])
        rows = [
            {
                "filename": "paper.pdf",
                "chunk_index": 0,
                "page": 1,
                "char_start": 0,
                "section": "abstract",
                "text": "hello",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "vectorized_at": "2024-01-15T10:30:00Z",
                "embedding_model": "text-embedding-3-small",
                "embedding_provider": "openai",
            }
        ]
        db.create_table("articles", data=rows, schema=schema)

        os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
        import importlib
        import lutz.server.app as app_mod
        importlib.reload(app_mod)
        with TestClient(app_mod.app) as c:
            resp = c.get("/api/store/catalog")
        os.environ.pop("LUTZ_PROJECT_ROOT", None)

        data = resp.json()
        articles = next(t for t in data["tables"] if t["name"] == "articles")
        col_names = {c["name"] for c in articles["columns"]}
        assert "embedding" in col_names
        embedding_col = next(c for c in articles["columns"] if c["name"] == "embedding")
        assert "float32" in embedding_col["type"]


class TestStoreCatalogNeverRaises:
    """Endpoint must swallow all LanceDB/IO errors and return partial data."""

    def test_corrupt_store_path_returns_200(self, project_root: Path):
        """If a store directory is a file (corrupt), endpoint still returns 200."""
        # Create a file where the vector_store directory should be
        vs_path = project_root / ".lutz" / "vector_store"
        vs_path.write_text("not a db")  # file instead of directory

        os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
        import importlib
        import lutz.server.app as app_mod
        importlib.reload(app_mod)
        with TestClient(app_mod.app) as c:
            resp = c.get("/api/store/catalog")
        os.environ.pop("LUTZ_PROJECT_ROOT", None)

        assert resp.status_code == 200
        data = resp.json()
        assert "tables" in data
        assert len(data["tables"]) == 3
