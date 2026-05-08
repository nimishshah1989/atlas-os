"""Unit tests for Jaccard overlap matrix — no DB required."""

from __future__ import annotations

import uuid

from atlas.simulation.core.overlap import jaccard_similarity, upper_triangle_pairs


def test_jaccard_disjoint_sets_returns_zero():
    a = {"INFY", "TCS", "HDFC"}
    b = {"RELIANCE", "BAJFINANCE", "WIPRO"}
    assert jaccard_similarity(a, b) == 0.0


def test_jaccard_identical_sets_returns_one():
    a = {"INFY", "TCS", "HDFC"}
    assert jaccard_similarity(a, a) == 1.0


def test_jaccard_fifty_percent_overlap():
    a = {"INFY", "TCS"}
    b = {"INFY", "HDFC"}
    # |intersection| = 1, |union| = 3 → 1/3 ≈ 0.333
    result = jaccard_similarity(a, b)
    assert abs(result - 1 / 3) < 0.001


def test_jaccard_empty_sets_returns_zero():
    assert jaccard_similarity(set(), set()) == 0.0


def test_upper_triangle_pairs_count():
    ids = [uuid.uuid4() for _ in range(15)]
    pairs = upper_triangle_pairs(ids)
    # C(15, 2) = 105
    assert len(pairs) == 105


def test_upper_triangle_pairs_canonical_ordering():
    ids = [uuid.uuid4() for _ in range(5)]
    pairs = upper_triangle_pairs(ids)
    for a, b in pairs:
        assert str(a) < str(b), f"Pair not in canonical order: {a} < {b}"


def test_upper_triangle_pairs_no_self_pairs():
    ids = [uuid.uuid4() for _ in range(5)]
    pairs = upper_triangle_pairs(ids)
    for a, b in pairs:
        assert a != b
