"""Tests for predict_cluster / predict_coords UDFs — TDD phase Red/Green for US-0."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_corpus(n: int, dim: int, seed: int = 0) -> np.ndarray:
    """Return a (n, dim) float32 matrix of synthetic embeddings."""
    rng = np.random.default_rng(seed)
    # Two well-separated clusters
    half = n // 2
    A = rng.normal(loc=1.0, scale=0.2, size=(half, dim)).astype(np.float32)
    B = rng.normal(loc=-1.0, scale=0.2, size=(n - half, dim)).astype(np.float32)
    return np.vstack([A, B])


def _fit_and_persist_kmeans(models_dir: Path, model_id: str, X: np.ndarray, k: int = 2,
                             embedding_model: str = "text-embedding-3-small") -> object:
    """Train KMeans on X and persist via FittedModelStore. Returns fitted model."""
    from sklearn.cluster import KMeans
    from lutz.analytics.model_store import FittedModelStore

    model = KMeans(n_clusters=k, random_state=42, n_init="auto")
    model.fit(X)
    meta = {
        "model_id": model_id,
        "algorithm": "kmeans",
        "params": {"n_clusters": k},
        "embedding_model": embedding_model,
        "n_rows": X.shape[0],
        "corpus_hash": "testhash",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "random_state": 42,
    }
    store = FittedModelStore(models_dir)
    store.save(model_id, model, meta)
    return model


def _fit_and_persist_pca(models_dir: Path, model_id: str, X: np.ndarray, n_components: int = 2,
                          embedding_model: str = "text-embedding-3-small") -> object:
    """Train PCA on X and persist via FittedModelStore. Returns fitted model."""
    from sklearn.decomposition import PCA
    from lutz.analytics.model_store import FittedModelStore

    model = PCA(n_components=n_components, random_state=42)
    model.fit(X)
    meta = {
        "model_id": model_id,
        "algorithm": "pca",
        "params": {"n_components": n_components},
        "embedding_model": embedding_model,
        "n_rows": X.shape[0],
        "corpus_hash": "testhash",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "random_state": 42,
    }
    store = FittedModelStore(models_dir)
    store.save(model_id, model, meta)
    return model


# ---------------------------------------------------------------------------
# test_predict_cluster_stable_labels
# ---------------------------------------------------------------------------

def test_predict_cluster_stable_labels(tmp_path: Path):
    """predict_cluster labels must be identical to model.predict() called directly."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    dim = 16
    X = _build_corpus(200, dim)
    model = _fit_and_persist_kmeans(tmp_path, "kmeans_2", X, k=2)

    clear_model_cache()

    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    # Build Arrow table with embeddings as DOUBLE[] (float64 for DuckDB)
    table = pa.table({"embedding": [row.astype(np.float64).tolist() for row in X]})
    conn.register("vecs", table)

    rows = conn.execute(
        "SELECT predict_cluster(embedding, 'kmeans_2') AS label FROM vecs"
    ).fetchall()

    sql_labels = np.array([r[0] for r in rows])
    py_labels = model.predict(X)

    np.testing.assert_array_equal(sql_labels, py_labels)


# ---------------------------------------------------------------------------
# test_predict_cluster_consistent_across_batches
# ---------------------------------------------------------------------------

def test_predict_cluster_consistent_across_batches(tmp_path: Path):
    """Labels must be identical across two separate SQL queries (multi-batch)."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    # 3000 rows > DuckDB's 2048-row batch threshold
    dim = 8
    X = _build_corpus(3000, dim)
    _fit_and_persist_kmeans(tmp_path, "kmeans_2", X, k=2)

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": [row.astype(np.float64).tolist() for row in X]})
    conn.register("vecs", table)

    run1 = [r[0] for r in conn.execute(
        "SELECT predict_cluster(embedding, 'kmeans_2') FROM vecs"
    ).fetchall()]
    run2 = [r[0] for r in conn.execute(
        "SELECT predict_cluster(embedding, 'kmeans_2') FROM vecs"
    ).fetchall()]

    assert run1 == run2, "Labels must be stable across separate queries"
    assert len(run1) == 3000


# ---------------------------------------------------------------------------
# test_predict_coords_stable
# ---------------------------------------------------------------------------

def test_predict_coords_stable(tmp_path: Path):
    """predict_coords must return identical 2-D projections across queries."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    dim = 16
    X = _build_corpus(200, dim)
    model = _fit_and_persist_pca(tmp_path, "pca_2", X, n_components=2)

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": [row.astype(np.float64).tolist() for row in X]})
    conn.register("vecs", table)

    rows = conn.execute(
        "SELECT predict_coords(embedding, 'pca_2') AS coords FROM vecs"
    ).fetchall()

    sql_coords = np.array([r[0] for r in rows])
    py_coords = model.transform(X)

    np.testing.assert_allclose(sql_coords, py_coords, rtol=1e-5)


# ---------------------------------------------------------------------------
# test_predict_cluster_rejects_wrong_embedding_model
# ---------------------------------------------------------------------------

def test_predict_cluster_rejects_wrong_embedding_model(tmp_path: Path):
    """If embedding_model param mismatches model meta, a UserWarning is emitted."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    dim = 8
    X = _build_corpus(50, dim, seed=7)
    _fit_and_persist_kmeans(tmp_path, "kmeans_2", X, k=2, embedding_model="model-A")

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": [row.astype(np.float64).tolist() for row in X]})
    conn.register("vecs", table)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        conn.execute(
            "SELECT predict_cluster_checked(embedding, 'kmeans_2', 'model-B') FROM vecs"
        ).fetchall()

    matched = [x for x in w if issubclass(x.category, UserWarning) and "model-A" in str(x.message)]
    assert matched, "Expected a UserWarning about embedding model mismatch"


# ---------------------------------------------------------------------------
# test_predict_cluster_model_not_found
# ---------------------------------------------------------------------------

def test_predict_cluster_model_not_found(tmp_path: Path):
    """Calling predict_cluster with an unknown model_id raises a descriptive error."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": [[1.0, 0.0, 0.0]]})
    conn.register("tiny", table)

    with pytest.raises(Exception, match="kmeans_99"):
        conn.execute("SELECT predict_cluster(embedding, 'kmeans_99') FROM tiny").fetchall()
