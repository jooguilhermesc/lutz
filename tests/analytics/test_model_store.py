"""Tests for FittedModelStore — TDD phase Red/Green for US-0."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kmeans(n_clusters: int = 3, n_features: int = 8, n_samples: int = 60):
    """Return a fitted KMeans and a metadata dict for it."""
    from sklearn.cluster import KMeans

    rng = np.random.default_rng(0)
    X = rng.normal(size=(n_samples, n_features)).astype(np.float32)
    model = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    model.fit(X)
    meta = {
        "model_id": f"kmeans_{n_clusters}",
        "algorithm": "kmeans",
        "params": {"n_clusters": n_clusters},
        "embedding_model": "text-embedding-3-small",
        "n_rows": n_samples,
        "corpus_hash": "abc123",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "random_state": 42,
    }
    return model, meta


# ---------------------------------------------------------------------------
# test_fitted_model_store_save_load
# ---------------------------------------------------------------------------

def test_fitted_model_store_save_load(tmp_path: Path):
    """Saving a model and reloading it should reproduce identical predictions."""
    from lutz.analytics.model_store import FittedModelStore

    store = FittedModelStore(tmp_path)
    model, meta = _make_kmeans(n_clusters=3)
    store.save("kmeans_3", model, meta)

    # Both artefact files must exist
    assert (tmp_path / "kmeans_3.joblib").exists()
    assert (tmp_path / "kmeans_3.meta.json").exists()

    loaded_model, loaded_meta = store.load("kmeans_3")

    # Metadata round-trip
    assert loaded_meta["model_id"] == "kmeans_3"
    assert loaded_meta["algorithm"] == "kmeans"
    assert loaded_meta["embedding_model"] == "text-embedding-3-small"
    assert loaded_meta["corpus_hash"] == "abc123"

    # Predictions must be identical to the original model
    rng = np.random.default_rng(99)
    X_test = rng.normal(size=(20, 8)).astype(np.float32)
    np.testing.assert_array_equal(model.predict(X_test), loaded_model.predict(X_test))


# ---------------------------------------------------------------------------
# test_corpus_hash_invalidation
# ---------------------------------------------------------------------------

def test_corpus_hash_invalidation(tmp_path: Path):
    """check_corpus_valid returns True for matching hash, False when hash changes."""
    from lutz.analytics.model_store import FittedModelStore

    store = FittedModelStore(tmp_path)
    model, meta = _make_kmeans()
    store.save("kmeans_3", model, meta)

    # Same hash → valid
    assert store.check_corpus_valid("kmeans_3", "abc123") is True

    # Different hash → invalid (should also log a warning — no assertion on log here)
    assert store.check_corpus_valid("kmeans_3", "different_hash") is False


# ---------------------------------------------------------------------------
# test_fitted_model_store_exists_and_remove
# ---------------------------------------------------------------------------

def test_fitted_model_store_exists_and_remove(tmp_path: Path):
    """exists() and remove() behave correctly."""
    from lutz.analytics.model_store import FittedModelStore

    store = FittedModelStore(tmp_path)
    model, meta = _make_kmeans()

    assert store.exists("kmeans_3") is False
    store.save("kmeans_3", model, meta)
    assert store.exists("kmeans_3") is True

    store.remove("kmeans_3")
    assert store.exists("kmeans_3") is False
    assert not (tmp_path / "kmeans_3.joblib").exists()
    assert not (tmp_path / "kmeans_3.meta.json").exists()


# ---------------------------------------------------------------------------
# test_fitted_model_store_list_models
# ---------------------------------------------------------------------------

def test_fitted_model_store_list_models(tmp_path: Path):
    """list_models returns one entry per saved model."""
    from lutz.analytics.model_store import FittedModelStore

    store = FittedModelStore(tmp_path)
    model_a, meta_a = _make_kmeans(n_clusters=3)
    meta_a["model_id"] = "kmeans_3"
    model_b, meta_b = _make_kmeans(n_clusters=5)
    meta_b["model_id"] = "kmeans_5"

    store.save("kmeans_3", model_a, meta_a)
    store.save("kmeans_5", model_b, meta_b)

    models = store.list_models()
    ids = {m["model_id"] for m in models}
    assert ids == {"kmeans_3", "kmeans_5"}


# ---------------------------------------------------------------------------
# test_load_nonexistent_raises
# ---------------------------------------------------------------------------

def test_load_nonexistent_raises(tmp_path: Path):
    """Loading a model that has not been saved raises a descriptive error."""
    from lutz.analytics.model_store import FittedModelStore

    store = FittedModelStore(tmp_path)
    with pytest.raises(FileNotFoundError, match="kmeans_99"):
        store.load("kmeans_99")
