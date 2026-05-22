"""Classification UDFs for DuckDB.

Available functions
-------------------
knn_predict(v, labels, k) -> VARCHAR  — k-NN label prediction (batch-fitted)

Notes
-----
``knn_predict`` fits a k-NN classifier on the current Arrow batch using the
provided label column and returns leave-one-out predictions.  Useful for
quickly evaluating how well embeddings separate known categories.

Example
-------
    SELECT filename, section,
           knn_predict(embedding, section, 5) AS predicted_section
    FROM   vectors
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import duckdb

from lutz.analytics.registry import lutz_udf
from lutz.analytics.distances import _to_matrix, _LIST_DBL


@lutz_udf(
    name="knn_predict",
    parameters=[_LIST_DBL, duckdb.type("VARCHAR"), duckdb.type("INTEGER")],
    return_type=duckdb.type("VARCHAR"),
    description=(
        "k-NN label prediction (batch-fitted, leave-one-out). "
        "v = embedding, labels = known category column, k = neighbours."
    ),
)
def knn_predict(v: pa.Array, labels: pa.Array, k: pa.Array) -> pa.Array:
    from sklearn.neighbors import KNeighborsClassifier

    mat = _to_matrix(v)
    label_list = labels.to_pylist()
    k_val = min(int(k.to_pylist()[0]), mat.shape[0] - 1)

    if k_val < 1:
        return pa.array(label_list, type=pa.string())

    clf = KNeighborsClassifier(n_neighbors=k_val, metric="cosine")
    clf.fit(mat, label_list)
    predicted = clf.predict(mat)
    return pa.array(predicted.tolist(), type=pa.string())
