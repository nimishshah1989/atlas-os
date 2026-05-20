"""Tests for migration 095 — seed hybrid-classifier band + floor thresholds.

Structural unit tests (no DB required):
  - All 8 expected threshold keys are present in SEEDS.
  - Values match the inline defaults in sector.py / fund.py.
  - min_allowed < default_value < max_allowed for each row.
  - Category values are valid ("sector_rank" or "fund_rank").

Integration tests (requires ATLAS_INTEGRATION_TESTS=1, EC2 only):
  - All 8 keys are present in atlas.atlas_thresholds with is_active=TRUE.
  - Stored values match the SEEDS constants.
"""

from __future__ import annotations

import importlib
import os
from decimal import Decimal

import pytest

# Migration filenames start with digits so they cannot be imported with
# a regular 'from ... import' statement. Use importlib instead (same pattern
# as tests/unit/migrations/test_migration_064.py).
_migration = importlib.import_module("migrations.versions.095_seed_hybrid_classifier_thresholds")
SEEDS: tuple[tuple[str, float, str, str, float, float, float], ...] = _migration.SEEDS

# ---------------------------------------------------------------------------
# Structural unit tests (no DB, always run)
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = {
    "sector_band_p20",
    "sector_band_p50",
    "sector_band_p80",
    "sector_overweight_floor",
    "fund_band_p20",
    "fund_band_p50",
    "fund_band_p80",
    "fund_recommended_floor",
}

_EXPECTED_VALUES: dict[str, float] = {
    "sector_band_p20": 0.20,
    "sector_band_p50": 0.50,
    "sector_band_p80": 0.80,
    "sector_overweight_floor": 0.10,
    "fund_band_p20": 0.20,
    "fund_band_p50": 0.50,
    "fund_band_p80": 0.80,
    "fund_recommended_floor": 0.20,
}

_VALID_CATEGORIES = {"sector_rank", "fund_rank"}


def test_seeds_contains_all_eight_keys() -> None:
    """All 8 hybrid-classifier threshold keys are present in SEEDS."""
    seeded_keys = {row[0] for row in SEEDS}
    missing = _EXPECTED_KEYS - seeded_keys
    assert not missing, f"SEEDS is missing threshold keys: {missing}"


def test_seeds_values_match_inline_defaults() -> None:
    """Seeded values match the inline Decimal defaults in sector.py / fund.py.

    This is the contract test: if someone changes the inline default without
    updating the migration (or vice versa) this test catches the drift.
    """
    seed_map = {row[0]: row[1] for row in SEEDS}
    for key, expected in _EXPECTED_VALUES.items():
        assert key in seed_map, f"key {key!r} not found in SEEDS"
        actual = seed_map[key]
        assert abs(actual - expected) < 1e-9, (
            f"value mismatch for {key!r}: migration seeds {actual}, "
            f"inline default is {expected}"
        )


def test_seeds_range_constraints_are_valid() -> None:
    """Every seed row satisfies: min_allowed <= default_value <= max_allowed."""
    for key, value, _category, _desc, lo, hi, default in SEEDS:
        assert lo <= default <= hi, f"{key!r}: default {default} is outside [{lo}, {hi}]"
        assert lo <= value <= hi, f"{key!r}: seed value {value} is outside [{lo}, {hi}]"


def test_seeds_categories_are_valid() -> None:
    """All seed rows use a known category value."""
    for key, _value, category, *_ in SEEDS:
        assert (
            category in _VALID_CATEGORIES
        ), f"{key!r}: unknown category {category!r}, expected one of {_VALID_CATEGORIES}"


def test_sector_keys_use_sector_rank_category() -> None:
    """All sector_* keys are categorised as 'sector_rank'."""
    seed_map = {row[0]: row[2] for row in SEEDS}
    for key in ("sector_band_p20", "sector_band_p50", "sector_band_p80", "sector_overweight_floor"):
        assert (
            seed_map[key] == "sector_rank"
        ), f"{key!r} should have category 'sector_rank', got {seed_map[key]!r}"


