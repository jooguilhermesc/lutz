"""Ranking utility — pure functions for article relevance scoring.

No LLM in this module. Operates solely on pre-computed embeddings.
"""

from __future__ import annotations

import numpy as np


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two 1-D float vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def rank_articles_by_relevance(
    article_chunk_embeddings: dict[str, list[np.ndarray]],
    question_embedding: np.ndarray,
    aggregation: str = "mean",
) -> list[dict]:
    """Return articles ranked by relevance to the question embedding.

    Parameters
    ----------
    article_chunk_embeddings:
        Mapping from filename to list of chunk embedding arrays.
    question_embedding:
        Embedding of the research question (1-D float array).
    aggregation:
        ``"mean"`` — average cosine similarity across all chunks (default).
        ``"max"``  — maximum cosine similarity across all chunks.

    Returns
    -------
    list of dicts, each with keys:
        ``filename``   — article file name
        ``score``      — float relevance score in [-1, 1]
        ``chunks_used``— number of chunks considered
    Sorted by score descending; ties broken by filename ascending.
    """
    if not article_chunk_embeddings:
        return []

    results: list[dict] = []
    for filename, chunks in article_chunk_embeddings.items():
        if not chunks:
            score = 0.0
            chunks_used = 0
        else:
            similarities = [_cosine_similarity(chunk, question_embedding) for chunk in chunks]
            if aggregation == "max":
                score = float(max(similarities))
            else:
                score = float(sum(similarities) / len(similarities))
            chunks_used = len(chunks)

        results.append({"filename": filename, "score": score, "chunks_used": chunks_used})

    # Sort by score descending; filename ascending as deterministic tiebreaker
    results.sort(key=lambda r: (-r["score"], r["filename"]))
    return results
