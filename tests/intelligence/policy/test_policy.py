"""Tests for atlas.intelligence.policy.policy — effective-policy merge + validation.

All merge and validate tests are pure (no DB). Integration tests that exercise
the real DB read are guarded by the ``integration`` marker.
"""

from __future__ import annotations

from decimal import Decimal

from atlas.intelligence.policy.policy import (
    Policy,
    _merge,
    validate_policy,
)

# ---------------------------------------------------------------------------
# House-default fixture — mirrors scripts/seed_house_policy.py HOUSE_POLICY_DEFAULTS
# ---------------------------------------------------------------------------

HOUSE_DEFAULTS: dict[str, object] = {
    "cash_floor_pct": Decimal("5"),
    "respect_regime_cap": True,
    "max_per_stock_pct": Decimal("5"),
    "max_per_sector_pct": Decimal("15"),
    "max_small_cap_pct": Decimal("30"),
    "min_holdings": 15,
    "max_positions": 40,
    "buy_states": ["stage_2a", "stage_2b"],
    "min_within_state_rank": Decimal("0.60"),
    "min_rs_rank": Decimal("0.70"),
    "hard_stop_pct": Decimal("8"),
    "state_exit_trim": "stage_3",
    "state_exit_full": "stage_4",
    "trailing_stop_pct": None,
    "instrument_universe": "direct_equity",
    "benchmark": "Nifty 500",
    "rebalance_cadence": "weekly",
}


# ---------------------------------------------------------------------------
# _merge tests (C6)
# ---------------------------------------------------------------------------


class TestMerge:
    def test_empty_override_returns_pure_house_default(self) -> None:
        """A portfolio with no overrides (all None) returns the exact house default."""
        result = _merge(house=HOUSE_DEFAULTS, overrides={})
        assert result["cash_floor_pct"] == Decimal("5")
        assert result["respect_regime_cap"] is True
        assert result["max_per_stock_pct"] == Decimal("5")
        assert result["max_per_sector_pct"] == Decimal("15")
        assert result["max_small_cap_pct"] == Decimal("30")
        assert result["min_holdings"] == 15
        assert result["max_positions"] == 40
        assert result["buy_states"] == ["stage_2a", "stage_2b"]
        assert result["min_within_state_rank"] == Decimal("0.60")
        assert result["min_rs_rank"] == Decimal("0.70")
        assert result["hard_stop_pct"] == Decimal("8")
        assert result["state_exit_trim"] == "stage_3"
        assert result["state_exit_full"] == "stage_4"
        assert result["trailing_stop_pct"] is None
        assert result["instrument_universe"] == "direct_equity"
        assert result["benchmark"] == "Nifty 500"
        assert result["rebalance_cadence"] == "weekly"

    def test_two_field_override_changes_only_those_fields(self) -> None:
        """Override of 2 non-null fields produces merged dict equal to house except those 2."""
        overrides: dict[str, object] = {
            "max_per_stock_pct": Decimal("10"),
            "rebalance_cadence": "monthly",
        }
        result = _merge(house=HOUSE_DEFAULTS, overrides=overrides)

        # Changed fields
        assert result["max_per_stock_pct"] == Decimal("10")
        assert result["rebalance_cadence"] == "monthly"

        # All other fields must be unchanged from the house default
        assert result["cash_floor_pct"] == Decimal("5")
        assert result["respect_regime_cap"] is True
        assert result["max_per_sector_pct"] == Decimal("15")
        assert result["max_small_cap_pct"] == Decimal("30")
        assert result["min_holdings"] == 15
        assert result["max_positions"] == 40
        assert result["buy_states"] == ["stage_2a", "stage_2b"]
        assert result["min_within_state_rank"] == Decimal("0.60")
        assert result["min_rs_rank"] == Decimal("0.70")
        assert result["hard_stop_pct"] == Decimal("8")
        assert result["state_exit_trim"] == "stage_3"
        assert result["state_exit_full"] == "stage_4"
        assert result["trailing_stop_pct"] is None
        assert result["instrument_universe"] == "direct_equity"
        assert result["benchmark"] == "Nifty 500"

    def test_override_buy_states_replaces_entire_list(self) -> None:
        """An override of buy_states replaces the full list, not merges."""
        overrides: dict[str, object] = {
            "buy_states": ["stage_2a", "stage_2b", "stage_2c"],
        }
        result = _merge(house=HOUSE_DEFAULTS, overrides=overrides)
        assert result["buy_states"] == ["stage_2a", "stage_2b", "stage_2c"]

    def test_override_none_values_treated_as_inherit(self) -> None:
        """None values in override dict are treated as 'inherit from house default'."""
        # Explicitly passing None for cash_floor_pct should inherit house value
        overrides: dict[str, object] = {
            "cash_floor_pct": None,
            "max_per_stock_pct": Decimal("10"),
        }
        result = _merge(house=HOUSE_DEFAULTS, overrides=overrides)
        assert result["cash_floor_pct"] == Decimal("5")  # inherited
        assert result["max_per_stock_pct"] == Decimal("10")  # overridden

    def test_override_respect_regime_cap_false(self) -> None:
        """Boolean override works correctly."""
        overrides: dict[str, object] = {"respect_regime_cap": False}
        result = _merge(house=HOUSE_DEFAULTS, overrides=overrides)
        assert result["respect_regime_cap"] is False

    def test_merged_dict_produces_valid_policy_object(self) -> None:
        """_merge output can be unpacked into a Policy dataclass."""
        result = _merge(house=HOUSE_DEFAULTS, overrides={})
        policy = Policy(**result)
        assert policy.cash_floor_pct == Decimal("5")
        assert policy.rebalance_cadence == "weekly"


