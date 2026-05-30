"""Pure-function helpers for building cluster synthesis reports.

This module has no side effects and no I/O — it operates purely on in-memory
numpy arrays and Python dicts.  All distance calculations use cosine distance
(1 - cosine_similarity), consistent with lutz/analytics/distances.py.
"""

from __future__ import annotations

import numpy as np


def _cosine_distance_batch(vecs: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    """Return cosine distance from each row of *vecs* to *centroid*.

    Parameters
    ----------
    vecs:
        2-D float array of shape (N, D).
    centroid:
        1-D float array of shape (D,).

    Returns
    -------
    distances : np.ndarray of shape (N,), dtype float64
        Cosine distance (0 = identical, 2 = opposite).
    """
    vecs_f = vecs.astype(np.float64)
    centroid_f = centroid.astype(np.float64)

    dot = vecs_f @ centroid_f  # (N,)
    norm_vecs = np.linalg.norm(vecs_f, axis=1)  # (N,)
    norm_centroid = np.linalg.norm(centroid_f)  # scalar

    denom = norm_vecs * norm_centroid
    # Avoid division by zero — zero-norm vectors get distance 1.0
    safe_denom = np.where(denom == 0, 1e-10, denom)
    return 1.0 - dot / safe_denom


def build_cluster_report(
    mat: np.ndarray,
    rows: list[dict],
    cluster_centers: np.ndarray,
    labels: np.ndarray,
    top_chunks: int = 5,
) -> list[dict]:
    """Build a cluster synthesis report.

    Parameters
    ----------
    mat:
        Embedding matrix of shape (N, D), float32.  Each row corresponds to
        the element at the same index in *rows*.
    rows:
        List of N dicts, each with keys: ``filename``, ``chunk_index``,
        ``section``, ``text``.  Must be aligned with *mat* by index.
    cluster_centers:
        KMeans centroid matrix of shape (K, D).
    labels:
        Integer label array of shape (N,) — output of ``kmeans.predict(mat)``.
        Labels must be in range [0, K).
    top_chunks:
        Maximum number of representative chunks to include per cluster.
        When a cluster has fewer chunks than *top_chunks*, all are included.

    Returns
    -------
    list[dict]
        One dict per cluster (K entries), sorted by cluster_id ascending.
        Each dict contains::

            {
                "cluster_id": int,
                "n_articles": int,
                "article_filenames": list[str],   # unique, sorted
                "representative_chunks": list[dict],
            }

        where each representative chunk dict is::

            {
                "filename": str,
                "chunk_index": int,
                "section": str,
                "text": str,
                "distance_to_centroid": float,
            }

        The list is sorted by ascending ``distance_to_centroid``.
    """
    n_clusters = cluster_centers.shape[0]
    report: list[dict] = []

    for k in range(n_clusters):
        # Indices of all rows assigned to this cluster
        mask = labels == k
        indices = np.where(mask)[0]

        if len(indices) == 0:
            report.append(
                {
                    "cluster_id": k,
                    "n_articles": 0,
                    "article_filenames": [],
                    "representative_chunks": [],
                }
            )
            continue

        cluster_mat = mat[indices]  # (M, D)
        centroid = cluster_centers[k]  # (D,)
        distances = _cosine_distance_batch(cluster_mat, centroid)  # (M,)

        # Unique article filenames for chunks in this cluster
        filenames_set: set[str] = {rows[i]["filename"] for i in indices}
        article_filenames = sorted(filenames_set)

        # Sort by ascending distance, pick top_chunks
        sorted_order = np.argsort(distances)
        n_reps = min(top_chunks, len(sorted_order))

        representative_chunks: list[dict] = []
        for rank in range(n_reps):
            local_idx = int(sorted_order[rank])
            global_idx = int(indices[local_idx])
            row = rows[global_idx]
            representative_chunks.append(
                {
                    "filename": row["filename"],
                    "chunk_index": int(row.get("chunk_index", 0)),
                    "section": row.get("section", ""),
                    "text": row["text"],
                    "distance_to_centroid": float(distances[local_idx]),
                }
            )

        report.append(
            {
                "cluster_id": k,
                "n_articles": len(article_filenames),
                "article_filenames": article_filenames,
                "representative_chunks": representative_chunks,
            }
        )

    return report
