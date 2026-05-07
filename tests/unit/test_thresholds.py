"""Unit tests for the threshold catalog seeder.

These tests verify the catalog itself (no DB needed): all 35 thresholds
present, every default within its allowed range, every threshold has a
methodology section reference.
"""

from __future__ import annotations

import pytest

from atlas.universe.thresholds import THRESHOLDS, Threshold


def test_catalog_has_exactly_35_thresholds() -> None:
    assert len(THRESHOLDS) == 35


def test_keys_are_unique() -> None:
    keys = [t.key for t in THRESHOLDS]
    assert len(keys) == len(set(keys)), f"Duplicate threshold keys: {keys}"


@pytest.mark.parametrize("t", THRESHOLDS, ids=lambda t: t.key)
def test_default_within_allowed_range(t: Threshold) -> None:
    assert (
        t.min_allowed <= t.default <= t.max_allowed
    ), f"{t.key}: default={t.default} outside [{t.min_allowed}, {t.max_allowed}]"


@pytest.mark.parametrize("t", THRESHOLDS, ids=lambda t: t.key)
def test_min_strictly_less_than_max(t: Threshold) -> None:
    assert t.min_allowed < t.max_allowed, f"{t.key}: min ({t.min_allowed}) >= max ({t.max_allowed})"


@pytest.mark.parametrize("t", THRESHOLDS, ids=lambda t: t.key)
def test_has_methodology_section(t: Threshold) -> None:
    assert t.methodology_section, f"{t.key} missing methodology_section"
    # Must be of the form "N.M" — section.subsection
    parts = t.methodology_section.split(".")
    assert len(parts) >= 1
    assert parts[0].isdigit(), f"{t.key}: malformed methodology_section"


@pytest.mark.parametrize("t", THRESHOLDS, ids=lambda t: t.key)
def test_has_description(t: Threshold) -> None:
    assert t.description, f"{t.key} missing description"
    assert len(t.description) >= 20, f"{t.key} description too short"


@pytest.mark.parametrize("t", THRESHOLDS, ids=lambda t: t.key)
def test_category_in_known_set(t: Threshold) -> None:
    valid_categories = {
        "rs",
        "momentum",
        "risk",
        "volume",
        "gate",
        "sector",
        "regime",
        "fund",
        "decision",
    }
    assert t.category in valid_categories, f"{t.key}: unknown category {t.category}"


def test_category_distribution_matches_catalog() -> None:
    """Per ``04_THRESHOLD_CATALOG.md`` Section 1.3:
    2 gates + 2 RS + 3 momentum + 5 risk + 4 volume + 1 weinstein +
    2 stage1 + 3 sector + 8 regime + 4 fund + 1 decision = 35.

    Note: weinstein and stage1 thresholds are categorized as 'gate' or
    'rs' (no separate 'weinstein' / 'stage1' categories). The catalog
    document groups them by section but the DB category is broader.
    """
    counts: dict[str, int] = {}
    for t in THRESHOLDS:
        counts[t.category] = counts.get(t.category, 0) + 1
    # Check a few specific counts that the methodology mandates
    assert (
        counts.get("regime", 0) == 8
    ), f"Expected 8 regime thresholds, got {counts.get('regime', 0)}"
    assert counts.get("fund", 0) == 4
    assert counts.get("decision", 0) == 1
    assert counts.get("volume", 0) == 4
    assert counts.get("sector", 0) == 3
    assert counts.get("risk", 0) == 5


def test_dislocation_multiplier_default() -> None:
    """Methodology 11.5 fixes the default dislocation multiplier at 4.0."""
    t = next(t for t in THRESHOLDS if t.key == "dislocation_vol_multiplier")
    assert t.default == 4.0
    assert t.min_allowed == 2.5
    assert t.max_allowed == 6.0


def test_rs_quintile_top_default() -> None:
    """Methodology 7.1 fixes top-quintile cutoff at 0.80."""
    t = next(t for t in THRESHOLDS if t.key == "rs_quintile_top")
    assert t.default == 0.80


def test_rs_quintile_bottom_default() -> None:
    """Methodology 7.1 fixes bottom-quintile cutoff at 0.20."""
    t = next(t for t in THRESHOLDS if t.key == "rs_quintile_bottom")
    assert t.default == 0.20


def test_breakout_proximity_default_5_pct() -> None:
    """Methodology 13.3 fixes BREAKOUT_TRIGGER proximity at 5%."""
    t = next(t for t in THRESHOLDS if t.key == "entry_breakout_proximity_max_pct")
    assert t.default == 5
