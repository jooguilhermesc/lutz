"""Auto-discovery and registration of lutz analytical UDFs in DuckDB."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

import duckdb

# Sub-modules that contribute UDFs via the @lutz_udf decorator.
_SUBMODULES = (
    "distances",
    "stats",
    "clustering",
    "reduction",
    "classification",
    "similarity",
)

# Global registry populated by @lutz_udf at import time.
_REGISTRY: list[UDFSpec] = []
# Track which sub-modules have already been imported (idempotent).
_IMPORTED: set[str] = set()


@dataclass
class UDFSpec:
    name: str
    fn: Callable
    parameters: list
    return_type: Any
    is_vectorized: bool = True
    description: str = ""


def lutz_udf(
    name: str,
    parameters: list,
    return_type: Any,
    *,
    description: str = "",
    is_vectorized: bool = True,
) -> Callable:
    """Decorator that registers a Python function as a DuckDB UDF.

    Parameters
    ----------
    name:
        SQL function name (e.g. ``"cosine_distance"``).
    parameters:
        List of DuckDB type objects (e.g. ``[duckdb.list_type(duckdb.typing.DOUBLE)]``).
    return_type:
        DuckDB type object for the return value.
    description:
        Human-readable description shown by ``lutz_udfs()``.
    is_vectorized:
        When ``True`` the function is registered as an Arrow UDF (receives
        ``pa.Array`` per argument, returns ``pa.Array``).  When ``False`` it
        is registered as a native scalar UDF.
    """

    def decorator(fn: Callable) -> Callable:
        _REGISTRY.append(
            UDFSpec(
                name=name,
                fn=fn,
                parameters=parameters,
                return_type=return_type,
                is_vectorized=is_vectorized,
                description=description,
            )
        )
        return fn

    return decorator


def register_all(conn: duckdb.DuckDBPyConnection) -> None:
    """Register every discovered lutz UDF into *conn*.

    Importing the sub-modules triggers their ``@lutz_udf`` decorators, which
    populate ``_REGISTRY``.  Subsequent calls re-register from the same
    (already-populated) registry without re-importing.
    """
    for mod in _SUBMODULES:
        full = f"lutz.analytics.{mod}"
        if full not in _IMPORTED:
            importlib.import_module(full)
            _IMPORTED.add(full)

    for spec in _REGISTRY:
        udf_type = "arrow" if spec.is_vectorized else "native"
        conn.create_function(
            spec.name,
            spec.fn,
            parameters=spec.parameters,
            return_type=spec.return_type,
            type=udf_type,
        )


def list_udfs() -> list[dict]:
    """Return metadata for every registered UDF."""
    # Ensure sub-modules are imported so the registry is populated.
    for mod in _SUBMODULES:
        full = f"lutz.analytics.{mod}"
        if full not in _IMPORTED:
            importlib.import_module(full)
            _IMPORTED.add(full)

    return [
        {
            "name": s.name,
            "description": s.description,
            "vectorized": s.is_vectorized,
        }
        for s in _REGISTRY
    ]
