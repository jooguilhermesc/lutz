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

# Columns needed for text retrieval (excludes the embedding float arrays).
# Projecting only these columns avoids deserialising potentially hundreds of
# megabytes of float32 vectors when only text is required.
_TEXT_COLUMNS = ["filename", "chunk_index", "page", "char_start", "section", "text"]
_META_COLUMNS = [
    "filename", "vectorized_at", "embedding_model", "embedding_provider",
    "extraction_backend",
]


def _project(arrow_table: pa.Table, columns: list[str]) -> pa.Table:
    """Select only the requested columns that are present in the table."""
    available = arrow_table.schema.names
    return arrow_table.select([c for c in columns if c in available])


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
                pa.field("extraction_backend", pa.string()),
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
                "extraction_backend": r.get("extraction_backend", "pymupdf"),
            }
            for r in records
        ]

        if _TABLE_NAME in self._db.list_tables().tables:
            tbl = self._db.open_table(_TABLE_NAME)
            # Graceful schema-evolution: strip fields absent in the existing table
            # so that stores created before this field was added keep working.
            existing_cols = set(tbl.schema.names)
            if "extraction_backend" not in existing_cols:
                compat_rows = [
                    {k: v for k, v in row.items() if k in existing_cols}
                    for row in rows
                ]
                tbl.add(compat_rows)
            else:
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
        if _TABLE_NAME not in self._db.list_tables().tables:
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
        if _TABLE_NAME not in self._db.list_tables().tables:
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        # Project only text columns — skip embedding vectors
        arrow_tbl = _project(tbl.to_arrow(), _TEXT_COLUMNS)
        arrow_tbl = arrow_tbl.filter(
            pa.compute.equal(arrow_tbl.column("filename"), filename)
        ).sort_by([("chunk_index", "ascending")])

        return [
            {
                "filename": row["filename"].as_py(),
                "page": int(row["page"].as_py()),
                "chunk_index": int(row["chunk_index"].as_py()),
                "section": row["section"].as_py() if "section" in arrow_tbl.schema.names else "",
                "text": row["text"].as_py(),
            }
            for row in arrow_tbl.to_pylist()
        ]

    def get_all_grouped(
        self, sections: list[str] | None = None
    ) -> dict[str, list[dict]]:
        """Return all chunks grouped by filename in a single DB read.

        Each group is sorted by chunk_index. Use this instead of calling
        get_by_filename() N times — it reads the table once.

        Embedding vectors are deliberately excluded from the read to avoid
        materialising potentially hundreds of megabytes of float32 data that
        is not needed for text-only operations.

        Parameters
        ----------
        sections:
            When provided, only chunks whose ``section`` field is in this list
            are included. Articles that end up with zero chunks after filtering
            are still present as empty lists so callers can detect them.
        """
        if _TABLE_NAME not in self._db.list_tables().tables:
            return {}
        tbl = self._db.open_table(_TABLE_NAME)

        # Read only text columns — avoids deserialising embedding arrays
        arrow_tbl = _project(tbl.to_arrow(), _TEXT_COLUMNS)
        arrow_tbl = arrow_tbl.sort_by(
            [("filename", "ascending"), ("chunk_index", "ascending")]
        )

        if sections and "section" in arrow_tbl.schema.names:
            mask = pa.compute.is_in(
                arrow_tbl.column("section"),
                value_set=pa.array(sections, type=pa.string()),
            )
            arrow_tbl = arrow_tbl.filter(mask)

        has_section = "section" in arrow_tbl.schema.names
        grouped: dict[str, list[dict]] = {}
        for row in arrow_tbl.to_pylist():
            fn = row["filename"]
            grouped.setdefault(fn, []).append(
                {
                    "filename": fn,
                    "page": int(row["page"]),
                    "chunk_index": int(row["chunk_index"]),
                    "section": row.get("section", "") if has_section else "",
                    "text": row["text"],
                }
            )
        return grouped

    def get_all_embeddings(self) -> tuple[np.ndarray, dict]:
        """Return all chunk embeddings as a 2-D float32 array plus corpus metadata.

        Returns
        -------
        embeddings : np.ndarray of shape (N, D), dtype float32
            All chunk embeddings in table order.
        meta : dict with keys:
            embedding_model  — most frequent embedding model in the store
            n_rows           — total number of chunk rows
            corpus_hash      — sha256(f"{last_updated}:{n_rows}")

        When the store is empty, returns ``(np.empty((0, 0), dtype=np.float32), {})`` .
        """
        import hashlib

        if _TABLE_NAME not in self._db.list_tables().tables:
            return np.empty((0, 0), dtype=np.float32), {}

        tbl = self._db.open_table(_TABLE_NAME)
        n_rows = tbl.count_rows()
        if n_rows == 0:
            return np.empty((0, 0), dtype=np.float32), {}

        arrow_tbl = _project(tbl.to_arrow(), ["embedding", "embedding_model", "vectorized_at"])
        if "embedding" not in arrow_tbl.schema.names:
            return np.empty((0, 0), dtype=np.float32), {}

        # Efficiently convert list<float32> column to 2-D numpy array
        emb_col = arrow_tbl.column("embedding")
        if isinstance(emb_col, pa.ChunkedArray):
            emb_col = emb_col.combine_chunks()
        matrix = np.array(
            emb_col.to_pylist(), dtype=np.float32
        )

        # Determine dominant embedding_model
        all_models: list[str] = []
        if "embedding_model" in arrow_tbl.schema.names:
            all_models = [
                v for v in arrow_tbl.column("embedding_model").to_pylist() if v
            ]
        embedding_model = (
            max(set(all_models), key=all_models.count) if all_models else ""
        )

        # Corpus hash for invalidation
        timestamps: list[str] = []
        if "vectorized_at" in arrow_tbl.schema.names:
            timestamps = [v for v in arrow_tbl.column("vectorized_at").to_pylist() if v]
        last_updated = max(timestamps) if timestamps else ""
        raw = f"{last_updated}:{n_rows}".encode()
        corpus_hash = hashlib.sha256(raw).hexdigest()

        meta = {
            "embedding_model": embedding_model,
            "n_rows": n_rows,
            "corpus_hash": corpus_hash,
        }
        return matrix, meta

    def get_all_embeddings_with_metadata(self) -> tuple[np.ndarray, list[dict]]:
        """Return all chunk embeddings aligned with their metadata rows.

        This method pairs each embedding with its corresponding metadata so
        that callers can assign cluster labels and map them back to the
        originating article and chunk without a secondary lookup.

        Returns
        -------
        matrix : np.ndarray of shape (N, D), dtype float32
            All chunk embeddings in table order (same order as *rows*).
        rows : list[dict]
            One dict per chunk with keys:
            ``filename``, ``chunk_index``, ``section``, ``text``.
            Index *i* in *rows* corresponds to row *i* in *matrix*.

        When the store is empty, returns ``(np.empty((0, 0), dtype=np.float32), [])``.
        """
        if _TABLE_NAME not in self._db.list_tables().tables:
            return np.empty((0, 0), dtype=np.float32), []

        tbl = self._db.open_table(_TABLE_NAME)
        n_rows = tbl.count_rows()
        if n_rows == 0:
            return np.empty((0, 0), dtype=np.float32), []

        cols = ["filename", "chunk_index", "section", "text", "embedding"]
        arrow_tbl = _project(tbl.to_arrow(), cols)

        if "embedding" not in arrow_tbl.schema.names:
            return np.empty((0, 0), dtype=np.float32), []

        emb_col = arrow_tbl.column("embedding")
        if isinstance(emb_col, pa.ChunkedArray):
            emb_col = emb_col.combine_chunks()
        matrix = np.array(emb_col.to_pylist(), dtype=np.float32)

        has_section = "section" in arrow_tbl.schema.names
        rows_out: list[dict] = []
        for row in arrow_tbl.to_pylist():
            rows_out.append(
                {
                    "filename": row["filename"],
                    "chunk_index": int(row.get("chunk_index", 0)),
                    "section": row.get("section", "") if has_section else "",
                    "text": row["text"],
                }
            )

        return matrix, rows_out

    def get_embeddings_by_article(self) -> "dict[str, np.ndarray]":
        """Return mean embedding per article (average of all chunk embeddings).

        Used by the reading roadmap feature to compute semantic distances
        between articles and the corpus centroid.
        """
        if _TABLE_NAME not in self._db.list_tables().tables:
            return {}
        tbl = self._db.open_table(_TABLE_NAME)
        # Must include embeddings here — this is the one method that needs them
        arrow_tbl = _project(tbl.to_arrow(), ["filename", "embedding"])
        if "embedding" not in arrow_tbl.schema.names:
            return {}

        result: dict[str, np.ndarray] = {}
        rows = arrow_tbl.to_pylist()
        grouped: dict[str, list] = {}
        for row in rows:
            grouped.setdefault(row["filename"], []).append(row["embedding"])
        for filename, vecs in grouped.items():
            result[str(filename)] = np.array(vecs, dtype=np.float32).mean(axis=0)
        return result

    def get_chunk_embeddings_by_article(
        self,
        sections: list[str] | None = None,
    ) -> dict[str, list[np.ndarray]]:
        """Return chunk embeddings grouped by article filename.

        Each article maps to an ordered list of its chunk embedding vectors.
        Unlike :meth:`get_embeddings_by_article`, this method preserves
        individual chunk vectors so callers can apply their own aggregation
        (mean, max, etc.).

        Parameters
        ----------
        sections:
            When provided, only chunks whose ``section`` field is in this list
            are included. Articles that end up with zero chunks after filtering
            are still present as empty lists.
        """
        if _TABLE_NAME not in self._db.list_tables().tables:
            return {}

        tbl = self._db.open_table(_TABLE_NAME)
        cols = ["filename", "chunk_index", "section", "embedding"]
        arrow_tbl = _project(tbl.to_arrow(), cols)

        if "embedding" not in arrow_tbl.schema.names:
            return {}

        # Apply section filter when requested
        if sections and "section" in arrow_tbl.schema.names:
            mask = pa.compute.is_in(
                arrow_tbl.column("section"),
                value_set=pa.array(sections, type=pa.string()),
            )
            arrow_tbl = arrow_tbl.filter(mask)

        # Sort by filename then chunk_index for stable ordering
        arrow_tbl = arrow_tbl.sort_by(
            [("filename", "ascending"), ("chunk_index", "ascending")]
        )

        grouped: dict[str, list[np.ndarray]] = {}
        for row in arrow_tbl.to_pylist():
            fn = row["filename"]
            emb = np.array(row["embedding"], dtype=np.float32)
            grouped.setdefault(fn, []).append(emb)
        return grouped

    def list_filenames(self) -> list[str]:
        """Return sorted list of unique article filenames in the store."""
        if _TABLE_NAME not in self._db.list_tables().tables:
            return []
        tbl = self._db.open_table(_TABLE_NAME)
        # Project only the filename column
        arrow_tbl = _project(tbl.to_arrow(), ["filename"])
        return sorted(set(arrow_tbl.column("filename").to_pylist()))

    def rename_filename(self, old_name: str, new_name: str) -> int:
        """Rename all chunks that reference *old_name* to *new_name*.

        Uses LanceDB's update() API (available since 0.4.x).  Returns the
        number of rows that were updated (0 if the article wasn't in the store).
        """
        if _TABLE_NAME not in self._db.list_tables().tables:
            return 0
        tbl = self._db.open_table(_TABLE_NAME)
        # Escape single quotes in filenames to prevent SQL injection
        safe_old = old_name.replace("'", "''")
        safe_new = new_name.replace("'", "''")
        tbl.update(where=f"filename = '{safe_old}'", values={"filename": safe_new})
        return tbl.count_rows()

    def drop_all(self) -> int:
        """Delete all records and return the count of deleted rows."""
        if _TABLE_NAME not in self._db.list_tables().tables:
            return 0
        tbl = self._db.open_table(_TABLE_NAME)
        count = tbl.count_rows()
        self._db.drop_table(_TABLE_NAME)
        return count

    def info(self) -> dict[str, Any]:
        """Return metadata about the current vector store state."""
        if _TABLE_NAME not in self._db.list_tables().tables:
            return {"total_records": 0, "unique_documents": 0, "last_updated": None}

        tbl = self._db.open_table(_TABLE_NAME)
        total = tbl.count_rows()
        # Project only the columns we need — skip text and embeddings
        arrow_tbl = _project(tbl.to_arrow(), ["filename", "vectorized_at"])
        filenames = arrow_tbl.column("filename").to_pylist()
        timestamps = arrow_tbl.column("vectorized_at").to_pylist() if "vectorized_at" in arrow_tbl.schema.names else []
        unique_docs = len(set(filenames))
        last_updated = max(timestamps) if timestamps else None

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
        if _TABLE_NAME not in self._db.list_tables().tables:
            return {}
        tbl = self._db.open_table(_TABLE_NAME)
        arrow_tbl = _project(tbl.to_arrow(), ["filename", "section"])

        if "section" not in arrow_tbl.schema.names:
            # Store predates section support — treat everything as unlabeled
            filenames = set(arrow_tbl.column("filename").to_pylist())
            total = arrow_tbl.num_rows
            per_file = total // max(len(filenames), 1)
            return {fn: {"": per_file} for fn in filenames}

        result: dict[str, dict[str, int]] = {}
        for row in arrow_tbl.to_pylist():
            fn = row["filename"]
            sec = row.get("section") or ""
            counts = result.setdefault(fn, {})
            counts[sec] = counts.get(sec, 0) + 1
        return result

    def summarize(self) -> dict[str, Any]:
        """Return a detailed summary including per-article breakdown."""
        if _TABLE_NAME not in self._db.list_tables().tables:
            return {
                "total_records": 0,
                "unique_documents": 0,
                "last_updated": None,
                "embedding_model": None,
                "embedding_provider": None,
                "articles": [],
            }

        tbl = self._db.open_table(_TABLE_NAME)
        # Project only the metadata columns — skip text and embeddings
        arrow_tbl = _project(tbl.to_arrow(), _META_COLUMNS)
        rows = arrow_tbl.to_pylist()

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["filename"], []).append(row)

        articles = []
        for filename, group in sorted(grouped.items()):
            articles.append({
                "filename": filename,
                "chunk_count": len(group),
                "vectorized_at": group[0].get("vectorized_at", ""),
                "embedding_model": group[0].get("embedding_model", ""),
                "embedding_provider": group[0].get("embedding_provider", ""),
                "extraction_backend": group[0].get("extraction_backend", ""),
            })

        total = len(rows)
        all_timestamps = [r.get("vectorized_at", "") for r in rows if r.get("vectorized_at")]
        all_models = [r.get("embedding_model", "") for r in rows if r.get("embedding_model")]
        all_providers = [r.get("embedding_provider", "") for r in rows if r.get("embedding_provider")]

        return {
            "total_records": total,
            "unique_documents": len(grouped),
            "last_updated": max(all_timestamps) if all_timestamps else None,
            "embedding_model": max(set(all_models), key=all_models.count) if all_models else None,
            "embedding_provider": max(set(all_providers), key=all_providers.count) if all_providers else None,
            "articles": articles,
        }
