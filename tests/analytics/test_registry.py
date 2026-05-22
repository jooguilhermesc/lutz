"""Tests for the UDF registry and create_connection factory."""

from __future__ import annotations

import duckdb
import pytest

from lutz.analytics import create_connection, list_udfs
from lutz.analytics.registry import _REGISTRY


def test_registry_populated():
    """Registry must contain at least the core UDFs after import."""
    list_udfs()  # triggers sub-module imports
    names = {s.name for s in _REGISTRY}
    required = {
        "cosine_distance",
        "euclidean_distance",
        "dot_product",
        "embedding_norm",
        "kmeans_label",
        "pca_project",
        "corpus_centroid_distance",
    }
    assert required.issubset(names), f"Missing UDFs: {required - names}"


def test_create_connection_returns_duckdb():
    con = create_connection()
    assert isinstance(con, duckdb.DuckDBPyConnection)
    con.close()


def test_udfs_callable_after_create_connection():
    """All registered UDFs should be executable after create_connection()."""
    con = create_connection()
    # A simple sanity query that uses a lutz UDF
    result = con.execute(
        "SELECT cosine_distance([1.0, 0.0], [1.0, 0.0]) AS d"
    ).fetchone()
    assert result is not None
    assert abs(result[0]) < 1e-6, "cosine_distance of identical vectors should be ~0"
    con.close()


def test_list_udfs_returns_metadata():
    udfs = list_udfs()
    assert isinstance(udfs, list)
    assert len(udfs) >= 1
    for entry in udfs:
        assert "name" in entry
        assert "description" in entry
        assert "vectorized" in entry


def test_no_duplicate_registrations():
    """Calling create_connection twice must not raise errors."""
    c1 = create_connection()
    c2 = create_connection()
    r1 = c1.execute("SELECT embedding_norm([3.0, 4.0])").fetchone()[0]
    r2 = c2.execute("SELECT embedding_norm([3.0, 4.0])").fetchone()[0]
    assert abs(r1 - 5.0) < 1e-6
    assert abs(r2 - 5.0) < 1e-6
    c1.close()
    c2.close()
