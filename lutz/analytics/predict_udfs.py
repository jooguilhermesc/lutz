"""Stateless predict UDFs for DuckDB — uses pre-trained models from FittedModelStore.

Available SQL functions (after register_predict_udfs is called):
  predict_cluster(embedding DOUBLE[], model_id VARCHAR)                    -> INTEGER
  predict_cluster(embedding DOUBLE[], model_id VARCHAR, emb_model VARCHAR) -> INTEGER
  predict_coords(embedding DOUBLE[], model_id VARCHAR)                     -> DOUBLE[]
  predict_coords(embedding DOUBLE[], model_id VARCHAR, emb_model VARCHAR)  -> DOUBLE[]

Models are loaded once per process and cached in ``_MODEL_CACHE``.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pyarrow as pa

# Module-level cache: model_id -> (model, metadata)
_MODEL_CACHE: dict[str, tuple[object, dict]] = {}

# Injected at registration time — the directory where FittedModelStore looks.
_MODELS_DIR: Path | None = None


def clear_model_cache() -> None:
    """Clear the in-process model cache (useful for tests)."""
    _MODEL_CACHE.clear()


def _load_model(model_id: str) -> tuple[object, dict]:
    """Load model from cache or disk, raising descriptive errors on miss."""
    if model_id in _MODEL_CACHE:
        return _MODEL_CACHE[model_id]

    if _MODELS_DIR is None:
        raise RuntimeError(
            "predict_udfs: models_dir not configured — call register_predict_udfs() first."
        )

    from lutz.analytics.model_store import FittedModelStore

    store = FittedModelStore(_MODELS_DIR)
    if not store.exists(model_id):
        raise FileNotFoundError(
            f"Model '{model_id}' not found — run 'lutz model fit' to train it first."
        )

    model, meta = store.load(model_id)
    _MODEL_CACHE[model_id] = (model, meta)
    return model, meta


def _check_embedding_model(meta: dict, requested_embedding_model: str | None) -> None:
    """Emit a UserWarning if the stored embedding_model differs from the requested one."""
    if requested_embedding_model is None:
        return
    stored = meta.get("embedding_model", "")
    if stored and stored != requested_embedding_model:
        warnings.warn(
            f"Embedding model mismatch: model '{meta.get('model_id')}' was trained with "
            f"embedding_model='{stored}' but the caller passed '{requested_embedding_model}'. "
            "Labels may be incoherent. Re-train with 'lutz model fit'.",
            UserWarning,
            stacklevel=4,
        )


def _to_matrix_float32(arr: pa.Array | pa.ChunkedArray) -> np.ndarray:
    """Convert Arrow array of list<double> to a 2-D float32 numpy matrix."""
    if isinstance(arr, pa.ChunkedArray):
        arr = arr.combine_chunks()
    flat = arr.to_pylist()
    return np.array(flat, dtype=np.float32)


# ---------------------------------------------------------------------------
# UDF implementations (Arrow batch functions — receive pa.Array per argument)
# ---------------------------------------------------------------------------

def _predict_cluster_2arg(embedding: pa.Array, model_id_arr: pa.Array) -> pa.Array:
    """predict_cluster(embedding, model_id) -> INTEGER."""
    model_id = model_id_arr.to_pylist()[0]
    model, meta = _load_model(model_id)
    X = _to_matrix_float32(embedding)
    labels = model.predict(X)
    return pa.array(labels.tolist(), type=pa.int32())


def _predict_cluster_3arg(
    embedding: pa.Array, model_id_arr: pa.Array, emb_model_arr: pa.Array
) -> pa.Array:
    """predict_cluster(embedding, model_id, embedding_model) -> INTEGER."""
    model_id = model_id_arr.to_pylist()[0]
    requested_emb = emb_model_arr.to_pylist()[0]
    model, meta = _load_model(model_id)
    _check_embedding_model(meta, requested_emb)
    X = _to_matrix_float32(embedding)
    labels = model.predict(X)
    return pa.array(labels.tolist(), type=pa.int32())


def _predict_coords_2arg(embedding: pa.Array, model_id_arr: pa.Array) -> pa.Array:
    """predict_coords(embedding, model_id) -> DOUBLE[]."""
    model_id = model_id_arr.to_pylist()[0]
    model, meta = _load_model(model_id)
    X = _to_matrix_float32(embedding)
    coords = model.transform(X)  # PCA / dimensionality reducer
    return pa.array(coords.tolist())


def _predict_coords_3arg(
    embedding: pa.Array, model_id_arr: pa.Array, emb_model_arr: pa.Array
) -> pa.Array:
    """predict_coords(embedding, model_id, embedding_model) -> DOUBLE[]."""
    model_id = model_id_arr.to_pylist()[0]
    requested_emb = emb_model_arr.to_pylist()[0]
    model, meta = _load_model(model_id)
    _check_embedding_model(meta, requested_emb)
    X = _to_matrix_float32(embedding)
    coords = model.transform(X)
    return pa.array(coords.tolist())


def _cosine_distance_to_centroid(X: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    """Return cosine distance from each row of X to centroid (1-D array)."""
    centroid = centroid.astype(np.float64)
    X = X.astype(np.float64)
    dot = X @ centroid  # (N,)
    norm_rows = np.linalg.norm(X, axis=1)  # (N,)
    norm_c = np.linalg.norm(centroid)
    denom = norm_rows * norm_c
    denom = np.where(denom == 0, 1e-10, denom)
    return 1.0 - dot / denom


def _predict_centroid_distance_2arg(embedding: pa.Array, model_id_arr: pa.Array) -> pa.Array:
    """predict_centroid_distance(embedding, model_id) -> DOUBLE."""
    model_id = model_id_arr.to_pylist()[0]
    centroid, _meta = _load_model(model_id)
    X = _to_matrix_float32(embedding)
    dist = _cosine_distance_to_centroid(X, np.asarray(centroid))
    return pa.array(dist.tolist())


def _predict_centroid_distance_3arg(
    embedding: pa.Array, model_id_arr: pa.Array, emb_model_arr: pa.Array
) -> pa.Array:
    """predict_centroid_distance_checked(embedding, model_id, embedding_model) -> DOUBLE."""
    model_id = model_id_arr.to_pylist()[0]
    requested_emb = emb_model_arr.to_pylist()[0]
    centroid, meta = _load_model(model_id)
    _check_embedding_model(meta, requested_emb)
    X = _to_matrix_float32(embedding)
    dist = _cosine_distance_to_centroid(X, np.asarray(centroid))
    return pa.array(dist.tolist())


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_predict_udfs(conn, *, models_dir: Path) -> None:
    """Register ``predict_cluster`` and ``predict_coords`` in a DuckDB connection.

    Parameters
    ----------
    conn:
        Open ``duckdb.DuckDBPyConnection``.
    models_dir:
        Directory managed by :class:`~lutz.analytics.model_store.FittedModelStore`.
    """
    import duckdb

    global _MODELS_DIR
    _MODELS_DIR = Path(models_dir)

    _LIST_DBL = duckdb.list_type(duckdb.type("DOUBLE"))
    _VARCHAR = duckdb.type("VARCHAR")
    _INT = duckdb.type("INTEGER")

    # predict_cluster(embedding, model_id) -> INTEGER
    conn.create_function(
        "predict_cluster",
        _predict_cluster_2arg,
        parameters=[_LIST_DBL, _VARCHAR],
        return_type=_INT,
        type="arrow",
    )

    # predict_cluster_checked(embedding, model_id, embedding_model) -> INTEGER
    # Emits UserWarning when embedding_model does not match model metadata.
    conn.create_function(
        "predict_cluster_checked",
        _predict_cluster_3arg,
        parameters=[_LIST_DBL, _VARCHAR, _VARCHAR],
        return_type=_INT,
        type="arrow",
    )

    # predict_coords(embedding, model_id) -> DOUBLE[]
    conn.create_function(
        "predict_coords",
        _predict_coords_2arg,
        parameters=[_LIST_DBL, _VARCHAR],
        return_type=_LIST_DBL,
        type="arrow",
    )

    # predict_coords_checked(embedding, model_id, embedding_model) -> DOUBLE[]
    conn.create_function(
        "predict_coords_checked",
        _predict_coords_3arg,
        parameters=[_LIST_DBL, _VARCHAR, _VARCHAR],
        return_type=_LIST_DBL,
        type="arrow",
    )

    _DBL = duckdb.type("DOUBLE")

    # predict_centroid_distance(embedding, model_id) -> DOUBLE
    conn.create_function(
        "predict_centroid_distance",
        _predict_centroid_distance_2arg,
        parameters=[_LIST_DBL, _VARCHAR],
        return_type=_DBL,
        type="arrow",
    )

    # predict_centroid_distance_checked(embedding, model_id, embedding_model) -> DOUBLE
    conn.create_function(
        "predict_centroid_distance_checked",
        _predict_centroid_distance_3arg,
        parameters=[_LIST_DBL, _VARCHAR, _VARCHAR],
        return_type=_DBL,
        type="arrow",
    )
