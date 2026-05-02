"""LanceDB-backed vector store."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

logger = logging.getLogger(__name__)

_TABLE_NAME = "articles"


class VectorStore:
    """Thin wrapper around LanceDB for storing and querying article chunks."""

    def __init__(self, db_path: Path) -> None:
        db_path.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._db = self._open()

    def _open(self):
        import lancedb
        return lancedb.connect(str(self._db_path))

    # ------------------------------------------------------------------

    def upsert(self, records: list[dict]) -> None:
        """Insert or overwrite records in the vector store.

        If a record with the same (filename, chunk_index) already exists it is
        replaced; otherwise it is appended.
        """
        if not records:
            return

        dim = len(records[0]["embedding"])

        schema = pa.schema(
            [
                pa.field("filename", pa.string()),
                pa.field("chunk_index", pa.int32()),
                pa.field("page", pa.int32()),
                pa.field("char_start", pa.int32()),
                pa.field("text", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), dim)),
                pa.field("vectorized_at", pa.string()),
                pa.field("embedding_model", pa.string()),
                pa.field("embedding_provider", pa.string()),
            ]
        )

        rows = [
            {
                "filename": r["filename"],
                "chunk_index": int(r.get("chunk_index", 0)),
                "page": int(r.get("page", 0)),
                "char_start": int(r.get("char_start", 0)),
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

        logger.debug("Upserted %d records into '%s'", len(rows), _TABLE_NAME)

    def search(self, query_embedding: list[float], top_k: int | None = 10) -> list[dict]:
        """Return the most similar chunks to the query embedding.

        When top_k is None all records are returned, ranked by similarity.
        """
        if _TABLE_NAME not in self._db.table_names():
            return []

        tbl = self._db.open_table(_TABLE_NAME)
        limit = top_k if top_k is not None else tbl.count_rows()
        results = (
            tbl.search(query_embedding)
            .limit(limit)
            .to_list()
        )

        return [
            {
                "filename": r["filename"],
                "page": r["page"],
                "chunk_index": r["chunk_index"],
                "text": r["text"],
                "score": r.get("_distance", None),
            }
            for r in results
        ]

    def get_by_filename(self, filename: str) -> list[dict]:
        """Return all chunks for a specific article, ordered by chunk_index."""
        if _TABLE_NAME not in self._db.table_names():
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        df = tbl.to_pandas()
        filtered = df[df["filename"] == filename].sort_values("chunk_index")
        return [
            {
                "filename": row["filename"],
                "page": int(row["page"]),
                "chunk_index": int(row["chunk_index"]),
                "text": row["text"],
            }
            for _, row in filtered.iterrows()
        ]

    def get_all_grouped(self) -> dict[str, list[dict]]:
        """Return all chunks grouped by filename in a single DB read.

        Each group is sorted by chunk_index. Use this instead of calling
        get_by_filename() N times — it reads the table once.
        """
        if _TABLE_NAME not in self._db.table_names():
            return {}
        tbl = self._db.open_table(_TABLE_NAME)
        df = tbl.to_pandas().sort_values(["filename", "chunk_index"])
        grouped: dict[str, list[dict]] = {}
        for filename, group in df.groupby("filename", sort=False):
            grouped[filename] = [
                {
                    "filename": row["filename"],
                    "page": int(row["page"]),
                    "chunk_index": int(row["chunk_index"]),
                    "text": row["text"],
                }
                for _, row in group.iterrows()
            ]
        return grouped

    def list_filenames(self) -> list[str]:
        """Return sorted list of unique article filenames in the store."""
        if _TABLE_NAME not in self._db.table_names():
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        df = tbl.to_pandas()[["filename"]]
        return sorted(df["filename"].unique().tolist())

    def drop_all(self) -> int:
        """Delete all records and return the count of deleted rows."""
        if _TABLE_NAME not in self._db.table_names():
            return 0
        tbl = self._db.open_table(_TABLE_NAME)
        count = tbl.count_rows()
        self._db.drop_table(_TABLE_NAME)
        return count

    def info(self) -> dict[str, Any]:
        """Return metadata about the current vector store state."""
        if _TABLE_NAME not in self._db.table_names():
            return {"total_records": 0, "unique_documents": 0, "last_updated": None}

        tbl = self._db.open_table(_TABLE_NAME)
        total = tbl.count_rows()
        df = tbl.to_pandas()[["filename", "vectorized_at"]]
        unique_docs = df["filename"].nunique()
        last_updated = df["vectorized_at"].max() if total > 0 else None

        return {
            "total_records": total,
            "unique_documents": unique_docs,
            "last_updated": last_updated,
        }

    def summarize(self) -> dict[str, Any]:
        """Return a detailed summary including per-article breakdown."""
        if _TABLE_NAME not in self._db.table_names():
            return {
                "total_records": 0,
                "unique_documents": 0,
                "last_updated": None,
                "embedding_model": None,
                "embedding_provider": None,
                "articles": [],
            }

        tbl = self._db.open_table(_TABLE_NAME)
        df = tbl.to_pandas()[
            ["filename", "vectorized_at", "embedding_model", "embedding_provider"]
        ]

        articles = []
        for filename, group in df.groupby("filename"):
            articles.append({
                "filename": filename,
                "chunk_count": len(group),
                "vectorized_at": group["vectorized_at"].iloc[0],
                "embedding_model": group["embedding_model"].iloc[0],
                "embedding_provider": group["embedding_provider"].iloc[0],
            })

        articles.sort(key=lambda a: a["filename"])

        return {
            "total_records": len(df),
            "unique_documents": int(df["filename"].nunique()),
            "last_updated": df["vectorized_at"].max() if len(df) > 0 else None,
            "embedding_model": df["embedding_model"].mode().iloc[0] if len(df) > 0 else None,
            "embedding_provider": df["embedding_provider"].mode().iloc[0] if len(df) > 0 else None,
            "articles": articles,
        }