def test_fund_keys_use_fund_rank_category() -> None:
    """All fund_* keys are categorised as 'fund_rank'."""
    seed_map = {row[0]: row[2] for row in SEEDS}
    for key in ("fund_band_p20", "fund_band_p50", "fund_band_p80", "fund_recommended_floor"):
        assert (
            seed_map[key] == "fund_rank"
        ), f"{key!r} should have category 'fund_rank', got {seed_map[key]!r}"


def test_seeds_values_match_sector_module_defaults() -> None:
    """Seeded values are in sync with the inline Decimal defaults in sector.py.

    Imports the actual default constants from the module — if anyone changes
    the inline default and forgets to update the migration this test fails.
    """
    from atlas.intelligence.aggregations.sector import (
        _DEFAULT_BAND_P20,
        _DEFAULT_BAND_P50,
        _DEFAULT_BAND_P80,
        _DEFAULT_OVERWEIGHT_FLOOR,
    )

    seed_map = {row[0]: Decimal(str(row[1])) for row in SEEDS}
    assert seed_map["sector_band_p20"] == _DEFAULT_BAND_P20
    assert seed_map["sector_band_p50"] == _DEFAULT_BAND_P50
    assert seed_map["sector_band_p80"] == _DEFAULT_BAND_P80
    assert seed_map["sector_overweight_floor"] == _DEFAULT_OVERWEIGHT_FLOOR


def test_seeds_values_match_fund_module_defaults() -> None:
    """Seeded values are in sync with the inline Decimal defaults in fund.py."""
    from atlas.intelligence.aggregations.fund import (
        _DEFAULT_FUND_BAND_P20,
        _DEFAULT_FUND_BAND_P50,
        _DEFAULT_FUND_BAND_P80,
        _DEFAULT_FUND_RECOMMENDED_FLOOR,
    )

    seed_map = {row[0]: Decimal(str(row[1])) for row in SEEDS}
    assert seed_map["fund_band_p20"] == _DEFAULT_FUND_BAND_P20
    assert seed_map["fund_band_p50"] == _DEFAULT_FUND_BAND_P50
    assert seed_map["fund_band_p80"] == _DEFAULT_FUND_BAND_P80
    assert seed_map["fund_recommended_floor"] == _DEFAULT_FUND_RECOMMENDED_FLOOR


# ---------------------------------------------------------------------------
# Integration tests (live DB — EC2 only)
# ---------------------------------------------------------------------------

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB, EC2 only)",
)


@_SKIP_INTEGRATION
def test_hybrid_thresholds_seeded_in_db(db_engine) -> None:  # type: ignore[no-untyped-def]
    """All 8 keys present in atlas_thresholds with is_active=TRUE."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT threshold_key, threshold_value
                FROM atlas.atlas_thresholds
                WHERE threshold_key = ANY(:keys) AND is_active = TRUE
            """),
            {"keys": list(_EXPECTED_KEYS)},
        ).fetchall()

    found_keys = {r[0] for r in rows}
    missing = _EXPECTED_KEYS - found_keys
    assert not missing, f"keys missing from live atlas_thresholds: {missing}"


@_SKIP_INTEGRATION
def test_hybrid_thresholds_db_values_match_seeds(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Stored values in atlas_thresholds match the SEEDS constants."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT threshold_key, threshold_value
                FROM atlas.atlas_thresholds
                WHERE threshold_key = ANY(:keys) AND is_active = TRUE
            """),
            {"keys": list(_EXPECTED_KEYS)},
        ).fetchall()

    db_map = {r[0]: float(r[1]) for r in rows}
    for key, expected in _EXPECTED_VALUES.items():
        if key not in db_map:
            pytest.skip(f"{key!r} not yet seeded (migration 095 not applied)")
        assert (
            abs(db_map[key] - expected) < 1e-6
        ), f"{key!r}: DB has {db_map[key]}, expected {expected}"
