# allow-large: single-responsibility module; LOC is docstrings + SQL constants + 3 public functions
"""Effective-policy resolution and validation for atlas.intelligence.policy.

Storage convention (mirrors scripts/seed_house_policy.py):
- pct columns  (cash_floor_pct, max_per_stock_pct, max_per_sector_pct,
  max_small_cap_pct, hard_stop_pct, trailing_stop_pct): whole-number percent
  stored as Decimal  (5 means 5%, 15 means 15%)
- rank columns (min_within_state_rank, min_rs_rank): fraction in [0, 1]
  stored as Decimal  (0.60 means 60th-percentile rank)

Decimal end-to-end: all numeric fields are Decimal.  Never float.

Nullable-inherit ambiguity note
---------------------------------
``trailing_stop_pct`` is legitimately NULL in the house default (None means
"no trailing stop is active").  A portfolio override row with
``trailing_stop_pct = NULL`` is therefore indistinguishable from
"portfolio did not override this field".  This module treats None in the
override dict as "inherit from house default" — the same semantics for
every field.  Known limitation: a portfolio cannot explicitly override
trailing_stop_pct back to None if the house default ever becomes non-None.
For this task that is acceptable; the house default is None, so the practical
impact is zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Allowed-value sets — mirror CHECK constraints in migration 092
# ---------------------------------------------------------------------------

_ALLOWED_UNIVERSES: frozenset[str] = frozenset({"direct_equity", "etf", "mutual_fund", "mixed"})
_ALLOWED_CADENCES: frozenset[str] = frozenset({"daily", "weekly", "monthly"})

# ---------------------------------------------------------------------------
# Policy dataclass
# ---------------------------------------------------------------------------


# All 17 policy fields from migration 092; row-metadata columns excluded.
@dataclass(frozen=True)
class Policy:
    """Effective trade-philosophy configuration for a portfolio.

    Fields correspond 1-to-1 with the meaningful columns of
    ``atlas.atlas_portfolio_policy`` (row metadata excluded).
    """

    # Deployment
    cash_floor_pct: Decimal
    respect_regime_cap: bool
    # Concentration
    max_per_stock_pct: Decimal
    max_per_sector_pct: Decimal
    max_small_cap_pct: Decimal
    min_holdings: int
    max_positions: int
    # Entry
    buy_states: list[str]
    min_within_state_rank: Decimal
    min_rs_rank: Decimal
    # Exit
    hard_stop_pct: Decimal
    state_exit_trim: str
    state_exit_full: str
    trailing_stop_pct: Decimal | None  # None = no trailing stop
    # Instrument
    instrument_universe: str
    # Benchmark
    benchmark: str
    # Cadence
    rebalance_cadence: str


# ---------------------------------------------------------------------------
# Pure merge function
# ---------------------------------------------------------------------------


def _merge(
    house: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge a portfolio's override dict onto the house-default dict.

    Rules:
    - For each field, use the override value if it is non-None.
    - If the override value is None (or the key is absent), fall back to the
      house-default value.

    Note on trailing_stop_pct: this field is legitimately nullable in the
    house default (None = no trailing stop).  An override of None is treated
    as "inherit" rather than "override to None" — see module docstring for the
    known limitation this introduces.

    Args:
        house: House-default field dict.  All policy fields must be present
               and non-None (except trailing_stop_pct which may be None).
        overrides: Portfolio-row field dict.  Only fields that differ from the
                   house default need to be present; absent or None values
                   trigger inheritance.

    Returns:
        Merged dict suitable for ``Policy(**merged)``.
    """
    result: dict[str, Any] = {}
    for field in _POLICY_FIELDS:
        override_val = overrides.get(field)
        if override_val is not None:
            result[field] = override_val
        else:
            result[field] = house[field]
    return result


