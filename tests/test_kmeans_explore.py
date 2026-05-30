"""Tests for kmeans_explore utility and the `lutz model explore kmeans` command.

TDD cycle: RED phase — these tests are written before the implementation.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clustered_matrix(n_per_cluster: int, n_dims: int, seed: int = 0) -> np.ndarray:
    """Return a matrix with clearly separated clusters for deterministic tests."""
    rng = np.random.default_rng(seed)
    centers = rng.standard_normal((3, n_dims)) * 10  # well-separated centers
    chunks = []
    for center in centers:
        cluster = center + rng.standard_normal((n_per_cluster, n_dims)) * 0.01
        chunks.append(cluster)
    return np.vstack(chunks).astype(np.float32)


# ---------------------------------------------------------------------------
# Tests for explore_kmeans()
# ---------------------------------------------------------------------------


class TestExploreKmeans:
    def test_explore_kmeans_returns_all_k_values(self) -> None:
        """k_range=range(2,6) must produce exactly 4 entries."""
        from lutz.utils.kmeans_explore import explore_kmeans

        mat = _make_clustered_matrix(n_per_cluster=20, n_dims=8)
        results = explore_kmeans(mat, k_range=range(2, 6), random_state=42)

        assert len(results) == 4
        assert [r["k"] for r in results] == [2, 3, 4, 5]

    def test_explore_kmeans_silhouette_positive_for_good_clusters(self) -> None:
        """With 3 well-separated clusters, silhouette(k=3) > silhouette(k=2)."""
        from lutz.utils.kmeans_explore import explore_kmeans

        mat = _make_clustered_matrix(n_per_cluster=30, n_dims=16, seed=7)
        results = explore_kmeans(mat, k_range=range(2, 5), random_state=42)

        by_k = {r["k"]: r["silhouette"] for r in results}
        assert by_k[3] > by_k[2]

    def test_explore_kmeans_deterministic(self) -> None:
        """Same call twice must return identical results."""
        from lutz.utils.kmeans_explore import explore_kmeans

        mat = _make_clustered_matrix(n_per_cluster=20, n_dims=8, seed=3)
        r1 = explore_kmeans(mat, k_range=range(2, 5), random_state=42)
        r2 = explore_kmeans(mat, k_range=range(2, 5), random_state=42)

        for a, b in zip(r1, r2):
            assert a["k"] == b["k"]
            assert a["silhouette"] == pytest.approx(b["silhouette"])
            assert a["inertia"] == pytest.approx(b["inertia"])

    def test_explore_kmeans_suggested_k(self) -> None:
        """The entry with the highest silhouette is the suggested k."""
        from lutz.utils.kmeans_explore import explore_kmeans

        mat = _make_clustered_matrix(n_per_cluster=25, n_dims=12, seed=5)
        results = explore_kmeans(mat, k_range=range(2, 7), random_state=42)

        best = max(results, key=lambda r: r["silhouette"])
        # Confirm that silhouette and inertia are present and plausible
        assert best["silhouette"] > 0
        assert best["inertia"] > 0
        # The suggested k key must be present on each record so callers can
        # identify the recommendation
        assert all("k" in r and "silhouette" in r and "inertia" in r for r in results)


# ---------------------------------------------------------------------------
# Tests for parse_k_range()
# ---------------------------------------------------------------------------


class TestParseKRange:
    def test_parse_k_range_valid(self) -> None:
        """'2..10' must produce range(2, 11)."""
        from lutz.utils.kmeans_explore import parse_k_range

        r = parse_k_range("2..10")
        assert r == range(2, 11)

    def test_parse_k_range_valid_tight(self) -> None:
        """'3..5' must produce range(3, 6)."""
        from lutz.utils.kmeans_explore import parse_k_range

        r = parse_k_range("3..5")
        assert r == range(3, 6)

    def test_parse_k_range_invalid_format(self) -> None:
        """Non-numeric input must raise ValueError."""
        from lutz.utils.kmeans_explore import parse_k_range

        with pytest.raises(ValueError, match="k-range"):
            parse_k_range("abc")

    def test_parse_k_range_invalid_a_less_than_2(self) -> None:
        """A=1 (< 2) must raise ValueError."""
        from lutz.utils.kmeans_explore import parse_k_range

        with pytest.raises(ValueError, match="2"):
            parse_k_range("1..5")

    def test_parse_k_range_invalid_b_not_greater_than_a(self) -> None:
        """B <= A must raise ValueError."""
        from lutz.utils.kmeans_explore import parse_k_range

        with pytest.raises(ValueError):
            parse_k_range("10..5")

        with pytest.raises(ValueError):
            parse_k_range("5..5")

    def test_parse_k_range_invalid_too_wide(self) -> None:
        """B - A > 30 must raise ValueError."""
        from lutz.utils.kmeans_explore import parse_k_range

        with pytest.raises(ValueError, match="30"):
            parse_k_range("2..33")


# ---------------------------------------------------------------------------
# Smoke test for the CLI command
# ---------------------------------------------------------------------------


class TestExploreCommandSmoke:
    def _make_fake_matrix(self) -> tuple[np.ndarray, dict]:
        mat = _make_clustered_matrix(n_per_cluster=20, n_dims=8, seed=0)
        meta = {
            "embedding_model": "test-model",
            "n_rows": mat.shape[0],
            "corpus_hash": "abc123",
        }
        return mat, meta

    def test_explore_command_smoke_table(self) -> None:
        """Smoke test: command runs without error and prints a table."""
        from lutz.cli import cli

        runner = CliRunner()
        fake_mat, fake_meta = self._make_fake_matrix()

        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings.return_value = (fake_mat, fake_meta)

            result = runner.invoke(cli, ["model", "explore", "kmeans", "--k-range", "2..4"])

        assert result.exit_code == 0, result.output
        # Table must contain k values
        assert "2" in result.output
        assert "3" in result.output
        assert "4" in result.output
        # Suggestion message must be present
        assert "Suggested k=" in result.output

    def test_explore_command_smoke_json(self) -> None:
        """With --format json, output must be parseable JSON list."""
        from lutz.cli import cli

        runner = CliRunner()
        fake_mat, fake_meta = self._make_fake_matrix()

        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings.return_value = (fake_mat, fake_meta)

            result = runner.invoke(
                cli, ["model", "explore", "kmeans", "--k-range", "2..4", "--format", "json"]
            )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 3  # k=2,3,4
        assert all("k" in item and "silhouette" in item and "inertia" in item for item in data)

    def test_explore_command_smoke_sample(self) -> None:
        """--sample N triggers sample warning in output."""
        from lutz.cli import cli

        runner = CliRunner()
        fake_mat, fake_meta = self._make_fake_matrix()

        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings.return_value = (fake_mat, fake_meta)

            result = runner.invoke(
                cli,
                ["model", "explore", "kmeans", "--k-range", "2..4", "--sample", "30"],
            )

        assert result.exit_code == 0, result.output
        assert "sample" in result.output.lower()

    def test_explore_command_empty_store(self) -> None:
        """Empty vector store must exit early with a user-friendly message."""
        from lutz.cli import cli

        runner = CliRunner()
        empty_mat = np.empty((0, 0), dtype=np.float32)

        with (
            patch("lutz.commands.model_cmd.require_project_root", return_value=MagicMock()),
            patch("lutz.commands.model_cmd.VectorStore") as MockVS,
        ):
            mock_vs = MockVS.return_value
            mock_vs.get_all_embeddings.return_value = (empty_mat, {})

            result = runner.invoke(cli, ["model", "explore", "kmeans", "--k-range", "2..4"])

        assert result.exit_code == 0
        assert "empty" in result.output.lower() or "vectorize" in result.output.lower()
