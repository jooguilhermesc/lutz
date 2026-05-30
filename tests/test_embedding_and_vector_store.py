"""Unit tests for EmbeddingClient.from_env and VectorStore core paths.

These tests cover:
  - EmbeddingClient.from_env factory for all providers
  - _default_embedding_model helper
  - EmbeddingClient._embed_openai via mock
  - VectorStore construction, is_empty, summarize on empty store
  - VectorStore upsert + search + drop_all (with fake embeddings)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# EmbeddingClient.from_env — factory tests
# ---------------------------------------------------------------------------

class TestEmbeddingClientFromEnv:

    def test_from_env_openai(self) -> None:
        """from_env returns an openai-provider EmbeddingClient."""
        from lutz.core.embedding_client import EmbeddingClient

        env = {"EMBEDDING_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test"}  # pragma: allowlist secret
        client = EmbeddingClient.from_env(env)
        assert client.provider == "openai"
        assert client.model_id == "text-embedding-3-small"

    def test_from_env_openai_custom_model(self) -> None:
        """from_env picks up a custom EMBEDDING_MODEL."""
        from lutz.core.embedding_client import EmbeddingClient

        env = {
            "EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-test",  # pragma: allowlist secret
            "EMBEDDING_MODEL": "text-embedding-ada-002",
        }
        client = EmbeddingClient.from_env(env)
        assert client.model_id == "text-embedding-ada-002"

    def test_from_env_openai_missing_key_raises(self) -> None:
        """from_env raises ValueError when OPENAI_API_KEY is absent."""
        from lutz.core.embedding_client import EmbeddingClient

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            EmbeddingClient.from_env({"EMBEDDING_PROVIDER": "openai"})

    def test_from_env_docker_model_runner(self) -> None:
        """from_env returns a docker_model_runner-provider client."""
        from lutz.core.embedding_client import EmbeddingClient

        client = EmbeddingClient.from_env({"EMBEDDING_PROVIDER": "docker_model_runner"})
        assert client.provider == "docker_model_runner"
        assert "model-runner.docker.internal" in client._kwargs.get("base_url", "")

    def test_from_env_sentence_transformers(self) -> None:
        """from_env returns a sentence_transformers-provider client."""
        from lutz.core.embedding_client import EmbeddingClient

        client = EmbeddingClient.from_env({"EMBEDDING_PROVIDER": "sentence_transformers"})
        assert client.provider == "sentence_transformers"
        assert client.model_id == "all-MiniLM-L6-v2"

    def test_from_env_unknown_provider_raises(self) -> None:
        """from_env raises ValueError for an unknown provider."""
        from lutz.core.embedding_client import EmbeddingClient

        with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
            EmbeddingClient.from_env({"EMBEDDING_PROVIDER": "magic_model"})

    def test_from_env_defaults_to_sentence_transformers(self) -> None:
        """from_env defaults to sentence_transformers when no provider is given."""
        from lutz.core.embedding_client import EmbeddingClient

        client = EmbeddingClient.from_env({})
        assert client.provider == "sentence_transformers"


# ---------------------------------------------------------------------------
# _default_embedding_model
# ---------------------------------------------------------------------------

class TestDefaultEmbeddingModel:

    def test_openai_default_model(self) -> None:
        from lutz.core.embedding_client import _default_embedding_model
        assert _default_embedding_model("openai") == "text-embedding-3-small"

    def test_docker_default_model(self) -> None:
        from lutz.core.embedding_client import _default_embedding_model
        assert _default_embedding_model("docker_model_runner") == "nomic-embed-text"

    def test_unknown_provider_default_model(self) -> None:
        from lutz.core.embedding_client import _default_embedding_model
        assert _default_embedding_model("anything_else") == "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# EmbeddingClient._embed_openai via mocking
# ---------------------------------------------------------------------------

class TestEmbeddingClientEmbedOpenai:

    def test_embed_openai_returns_embeddings(self) -> None:
        """_embed_openai calls the OpenAI client and returns embeddings."""
        from lutz.core.embedding_client import EmbeddingClient

        client = EmbeddingClient(provider="openai", model_id="text-embedding-3-small",
                                 api_key="sk-test")  # pragma: allowlist secret

        openai_mock = MagicMock()
        item = MagicMock()
        item.embedding = [0.1, 0.2, 0.3]
        response = MagicMock()
        response.data = [item]
        response.usage.total_tokens = 10
        openai_mock.embeddings.create.return_value = response

        with patch.object(client, "_get_openai_client", return_value=openai_mock):
            embeddings, total_tokens = client.embed(["hello world"])

        assert len(embeddings) == 1
        assert embeddings[0] == [0.1, 0.2, 0.3]
        assert total_tokens == 10

    def test_embed_multiple_texts(self) -> None:
        """embed() batches texts correctly and accumulates token counts."""
        from lutz.core.embedding_client import EmbeddingClient

        client = EmbeddingClient(provider="openai", model_id="text-embedding-3-small",
                                 api_key="sk-test")  # pragma: allowlist secret

        openai_mock = MagicMock()

        def create_response(model, input, encoding_format):
            items = [MagicMock(embedding=[float(i)] * 4) for i in range(len(input))]
            resp = MagicMock()
            resp.data = items
            resp.usage.total_tokens = len(input) * 5
            return resp

        openai_mock.embeddings.create.side_effect = create_response

        with patch.object(client, "_get_openai_client", return_value=openai_mock):
            embeddings, total_tokens = client.embed(["text A", "text B", "text C"])

        assert len(embeddings) == 3
        assert total_tokens == 15  # 3 texts * 5 tokens each

    def test_embed_delegates_correctly_for_docker_model_runner(self) -> None:
        """docker_model_runner routes to _embed_openai."""
        from lutz.core.embedding_client import EmbeddingClient

        client = EmbeddingClient(provider="docker_model_runner", model_id="nomic",
                                 api_key="dummy", base_url="http://localhost/engines/v1")  # pragma: allowlist secret

        openai_mock = MagicMock()
        item = MagicMock()
        item.embedding = [1.0, 0.0]
        response = MagicMock()
        response.data = [item]
        response.usage.total_tokens = 3
        openai_mock.embeddings.create.return_value = response

        with patch.object(client, "_get_openai_client", return_value=openai_mock):
            embeddings, _ = client.embed(["test"])

        assert embeddings[0] == [1.0, 0.0]


# ---------------------------------------------------------------------------
# VectorStore — basic lifecycle tests
# ---------------------------------------------------------------------------

class TestVectorStore:
    """Tests using a real ephemeral LanceDB vector store."""

    @pytest.fixture()
    def store(self, tmp_path: Path):
        from lutz.core.vector_store import VectorStore
        return VectorStore(tmp_path / "vs")

    def _make_records(self, filename: str, count: int = 2, dim: int = 8) -> list[dict]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return [
            {
                "filename": filename,
                "chunk_index": i,
                "page": i + 1,
                "char_start": i * 100,
                "section": "Abstract",
                "text": f"Chunk {i} of {filename}",
                "embedding": [float(i + j * 0.1) for j in range(dim)],
                "vectorized_at": now,
                "embedding_model": "test-model",
                "embedding_provider": "test",
                "extraction_backend": "pymupdf",
            }
            for i in range(count)
        ]

    # Construction -----------------------------------------------------------

    def test_store_creates_directory(self, tmp_path: Path) -> None:
        from lutz.core.vector_store import VectorStore
        vs_path = tmp_path / "new_vs"
        VectorStore(vs_path)
        assert vs_path.exists()

    # summarize --------------------------------------------------------------

    def test_summarize_empty_store(self, store) -> None:
        summary = store.summarize()
        assert "articles" in summary
        assert summary["articles"] == []
        assert summary["total_records"] == 0
        assert summary["unique_documents"] == 0

    def test_summarize_after_upsert(self, store) -> None:
        store.upsert(self._make_records("paper.pdf", count=3))
        summary = store.summarize()
        assert summary["total_records"] == 3
        assert summary["unique_documents"] == 1
        assert len(summary["articles"]) == 1
        assert summary["articles"][0]["filename"] == "paper.pdf"
        assert summary["articles"][0]["chunk_count"] == 3

    # upsert + search --------------------------------------------------------

    def test_upsert_adds_records(self, store) -> None:
        store.upsert(self._make_records("doc.pdf", count=4))
        summary = store.summarize()
        assert summary["total_records"] == 4

    def test_search_returns_results(self, store) -> None:
        store.upsert(self._make_records("paper.pdf", count=5, dim=8))
        query = [0.5] * 8
        results = store.search(query, top_k=3)
        assert len(results) <= 3
        assert all("filename" in r for r in results)
        assert all("text" in r for r in results)

    def test_search_empty_store_returns_empty(self, store) -> None:
        results = store.search([0.0] * 8, top_k=5)
        assert results == []

    # drop_all ---------------------------------------------------------------

    def test_drop_all_empties_store(self, store) -> None:
        store.upsert(self._make_records("paper.pdf"))
        count = store.drop_all()
        assert count >= 0
        summary = store.summarize()
        assert summary["total_records"] == 0
        assert summary["articles"] == []

    # _project helper --------------------------------------------------------

    def test_project_selects_available_columns(self) -> None:
        import pyarrow as pa
        from lutz.core.vector_store import _project

        table = pa.table({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        projected = _project(table, ["a", "c", "nonexistent"])
        assert projected.schema.names == ["a", "c"]

    # rename_filename --------------------------------------------------------

    def test_rename_filename(self, store) -> None:
        store.upsert(self._make_records("old_name.pdf", count=2))
        store.rename_filename("old_name.pdf", "new_name.pdf")
        results = store.search([0.5] * 8, top_k=10)
        filenames = {r["filename"] for r in results}
        assert "new_name.pdf" in filenames
        assert "old_name.pdf" not in filenames
