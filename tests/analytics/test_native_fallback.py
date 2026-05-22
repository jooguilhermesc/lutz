"""Verify that lutz analytics works without the optional lutz-native Rust extension."""

from __future__ import annotations

import sys
import importlib
import pytest


def test_distances_work_without_native():
    """distances.py must not import lutz_native — it doesn't exist yet."""
    # Ensure lutz_native is not available
    assert "lutz_native" not in sys.modules

    import lutz.analytics.distances as dist_mod

    # If lutz_native were required, importing the module would have failed.
    # Verify the UDFs are usable via a fresh connection.
    from lutz.analytics import create_connection

    con = create_connection()
    row = con.execute(
        "SELECT cosine_distance([1.0, 0.0], [0.0, 1.0])"
    ).fetchone()
    assert abs(row[0] - 1.0) < 1e-6
    con.close()
