"""Deduplication utilities — pure functions for article-level similarity clustering.

Uses Union-Find (without external dependencies) to group articles whose
mean embeddings have cosine distance below a configurable threshold.
"""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Union-Find (path-compressed, union-by-rank)
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, keys: list[str]) -> None:
        self._parent: dict[str, str] = {k: k for k in keys}
        self._rank: dict[str, int] = {k: 0 for k in keys}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            # path compression (halving)
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Return cosine distance between two 1-D float32 vectors.

    Cosine distance = 1 − cosine_similarity.
    Clipped to [0, 2] to handle floating-point imprecision.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    similarity = float(np.dot(a, b) / (norm_a * norm_b))
    # Clip to [-1, 1] before computing distance
    similarity = max(-1.0, min(1.0, similarity))
    return 1.0 - similarity


def find_duplicate_groups(
    article_embeddings: dict[str, np.ndarray],
    threshold: float = 0.05,
) -> list[dict]:
    """Given a filename→embedding dict, return clusters of near-duplicate articles.

    Pairs with cosine_distance < threshold are merged into the same cluster
    using Union-Find. Clusters with only one article are excluded.

    Parameters
    ----------
    article_embeddings:
        Mapping of filename to mean embedding vector (np.ndarray, 1-D float32).
    threshold:
        Maximum cosine distance for two articles to be considered near-duplicates.
        Default 0.05 corresponds to roughly ≥ 95% cosine similarity.

    Returns
    -------
    list of dicts, each with keys:
        "keep"       — filename of the article elected as representative
        "duplicates" — list of {"filename": str, "distance": float}

    The representative ("keep") is the article with the highest chunk count
    within the cluster.  Since chunk count is not available here, we elect
    the article that appears first in sorted order (lexicographic) to ensure
    determinism.  The caller (command layer) may override this with chunk-count
    information when available.
    """
    if len(article_embeddings) < 2:
        return []

    # Sorted list of filenames for deterministic output regardless of dict order
    filenames = sorted(article_embeddings.keys())

    uf = _UnionFind(filenames)

    # Compute all pairwise distances — O(n²) on article count (not chunk count)
    # and merge pairs below threshold
    n = len(filenames)
    for i in range(n):
        for j in range(i + 1, n):
            fn_i = filenames[i]
            fn_j = filenames[j]
            dist = cosine_distance(article_embeddings[fn_i], article_embeddings[fn_j])
            if dist < threshold:
                uf.union(fn_i, fn_j)

    # Group filenames by their root representative
    clusters: dict[str, list[str]] = {}
    for fn in filenames:
        root = uf.find(fn)
        clusters.setdefault(root, []).append(fn)

    # Build output — exclude singleton clusters
    groups: list[dict] = []
    for cluster_members in sorted(clusters.values(), key=lambda m: sorted(m)[0]):
        if len(cluster_members) < 2:
            continue
        members_sorted = sorted(cluster_members)
        # Elect the first in sorted order as "keep" for determinism
        keep = members_sorted[0]
        duplicates = []
        for fn in members_sorted[1:]:
            dist = cosine_distance(article_embeddings[keep], article_embeddings[fn])
            duplicates.append({"filename": fn, "distance": round(dist, 6)})
        groups.append({"keep": keep, "duplicates": duplicates})

    return groups
