"""Seed the single house-default row in atlas.atlas_portfolio_policy.

Percentage storage convention
------------------------------
- pct columns (cash_floor_pct, max_per_stock_pct, max_per_sector_pct,
  max_small_cap_pct, hard_stop_pct) store **whole-number percent**:
    5   means  5%
   15   means 15%
    8   means  8%  (hard_stop: exit if position is down 8% from entry)
- rank columns (min_within_state_rank, min_rs_rank) store **fractions in
  [0, 1]** because they represent quantile ranks, not percentages:
    0.60  means the 60th percentile rank
    0.70  means the 70th percentile rank

This is internally consistent and matches how fund-manager tooling presents
risk parameters (whole-percent) vs statistical rank thresholds (0-1 fractions).

Idempotency
-----------
INSERT ... ON CONFLICT DO NOTHING, keyed on the partial unique index
uix_portfolio_policy_house_default (is_house_default WHERE is_house_default).
Running the script a second time is a no-op; the script prints which path it took.

EC2 execution
-------------
This script requires a live DB connection. Run on EC2 after migration 092 is
applied:
    python scripts/seed_house_policy.py
"""

from __future__ import annotations

import sys
from decimal import Decimal

import structlog
from sqlalchemy import text

from atlas.db import get_engine

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# House-default policy definition
# ---------------------------------------------------------------------------

HOUSE_POLICY_DEFAULTS: dict[str, object] = {
    # Identity
    "portfolio_id": None,
    "is_house_default": True,
    # Deployment — whole-number percent (5 = 5%)
    "cash_floor_pct": Decimal("5"),
    "respect_regime_cap": True,
    # Concentration — whole-number percent
    "max_per_stock_pct": Decimal("5"),
    "max_per_sector_pct": Decimal("15"),
    "max_small_cap_pct": Decimal("30"),
    "min_holdings": 15,
    "max_positions": 40,
    # Entry — buy_states as list; ranks as fractions in [0, 1]
    "buy_states": ["stage_2a", "stage_2b"],
    "min_within_state_rank": Decimal("0.60"),
    "min_rs_rank": Decimal("0.70"),
    # Exit — hard_stop as whole-number percent magnitude (8 = 8%)
    # Semantics: exit position if it is down 8% from entry price
    "hard_stop_pct": Decimal("8"),
    "state_exit_trim": "stage_3",
    "state_exit_full": "stage_4",
    "trailing_stop_pct": None,  # off by default
    # Instrument
    "instrument_universe": "direct_equity",
    # Benchmark
    "benchmark": "Nifty 500",
    # Cadence
    "rebalance_cadence": "weekly",
}

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

INSERT_SQL = """
    INSERT INTO atlas.atlas_portfolio_policy (
        portfolio_id,
        is_house_default,
        cash_floor_pct,
        respect_regime_cap,
        max_per_stock_pct,
        max_per_sector_pct,
        max_small_cap_pct,
        min_holdings,
        max_positions,
        buy_states,
        min_within_state_rank,
        min_rs_rank,
        hard_stop_pct,
        state_exit_trim,
        state_exit_full,
        trailing_stop_pct,
        instrument_universe,
        benchmark,
        rebalance_cadence
    ) VALUES (
        :portfolio_id,
        :is_house_default,
        :cash_floor_pct,
        :respect_regime_cap,
        :max_per_stock_pct,
        :max_per_sector_pct,
        :max_small_cap_pct,
        :min_holdings,
        :max_positions,
        :buy_states,
        :min_within_state_rank,
        :min_rs_rank,
        :hard_stop_pct,
        :state_exit_trim,
        :state_exit_full,
        :trailing_stop_pct,
        :instrument_universe,
        :benchmark,
        :rebalance_cadence
    )
    ON CONFLICT DO NOTHING
"""

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Insert the house-default policy row if it does not already exist.

    Returns 0 on success, 1 on error.
    """
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(INSERT_SQL), HOUSE_POLICY_DEFAULTS)

    if result.rowcount > 0:
        log.info("seed_house_policy_inserted")
        print("Inserted 1 new house-default row into atlas.atlas_portfolio_policy.")
    else:
        log.info("seed_house_policy_skipped", reason="already_exists")
        print("House-default row already exists — no changes made.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
