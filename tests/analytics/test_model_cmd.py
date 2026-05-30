"""Smoke tests for 'lutz model' command — TDD phase Red/Green for US-0."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_store(n_rows: int = 200, dim: int = 8, embedding_model: str = "em3-small"):
    """Return a MagicMock that mimics VectorStore with get_all_embeddings."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n_rows, dim)).astype(np.float32)
    corpus_hash = "testhash"
    store_mock = MagicMock()
    store_mock.get_all_embeddings.return_value = (
        X,
        {"embedding_model": embedding_model, "n_rows": n_rows, "corpus_hash": corpus_hash},
    )
    return store_mock


# ---------------------------------------------------------------------------
# test_model_cmd_fit_kmeans
# ---------------------------------------------------------------------------

def test_model_cmd_fit_kmeans(tmp_path: Path):
    """lutz model fit kmeans --k 3 persists a model and prints confirmation."""
    from lutz.commands.model_cmd import model

    runner = CliRunner()

    store_mock = _make_mock_store()

    with patch("lutz.commands.model_cmd.require_project_root", return_value=tmp_path), \
         patch("lutz.commands.model_cmd.VectorStore", return_value=store_mock):

        # Ensure .lutz/models dir doesn't block the test
        (tmp_path / ".lutz" / "models").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".lutz" / "vector_store").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(model, ["fit", "kmeans", "--k", "3"])

    assert result.exit_code == 0, result.output
    assert "kmeans_3" in result.output


# ---------------------------------------------------------------------------
# test_model_cmd_fit_pca
# ---------------------------------------------------------------------------

def test_model_cmd_fit_pca(tmp_path: Path):
    """lutz model fit pca --n 2 persists a PCA model."""
    from lutz.commands.model_cmd import model

    runner = CliRunner()
    store_mock = _make_mock_store()

    with patch("lutz.commands.model_cmd.require_project_root", return_value=tmp_path), \
         patch("lutz.commands.model_cmd.VectorStore", return_value=store_mock):

        (tmp_path / ".lutz" / "models").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".lutz" / "vector_store").mkdir(parents=True, exist_ok=True)

        result = runner.invoke(model, ["fit", "pca", "--n", "2"])

    assert result.exit_code == 0, result.output
    assert "pca_2" in result.output


# ---------------------------------------------------------------------------
# test_model_cmd_list
# ---------------------------------------------------------------------------

def test_model_cmd_list(tmp_path: Path):
    """lutz model list shows model_id column after fitting."""
    from lutz.commands.model_cmd import model
    from lutz.analytics.model_store import FittedModelStore
    from sklearn.cluster import KMeans

    runner = CliRunner()

    # Pre-create a persisted model
    models_dir = tmp_path / ".lutz" / "models"
    models_dir.mkdir(parents=True)

    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, 8)).astype(np.float32)
    km = KMeans(n_clusters=3, random_state=42, n_init="auto").fit(X)
    fs = FittedModelStore(models_dir)
    fs.save("kmeans_3", km, {
        "model_id": "kmeans_3",
        "algorithm": "kmeans",
        "params": {"n_clusters": 3},
        "embedding_model": "em3-small",
        "n_rows": 60,
        "corpus_hash": "hash1",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "random_state": 42,
    })

    store_mock = _make_mock_store()

    with patch("lutz.commands.model_cmd.require_project_root", return_value=tmp_path), \
         patch("lutz.commands.model_cmd.VectorStore", return_value=store_mock):

        result = runner.invoke(model, ["list"])

    assert result.exit_code == 0, result.output
    assert "kmeans_3" in result.output


# ---------------------------------------------------------------------------
# test_model_cmd_rm
# ---------------------------------------------------------------------------

def test_model_cmd_rm(tmp_path: Path):
    """lutz model rm <id> removes the model files."""
    from lutz.commands.model_cmd import model
    from lutz.analytics.model_store import FittedModelStore
    from sklearn.cluster import KMeans

    runner = CliRunner()

    models_dir = tmp_path / ".lutz" / "models"
    models_dir.mkdir(parents=True)

    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, 8)).astype(np.float32)
    km = KMeans(n_clusters=3, random_state=42, n_init="auto").fit(X)
    fs = FittedModelStore(models_dir)
    fs.save("kmeans_3", km, {
        "model_id": "kmeans_3",
        "algorithm": "kmeans",
        "params": {"n_clusters": 3},
        "embedding_model": "em3-small",
        "n_rows": 60,
        "corpus_hash": "hash1",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "random_state": 42,
    })

    with patch("lutz.commands.model_cmd.require_project_root", return_value=tmp_path):
        result = runner.invoke(model, ["rm", "kmeans_3"])

    assert result.exit_code == 0, result.output
    assert not (models_dir / "kmeans_3.joblib").exists()
