"""Factor loader — joins state tables and computes the decision_state composite.

Reads:
  atlas.atlas_stock_states_daily   (rs/momentum/risk/volume per stock per date)
  atlas.atlas_sector_states_daily  (sector_state per sector per date)
  atlas.atlas_market_regime_daily  (regime_state per date)

Schema notes (verified 2026-05-12):
- atlas_stock_states_daily has a 'sector' column that joins directly to
  atlas_sector_states_daily.sector_name — no atlas_universe_stocks join needed.
- atlas_universe_stocks has a 'sector' column (not 'sector_name') but the
  direct join via atlas_stock_states_daily.sector is cleaner and sufficient.

Output: DataFrame indexed by (date, instrument_id) with single column 'factor'.
Sentinel rows are dropped.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.encoding import compute_decision_state_score

log = structlog.get_logger()

# Base SQL — joins stock states to sector states (via stock's sector column)
# and market regime. No atlas_universe_stocks join needed as atlas_stock_states_daily
# already carries the sector label.
_LOAD_SQL = """
    SELECT
        s.date,
        s.instrument_id,
        s.rs_state,
        s.momentum_state,
        s.risk_state,
        s.volume_state,
        COALESCE(sec.sector_state, 'Neutral') AS sector_state,
        COALESCE(reg.regime_state, 'Constructive') AS regime_state
    FROM atlas.atlas_stock_states_daily s
    LEFT JOIN atlas.atlas_sector_states_daily sec
           ON sec.sector_name = s.sector
          AND sec.date = s.date
    LEFT JOIN atlas.atlas_market_regime_daily reg
           ON reg.date = s.date
    WHERE s.date >= :start_date
      AND s.date <= :end_date
"""

_LOAD_SQL_WITH_UNIVERSE = _LOAD_SQL + "\n      AND s.instrument_id = ANY(CAST(:universe AS uuid[]))"


def load_decision_state_factor(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    universe_filter: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Load (date, instrument_id) → decision_state_score factor DataFrame.

    Drops rows where any dimension is a sentinel state. Returns empty
    DataFrame with correct MultiIndex if no rows match.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the Atlas Supabase instance.
    start_date / end_date:
        Inclusive date range for atlas_stock_states_daily.
    universe_filter:
        Optional list of instrument_id strings (UUIDs). When provided,
        only these instruments are included. Pass a dummy non-existent ID
        to get an empty result (used in tests).
    """
    if universe_filter is not None:
        sql = _LOAD_SQL_WITH_UNIVERSE
        params: dict[str, object] = {
            "start_date": start_date,
            "end_date": end_date,
            "universe": list(universe_filter),
        }
    else:
        sql = _LOAD_SQL
        params = {"start_date": start_date, "end_date": end_date}

    with engine.connect() as conn:
        raw = pd.read_sql(text(sql), conn, params=params)

    if raw.empty:
        empty_idx = pd.MultiIndex.from_arrays([[], []], names=["date", "instrument_id"])
        return pd.DataFrame({"factor": pd.Series(dtype=float)}, index=empty_idx)

    # Compute the composite score. Sentinel dimensions → None → row dropped.
    raw["factor"] = raw.apply(compute_decision_state_score, axis=1)
    n_before = len(raw)
    cleaned = raw.dropna(subset=["factor"]).copy()
    n_after = len(cleaned)
    log.info(
        "decision_state_factor_loaded",
        n_raw=n_before,
        n_after_sentinel_drop=n_after,
        date_range=f"{start_date}..{end_date}",
        universe_filter_applied=universe_filter is not None,
    )

    cleaned = cleaned[["date", "instrument_id", "factor"]]
    cleaned["date"] = pd.to_datetime(cleaned["date"])
    return cleaned.set_index(["date", "instrument_id"])
