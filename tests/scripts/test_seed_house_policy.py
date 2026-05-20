"""Tests for scripts.seed_house_policy.

Structural tests run everywhere (no DB required).
DB-gated integration tests run only when ATLAS_INTEGRATION_TESTS=1.

Percentage storage convention: pct columns hold whole-number percent (5 for
5%, 15 for 15%). Rank columns hold fractions in [0, 1]. See script docstring.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# Structural tests — import the constants, no DB needed
# ---------------------------------------------------------------------------


def test_house_policy_defaults_importable() -> None:
    """HOUSE_POLICY_DEFAULTS must be importable without a DB connection."""
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert isinstance(HOUSE_POLICY_DEFAULTS, dict)


def test_house_policy_defaults_has_required_keys() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    required_keys = {
        "portfolio_id",
        "is_house_default",
        "cash_floor_pct",
        "respect_regime_cap",
        "max_per_stock_pct",
        "max_per_sector_pct",
        "max_small_cap_pct",
        "min_holdings",
        "max_positions",
        "buy_states",
        "min_within_state_rank",
        "min_rs_rank",
        "hard_stop_pct",
        "state_exit_trim",
        "state_exit_full",
        "trailing_stop_pct",
        "instrument_universe",
        "benchmark",
        "rebalance_cadence",
    }
    missing = required_keys - set(HOUSE_POLICY_DEFAULTS.keys())
    assert not missing, f"Missing keys: {missing}"


def test_is_house_default_true() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["is_house_default"] is True


def test_portfolio_id_is_none() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["portfolio_id"] is None


def test_trailing_stop_pct_is_none() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["trailing_stop_pct"] is None


def test_pct_fields_are_decimal() -> None:
    """All percentage fields must be Decimal, not float."""
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    pct_keys = [
        "cash_floor_pct",
        "max_per_stock_pct",
        "max_per_sector_pct",
        "max_small_cap_pct",
        "hard_stop_pct",
    ]
    for key in pct_keys:
        val = HOUSE_POLICY_DEFAULTS[key]
        assert isinstance(val, Decimal), f"{key} must be Decimal, got {type(val)}"


def test_pct_fields_are_whole_number_percent() -> None:
    """Convention: pct columns store whole-number percent (5 for 5%, not 0.05)."""
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["cash_floor_pct"] == Decimal("5")
    assert HOUSE_POLICY_DEFAULTS["max_per_stock_pct"] == Decimal("5")
    assert HOUSE_POLICY_DEFAULTS["max_per_sector_pct"] == Decimal("15")
    assert HOUSE_POLICY_DEFAULTS["max_small_cap_pct"] == Decimal("30")
    assert HOUSE_POLICY_DEFAULTS["hard_stop_pct"] == Decimal("8")


def test_rank_fields_are_decimal_fractions() -> None:
    """Rank columns store fractions in [0, 1], not percent."""
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    for key in ("min_within_state_rank", "min_rs_rank"):
        val = HOUSE_POLICY_DEFAULTS[key]
        assert isinstance(val, Decimal), f"{key} must be Decimal, got {type(val)}"
        assert Decimal("0") <= val <= Decimal("1"), f"{key}={val} must be in [0, 1]"


def test_rank_field_values() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["min_within_state_rank"] == Decimal("0.60")
    assert HOUSE_POLICY_DEFAULTS["min_rs_rank"] == Decimal("0.70")


def test_integer_fields() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["min_holdings"] == 15
    assert HOUSE_POLICY_DEFAULTS["max_positions"] == 40
    assert isinstance(HOUSE_POLICY_DEFAULTS["min_holdings"], int)
    assert isinstance(HOUSE_POLICY_DEFAULTS["max_positions"], int)


def test_buy_states_is_list_of_strings() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    buy_states = HOUSE_POLICY_DEFAULTS["buy_states"]
    assert isinstance(buy_states, list)
    assert len(buy_states) >= 1
    for s in buy_states:
        assert isinstance(s, str)


def test_buy_states_values() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["buy_states"] == ["stage_2a", "stage_2b"]


def test_instrument_universe_passes_check_constraint() -> None:
    """Must be one of the 4 allowed values from the CHECK constraint."""
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    allowed = {"direct_equity", "etf", "mutual_fund", "mixed"}
    assert HOUSE_POLICY_DEFAULTS["instrument_universe"] in allowed


def test_instrument_universe_value() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["instrument_universe"] == "direct_equity"


def test_rebalance_cadence_passes_check_constraint() -> None:
    """Must be one of the 3 allowed values from the CHECK constraint."""
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    allowed = {"daily", "weekly", "monthly"}
    assert HOUSE_POLICY_DEFAULTS["rebalance_cadence"] in allowed


def test_rebalance_cadence_value() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["rebalance_cadence"] == "weekly"


def test_benchmark_value() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["benchmark"] == "Nifty 500"


def test_state_exit_values() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["state_exit_trim"] == "stage_3"
    assert HOUSE_POLICY_DEFAULTS["state_exit_full"] == "stage_4"


def test_respect_regime_cap_is_true() -> None:
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS

    assert HOUSE_POLICY_DEFAULTS["respect_regime_cap"] is True


def test_insert_sql_has_on_conflict_do_nothing() -> None:
    """Idempotency guard: INSERT must use ON CONFLICT DO NOTHING."""
    from scripts.seed_house_policy import INSERT_SQL

    assert "ON CONFLICT" in INSERT_SQL.upper()
    assert "DO NOTHING" in INSERT_SQL.upper()


def test_main_function_is_callable() -> None:
    from scripts.seed_house_policy import main

    assert callable(main)


# ---------------------------------------------------------------------------
# DB-gated integration tests
# ---------------------------------------------------------------------------

_INTEGRATION = os.getenv("ATLAS_INTEGRATION_TESTS") == "1"


@pytest.mark.skipif(not _INTEGRATION, reason="requires ATLAS_INTEGRATION_TESTS=1")
def test_integration_seed_inserts_exactly_one_row() -> None:
    """After seeding, exactly one is_house_default row must exist."""
    from sqlalchemy import text

    from atlas.db import get_engine
    from scripts.seed_house_policy import main

    engine = get_engine()

    # Clean up any pre-existing house-default row so test is deterministic
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM atlas.atlas_portfolio_policy WHERE is_house_default = TRUE"))

    main()

    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_portfolio_policy" " WHERE is_house_default = TRUE"
            )
        ).scalar()

    assert count == 1, f"Expected 1 house-default row, got {count}"


@pytest.mark.skipif(not _INTEGRATION, reason="requires ATLAS_INTEGRATION_TESTS=1")
def test_integration_second_run_is_idempotent() -> None:
    """Running main() twice must still yield exactly one house-default row."""
    from sqlalchemy import text

    from atlas.db import get_engine
    from scripts.seed_house_policy import main

    engine = get_engine()

    # Ensure a clean slate (first integration test may have run; re-seed anyway)
    main()
    main()

    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_portfolio_policy" " WHERE is_house_default = TRUE"
            )
        ).scalar()

    assert count == 1, f"Expected 1 row after two runs, got {count}"


@pytest.mark.skipif(not _INTEGRATION, reason="requires ATLAS_INTEGRATION_TESTS=1")
def test_integration_field_values_match_constants() -> None:
    """Seeded row fields must match HOUSE_POLICY_DEFAULTS exactly."""
    from decimal import Decimal

    from sqlalchemy import text

    from atlas.db import get_engine
    from scripts.seed_house_policy import HOUSE_POLICY_DEFAULTS, main

    engine = get_engine()
    main()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT cash_floor_pct, max_per_stock_pct, max_per_sector_pct,"
                " max_small_cap_pct, min_holdings, max_positions,"
                " min_within_state_rank, min_rs_rank, hard_stop_pct,"
                " instrument_universe, rebalance_cadence, benchmark,"
                " state_exit_trim, state_exit_full, buy_states,"
                " respect_regime_cap, trailing_stop_pct"
                " FROM atlas.atlas_portfolio_policy"
                " WHERE is_house_default = TRUE"
                " LIMIT 1"
            )
        ).fetchone()

    assert row is not None, "No house-default row found"

    assert Decimal(str(row[0])) == HOUSE_POLICY_DEFAULTS["cash_floor_pct"]
    assert Decimal(str(row[1])) == HOUSE_POLICY_DEFAULTS["max_per_stock_pct"]
    assert Decimal(str(row[2])) == HOUSE_POLICY_DEFAULTS["max_per_sector_pct"]
    assert Decimal(str(row[3])) == HOUSE_POLICY_DEFAULTS["max_small_cap_pct"]
    assert row[4] == HOUSE_POLICY_DEFAULTS["min_holdings"]
    assert row[5] == HOUSE_POLICY_DEFAULTS["max_positions"]
    assert Decimal(str(row[6])) == HOUSE_POLICY_DEFAULTS["min_within_state_rank"]
    assert Decimal(str(row[7])) == HOUSE_POLICY_DEFAULTS["min_rs_rank"]
    assert Decimal(str(row[8])) == HOUSE_POLICY_DEFAULTS["hard_stop_pct"]
    assert row[9] == HOUSE_POLICY_DEFAULTS["instrument_universe"]
    assert row[10] == HOUSE_POLICY_DEFAULTS["rebalance_cadence"]
    assert row[11] == HOUSE_POLICY_DEFAULTS["benchmark"]
    assert row[12] == HOUSE_POLICY_DEFAULTS["state_exit_trim"]
    assert row[13] == HOUSE_POLICY_DEFAULTS["state_exit_full"]
    assert row[14] == HOUSE_POLICY_DEFAULTS["buy_states"]
    assert row[15] == HOUSE_POLICY_DEFAULTS["respect_regime_cap"]
    assert row[16] is None  # trailing_stop_pct is NULL by default
