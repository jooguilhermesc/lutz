"""Tests for embedding statistics UDFs."""

from __future__ import annotations

import math
import pytest


def test_embedding_norm_known(conn):
    # ||[3, 4]|| = 5
    row = conn.execute("SELECT embedding_norm([3.0, 4.0])").fetchone()
    assert abs(row[0] - 5.0) < 1e-6


def test_embedding_norm_unit(conn):
    row = conn.execute("SELECT embedding_norm([1.0, 0.0, 0.0])").fetchone()
    assert abs(row[0] - 1.0) < 1e-6


def test_embedding_normalize_produces_unit(conn):
    row = conn.execute(
        "SELECT embedding_normalize([3.0, 4.0])"
    ).fetchone()
    vec = row[0]
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-6


def test_embedding_normalize_direction_preserved(conn):
    row = conn.execute(
        "SELECT embedding_normalize([3.0, 0.0, 0.0])"
    ).fetchone()
    vec = row[0]
    assert abs(vec[0] - 1.0) < 1e-6
    assert abs(vec[1]) < 1e-6
    assert abs(vec[2]) < 1e-6


def test_embedding_z_score_mean_zero(conn_with_vectors):
    """After z-score normalization, per-dimension mean across the batch ≈ 0."""
    rows = conn_with_vectors.execute(
        "SELECT embedding_z_score(embedding) AS z FROM vectors"
    ).fetchall()
    assert len(rows) == 100

    dim = len(rows[0][0])
    # Compute per-dimension mean
    sums = [0.0] * dim
    for (z,) in rows:
        for i, v in enumerate(z):
            sums[i] += v
    means = [s / len(rows) for s in sums]
    for m in means:
        assert abs(m) < 1e-4, f"z-score mean not near zero: {m}"
