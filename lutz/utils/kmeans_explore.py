"""Pure utility functions for k-means hyperparameter exploration.

These functions are intentionally side-effect-free: they do not persist
models, write to disk, or modify any shared state.  The same inputs always
produce the same outputs (deterministic via random_state).
"""
from __future__ import annotations

import numpy as np


def parse_k_range(s: str) -> range:
    """Parse a k-range string of the form 'A..B' into a Python range object.

    The resulting range is *inclusive* of B, i.e. 'A..B' → range(A, B+1).

    Validation rules
    ----------------
    - Format must be 'A..B' where A and B are integers.
    - A must be >= 2 (KMeans requires at least 2 clusters).
    - B must be > A.
    - B - A must be <= 30 (prevents absurdly long sweeps).

    Raises
    ------
    ValueError
        With a descriptive message when any constraint is violated.
    """
    parts = s.split("..")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid k-range '{s}'. Expected format 'A..B' (e.g. '2..15')."
        )
    try:
        a = int(parts[0])
        b = int(parts[1])
    except ValueError:
        raise ValueError(
            f"Invalid k-range '{s}'. Both A and B in 'A..B' must be integers."
        )

    if a < 2:
        raise ValueError(
            f"Invalid k-range '{s}'. A must be >= 2 (KMeans needs at least 2 clusters)."
        )
    if b <= a:
        raise ValueError(
            f"Invalid k-range '{s}'. B must be greater than A."
        )
    if (b - a) > 30:
        raise ValueError(
            f"Invalid k-range '{s}'. Range span (B - A = {b - a}) exceeds the limit of 30."
        )

    return range(a, b + 1)


def explore_kmeans(
    mat: np.ndarray,
    k_range: range,
    random_state: int = 42,
) -> list[dict]:
    """Fit KMeans for each k in k_range and compute silhouette + inertia.

    Parameters
    ----------
    mat:
        2-D float32 array of shape (N, D) — the corpus embeddings.
    k_range:
        Range of k values to evaluate (e.g. range(2, 16)).
    random_state:
        Seed passed to KMeans and used for any internal sampling.
        Same seed → identical results (deterministic).

    Returns
    -------
    list of dicts, one per k value, each containing:
        k          : int   — number of clusters
        silhouette : float — silhouette score (cosine metric)
        inertia    : float — KMeans inertia (sum of squared distances to centroids)
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    results: list[dict] = []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=random_state, n_init="auto")
        km.fit(mat)
        labels = km.labels_
        sil = float(silhouette_score(mat, labels, metric="cosine"))
        results.append(
            {
                "k": k,
                "silhouette": sil,
                "inertia": float(km.inertia_),
            }
        )
    return results
