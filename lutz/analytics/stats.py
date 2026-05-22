"""Embedding statistics UDFs for DuckDB.

Available functions
-------------------
embedding_norm(v)        -> DOUBLE         — L2 magnitude of a vector
embedding_normalize(v)   -> DOUBLE[]       — unit-length version of a vector
embedding_z_score(v)     -> DOUBLE[]       — batch-wise z-score normalization
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import duckdb

from lutz.analytics.registry import lutz_udf
from lutz.analytics.distances import _to_matrix, _LIST_DBL


@lutz_udf(
    name="embedding_norm",
    parameters=[_LIST_DBL],
    return_type=duckdb.type("DOUBLE"),
    description="L2 norm (magnitude) of an embedding vector.",
)
def embedding_norm(v: pa.Array) -> pa.Array:
    mat = _to_matrix(v)
    norms = np.linalg.norm(mat, axis=1)
    return pa.array(norms.tolist())


@lutz_udf(
    name="embedding_normalize",
    parameters=[_LIST_DBL],
    return_type=_LIST_DBL,
    description="Return the L2-normalized (unit vector) version of an embedding.",
)
def embedding_normalize(v: pa.Array) -> pa.Array:
    mat = _to_matrix(v)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    normalized = mat / np.where(norms == 0, 1e-10, norms)
    return pa.array(normalized.tolist())


@lutz_udf(
    name="embedding_z_score",
    parameters=[_LIST_DBL],
    return_type=_LIST_DBL,
    description=(
        "Z-score normalize an embedding across the batch: "
        "subtract per-dimension mean, divide by per-dimension std."
    ),
)
def embedding_z_score(v: pa.Array) -> pa.Array:
    mat = _to_matrix(v)
    mean = mat.mean(axis=0)
    std = mat.std(axis=0)
    std = np.where(std == 0, 1e-10, std)
    z = (mat - mean) / std
    return pa.array(z.tolist())
