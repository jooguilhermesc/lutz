"""Tests for US-2 — Ranking de relevância contra a pergunta de pesquisa.

TDD: tests written before implementation.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Pure function: rank_articles_by_relevance
# ---------------------------------------------------------------------------


class TestRankArticlesMeanAggregation:
    """Question closer to cluster A → articles of A score higher than cluster B."""

    def test_rank_articles_mean_aggregation(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        # Cluster A: two 3-D embeddings near [1, 0, 0]
        cluster_a = [np.array([1.0, 0.1, 0.0]), np.array([0.9, 0.2, 0.0])]
        # Cluster B: two 3-D embeddings near [0, 1, 0]
        cluster_b = [np.array([0.0, 1.0, 0.1]), np.array([0.1, 0.9, 0.0])]

        article_chunk_embeddings = {
            "article_a.pdf": cluster_a,
            "article_b.pdf": cluster_b,
        }
        question = np.array([1.0, 0.0, 0.0])

        results = rank_articles_by_relevance(article_chunk_embeddings, question, aggregation="mean")

        assert len(results) == 2
        assert results[0]["filename"] == "article_a.pdf"
        assert results[1]["filename"] == "article_b.pdf"
        assert results[0]["score"] > results[1]["score"]


class TestRankArticlesMaxAggregation:
    """Same cluster scenario with aggregation='max'."""

    def test_rank_articles_max_aggregation(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        cluster_a = [np.array([1.0, 0.0, 0.0]), np.array([0.5, 0.5, 0.0])]
        cluster_b = [np.array([0.0, 1.0, 0.0]), np.array([0.1, 0.9, 0.0])]

        article_chunk_embeddings = {
            "article_a.pdf": cluster_a,
            "article_b.pdf": cluster_b,
        }
        question = np.array([1.0, 0.0, 0.0])

        results = rank_articles_by_relevance(article_chunk_embeddings, question, aggregation="max")

        assert results[0]["filename"] == "article_a.pdf"
        assert results[0]["score"] > results[1]["score"]
        assert all(r["chunks_used"] == 2 for r in results)


class TestRankArticlesDeterministic:
    """Same input always produces same output in the same order."""

    def test_rank_articles_deterministic(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        # Two articles with intentionally equal scores (same embedding)
        shared = np.array([0.6, 0.8, 0.0])
        article_chunk_embeddings = {
            "zebra.pdf": [shared.copy()],
            "alpha.pdf": [shared.copy()],
        }
        question = np.array([1.0, 0.0, 0.0])

        first = rank_articles_by_relevance(article_chunk_embeddings, question)
        second = rank_articles_by_relevance(article_chunk_embeddings, question)

        assert [r["filename"] for r in first] == [r["filename"] for r in second]
        # Tie broken by filename — alpha < zebra alphabetically
        assert first[0]["filename"] == "alpha.pdf"
        assert first[1]["filename"] == "zebra.pdf"


class TestRankArticlesEmpty:
    """Empty dict input → empty list, no exception."""

    def test_rank_articles_empty(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        results = rank_articles_by_relevance({}, np.array([1.0, 0.0, 0.0]))
        assert results == []


class TestRankArticlesZeroNorm:
    """Zero-norm vectors (all-zero embeddings) must not raise and score 0."""

    def test_zero_question_vector_scores_zero(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        article_chunk_embeddings = {
            "article.pdf": [np.array([1.0, 0.0, 0.0])],
        }
        question = np.array([0.0, 0.0, 0.0])  # zero-norm vector

        results = rank_articles_by_relevance(article_chunk_embeddings, question)
        assert results[0]["score"] == 0.0

    def test_empty_chunks_list_scores_zero(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        article_chunk_embeddings = {
            "empty.pdf": [],
            "normal.pdf": [np.array([1.0, 0.0, 0.0])],
        }
        question = np.array([1.0, 0.0, 0.0])

        results = rank_articles_by_relevance(article_chunk_embeddings, question)
        filenames = [r["filename"] for r in results]
        empty_result = next(r for r in results if r["filename"] == "empty.pdf")
        assert empty_result["score"] == 0.0
        assert empty_result["chunks_used"] == 0


class TestRankArticlesStructure:
    """Each result dict must contain required keys with correct types."""

    def test_result_dict_keys(self) -> None:
        from lutz.utils.ranking import rank_articles_by_relevance

        article_chunk_embeddings = {
            "paper.pdf": [np.array([1.0, 0.0, 0.0]), np.array([0.8, 0.2, 0.0])],
        }
        question = np.array([1.0, 0.0, 0.0])

        results = rank_articles_by_relevance(article_chunk_embeddings, question)

        assert len(results) == 1
        r = results[0]
        assert "filename" in r
        assert "score" in r
        assert "chunks_used" in r
        assert r["filename"] == "paper.pdf"
        assert isinstance(r["score"], float)
        assert r["chunks_used"] == 2


# ---------------------------------------------------------------------------
# CLI command: lutz rank
# ---------------------------------------------------------------------------


def _make_mock_store(filenames_embeddings: dict[str, list[np.ndarray]]) -> MagicMock:
    """Build a VectorStore mock with get_chunk_embeddings_by_article configured."""
    store = MagicMock()
    store.get_chunk_embeddings_by_article.return_value = filenames_embeddings
    info_data = {
        "total_records": sum(len(v) for v in filenames_embeddings.values()),
        "unique_documents": len(filenames_embeddings),
        "last_updated": "2024-01-01T00:00:00",
        "embedding_model": "all-MiniLM-L6-v2",
    }
    store.info.return_value = info_data
    store.summarize.return_value = {**info_data, "articles": []}
    return store


def _make_mock_embedding_client(embedding: np.ndarray) -> MagicMock:
    client = MagicMock()
    client.embed.return_value = ([embedding.tolist()], 10)
    client.model_id = "all-MiniLM-L6-v2"
    client.provider = "sentence_transformers"
    return client


class TestRankCommandTableOutput:
    """Smoke test: rank command with table format produces expected output."""

    def test_rank_command_table_output(self, tmp_path) -> None:
        from lutz.commands.rank import rank

        # Prepare fake store data
        dim = 3
        chunk_embs = {
            "high_relevance.pdf": [np.array([1.0, 0.0, 0.0], dtype=np.float32)],
            "low_relevance.pdf": [np.array([0.0, 1.0, 0.0], dtype=np.float32)],
        }
        question_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        mock_store = _make_mock_store(chunk_embs)
        mock_client = _make_mock_embedding_client(question_emb)

        runner = CliRunner()
        with (
            patch("lutz.commands.rank.require_project_root", return_value=tmp_path),
            patch("lutz.commands.rank.load_env", return_value={}),
            patch("lutz.commands.rank.VectorStore", return_value=mock_store),
            patch("lutz.commands.rank.EmbeddingClient") as mock_ec_cls,
        ):
            mock_ec_cls.from_env.return_value = mock_client
            # Create .lutz/vector_store directory so VectorStore init doesn't fail
            (tmp_path / ".lutz" / "vector_store").mkdir(parents=True)
            result = runner.invoke(rank, ["--question", "machine learning", "--format", "table"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "high_relevance.pdf" in result.output
        assert "low_relevance.pdf" in result.output
        assert "Ranked 2 articles" in result.output


class TestRankCommandJsonOutput:
    """rank --format json must produce parseable JSON output."""

    def test_rank_command_json_output(self, tmp_path) -> None:
        from lutz.commands.rank import rank

        chunk_embs = {
            "article_a.pdf": [np.array([1.0, 0.0, 0.0], dtype=np.float32)],
            "article_b.pdf": [np.array([0.0, 1.0, 0.0], dtype=np.float32)],
        }
        question_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        mock_store = _make_mock_store(chunk_embs)
        mock_client = _make_mock_embedding_client(question_emb)

        runner = CliRunner()
        with (
            patch("lutz.commands.rank.require_project_root", return_value=tmp_path),
            patch("lutz.commands.rank.load_env", return_value={}),
            patch("lutz.commands.rank.VectorStore", return_value=mock_store),
            patch("lutz.commands.rank.EmbeddingClient") as mock_ec_cls,
        ):
            mock_ec_cls.from_env.return_value = mock_client
            (tmp_path / ".lutz" / "vector_store").mkdir(parents=True)
            result = runner.invoke(rank, ["--question", "neural networks", "--format", "json"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        # Extract the JSON array from the output (ignore any trailing summary line)
        output = result.output.strip()
        json_end = output.rfind("]") + 1
        data = json.loads(output[:json_end])
        assert isinstance(data, list)
        assert len(data) == 2
        first = data[0]
        assert "rank" in first
        assert "filename" in first
        assert "score" in first
        assert "chunks_used" in first
        assert first["rank"] == 1
        assert first["filename"] == "article_a.pdf"


class TestRankCommandEmptyStore:
    """rank with empty store must produce descriptive error."""

    def test_rank_command_empty_store(self, tmp_path) -> None:
        from lutz.commands.rank import rank

        mock_store = _make_mock_store({})
        mock_client = _make_mock_embedding_client(np.array([1.0, 0.0, 0.0]))

        runner = CliRunner()
        with (
            patch("lutz.commands.rank.require_project_root", return_value=tmp_path),
            patch("lutz.commands.rank.load_env", return_value={}),
            patch("lutz.commands.rank.VectorStore", return_value=mock_store),
            patch("lutz.commands.rank.EmbeddingClient") as mock_ec_cls,
        ):
            mock_ec_cls.from_env.return_value = mock_client
            (tmp_path / ".lutz" / "vector_store").mkdir(parents=True)
            result = runner.invoke(rank, ["--question", "any question"])

        # Should exit with non-zero or contain an error message
        assert result.exit_code != 0 or "empty" in result.output.lower() or "no articles" in result.output.lower()


class TestRankCommandCsvOutput:
    """rank --format csv must produce rank,filename,score,chunks_used header."""

    def test_rank_command_csv_output(self, tmp_path) -> None:
        from lutz.commands.rank import rank

        chunk_embs = {
            "paper_one.pdf": [np.array([1.0, 0.0, 0.0], dtype=np.float32)],
        }
        question_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        mock_store = _make_mock_store(chunk_embs)
        mock_client = _make_mock_embedding_client(question_emb)

        runner = CliRunner()
        with (
            patch("lutz.commands.rank.require_project_root", return_value=tmp_path),
            patch("lutz.commands.rank.load_env", return_value={}),
            patch("lutz.commands.rank.VectorStore", return_value=mock_store),
            patch("lutz.commands.rank.EmbeddingClient") as mock_ec_cls,
        ):
            mock_ec_cls.from_env.return_value = mock_client
            (tmp_path / ".lutz" / "vector_store").mkdir(parents=True)
            result = runner.invoke(rank, ["--question", "deep learning", "--format", "csv"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert lines[0] == "rank,filename,score,chunks_used"
        assert "paper_one.pdf" in lines[1]
