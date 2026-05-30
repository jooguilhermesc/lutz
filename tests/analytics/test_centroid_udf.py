"""Tests for predict_centroid_distance UDF and 'lutz model fit centroid' — US-4 TDD Red."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pyarrow as pa
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_embeddings(n: int, dim: int, seed: int = 0) -> np.ndarray:
    """Return a (n, dim) float64 matrix of synthetic embeddings."""
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n, dim)).astype(np.float64)


def _persist_centroid(
    models_dir: Path,
    model_id: str,
    centroid: np.ndarray,
    embedding_model: str = "text-embedding-3-small",
    corpus_hash: str = "testhash",
    n_rows: int = 100,
) -> None:
    """Persist a centroid array via FittedModelStore."""
    from lutz.analytics.model_store import FittedModelStore

    meta = {
        "model_id": model_id,
        "algorithm": "centroid",
        "embedding_model": embedding_model,
        "n_rows": n_rows,
        "corpus_hash": corpus_hash,
        "trained_at": "2026-01-01T00:00:00+00:00",
    }
    store = FittedModelStore(models_dir)
    store.save(model_id, centroid, meta)


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine distance between two 1-D vectors."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(1.0 - np.dot(a, b) / denom)


# ---------------------------------------------------------------------------
# test_predict_centroid_distance_stable_across_batches
# ---------------------------------------------------------------------------

def test_predict_centroid_distance_stable_across_batches(tmp_path: Path):
    """Scores must be identical in two separate SQL queries — not batch-dependent.

    With a corpus of 3000 rows DuckDB splits into multiple batches of ~2048 rows.
    The batch-based implementation recomputes the centroid per batch, so the
    scores differ. predict_centroid_distance must load the pre-fitted centroid
    and produce stable results.
    """
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    n, dim = 3000, 8
    X = _build_embeddings(n, dim, seed=1)
    centroid = X.mean(axis=0)

    _persist_centroid(tmp_path, "corpus_centroid", centroid, n_rows=n)

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": X.tolist()})
    conn.register("vecs", table)

    run1 = [r[0] for r in conn.execute(
        "SELECT predict_centroid_distance(embedding, 'corpus_centroid') FROM vecs"
    ).fetchall()]
    run2 = [r[0] for r in conn.execute(
        "SELECT predict_centroid_distance(embedding, 'corpus_centroid') FROM vecs"
    ).fetchall()]

    assert run1 == run2, "Scores must be stable across separate queries"
    assert len(run1) == n


# ---------------------------------------------------------------------------
# test_predict_centroid_distance_matches_manual
# ---------------------------------------------------------------------------

def test_predict_centroid_distance_matches_manual(tmp_path: Path):
    """UDF output must match manually computed cosine distance to centroid."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    dim = 16
    X = _build_embeddings(50, dim, seed=2)
    centroid = X.mean(axis=0)

    _persist_centroid(tmp_path, "corpus_centroid", centroid, n_rows=50)

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": X.tolist()})
    conn.register("vecs", table)

    rows = conn.execute(
        "SELECT predict_centroid_distance(embedding, 'corpus_centroid') FROM vecs"
    ).fetchall()
    sql_scores = np.array([r[0] for r in rows])

    # Manual computation
    expected = np.array([_cosine_distance(row, centroid) for row in X])

    np.testing.assert_allclose(sql_scores, expected, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# test_predict_centroid_distance_model_not_found
# ---------------------------------------------------------------------------

def test_predict_centroid_distance_model_not_found(tmp_path: Path):
    """Calling predict_centroid_distance with an unknown model_id raises a descriptive error."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": [[1.0, 0.0, 0.0]]})
    conn.register("tiny", table)

    with pytest.raises(Exception, match="corpus_centroid"):
        conn.execute(
            "SELECT predict_centroid_distance(embedding, 'corpus_centroid') FROM tiny"
        ).fetchall()


# ---------------------------------------------------------------------------
# test_model_fit_centroid_command_smoke
# ---------------------------------------------------------------------------

def test_model_fit_centroid_command_smoke(tmp_path: Path):
    """'lutz model fit centroid' saves a corpus_centroid model and prints confirmation."""
    from lutz.commands.model_cmd import model
    from click.testing import CliRunner

    runner = CliRunner()

    n_rows, dim = 150, 8
    rng = np.random.default_rng(42)
    X = rng.normal(size=(n_rows, dim)).astype(np.float32)

    store_mock = MagicMock()
    store_mock.get_all_embeddings.return_value = (
        X,
        {
            "embedding_model": "em3-small",
            "n_rows": n_rows,
            "corpus_hash": "abc123",
        },
    )

    (tmp_path / ".lutz" / "models").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".lutz" / "vector_store").mkdir(parents=True, exist_ok=True)

    with patch("lutz.commands.model_cmd.require_project_root", return_value=tmp_path), \
         patch("lutz.commands.model_cmd.VectorStore", return_value=store_mock):

        result = runner.invoke(model, ["fit", "centroid"])

    assert result.exit_code == 0, result.output
    assert "corpus_centroid" in result.output
    assert str(n_rows) in result.output

    # Verify the model was actually persisted
    from lutz.analytics.model_store import FittedModelStore
    ms = FittedModelStore(tmp_path / ".lutz" / "models")
    assert ms.exists("corpus_centroid"), "centroid model must be persisted on disk"

    centroid, meta = ms.load("corpus_centroid")
    assert isinstance(centroid, np.ndarray)
    assert centroid.shape == (dim,)
    assert meta["algorithm"] == "centroid"
    assert meta["n_rows"] == n_rows
    assert meta["embedding_model"] == "em3-small"


# ---------------------------------------------------------------------------
# test_model_fit_centroid_custom_name
# ---------------------------------------------------------------------------

def test_model_fit_centroid_custom_name(tmp_path: Path):
    """'lutz model fit centroid --name my_centroid' saves with custom id."""
    from lutz.commands.model_cmd import model
    from click.testing import CliRunner

    runner = CliRunner()

    n_rows, dim = 50, 4
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n_rows, dim)).astype(np.float32)

    store_mock = MagicMock()
    store_mock.get_all_embeddings.return_value = (
        X,
        {"embedding_model": "em3", "n_rows": n_rows, "corpus_hash": "xyz"},
    )

    (tmp_path / ".lutz" / "models").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".lutz" / "vector_store").mkdir(parents=True, exist_ok=True)

    with patch("lutz.commands.model_cmd.require_project_root", return_value=tmp_path), \
         patch("lutz.commands.model_cmd.VectorStore", return_value=store_mock):

        result = runner.invoke(model, ["fit", "centroid", "--name", "my_centroid"])

    assert result.exit_code == 0, result.output
    assert "my_centroid" in result.output

    from lutz.analytics.model_store import FittedModelStore
    ms = FittedModelStore(tmp_path / ".lutz" / "models")
    assert ms.exists("my_centroid")


# ---------------------------------------------------------------------------
# test_centroid_invalidation_warning (end-to-end corpus_hash check)
# ---------------------------------------------------------------------------

def test_centroid_invalidation_warning(tmp_path: Path):
    """check_corpus_valid returns False (and logs warning) when corpus_hash changed."""
    from lutz.analytics.model_store import FittedModelStore

    dim = 8
    centroid = np.zeros(dim, dtype=np.float64)
    store = FittedModelStore(tmp_path)
    meta = {
        "model_id": "corpus_centroid",
        "algorithm": "centroid",
        "embedding_model": "em3-small",
        "n_rows": 100,
        "corpus_hash": "original_hash",
        "trained_at": "2026-01-01T00:00:00+00:00",
    }
    store.save("corpus_centroid", centroid, meta)

    # Same hash — should be valid
    assert store.check_corpus_valid("corpus_centroid", "original_hash") is True

    # Changed hash — should be invalid and emit a warning via logger.warning
    with patch("lutz.analytics.model_store.logger") as mock_logger:
        result = store.check_corpus_valid("corpus_centroid", "new_hash")

    assert result is False
    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "corpus_hash" in warning_msg or "Re-run" in warning_msg


# ---------------------------------------------------------------------------
# test_predict_centroid_distance_checked_warns_on_mismatch
# ---------------------------------------------------------------------------

def test_predict_centroid_distance_checked_warns_on_mismatch(tmp_path: Path):
    """predict_centroid_distance_checked emits UserWarning when embedding_model differs."""
    import duckdb
    from lutz.analytics.predict_udfs import register_predict_udfs, clear_model_cache

    dim = 8
    X = _build_embeddings(20, dim, seed=5)
    centroid = X.mean(axis=0)

    _persist_centroid(
        tmp_path, "corpus_centroid", centroid,
        embedding_model="model-A", n_rows=20,
    )

    clear_model_cache()
    conn = duckdb.connect()
    register_predict_udfs(conn, models_dir=tmp_path)

    table = pa.table({"embedding": X.tolist()})
    conn.register("vecs", table)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        conn.execute(
            "SELECT predict_centroid_distance_checked(embedding, 'corpus_centroid', 'model-B') "
            "FROM vecs"
        ).fetchall()

    matched = [
        x for x in w
        if issubclass(x.category, UserWarning) and "model-A" in str(x.message)
    ]
    assert matched, "Expected a UserWarning about embedding model mismatch"
