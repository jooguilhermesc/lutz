"""Tests for US-3 — cluster-report synthesis.

TDD cycle: RED phase — tests written before implementation.

Covers:
  - build_cluster_report() pure function
  - VectorStore.get_all_embeddings_with_metadata()
  - `lutz model cluster-report` CLI command (smoke + error)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from click.testing import CliRunner
from sklearn.cluster import KMeans


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_rows_and_matrix(
    n_articles: int = 10,
    chunks_per_article: int = 10,
    n_dims: int = 8,
    n_clusters: int = 2,
    seed: int = 0,
) -> tuple[np.ndarray, list[dict], KMeans]:
    """Return (matrix, rows, fitted_kmeans) with well-separated clusters.

    Articles 0..n_articles//2-1 belong to cluster 0 region,
    the rest belong to cluster 1 region.
    """
    rng = np.random.default_rng(seed)
    centers = np.array(
        [rng.standard_normal(n_dims) * 10, rng.standard_normal(n_dims) * 10 + 50]
    )

    rows: list[dict] = []
    embeddings: list[np.ndarray] = []

    half = n_articles // 2
    for article_idx in range(n_articles):
        cluster_center = centers[0 if article_idx < half else 1]
        for chunk_idx in range(chunks_per_article):
            emb = cluster_center + rng.standard_normal(n_dims) * 0.01
            embeddings.append(emb.astype(np.float32))
            rows.append(
                {
                    "filename": f"article_{article_idx:02d}.pdf",
                    "chunk_index": chunk_idx,
                    "section": "abstract" if chunk_idx == 0 else "body",
                    "text": f"Text of article {article_idx} chunk {chunk_idx}.",
                }
            )

    mat = np.array(embeddings, dtype=np.float32)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    km.fit(mat)
    return mat, rows, km


# ---------------------------------------------------------------------------
# Tests for build_cluster_report()
# ---------------------------------------------------------------------------


class TestBuildClusterReport:
    def test_build_cluster_report_structure(self) -> None:
        """Report has one entry per cluster; each entry has required keys."""
        from lutz.utils.cluster_report import build_cluster_report

        mat, rows, km = _make_rows_and_matrix(
            n_articles=10, chunks_per_article=10, n_dims=8, n_clusters=2
        )
        labels = km.predict(mat)
        report = build_cluster_report(mat, rows, km.cluster_centers_, labels)

        assert len(report) == 2
        for entry in report:
            assert "cluster_id" in entry
            assert "n_articles" in entry
            assert "article_filenames" in entry
            assert "representative_chunks" in entry
            assert isinstance(entry["article_filenames"], list)
            assert isinstance(entry["representative_chunks"], list)

    def test_build_cluster_report_top_chunks_respected(self) -> None:
        """top_chunks=3 yields at most 3 representative chunks per cluster."""
        from lutz.utils.cluster_report import build_cluster_report

        mat, rows, km = _make_rows_and_matrix(
            n_articles=10, chunks_per_article=10, n_dims=8, n_clusters=2
        )
        labels = km.predict(mat)
        report = build_cluster_report(mat, rows, km.cluster_centers_, labels, top_chunks=3)

        for entry in report:
            assert len(entry["representative_chunks"]) <= 3
            # Clusters with >= 3 chunks must have exactly 3
            if entry["n_articles"] * 10 >= 3:
                assert len(entry["representative_chunks"]) == 3

    def test_build_cluster_report_representative_closest(self) -> None:
        """The first representative chunk has the lowest cosine distance to centroid."""
        from lutz.utils.cluster_report import build_cluster_report

        mat, rows, km = _make_rows_and_matrix(
            n_articles=10, chunks_per_article=10, n_dims=8, n_clusters=2
        )
        labels = km.predict(mat)
        report = build_cluster_report(mat, rows, km.cluster_centers_, labels, top_chunks=5)

        for entry in report:
            reps = entry["representative_chunks"]
            if len(reps) >= 2:
                distances = [r["distance_to_centroid"] for r in reps]
                # Representatives must be sorted by ascending distance
                assert distances == sorted(distances), (
                    f"Cluster {entry['cluster_id']} representatives are not sorted by distance"
                )
                # First representative is the closest
                assert distances[0] <= distances[-1]

    def test_build_cluster_report_articles_correct(self) -> None:
        """Articles in each cluster match the labels assigned by model.predict()."""
        from lutz.utils.cluster_report import build_cluster_report

        mat, rows, km = _make_rows_and_matrix(
            n_articles=10, chunks_per_article=10, n_dims=8, n_clusters=2
        )
        labels = km.predict(mat)
        report = build_cluster_report(mat, rows, km.cluster_centers_, labels)

        for entry in report:
            k = entry["cluster_id"]
            expected_filenames = {
                rows[i]["filename"] for i, lbl in enumerate(labels) if lbl == k
            }
            assert set(entry["article_filenames"]) == expected_filenames

    def test_build_cluster_report_representative_chunks_have_distance_key(self) -> None:
        """Each representative chunk dict contains 'distance_to_centroid'."""
        from lutz.utils.cluster_report import build_cluster_report

        mat, rows, km = _make_rows_and_matrix(
            n_articles=6, chunks_per_article=5, n_dims=8, n_clusters=2
        )
        labels = km.predict(mat)
        report = build_cluster_report(mat, rows, km.cluster_centers_, labels, top_chunks=2)

        for entry in report:
            for chunk in entry["representative_chunks"]:
                assert "distance_to_centroid" in chunk
                assert "filename" in chunk
                assert "section" in chunk
                assert "text" in chunk
                assert isinstance(chunk["distance_to_centroid"], float)
                assert chunk["distance_to_centroid"] >= 0.0

    def test_build_cluster_report_deterministic(self) -> None:
        """Same inputs produce identical reports."""
        from lutz.utils.cluster_report import build_cluster_report

        mat, rows, km = _make_rows_and_matrix(
            n_articles=8, chunks_per_article=5, n_dims=8, n_clusters=2
        )
        labels = km.predict(mat)

        r1 = build_cluster_report(mat, rows, km.cluster_centers_, labels, top_chunks=3)
        r2 = build_cluster_report(mat, rows, km.cluster_centers_, labels, top_chunks=3)

        assert len(r1) == len(r2)
        for e1, e2 in zip(r1, r2):
            assert e1["cluster_id"] == e2["cluster_id"]
            assert e1["article_filenames"] == e2["article_filenames"]
            assert len(e1["representative_chunks"]) == len(e2["representative_chunks"])
            for c1, c2 in zip(e1["representative_chunks"], e2["representative_chunks"]):
                assert c1["filename"] == c2["filename"]
                assert c1["distance_to_centroid"] == pytest.approx(c2["distance_to_centroid"])


# ---------------------------------------------------------------------------
# Tests for VectorStore.get_all_embeddings_with_metadata()
# ---------------------------------------------------------------------------


class TestGetAllEmbeddingsWithMetadata:
    def test_returns_matrix_and_aligned_rows(self, tmp_path: "Path") -> None:
        """Matrix rows and metadata rows are aligned by index."""
        from lutz.core.vector_store import VectorStore

        vs = VectorStore(tmp_path / "vs")
        records = [
            {
                "filename": f"art_{i}.pdf",
                "chunk_index": j,
                "page": 0,
                "char_start": 0,
                "section": "abstract",
                "text": f"text {i}-{j}",
                "embedding": [float(i + j * 0.1)] * 4,
                "vectorized_at": "2024-01-01T00:00:00",
                "embedding_model": "test-model",
                "embedding_provider": "openai",
                "extraction_backend": "pymupdf",
            }
            for i in range(3)
            for j in range(2)
        ]
        vs.upsert(records)

        mat, rows = vs.get_all_embeddings_with_metadata()

        assert mat.shape[0] == len(rows) == 6
        assert mat.shape[1] == 4
        assert mat.dtype == np.float32
        # Each row must have the required keys
        for row in rows:
            assert "filename" in row
            assert "chunk_index" in row
            assert "section" in row
            assert "text" in row

    def test_returns_empty_for_empty_store(self, tmp_path: "Path") -> None:
        """Empty store returns empty matrix and empty list."""
        from lutz.core.vector_store import VectorStore

        vs = VectorStore(tmp_path / "vs_empty")
        mat, rows = vs.get_all_embeddings_with_metadata()

        assert mat.shape == (0, 0)
        assert rows == []


# ---------------------------------------------------------------------------
# Tests for `lutz model cluster-report` CLI command
# ---------------------------------------------------------------------------


def _fake_kmeans(n_clusters: int = 2, n_dims: int = 8, seed: int = 0) -> KMeans:
    """Return a fitted KMeans model on synthetic data."""
    mat, _, km = _make_rows_and_matrix(
        n_articles=10, chunks_per_article=10, n_dims=n_dims, n_clusters=n_clusters, seed=seed
    )
    return km


class TestClusterReportCommand:
    def _make_fake_data(
        self,
        n_articles: int = 10,
        chunks_per_article: int = 10,
        n_dims: int = 8,
        n_clusters: int = 2,
    ) -> tuple[np.ndarray, list[dict], KMeans]:
        return _make_rows_and_matrix(
            n_articles=n_articles,
            chunks_per_article=chunks_per_article,
            n_dims=n_dims,
            n_clusters=n_clusters,
        )

    def test_cluster_report_command_smoke_table(self) -> None:
        """Smoke test: table format exits 0 and prints cluster info."""
        from lutz.cli import cli

        mat, rows, km = self._make_fake_data()
        meta = {
            "model_id": "kmeans_2",
            "algorithm": "kmeans",
            "params": {"n_clusters": 2},
            "embedding_model": "test-model",
            "n_rows": mat.shape[0],
            "corpus_hash": "abc123",
            "trained_at": "2024-01-01T00:00:00",
        }

        runner = CliRunner()
        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.FittedModelStore") as MockStore,
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_store = MockStore.return_value
            mock_store.load.return_value = (km, meta)

            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings_with_metadata.return_value = (mat, rows)

            result = runner.invoke(cli, ["model", "cluster-report", "--model", "kmeans_2"])

        assert result.exit_code == 0, result.output
        assert "Cluster" in result.output

    def test_cluster_report_command_smoke_json(self) -> None:
        """JSON format produces parseable output with 'model_id' and 'clusters' keys."""
        from lutz.cli import cli

        mat, rows, km = self._make_fake_data()
        meta = {
            "model_id": "kmeans_2",
            "algorithm": "kmeans",
            "params": {"n_clusters": 2},
            "embedding_model": "test-model",
            "n_rows": mat.shape[0],
            "corpus_hash": "abc123",
            "trained_at": "2024-01-01T00:00:00",
        }

        runner = CliRunner()
        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.FittedModelStore") as MockStore,
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_store = MockStore.return_value
            mock_store.load.return_value = (km, meta)

            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings_with_metadata.return_value = (mat, rows)

            result = runner.invoke(
                cli,
                ["model", "cluster-report", "--model", "kmeans_2", "--format", "json"],
            )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["model_id"] == "kmeans_2"
        assert "clusters" in data
        assert isinstance(data["clusters"], list)
        assert len(data["clusters"]) == 2

    def test_cluster_report_command_model_not_found(self) -> None:
        """When model does not exist, a descriptive error message is shown."""
        from lutz.cli import cli

        runner = CliRunner()
        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.FittedModelStore") as MockStore,
        ):
            mock_store = MockStore.return_value
            mock_store.load.side_effect = FileNotFoundError(
                "Model 'kmeans_99' not found in /fake — run 'lutz model fit' to train it first."
            )

            result = runner.invoke(
                cli, ["model", "cluster-report", "--model", "kmeans_99"]
            )

        # Exit code non-zero or error message in output
        assert result.exit_code != 0 or "not found" in result.output.lower()
        # Must hint the user to run fit
        assert "fit" in result.output.lower() or "kmeans_99" in result.output

    def test_cluster_report_command_top_chunks_option(self) -> None:
        """--top-chunks N is forwarded to build_cluster_report."""
        from lutz.cli import cli

        mat, rows, km = self._make_fake_data()
        meta = {
            "model_id": "kmeans_2",
            "algorithm": "kmeans",
            "params": {"n_clusters": 2},
            "embedding_model": "test-model",
            "n_rows": mat.shape[0],
            "corpus_hash": "abc123",
            "trained_at": "2024-01-01T00:00:00",
        }

        runner = CliRunner()
        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.FittedModelStore") as MockStore,
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_store = MockStore.return_value
            mock_store.load.return_value = (km, meta)

            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings_with_metadata.return_value = (mat, rows)

            result = runner.invoke(
                cli,
                ["model", "cluster-report", "--model", "kmeans_2", "--top-chunks", "2"],
            )

        assert result.exit_code == 0, result.output

    def test_cluster_report_command_embedding_model_mismatch_warning(self) -> None:
        """Mismatched embedding_model between corpus and model triggers a warning."""
        from lutz.cli import cli

        mat, rows, km = self._make_fake_data()
        # Model was trained with a different embedding model
        meta = {
            "model_id": "kmeans_2",
            "algorithm": "kmeans",
            "params": {"n_clusters": 2},
            "embedding_model": "different-model",  # mismatch
            "n_rows": mat.shape[0],
            "corpus_hash": "abc123",
            "trained_at": "2024-01-01T00:00:00",
        }

        runner = CliRunner()
        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.FittedModelStore") as MockStore,
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_store = MockStore.return_value
            mock_store.load.return_value = (km, meta)

            mock_vs = MockVS.return_value
            # Corpus uses "test-model" but meta says "different-model"
            # We simulate corpus metadata by patching get_all_embeddings
            mock_vs.get_all_embeddings.return_value = (
                mat,
                {"embedding_model": "test-model", "n_rows": mat.shape[0], "corpus_hash": "abc123"},
            )
            mock_vs.get_all_embeddings_with_metadata.return_value = (mat, rows)

            result = runner.invoke(
                cli, ["model", "cluster-report", "--model", "kmeans_2"]
            )

        # Command should still succeed (warning, not error)
        assert result.exit_code == 0, result.output
        assert "warning" in result.output.lower() or "mismatch" in result.output.lower() or "differ" in result.output.lower()
