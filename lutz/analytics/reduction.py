"""Dimensionality-reduction UDFs for DuckDB.

Available functions
-------------------
pca_project(v, n)   -> DOUBLE[]  — project embedding to n dimensions via PCA
tsne_project(v, n)  -> DOUBLE[]  — project embedding to n dimensions via t-SNE

Notes
-----
Both functions are *batch-fitted*: the projection is learned on all vectors in
the current Arrow batch.  For the typical lutz workflow of:

    SELECT filename, pca_project(embedding, 2) AS coords
    FROM   vectors

DuckDB sends all rows in a single batch, so the PCA space is consistent.
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import duckdb

from lutz.analytics.registry import lutz_udf
from lutz.analytics.distances import _to_matrix, _LIST_DBL


@lutz_udf(
    name="pca_project",
    parameters=[_LIST_DBL, duckdb.type("INTEGER")],
    return_type=_LIST_DBL,
    description=(
        "Project embeddings to n dimensions using PCA (batch-fitted). "
        "Returns a list of n floats."
    ),
)
def pca_project(v: pa.Array, n_components: pa.Array) -> pa.Array:
    from sklearn.decomposition import PCA

    mat = _to_matrix(v)
    n = int(n_components.to_pylist()[0])
    n_actual = min(n, mat.shape[1], mat.shape[0] - 1)

    pca = PCA(n_components=n_actual)
    reduced = pca.fit_transform(mat)
    return pa.array(reduced.tolist())


@lutz_udf(
    name="tsne_project",
    parameters=[_LIST_DBL, duckdb.type("INTEGER")],
    return_type=_LIST_DBL,
    description=(
        "Project embeddings to n dimensions using t-SNE (batch-fitted). "
        "Slow for large batches; prefer pca_project for >5 k rows. "
        "Returns a list of n floats."
    ),
)
def tsne_project(v: pa.Array, n_components: pa.Array) -> pa.Array:
    from sklearn.manifold import TSNE

    mat = _to_matrix(v)
    n = int(n_components.to_pylist()[0])
    n_actual = min(n, mat.shape[1])

    tsne = TSNE(n_components=n_actual, random_state=42, init="pca", learning_rate="auto")
    reduced = tsne.fit_transform(mat)
    return pa.array(reduced.tolist())
