"""Corpus-level similarity UDFs for DuckDB.

Available functions
-------------------
corpus_centroid_distance(v) -> DOUBLE
    Cosine distance from each embedding to the batch centroid.
    Rows far from the centroid are outliers relative to the corpus.

batch_centroid(v)           -> DOUBLE[]
    Mean (centroid) vector of all embeddings in the batch.

Example
-------
    -- Find the 10 chunks most unlike the rest of the corpus
    SELECT filename, section,
           corpus_centroid_distance(embedding) AS outlier_score
    FROM   vectors
    ORDER  BY outlier_score DESC
    LIMIT  10
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import duckdb

from lutz.analytics.registry import lutz_udf
from lutz.analytics.distances import _to_matrix, _LIST_DBL


@lutz_udf(
    name="corpus_centroid_distance",
    parameters=[_LIST_DBL],
    return_type=duckdb.type("DOUBLE"),
    description=(
        "Cosine distance from each embedding to the batch centroid. "
        "Higher values = more unlike the rest of the corpus."
    ),
)
def corpus_centroid_distance(v: pa.Array) -> pa.Array:
    mat = _to_matrix(v)
    centroid = mat.mean(axis=0, keepdims=True)  # (1, D)

    # Cosine distance to centroid
    dot = mat @ centroid.T  # (N, 1)
    norm_rows = np.linalg.norm(mat, axis=1, keepdims=True)  # (N, 1)
    norm_c = np.linalg.norm(centroid)
    denom = norm_rows * norm_c
    denom = np.where(denom == 0, 1e-10, denom)
    dist = 1.0 - (dot / denom)
    return pa.array(dist.flatten().tolist())


@lutz_udf(
    name="batch_centroid",
    parameters=[_LIST_DBL],
    return_type=_LIST_DBL,
    description=(
        "Mean (centroid) embedding of all vectors in the batch. "
        "Every row receives the same centroid vector."
    ),
)
def batch_centroid(v: pa.Array) -> pa.Array:
    mat = _to_matrix(v)
    centroid = mat.mean(axis=0)  # (D,)
    return pa.array([centroid.tolist()] * mat.shape[0])
