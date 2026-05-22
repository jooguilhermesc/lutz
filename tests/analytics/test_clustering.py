"""Tests for clustering UDFs."""

from __future__ import annotations

import pytest


def test_kmeans_label_returns_integers(conn_with_vectors):
    rows = conn_with_vectors.execute(
        "SELECT kmeans_label(embedding, 2) AS label FROM vectors"
    ).fetchall()
    assert len(rows) == 100
    labels = {r[0] for r in rows}
    assert labels.issubset({0, 1}), f"Unexpected labels: {labels}"


def test_kmeans_label_two_clusters_separates_data(conn_with_vectors):
    """With k=2 on two well-separated clusters, each natural cluster should
    map almost entirely to a single kmeans label."""
    rows = conn_with_vectors.execute(
        "SELECT chunk_index, kmeans_label(embedding, 2) AS label FROM vectors"
    ).fetchall()

    label_a = {r[1] for r in rows if r[0] < 50}
    label_b = {r[1] for r in rows if r[0] >= 50}

    # Each natural cluster should be dominated by one k-means label
    assert len(label_a) <= 2  # might straddle one label max
    assert len(label_b) <= 2

    # The dominant labels for each cluster should differ
    dominant_a = max(label_a, key=lambda l: sum(1 for r in rows if r[0] < 50 and r[1] == l))
    dominant_b = max(label_b, key=lambda l: sum(1 for r in rows if r[0] >= 50 and r[1] == l))
    assert dominant_a != dominant_b


def test_kmeans_label_k_larger_than_n(conn):
    """When k > n_rows the UDF should return label 0 for all rows."""
    import pyarrow as pa

    table = pa.table({"embedding": [[1.0, 0.0], [0.0, 1.0]]})
    conn.register("tiny", table)
    rows = conn.execute(
        "SELECT kmeans_label(embedding, 10) FROM tiny"
    ).fetchall()
    assert all(r[0] == 0 for r in rows)


def test_dbscan_label_returns_integers(conn_with_vectors):
    rows = conn_with_vectors.execute(
        "SELECT dbscan_label(embedding, 0.5, 3) AS label FROM vectors"
    ).fetchall()
    assert len(rows) == 100
    # All labels should be integers (-1 = noise is valid)
    for (label,) in rows:
        assert isinstance(label, int)
