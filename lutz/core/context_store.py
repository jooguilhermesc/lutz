"""LanceDB-backed store for reference/context files.

Keeps context chunks (from files attached to analysis prompts) in a separate
table so they never appear in corpus queries and no migration of existing
vector stores is needed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pyarrow as pa

logger = logging.getLogger(__name__)

_TABLE_NAME = "context"


class ContextStore:
    """Stores and retrieves chunks from reference/context files.

    Context files (PDF, DOCX, XLSX, PPTX) are vectorized and stored here.
    During analysis, their chunks are injected into the LLM prompt alongside
    the article chunks, providing additional context for classification.
    """

    def __init__(self, db_path: Path) -> None:
        db_path.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._db = self._open()

    def _open(self):
        import lancedb
        return lancedb.connect(str(self._db_path))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(self, records: list[dict]) -> None:
        """Insert or replace chunks for a context file."""
        if not records:
            return

        dim = len(records[0]["embedding"])
        schema = pa.schema([
            pa.field("filename", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("page", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), dim)),
            pa.field("vectorized_at", pa.string()),
            pa.field("embedding_model", pa.string()),
            pa.field("embedding_provider", pa.string()),
        ])

        rows = [
            {
                "filename": r["filename"],
                "chunk_index": int(r.get("chunk_index", 0)),
                "page": int(r.get("page", 0)),
                "text": r["text"],
                "embedding": [float(v) for v in r["embedding"]],
                "vectorized_at": r.get("vectorized_at", ""),
                "embedding_model": r.get("embedding_model", ""),
                "embedding_provider": r.get("embedding_provider", ""),
            }
            for r in records
        ]

        if _TABLE_NAME in self._db.table_names():
            tbl = self._db.open_table(_TABLE_NAME)
            tbl.add(rows)
        else:
            self._db.create_table(_TABLE_NAME, data=rows, schema=schema)

        logger.debug("Upserted %d context records for '%s'", len(rows), records[0]["filename"])

    def delete_by_filename(self, filename: str) -> int:
        """Delete all chunks for a context file. Returns the count deleted."""
        if _TABLE_NAME not in self._db.table_names():
            return 0
        tbl = self._db.open_table(_TABLE_NAME)
        before = tbl.count_rows()
        tbl.delete(f"filename = '{filename.replace(chr(39), chr(39)*2)}'")
        after = tbl.count_rows()
        return before - after

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all_chunks(self) -> list[dict]:
        """Return all context chunks ordered by filename + chunk_index."""
        if _TABLE_NAME not in self._db.table_names():
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        arrow_tbl = tbl.to_arrow().select(
            ["filename", "chunk_index", "page", "text"]
        ).sort_by([("filename", "ascending"), ("chunk_index", "ascending")])
        return arrow_tbl.to_pylist()

    def search(self, query_embedding: list[float], top_k: int = 10) -> list[dict]:
        """Return top-K context chunks closest to the query embedding."""
        if _TABLE_NAME not in self._db.table_names():
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        limit = min(top_k, tbl.count_rows())
        if limit == 0:
            return []
        results = tbl.search(query_embedding).limit(limit).to_list()
        return [
            {
                "filename": r["filename"],
                "page": r["page"],
                "chunk_index": r["chunk_index"],
                "text": r["text"],
            }
            for r in results
        ]

    def list_filenames(self) -> list[str]:
        """Return sorted list of unique context file names."""
        if _TABLE_NAME not in self._db.table_names():
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        arrow_tbl = tbl.to_arrow().select(["filename"])
        return sorted(set(arrow_tbl.column("filename").to_pylist()))

    def count_by_filename(self) -> dict[str, int]:
        """Return chunk count per context file."""
        if _TABLE_NAME not in self._db.table_names():
            return {}
        tbl = self._db.open_table(_TABLE_NAME)
        rows = tbl.to_arrow().select(["filename"]).to_pylist()
        counts: dict[str, int] = {}
        for r in rows:
            fn = r["filename"]
            counts[fn] = counts.get(fn, 0) + 1
        return counts

    def is_empty(self) -> bool:
        if _TABLE_NAME not in self._db.table_names():
            return True
        return self._db.open_table(_TABLE_NAME).count_rows() == 0

    def drop_all(self) -> None:
        if _TABLE_NAME in self._db.table_names():
            self._db.drop_table(_TABLE_NAME)
