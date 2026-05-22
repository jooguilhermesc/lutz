"""Clustering UDFs for DuckDB.

Available functions
-------------------
kmeans_label(v, k)       -> INTEGER   — K-Means cluster label (batch-fitted)
dbscan_label(v, eps, min_samples) -> INTEGER — DBSCAN label (batch-fitted)

Notes
-----
Both functions are *batch-fitted*: the clustering model is trained on all
vectors in the current Arrow batch and labels are assigned immediately.
For most lutz corpora (< 50 k chunks), DuckDB passes all rows in a single
batch, so results are coherent across the whole query.

If you need reproducible labels across queries, train a model explicitly and
use ``predict_cluster()`` (see Fase 4 of the roadmap).
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import duckdb

from lutz.analytics.registry import lutz_udf
from lutz.analytics.distances import _to_matrix, _LIST_DBL


@lutz_udf(
    name="kmeans_label",
    parameters=[_LIST_DBL, duckdb.type("INTEGER")],
    return_type=duckdb.type("INTEGER"),
    description=(
        "K-Means cluster label for each embedding. "
        "The model is fitted on the current batch. "
        "k = number of clusters."
    ),
)
def kmeans_label(v: pa.Array, k: pa.Array) -> pa.Array:
    from sklearn.cluster import KMeans  # lazy — sklearn already in deps

    mat = _to_matrix(v)
    k_val = int(k.to_pylist()[0])
    n = mat.shape[0]

    if n < k_val:
        # Not enough samples — assign label 0 to everyone
        return pa.array([0] * n, type=pa.int32())

    model = KMeans(n_clusters=k_val, random_state=42, n_init="auto")
    labels = model.fit_predict(mat)
    return pa.array(labels.tolist(), type=pa.int32())


@lutz_udf(
    name="dbscan_label",
    parameters=[_LIST_DBL, duckdb.type("DOUBLE"), duckdb.type("INTEGER")],
    return_type=duckdb.type("INTEGER"),
    description=(
        "DBSCAN cluster label for each embedding (batch-fitted). "
        "Noise points receive label -1. "
        "eps = neighbourhood radius, min_samples = core-point threshold."
    ),
)
def dbscan_label(v: pa.Array, eps: pa.Array, min_samples: pa.Array) -> pa.Array:
    from sklearn.cluster import DBSCAN

    mat = _to_matrix(v)
    eps_val = float(eps.to_pylist()[0])
    min_s = int(min_samples.to_pylist()[0])

    model = DBSCAN(eps=eps_val, min_samples=min_s, metric="cosine")
    labels = model.fit_predict(mat)
    return pa.array(labels.tolist(), type=pa.int32())
