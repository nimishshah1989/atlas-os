"""M14 decision-policy loader. Reads atlas.atlas_decision_policy at compute time
with hardcoded fallbacks for safety.

Pipeline never breaks. If a policy row is missing, malformed, or the JSON parse
fails, we log a structured warning and use the code-level default. This is the
explicit safety contract: FM tuning takes effect when present, methodology
defaults remain authoritative when not.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Code defaults — methodology baseline. M14 DB rows OVERRIDE these when present.
# ---------------------------------------------------------------------------

DEFAULT_GATE_POLICIES: dict[str, frozenset[str]] = {
    # Stock gates (decisions_stock.py)
    "strength_gate_stock": frozenset({"Leader", "Strong", "Emerging"}),
    "direction_gate_stock": frozenset({"Accelerating", "Improving"}),
    "risk_gate_stock": frozenset({"Low", "Normal"}),
    "volume_gate_stock": frozenset({"Accumulation", "Steady-Buying"}),
    "sector_gate_stock": frozenset({"Overweight", "Neutral"}),
    "market_gate": frozenset({"Risk-On", "Constructive", "Cautious"}),
    # ETF gates (decisions_etf.py) — same keys as stock for now; ETF UI v0 read-only
    "strength_gate_etf": frozenset({"Leader", "Strong", "Consolidating", "Emerging"}),
    "direction_gate_etf": frozenset({"Accelerating", "Improving"}),
    # Fund states (decisions_fund.py)
    "nav_strong_states_fund": frozenset({"Leader NAV", "Strong NAV"}),
    "nav_positive_states_fund": frozenset(
        {"Leader NAV", "Strong NAV", "Average NAV", "Emerging NAV"}
    ),
}

DEFAULT_MULTIPLIERS: dict[str, dict[str, Decimal]] = {
    "risk_multipliers_stock": {
        "Low": Decimal("1.2"),
        "Normal": Decimal("1.0"),
        "Elevated": Decimal("0.6"),
        "High": Decimal("0.0"),
        "Below Trend": Decimal("0.0"),
    },
    "market_multipliers": {
        "Risk-On": Decimal("1.0"),
        "Constructive": Decimal("0.7"),
        "Cautious": Decimal("0.4"),
        "Risk-Off": Decimal("0.0"),
    },
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_gate_policy(policy_key: str, engine: Engine) -> frozenset[str]:
    """Load a gate policy from the DB. Falls back to code default on miss/error."""
    default = DEFAULT_GATE_POLICIES.get(policy_key)
    if default is None:
        # Unknown key — caller bug. Return empty frozenset and log error.
        log.error("unknown_gate_policy_key", policy_key=policy_key)
        return frozenset()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT policy_value
                    FROM atlas.atlas_decision_policy
                    WHERE policy_key = :key
                      AND policy_kind = 'gate_states'
                      AND is_active = TRUE
                """),
                {"key": policy_key},
            ).fetchone()
        if row is None:
            log.warning("policy_fallback_used", policy_key=policy_key, reason="row_missing")
            return default
        # postgres returns JSONB as Python list/dict already
        value = row[0]
        if not isinstance(value, list):
            log.warning(
                "policy_fallback_used",
                policy_key=policy_key,
                reason="not_a_list",
                got_type=type(value).__name__,
            )
            return default
        return frozenset(str(s) for s in value)
    except Exception as exc:
        log.warning(
            "policy_fallback_used",
            policy_key=policy_key,
            reason="db_error",
            exc_type=type(exc).__name__,
            exc=str(exc)[:200],
        )
        return default


def load_multiplier_map(policy_key: str, engine: Engine) -> dict[str, Decimal]:
    """Load a multiplier dict from the DB. Falls back to code default on miss/error."""
    default = DEFAULT_MULTIPLIERS.get(policy_key)
    if default is None:
        log.error("unknown_multiplier_policy_key", policy_key=policy_key)
        return {}
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT policy_value
                    FROM atlas.atlas_decision_policy
                    WHERE policy_key = :key
                      AND policy_kind = 'multiplier_map'
                      AND is_active = TRUE
                """),
                {"key": policy_key},
            ).fetchone()
        if row is None:
            log.warning("policy_fallback_used", policy_key=policy_key, reason="row_missing")
            return dict(default)
        value = row[0]
        if not isinstance(value, dict):
            log.warning(
                "policy_fallback_used",
                policy_key=policy_key,
                reason="not_a_dict",
                got_type=type(value).__name__,
            )
            return dict(default)
        # Coerce numeric values to Decimal — JSON gives us float
        return {str(k): Decimal(str(v)) for k, v in value.items()}
    except Exception as exc:
        log.warning(
            "policy_fallback_used",
            policy_key=policy_key,
            reason="db_error",
            exc_type=type(exc).__name__,
            exc=str(exc)[:200],
        )
        return dict(default)
