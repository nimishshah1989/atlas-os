"""One-shot IC validation for legacy candidate signals.

Each entry in LEGACY_SIGNAL_CATALOG names a legacy signal we want to either
fold into the state engine (as a Tier 3 transition trigger) or cut entirely.
The harness runs the standard IC engine against forward returns, computes
status per the 4-class rule, and persists results to atlas_component_validation
with component_kind='legacy_candidate'.

Status rules (consistent with component_validator.py):
  IR  > 0.4 AND |spread| > 0.005 -> validated
  IR < -0.4 AND |spread| > 0.005 -> validated_inverse
  0.2 <= |IR| <= 0.4              -> weak
  |IR| < 0.2                      -> decorative

Schema notes:
  atlas_component_validation PK = (component_name, badge, horizon_days, as_of_date).
  Non-null columns threshold_range and implied_action use sentinels
  ('continuous' and 'investigate') for legacy candidates.
  component_kind column added by migration 090_legacy_validation_kind.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import (
    compute_ic_over_window,
    compute_quantile_spread,
)

# --------------------------------------------------------------------------- #
# Status classification                                                       #
# --------------------------------------------------------------------------- #


def classify_ic_status(ic_ir: float, q5_q1_spread: float) -> str:
    """Map (IR, q5_q1_spread) to 4-class status string.

    Matches state_validator.py / component_validator.py thresholds exactly.
    """
    if abs(q5_q1_spread) < 0.005:
        return "decorative"
    if ic_ir > 0.4:
        return "validated"
    if ic_ir < -0.4:
        return "validated_inverse"
    if abs(ic_ir) >= 0.2:
        return "weak"
    return "decorative"


# --------------------------------------------------------------------------- #
# Legacy signal loaders                                                       #
# --------------------------------------------------------------------------- #


def _load_cts_continuous(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    col: str,
) -> pd.DataFrame:
    """Load a CTS continuous score from atlas_cts_stock_signals.

    Returns empty DataFrame if the column or table doesn't exist / has no data.
    Factor is indexed by (date, instrument_id).
    """
    sql = text(
        f"""
        SELECT instrument_id::text AS instrument_id,
               signal_date         AS date,
               {col}::float8       AS factor
        FROM atlas.atlas_cts_stock_signals
        WHERE signal_date BETWEEN :s AND :e
          AND {col} IS NOT NULL
        """
    )
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"s": start, "e": end})

    if df.empty:
        empty: pd.DataFrame = pd.DataFrame(columns=["factor"])
        empty.index = pd.MultiIndex.from_tuples([], names=["date", "instrument_id"])
        return empty

    df["date"] = pd.to_datetime(df["date"])
    df["factor"] = df["factor"].astype(float)
    return df.set_index(["date", "instrument_id"])[["factor"]]


def _load_legacy_state_bool(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    col: str,
) -> pd.DataFrame:
    """Load a legacy boolean state column from atlas_stock_states_daily as 0/1.

    Returns empty DataFrame if the column doesn't exist or has no data.
    Factor is indexed by (date, instrument_id).
    """
    sql = text(
        f"""
        SELECT instrument_id::text AS instrument_id,
               date                AS date,
               CASE WHEN {col} THEN 1.0 ELSE 0.0 END AS factor
        FROM atlas.atlas_stock_states_daily
        WHERE date BETWEEN :s AND :e
          AND {col} IS NOT NULL
        """
    )
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"s": start, "e": end})

    if df.empty:
        empty: pd.DataFrame = pd.DataFrame(columns=["factor"])
        empty.index = pd.MultiIndex.from_tuples([], names=["date", "instrument_id"])
        return empty

    df["date"] = pd.to_datetime(df["date"])
    df["factor"] = df["factor"].astype(float)
    return df.set_index(["date", "instrument_id"])[["factor"]]


# --------------------------------------------------------------------------- #
# Signal catalog                                                              #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LegacySignal:
    """Descriptor for one legacy candidate signal."""

    name: str
    horizon_days: int
    loader: Callable[[Engine, dt.date, dt.date], pd.DataFrame]
    description: str


LEGACY_SIGNAL_CATALOG: list[LegacySignal] = [
    LegacySignal(
        name="cts_ppc_continuous",
        horizon_days=21,
        loader=lambda e, s, end: _load_cts_continuous(e, s, end, "ppc_score"),
        description="CTS PPC continuous score — phase1 pocket pivot. Tier collapse if decorative.",
    ),
    LegacySignal(
        name="cts_npc_continuous",
        horizon_days=21,
        loader=lambda e, s, end: _load_cts_continuous(e, s, end, "npc_score"),
        description="CTS NPC continuous score — non-pocket-pivot. Tier collapse if decorative.",
    ),
    LegacySignal(
        name="cts_contraction_continuous",
        horizon_days=21,
        loader=lambda e, s, end: _load_cts_continuous(e, s, end, "contraction_score"),
        description="CTS contraction continuous score. Tier collapse if decorative.",
    ),
    LegacySignal(
        name="transition_trigger",
        horizon_days=21,
        loader=lambda e, s, end: _load_legacy_state_bool(e, s, end, "transition_trigger"),
        description="Legacy transition trigger boolean (stage_1 -> stage_2 setup).",
    ),
    LegacySignal(
        name="breakout_trigger",
        horizon_days=21,
        loader=lambda e, s, end: _load_legacy_state_bool(e, s, end, "breakout_trigger"),
        description="Legacy breakout trigger boolean.",
    ),
    LegacySignal(
        name="nav_state",
        horizon_days=63,
        loader=lambda e, s, end: pd.DataFrame(),  # fund-level; deferred to fund harness
        description="Fund-internal NAV vs category state — deferred to fund-level harness.",
    ),
]


# --------------------------------------------------------------------------- #
# Run + persist                                                               #
# --------------------------------------------------------------------------- #


def run_legacy_ic_harness(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    signals: list[LegacySignal] | None = None,
) -> pd.DataFrame:
    """Run IC engine against each legacy candidate; return results DataFrame.

    Columns: name, horizon_days, mean_ic, ic_ir, q5_q1_spread,
             n_observations, status.
    nav_state rows have n_observations=0 and status='decorative' by design.
    """
    if signals is None:
        signals = LEGACY_SIGNAL_CATALOG

    prices = load_price_matrix(engine, start_date=start, end_date=end)
    fwd = compute_forward_returns(prices, periods=[21, 63]) if not prices.empty else pd.DataFrame()

    out_rows: list[dict[str, object]] = []
    for sig in signals:
        factor = sig.loader(engine, start, end)
        if factor.empty or fwd.empty:
            out_rows.append(
                {
                    "name": sig.name,
                    "horizon_days": sig.horizon_days,
                    "mean_ic": None,
                    "ic_ir": None,
                    "q5_q1_spread": None,
                    "n_observations": 0,
                    "status": "decorative",
                }
            )
            continue

        returns_wide = fwd[f"return_{sig.horizon_days}d"]
        ic = compute_ic_over_window(factor, returns_wide)
        ir = ic.mean_ic / ic.ic_std if ic.ic_std and ic.ic_std > 0 else 0.0
        spread = compute_quantile_spread(factor, returns_wide)

        out_rows.append(
            {
                "name": sig.name,
                "horizon_days": sig.horizon_days,
                "mean_ic": float(ic.mean_ic) if ic.n_observations > 0 else None,
                "ic_ir": float(ir),
                "q5_q1_spread": float(spread)
                if not (
                    spread != spread  # NaN check
                )
                else 0.0,
                "n_observations": int(ic.n_observations),
                "status": classify_ic_status(float(ir), float(spread) if spread == spread else 0.0),
            }
        )

    return pd.DataFrame(out_rows)


_UPSERT_SQL = text("""
    INSERT INTO atlas.atlas_component_validation (
        component_name, badge, threshold_range, implied_action,
        horizon_days, as_of_date,
        mean_ic, ic_std, ic_t_stat, ic_ir, q5_q1_spread,
        n_observations, status, component_kind
    ) VALUES (
        :name, 'Continuous', 'continuous', 'investigate',
        :horizon_days, :as_of_date,
        :mean_ic, NULL, NULL, :ic_ir, :q5_q1_spread,
        :n_observations, :status, 'legacy_candidate'
    )
    ON CONFLICT (component_name, badge, horizon_days, as_of_date) DO UPDATE SET
        mean_ic        = EXCLUDED.mean_ic,
        ic_ir          = EXCLUDED.ic_ir,
        q5_q1_spread   = EXCLUDED.q5_q1_spread,
        n_observations = EXCLUDED.n_observations,
        status         = EXCLUDED.status,
        component_kind = EXCLUDED.component_kind,
        validated_at   = NOW()
""")


def persist_legacy_ic_results(
    engine: Engine,
    df: pd.DataFrame,
    as_of_date: dt.date,
) -> int:
    """Persist harness results to atlas_component_validation.

    Uses component_kind='legacy_candidate' to distinguish from state-engine tiers.
    Conflict key: (component_name, badge, horizon_days, as_of_date).
    Returns number of rows upserted.
    """
    if df.empty:
        return 0
    records = [
        {
            "name": row["name"],
            "horizon_days": int(row["horizon_days"]),
            "mean_ic": float(row["mean_ic"]) if row["mean_ic"] is not None else None,
            "ic_ir": float(row["ic_ir"]) if row["ic_ir"] is not None else 0.0,
            "q5_q1_spread": (
                float(row["q5_q1_spread"]) if row["q5_q1_spread"] is not None else 0.0
            ),
            "n_observations": (
                int(row["n_observations"]) if row["n_observations"] is not None else 0
            ),
            "status": row["status"],
            "as_of_date": as_of_date,
        }
        for row in df.to_dict(orient="records")
    ]
    with engine.begin() as c:
        c.execute(_UPSERT_SQL, records)
    return len(records)
