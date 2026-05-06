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
                pa.field("section", pa.string()),
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
                "section": r.get("section", ""),
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

    def search(
        self,
        query_embedding: list[float],
        top_k: int | None = 10,
        sections: list[str] | None = None,
    ) -> list[dict]:
        """Return the most similar chunks to the query embedding.

        Parameters
        ----------
        query_embedding:
            The embedding vector to search against.
        top_k:
            Maximum number of results to return. ``None`` returns all records
            ranked by similarity.
        sections:
            When provided, only chunks whose ``section`` field is in this list
            are returned. Chunks without a section label (vectorized before
            ``--section-parse`` was introduced) are excluded when this filter
            is active.
        """
        if _TABLE_NAME not in self._db.table_names():
            return []

        tbl = self._db.open_table(_TABLE_NAME)
        limit = top_k if top_k is not None else tbl.count_rows()

        query = tbl.search(query_embedding).limit(limit)
        if sections:
            # Build SQL-style IN clause for LanceDB's where()
            quoted = ", ".join(f"'{s}'" for s in sections)
            query = query.where(f"section IN ({quoted})", prefilter=True)

        results = query.to_list()

        return [
            {
                "filename": r["filename"],
                "page": r["page"],
                "chunk_index": r["chunk_index"],
                "section": r.get("section", ""),
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
                "section": row.get("section", "") if hasattr(row, "get") else "",
                "text": row["text"],
            }
            for _, row in filtered.iterrows()
        ]

    def get_all_grouped(
        self, sections: list[str] | None = None
    ) -> dict[str, list[dict]]:
        """Return all chunks grouped by filename in a single DB read.

        Each group is sorted by chunk_index. Use this instead of calling
        get_by_filename() N times — it reads the table once.

        Parameters
        ----------
        sections:
            When provided, only chunks whose ``section`` field is in this list
            are included. Articles that end up with zero chunks after filtering
            are still present as empty lists so callers can detect them.
        """
        if _TABLE_NAME not in self._db.table_names():
            return {}
        tbl = self._db.open_table(_TABLE_NAME)
        df = tbl.to_pandas().sort_values(["filename", "chunk_index"])

        if sections and "section" in df.columns:
            df = df[df["section"].isin(sections)]

        grouped: dict[str, list[dict]] = {}
        for filename, group in df.groupby("filename", sort=False):
            grouped[filename] = [
                {
                    "filename": row["filename"],
                    "page": int(row["page"]),
                    "chunk_index": int(row["chunk_index"]),
                    "section": row["section"] if "section" in group.columns else "",
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

    def section_breakdown(self) -> dict[str, dict[str, int]]:
        """Return per-article section chunk counts.

        Returns a dict mapping filename → {section_name → chunk_count}.
        Articles vectorized without --section-parse will have all chunks under
        the empty string key ``""`` (no section label).
        """
        if _TABLE_NAME not in self._db.table_names():
            return {}
        tbl = self._db.open_table(_TABLE_NAME)
        df = tbl.to_pandas()

        if "section" not in df.columns:
            # Store predates section support — treat everything as unlabeled
            df["section"] = ""

        result: dict[str, dict[str, int]] = {}
        for filename, group in df.groupby("filename"):
            counts = group["section"].fillna("").value_counts().to_dict()
            result[str(filename)] = {str(k): int(v) for k, v in counts.items()}
        return result

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
