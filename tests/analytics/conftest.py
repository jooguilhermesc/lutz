"""Shared fixtures for lutz analytics tests."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from lutz.analytics import create_connection


@pytest.fixture
def conn():
    """DuckDB connection with all lutz UDFs registered."""
    c = create_connection()
    yield c
    c.close()


@pytest.fixture
def conn_with_vectors():
    """DuckDB connection with a ``vectors`` table of synthetic float64 embeddings."""
    rng = np.random.default_rng(42)
    n, dim = 100, 64

    # Two well-separated clusters in embedding space
    cluster_a = rng.normal(loc=1.0, scale=0.1, size=(50, dim)).astype(np.float64)
    cluster_b = rng.normal(loc=-1.0, scale=0.1, size=(50, dim)).astype(np.float64)
    embeddings = np.vstack([cluster_a, cluster_b])

    table = pa.table(
        {
            "filename": [f"article_{i:03d}.pdf" for i in range(n)],
            "chunk_index": list(range(n)),
            "section": ["abstract"] * 50 + ["methodology"] * 50,
            "text": [f"chunk text {i}" for i in range(n)],
            "embedding": [row.tolist() for row in embeddings],
        }
    )

    c = create_connection()
    c.register("vectors", table)
    yield c
    c.close()
