"""Lutz analytics — UDFs registered automatically in every DuckDB connection.

Usage
-----
Instead of ``duckdb.connect()``, call:

    from lutz.analytics import create_connection
    con = create_connection()

All lutz analytical functions are immediately available:

    con.execute("SELECT cosine_distance(a, b) FROM ...")
"""

from __future__ import annotations

import duckdb

from lutz.analytics.registry import register_all, list_udfs

__all__ = ["create_connection", "list_udfs"]


def create_connection(**kwargs) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection with all lutz UDFs pre-registered.

    All keyword arguments are forwarded to ``duckdb.connect()``.
    """
    conn = duckdb.connect(**kwargs)
    register_all(conn)
    return conn