# ---------------------------------------------------------------------------
# validate_policy tests (C7)
# ---------------------------------------------------------------------------


def _make_valid_policy(**overrides: object) -> Policy:
    """Build a known-valid Policy, optionally overriding specific fields."""
    base = dict(HOUSE_DEFAULTS)
    base.update(overrides)
    return Policy(**base)  # type: ignore[arg-type]


class TestValidatePolicy:
    def test_valid_policy_returns_empty_list(self) -> None:
        """A fully-valid house-default policy produces no violations."""
        policy = _make_valid_policy()
        violations = validate_policy(policy)
        assert violations == []

    def test_min_holdings_exceeds_max_positions_returns_violation(self) -> None:
        """min_holdings=50, max_positions=40 → exactly the min>max violation."""
        # Hand-computed: 50 > 40 is a coherence violation
        policy = _make_valid_policy(min_holdings=50, max_positions=40)
        violations = validate_policy(policy)
        assert len(violations) == 1
        assert "min_holdings" in violations[0]
        assert "50" in violations[0]
        assert "40" in violations[0]

    def test_max_per_stock_exceeds_max_per_sector_returns_violation(self) -> None:
        """max_per_stock_pct=20, max_per_sector_pct=15 → per-stock > per-sector violation."""
        # Hand-computed: 20 > 15 means one stock can exceed its whole sector cap — incoherent
        policy = _make_valid_policy(
            max_per_stock_pct=Decimal("20"),
            max_per_sector_pct=Decimal("15"),
        )
        violations = validate_policy(policy)
        assert len(violations) == 1
        assert "max_per_stock_pct" in violations[0] or "per-stock" in violations[0]

    def test_cash_floor_pct_negative_returns_violation(self) -> None:
        """cash_floor_pct=-1 is outside [0,100]."""
        policy = _make_valid_policy(cash_floor_pct=Decimal("-1"))
        violations = validate_policy(policy)
        assert any("cash_floor_pct" in v for v in violations)

    def test_cash_floor_pct_above_100_returns_violation(self) -> None:
        """cash_floor_pct=101 is outside [0,100]."""
        policy = _make_valid_policy(cash_floor_pct=Decimal("101"))
        violations = validate_policy(policy)
        assert any("cash_floor_pct" in v for v in violations)

    def test_cash_floor_pct_zero_is_valid(self) -> None:
        """cash_floor_pct=0 is on the boundary — valid."""
        policy = _make_valid_policy(cash_floor_pct=Decimal("0"))
        violations = validate_policy(policy)
        assert not any("cash_floor_pct" in v for v in violations)

    def test_cash_floor_pct_100_is_valid(self) -> None:
        """cash_floor_pct=100 is on the upper boundary — valid (edge case)."""
        policy = _make_valid_policy(cash_floor_pct=Decimal("100"))
        violations = validate_policy(policy)
        assert not any("cash_floor_pct" in v for v in violations)

    def test_min_within_state_rank_below_zero_returns_violation(self) -> None:
        """min_within_state_rank=-0.1 is outside [0,1]."""
        policy = _make_valid_policy(min_within_state_rank=Decimal("-0.1"))
        violations = validate_policy(policy)
        assert any("min_within_state_rank" in v for v in violations)

    def test_min_within_state_rank_above_one_returns_violation(self) -> None:
        """min_within_state_rank=1.5 is outside [0,1]."""
        policy = _make_valid_policy(min_within_state_rank=Decimal("1.5"))
        violations = validate_policy(policy)
        assert any("min_within_state_rank" in v for v in violations)

    def test_min_rs_rank_above_one_returns_violation(self) -> None:
        """min_rs_rank=1.01 is outside [0,1]."""
        policy = _make_valid_policy(min_rs_rank=Decimal("1.01"))
        violations = validate_policy(policy)
        assert any("min_rs_rank" in v for v in violations)

    def test_invalid_instrument_universe_returns_violation(self) -> None:
        """instrument_universe='crypto' is not in the allowed set."""
        policy = _make_valid_policy(instrument_universe="crypto")
        violations = validate_policy(policy)
        assert any("instrument_universe" in v for v in violations)

    def test_valid_instrument_universe_values(self) -> None:
        """All four allowed instrument_universe values pass validation."""
        for universe in ("direct_equity", "etf", "mutual_fund", "mixed"):
            policy = _make_valid_policy(instrument_universe=universe)
            violations = validate_policy(policy)
            assert not any(
                "instrument_universe" in v for v in violations
            ), f"Expected no instrument_universe violation for '{universe}', got {violations}"

    def test_invalid_rebalance_cadence_returns_violation(self) -> None:
        """rebalance_cadence='quarterly' is not in the allowed set."""
        policy = _make_valid_policy(rebalance_cadence="quarterly")
        violations = validate_policy(policy)
        assert any("rebalance_cadence" in v for v in violations)

    def test_valid_rebalance_cadence_values(self) -> None:
        """All three allowed rebalance_cadence values pass validation."""
        for cadence in ("daily", "weekly", "monthly"):
            policy = _make_valid_policy(rebalance_cadence=cadence)
            violations = validate_policy(policy)
            assert not any(
                "rebalance_cadence" in v for v in violations
            ), f"Expected no rebalance_cadence violation for '{cadence}', got {violations}"

    def test_hard_stop_pct_zero_returns_violation(self) -> None:
        """hard_stop_pct=0 is not a valid stop magnitude."""
        policy = _make_valid_policy(hard_stop_pct=Decimal("0"))
        violations = validate_policy(policy)
        assert any("hard_stop_pct" in v for v in violations)

    def test_hard_stop_pct_negative_returns_violation(self) -> None:
        """hard_stop_pct=-5 is not a valid stop magnitude."""
        policy = _make_valid_policy(hard_stop_pct=Decimal("-5"))
        violations = validate_policy(policy)
        assert any("hard_stop_pct" in v for v in violations)

    def test_hard_stop_pct_positive_is_valid(self) -> None:
        """hard_stop_pct=8 (house default) is valid."""
        policy = _make_valid_policy(hard_stop_pct=Decimal("8"))
        violations = validate_policy(policy)
        assert not any("hard_stop_pct" in v for v in violations)

    def test_multiple_violations_all_reported(self) -> None:
        """Multiple incoherent fields each produce their own violation string."""
        policy = _make_valid_policy(
            min_holdings=50,
            max_positions=40,
            max_per_stock_pct=Decimal("20"),
            max_per_sector_pct=Decimal("15"),
        )
        violations = validate_policy(policy)
        # Should have at least 2 violations
        assert len(violations) >= 2

    def test_trailing_stop_pct_none_is_valid(self) -> None:
        """trailing_stop_pct=None (no trailing stop) is valid."""
        policy = _make_valid_policy(trailing_stop_pct=None)
        violations = validate_policy(policy)
        assert violations == []

    def test_trailing_stop_pct_positive_is_valid(self) -> None:
        """trailing_stop_pct=10 (10% trailing stop) is valid."""
        policy = _make_valid_policy(trailing_stop_pct=Decimal("10"))
        violations = validate_policy(policy)
        assert violations == []

    def test_trailing_stop_pct_zero_returns_violation(self) -> None:
        """trailing_stop_pct=0 is a degenerate stop (triggers immediately)."""
        policy = _make_valid_policy(trailing_stop_pct=Decimal("0"))
        violations = validate_policy(policy)
        assert any("trailing_stop_pct" in v for v in violations)
