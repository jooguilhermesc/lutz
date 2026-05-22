"""Tests for vector distance UDFs."""

from __future__ import annotations

import math
import pytest


def test_cosine_distance_identical(conn):
    row = conn.execute(
        "SELECT cosine_distance([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])"
    ).fetchone()
    assert abs(row[0]) < 1e-6


def test_cosine_distance_orthogonal(conn):
    row = conn.execute(
        "SELECT cosine_distance([1.0, 0.0], [0.0, 1.0])"
    ).fetchone()
    assert abs(row[0] - 1.0) < 1e-6


def test_cosine_distance_opposite(conn):
    row = conn.execute(
        "SELECT cosine_distance([1.0, 0.0], [-1.0, 0.0])"
    ).fetchone()
    assert abs(row[0] - 2.0) < 1e-6


def test_cosine_similarity_identical(conn):
    row = conn.execute(
        "SELECT cosine_similarity([1.0, 0.0], [1.0, 0.0])"
    ).fetchone()
    assert abs(row[0] - 1.0) < 1e-6


def test_cosine_similarity_opposite(conn):
    row = conn.execute(
        "SELECT cosine_similarity([1.0, 0.0], [-1.0, 0.0])"
    ).fetchone()
    assert abs(row[0] + 1.0) < 1e-6


def test_euclidean_distance_known(conn):
    # distance between (0,0) and (3,4) = 5
    row = conn.execute(
        "SELECT euclidean_distance([0.0, 0.0], [3.0, 4.0])"
    ).fetchone()
    assert abs(row[0] - 5.0) < 1e-6


def test_euclidean_distance_zero(conn):
    row = conn.execute(
        "SELECT euclidean_distance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])"
    ).fetchone()
    assert abs(row[0]) < 1e-6


def test_dot_product_known(conn):
    # [1,2,3] · [4,5,6] = 4+10+18 = 32
    row = conn.execute(
        "SELECT dot_product([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])"
    ).fetchone()
    assert abs(row[0] - 32.0) < 1e-6


def test_dot_product_orthogonal(conn):
    row = conn.execute(
        "SELECT dot_product([1.0, 0.0], [0.0, 1.0])"
    ).fetchone()
    assert abs(row[0]) < 1e-6


def test_distance_batch(conn_with_vectors):
    """Distance functions should work over the synthetic vectors table."""
    # Use cosine_distance against a fixed target vector.
    # All embeddings in cluster_a (indices 0-49) should have lower distance
    # to each other than to cluster_b (indices 50-99).
    target = "[" + ", ".join(["1.0"] * 64) + "]"
    rows = conn_with_vectors.execute(
        f"SELECT chunk_index, cosine_distance(embedding, {target}::DOUBLE[]) AS d "
        f"FROM vectors ORDER BY d"
    ).fetchall()
    assert len(rows) == 100
    # The 50 closest should all come from cluster_a (chunk_index < 50)
    top50 = {r[0] for r in rows[:50]}
    cluster_a = set(range(50))
    assert len(top50 & cluster_a) >= 40, "Expected cluster_a to be closer to target"
