"""Unit + integration tests for atlas/intelligence/states/component_validator.py.

Unit tests run without DB (no ATLAS_INTEGRATION_TESTS needed).
Integration test is gated behind ATLAS_INTEGRATION_TESTS=1.

Test naming: test_<function>_<scenario>_<expected>
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from atlas.intelligence.states.component_validator import (
    _classify_status,
    _compute_q5_q1_spread,
    _tier_membership,
    validate_all_components,
)

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


# ---------------------------------------------------------------------------
# _classify_status unit tests
# ---------------------------------------------------------------------------


def test_classify_status_validated_positive() -> None:
    """IR > 0.4 with favours_long implied_action → validated."""
    assert _classify_status(0.5, "favours_long") == "validated"


def test_classify_status_validated_warns_long_negative_ir() -> None:
    """IR < -0.4 with warns_long implied_action → validated (negative IC expected)."""
    assert _classify_status(-0.45, "warns_long") == "validated"


def test_classify_status_validated_inverse() -> None:
    """IR > 0.4 with warns_long implied_action → validated_inverse (wrong sign)."""
    assert _classify_status(0.5, "warns_long") == "validated_inverse"


def test_classify_status_validated_inverse_negative_favours_long() -> None:
    """IR < -0.4 with favours_long implied_action → validated_inverse."""
    assert _classify_status(-0.45, "favours_long") == "validated_inverse"


def test_classify_status_weak_positive() -> None:
    """IR in (0.2, 0.4] → weak regardless of implied_action."""
    assert _classify_status(0.3, "favours_long") == "weak"


def test_classify_status_weak_negative() -> None:
    """IR in (-0.4, -0.2) → weak."""
    assert _classify_status(-0.25, "warns_long") == "weak"


def test_classify_status_decorative_near_zero() -> None:
    """IR at boundary 0.2 → decorative (not strictly above 0.2)."""
    assert _classify_status(0.2, "favours_long") == "decorative"


def test_classify_status_decorative_zero() -> None:
    """IR = 0.0 → decorative."""
    assert _classify_status(0.0, "favours_long") == "decorative"


def test_classify_status_neutral_informational_high_ir_validated() -> None:
    """neutral_informational with |IR| > 0.4 → validated regardless of sign."""
    assert _classify_status(0.6, "neutral_informational") == "validated"


def test_classify_status_neutral_informational_negative_high_ir_validated() -> None:
    """neutral_informational with |IR| > 0.4 (negative) → still validated."""
    assert _classify_status(-0.6, "neutral_informational") == "validated"


def test_classify_status_neutral_informational_weak() -> None:
    """neutral_informational with |IR| in (0.2, 0.4] → weak."""
    assert _classify_status(0.3, "neutral_informational") == "weak"


# ---------------------------------------------------------------------------
# _tier_membership unit tests
# ---------------------------------------------------------------------------


def _make_factor(values: list[float], dates: list[str], iids: list[str]) -> pd.DataFrame:
    """Build a (date, instrument_id) MultiIndex DataFrame with a 'factor' column."""
    index = pd.MultiIndex.from_arrays(
        [pd.to_datetime(dates), iids], names=["date", "instrument_id"]
    )
    return pd.DataFrame({"factor": values}, index=index)


def test_tier_membership_continuous_factor_in_range() -> None:
    """Factor within [low, high) maps to 1.0."""
    factor = _make_factor(
        [0.95, 0.50, 0.05],
        ["2024-01-01", "2024-01-01", "2024-01-01"],
        ["A", "B", "C"],
    )
    tier = _tier_membership(factor, low=0.90, high=1.01, percentile=False)
    assert tier.loc[(pd.Timestamp("2024-01-01"), "A"), "factor"] == 1.0
    assert tier.loc[(pd.Timestamp("2024-01-01"), "B"), "factor"] == 0.0
    assert tier.loc[(pd.Timestamp("2024-01-01"), "C"), "factor"] == 0.0


def test_tier_membership_continuous_factor_boundary_excluded() -> None:
    """Factor exactly at high boundary is excluded (uses < not <=)."""
    factor = _make_factor(
        [0.90, 1.01],
        ["2024-01-01", "2024-01-01"],
        ["A", "B"],
    )
    tier = _tier_membership(factor, low=0.90, high=1.01, percentile=False)
    # 0.90 >= 0.90 AND 0.90 < 1.01 → True
    assert tier.loc[(pd.Timestamp("2024-01-01"), "A"), "factor"] == 1.0
    # 1.01 >= 0.90 AND 1.01 < 1.01 → False
    assert tier.loc[(pd.Timestamp("2024-01-01"), "B"), "factor"] == 0.0


def test_tier_membership_percentile_mode() -> None:
    """In percentile mode, rank is computed cross-sectionally per date.

    With 4 instruments and values 10, 20, 30, 40:
    - rank(pct=True) = 0.25, 0.50, 0.75, 1.00
    - high tier (>= 0.75, < 1.01) → instruments C (0.75) and D (1.00) = 1.0
    - Wait: 1.0 < 1.01 is True, so both C and D qualify.
    """
    factor = _make_factor(
        [10.0, 20.0, 30.0, 40.0],
        ["2024-01-01"] * 4,
        ["A", "B", "C", "D"],
    )
    tier = _tier_membership(factor, low=0.75, high=1.01, percentile=True)
    dt = pd.Timestamp("2024-01-01")
    assert tier.loc[(dt, "A"), "factor"] == 0.0  # rank 0.25 — below 0.75
    assert tier.loc[(dt, "B"), "factor"] == 0.0  # rank 0.50 — below 0.75
    assert tier.loc[(dt, "C"), "factor"] == 1.0  # rank 0.75 — at boundary, included
    assert tier.loc[(dt, "D"), "factor"] == 1.0  # rank 1.00 — included


def test_tier_membership_percentile_low_tier() -> None:
    """Percentile mode with low=[0, 0.25): instruments with pct_rank < 0.25 map to 1.0.

    With 4 instruments, rank(pct=True) gives 0.25, 0.50, 0.75, 1.00.
    Since the range is [0, 0.25), none are strictly less than 0.25, so all map to 0.
    Use 5 instruments to get rank 0.20 (< 0.25) for the lowest.
    """
    # With 5 instruments, ranks = 0.20, 0.40, 0.60, 0.80, 1.00
    factor = _make_factor(
        [10.0, 20.0, 30.0, 40.0, 50.0],
        ["2024-01-01"] * 5,
        ["A", "B", "C", "D", "E"],
    )
    tier = _tier_membership(factor, low=0.0, high=0.25, percentile=True)
    dt = pd.Timestamp("2024-01-01")
    assert tier.loc[(dt, "A"), "factor"] == 1.0  # rank 0.20 — below 0.25 boundary
    assert tier.loc[(dt, "B"), "factor"] == 0.0  # rank 0.40 — above
    assert tier.loc[(dt, "C"), "factor"] == 0.0
    assert tier.loc[(dt, "D"), "factor"] == 0.0
    assert tier.loc[(dt, "E"), "factor"] == 0.0


# ---------------------------------------------------------------------------
# _compute_q5_q1_spread unit tests
# ---------------------------------------------------------------------------


def test_compute_q5_q1_spread_positive_spread() -> None:
    """Tier=1 instruments with higher forward returns produce positive spread."""
    dt = pd.Timestamp("2024-01-01")
    tier = _make_factor([1.0, 1.0, 0.0, 0.0], ["2024-01-01"] * 4, ["A", "B", "C", "D"])
    # Construct wide returns: A, B earn +5%; C, D earn -1%
    returns_wide = pd.DataFrame(
        {"A": [0.05], "B": [0.05], "C": [-0.01], "D": [-0.01]},
        index=pd.DatetimeIndex([dt]),
    )
    returns_wide.columns.name = "instrument_id"
    spread = _compute_q5_q1_spread(tier, returns_wide)
    assert abs(spread - 0.06) < 1e-9


def test_compute_q5_q1_spread_empty_tier_returns_zero() -> None:
    """Empty tier produces 0.0 spread without error."""
    empty_tier = pd.DataFrame(columns=["factor"])
    empty_tier.index = pd.MultiIndex.from_tuples([], names=["date", "instrument_id"])
    returns_wide = pd.DataFrame(
        {"A": [0.05]},
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-01")]),
    )
    returns_wide.columns.name = "instrument_id"
    spread = _compute_q5_q1_spread(empty_tier, returns_wide)
    assert spread == 0.0


def test_compute_q5_q1_spread_single_tier_returns_zero() -> None:
    """When all instruments are in tier=1 (no tier=0), spread is 0.0."""
    tier = _make_factor([1.0, 1.0], ["2024-01-01"] * 2, ["A", "B"])
    returns_wide = pd.DataFrame(
        {"A": [0.05], "B": [0.03]},
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-01")]),
    )
    returns_wide.columns.name = "instrument_id"
    spread = _compute_q5_q1_spread(tier, returns_wide)
    assert spread == 0.0


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_validate_all_components_populates_table(db_engine) -> None:  # type: ignore[no-untyped-def]
    """validate_all_components runs against live DB and populates atlas_component_validation.

    Uses a narrow 90-day window to keep runtime reasonable.
    Verifies at least 1 result is returned and rows land in DB.
    """
    import sqlalchemy as sa
    from sqlalchemy import text

    end = date(2024, 6, 30)
    start = date(2024, 4, 1)

    # Use only rs_rank_12m (SQL-only, fast) for integration smoke test
    # by patching the catalog before calling.
    from atlas.intelligence.states import component_validator as cv_mod

    original_catalog = cv_mod._COMPONENT_CATALOG
    try:
        cv_mod._COMPONENT_CATALOG = [e for e in original_catalog if e["name"] == "rs_rank_12m"]
        db_url = os.environ["ATLAS_DB_URL"]
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
        eng = sa.create_engine(db_url, pool_size=2, max_overflow=0)

        results = validate_all_components(eng, start, end)
    finally:
        cv_mod._COMPONENT_CATALOG = original_catalog

    assert len(results) >= 1, "expected at least 1 result from rs_rank_12m tiers"

    # Verify rows landed in DB
    with eng.connect() as c:
        count = c.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM atlas.atlas_component_validation
                WHERE component_name = 'rs_rank_12m'
                  AND as_of_date = :d
            """),
            {"d": end},
        ).fetchone()
    assert count is not None
    assert count.cnt >= 1

    # Verify each result has a valid status
    for r in results:
        assert r.status in ("validated", "validated_inverse", "weak", "decorative")
        assert r.component_name == "rs_rank_12m"
        assert isinstance(r.n_observations, int)
        assert r.n_observations >= 0
