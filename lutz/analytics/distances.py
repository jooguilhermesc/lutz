"""Vector distance UDFs for DuckDB.

Available functions
-------------------
cosine_distance(a, b)    -> DOUBLE   — 0 = identical, 2 = opposite
cosine_similarity(a, b)  -> DOUBLE   — 1 = identical, -1 = opposite
euclidean_distance(a, b) -> DOUBLE   — L2 distance
dot_product(a, b)        -> DOUBLE   — raw inner product
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import duckdb

from lutz.analytics.registry import lutz_udf

_LIST_DBL = duckdb.list_type(duckdb.type("DOUBLE"))


def _to_matrix(arr: pa.Array | pa.ChunkedArray) -> np.ndarray:
    """Convert a (Chunked)Array of list<double> to a 2-D float64 ndarray."""
    if isinstance(arr, pa.ChunkedArray):
        arr = arr.combine_chunks()
    return np.array(arr.to_pylist(), dtype=np.float64)


@lutz_udf(
    name="cosine_distance",
    parameters=[_LIST_DBL, _LIST_DBL],
    return_type=duckdb.type("DOUBLE"),
    description="Cosine distance between two embedding vectors (0 = identical, 2 = opposite).",
)
def cosine_distance(a: pa.Array, b: pa.Array) -> pa.Array:
    va, vb = _to_matrix(a), _to_matrix(b)
    dot = np.einsum("ij,ij->i", va, vb)
    norm = np.linalg.norm(va, axis=1) * np.linalg.norm(vb, axis=1)
    dist = 1.0 - dot / np.where(norm == 0, 1e-10, norm)
    return pa.array(dist.tolist())


@lutz_udf(
    name="cosine_similarity",
    parameters=[_LIST_DBL, _LIST_DBL],
    return_type=duckdb.type("DOUBLE"),
    description="Cosine similarity between two embedding vectors (1 = identical, -1 = opposite).",
)
def cosine_similarity(a: pa.Array, b: pa.Array) -> pa.Array:
    va, vb = _to_matrix(a), _to_matrix(b)
    dot = np.einsum("ij,ij->i", va, vb)
    norm = np.linalg.norm(va, axis=1) * np.linalg.norm(vb, axis=1)
    sim = dot / np.where(norm == 0, 1e-10, norm)
    return pa.array(sim.tolist())


@lutz_udf(
    name="euclidean_distance",
    parameters=[_LIST_DBL, _LIST_DBL],
    return_type=duckdb.type("DOUBLE"),
    description="Euclidean (L2) distance between two embedding vectors.",
)
def euclidean_distance(a: pa.Array, b: pa.Array) -> pa.Array:
    va, vb = _to_matrix(a), _to_matrix(b)
    dist = np.linalg.norm(va - vb, axis=1)
    return pa.array(dist.tolist())


@lutz_udf(
    name="dot_product",
    parameters=[_LIST_DBL, _LIST_DBL],
    return_type=duckdb.type("DOUBLE"),
    description="Dot product (inner product) between two embedding vectors.",
)
def dot_product(a: pa.Array, b: pa.Array) -> pa.Array:
    va, vb = _to_matrix(a), _to_matrix(b)
    result = np.einsum("ij,ij->i", va, vb)
    return pa.array(result.tolist())