# Field list — single source of truth, used by _merge and _row_to_fields
_POLICY_FIELDS: tuple[str, ...] = (
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
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_SELECT_HOUSE = text(
    "SELECT "
    "  cash_floor_pct, respect_regime_cap, "
    "  max_per_stock_pct, max_per_sector_pct, max_small_cap_pct, "
    "  min_holdings, max_positions, "
    "  buy_states, min_within_state_rank, min_rs_rank, "
    "  hard_stop_pct, state_exit_trim, state_exit_full, trailing_stop_pct, "
    "  instrument_universe, benchmark, rebalance_cadence "
    "FROM atlas.atlas_portfolio_policy "
    "WHERE is_house_default = TRUE "
    "LIMIT 1"
)

_SELECT_PORTFOLIO = text(
    "SELECT "
    "  cash_floor_pct, respect_regime_cap, "
    "  max_per_stock_pct, max_per_sector_pct, max_small_cap_pct, "
    "  min_holdings, max_positions, "
    "  buy_states, min_within_state_rank, min_rs_rank, "
    "  hard_stop_pct, state_exit_trim, state_exit_full, trailing_stop_pct, "
    "  instrument_universe, benchmark, rebalance_cadence "
    "FROM atlas.atlas_portfolio_policy "
    "WHERE portfolio_id = :pid "
    "LIMIT 1"
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy Row to a plain dict keyed by policy field names."""
    return dict(zip(_POLICY_FIELDS, row, strict=True))


# ---------------------------------------------------------------------------
# effective_policy — thin DB wrapper around the pure _merge
# ---------------------------------------------------------------------------


def effective_policy(
    portfolio_id: str | None,
    engine: Engine | None = None,
) -> Policy:
    """Return the effective Policy for a portfolio.

    Loads the house-default row and (if portfolio_id given) the portfolio's
    override row from ``atlas.atlas_portfolio_policy``, then delegates to the
    pure ``_merge`` function.

    A portfolio with no row in the table returns the pure house default.

    The merge step is a separately-testable pure function (``_merge``); it
    requires no DB and is tested directly in ``tests/intelligence/policy/``.

    Args:
        portfolio_id: UUID string of the portfolio, or None for house default.
        engine: Optional engine override; defaults to the process-wide engine.

    Returns:
        Merged ``Policy`` dataclass (frozen).

    Raises:
        RuntimeError: If no house-default row exists in the table.
    """
    eng = engine or get_engine()

    with eng.connect() as conn:
        house_row = conn.execute(_SELECT_HOUSE).fetchone()
        if house_row is None:
            raise RuntimeError(
                "No house-default row found in atlas.atlas_portfolio_policy. "
                "Run scripts/seed_house_policy.py to seed it."
            )
        house = _row_to_dict(house_row)

        overrides: dict[str, Any] = {}
        if portfolio_id is not None:
            port_row = conn.execute(
                _SELECT_PORTFOLIO,
                {"pid": portfolio_id},
            ).fetchone()
            if port_row is not None:
                overrides = _row_to_dict(port_row)
            else:
                log.info(
                    "policy_no_override_row",
                    portfolio_id=portfolio_id,
                    action="using_house_default",
                )

    merged = _merge(house=house, overrides=overrides)
    log.info(
        "effective_policy_resolved",
        portfolio_id=portfolio_id,
        rebalance_cadence=merged["rebalance_cadence"],
        instrument_universe=merged["instrument_universe"],
    )
    return Policy(**merged)


# ---------------------------------------------------------------------------
# validate_policy
# ---------------------------------------------------------------------------


def validate_policy(policy: Policy) -> list[str]:
    """Return a list of human-readable violation strings for a Policy.

    An empty list means the policy is internally consistent.

    Consistency rules checked:
    1. min_holdings must not exceed max_positions.
    2. max_per_stock_pct must not exceed max_per_sector_pct (a single stock
       cannot be allowed more weight than its whole sector cap).
    3. cash_floor_pct must be in [0, 100].
    4. min_within_state_rank must be in [0, 1] (it is a quantile rank).
    5. min_rs_rank must be in [0, 1] (it is a quantile rank).
    6. instrument_universe must be one of the four allowed values.
    7. rebalance_cadence must be one of the three allowed values.
    8. hard_stop_pct must be strictly positive (a zero or negative stop is
       degenerate — it would trigger immediately or never).
    9. trailing_stop_pct, if set, must be strictly positive (same reasoning as
       hard_stop_pct).
    """
    violations: list[str] = []

    # Rule 1: min_holdings <= max_positions
    if policy.min_holdings > policy.max_positions:
        violations.append(
            f"min_holdings {policy.min_holdings} exceeds max_positions "
            f"{policy.max_positions} — portfolio cannot be fully constructed"
        )

    # Rule 2: max_per_stock_pct <= max_per_sector_pct
    if policy.max_per_stock_pct > policy.max_per_sector_pct:
        violations.append(
            f"max_per_stock_pct {policy.max_per_stock_pct} exceeds "
            f"max_per_sector_pct {policy.max_per_sector_pct} — a single stock "
            "cannot be allowed more weight than its whole sector cap"
        )

    # Rule 3: cash_floor_pct in [0, 100]
    if not (Decimal("0") <= policy.cash_floor_pct <= Decimal("100")):
        violations.append(
            f"cash_floor_pct {policy.cash_floor_pct} is outside the valid " "range [0, 100]"
        )

    # Rule 4: min_within_state_rank in [0, 1]
    if not (Decimal("0") <= policy.min_within_state_rank <= Decimal("1")):
        violations.append(
            f"min_within_state_rank {policy.min_within_state_rank} is outside "
            "the valid range [0, 1] (must be a quantile fraction)"
        )

    # Rule 5: min_rs_rank in [0, 1]
    if not (Decimal("0") <= policy.min_rs_rank <= Decimal("1")):
        violations.append(
            f"min_rs_rank {policy.min_rs_rank} is outside the valid range [0, 1] "
            "(must be a quantile fraction)"
        )

    # Rule 6: instrument_universe in allowed set
    if policy.instrument_universe not in _ALLOWED_UNIVERSES:
        violations.append(
            f"instrument_universe '{policy.instrument_universe}' is not one of "
            f"{sorted(_ALLOWED_UNIVERSES)}"
        )

    # Rule 7: rebalance_cadence in allowed set
    if policy.rebalance_cadence not in _ALLOWED_CADENCES:
        violations.append(
            f"rebalance_cadence '{policy.rebalance_cadence}' is not one of "
            f"{sorted(_ALLOWED_CADENCES)}"
        )

    # Rule 8: hard_stop_pct > 0
    if policy.hard_stop_pct <= Decimal("0"):
        violations.append(
            f"hard_stop_pct {policy.hard_stop_pct} must be strictly positive — "
            "a zero or negative stop is degenerate"
        )

    # Rule 9: trailing_stop_pct, when set, must be > 0
    if policy.trailing_stop_pct is not None and policy.trailing_stop_pct <= Decimal("0"):
        violations.append(
            f"trailing_stop_pct {policy.trailing_stop_pct} must be strictly "
            "positive when set (use None to disable trailing stop)"
        )

    return violations
