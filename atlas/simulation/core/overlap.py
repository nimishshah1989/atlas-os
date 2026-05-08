"""Jaccard portfolio overlap matrix for 15 paper trading strategies."""

from __future__ import annotations

from uuid import UUID


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two instrument sets.

    Returns 0.0 for empty sets (both empty → no overlap).
    """
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union


def upper_triangle_pairs(ids: list[UUID]) -> list[tuple[UUID, UUID]]:
    """Return all C(n,2) pairs in canonical order (str(a) < str(b)).

    This ordering satisfies the CHECK constraint on strategy_overlap_daily.
    Always sort in Python before inserting — never rely on insertion order.
    """
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if str(a) < str(b):
                pairs.append((a, b))
            else:
                pairs.append((b, a))
    return pairs
