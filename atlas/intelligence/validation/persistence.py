"""Persist IC results to atlas.atlas_signal_ic.

UPSERT semantics on the natural key
(signal_name, timeframe, forward_period_days, rolling_window, as_of_date)
— re-running a window overwrites the prior row.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.ic_engine import ICResult

log = structlog.get_logger()

_UPSERT_SQL = """
    INSERT INTO atlas.atlas_signal_ic (
        signal_name, timeframe, forward_period_days, rolling_window,
        as_of_date, n_observations, mean_ic, ic_std, ic_t_stat, ic_ir,
        quantile_spread_ann, turnover_monthly
    ) VALUES (
        :signal_name, :timeframe, :forward_period_days, :rolling_window,
        :as_of_date, :n_observations, :mean_ic, :ic_std, :ic_t_stat, :ic_ir,
        :quantile_spread_ann, :turnover_monthly
    )
    ON CONFLICT (signal_name, timeframe, forward_period_days,
                 rolling_window, as_of_date)
    DO UPDATE SET
        n_observations       = EXCLUDED.n_observations,
        mean_ic              = EXCLUDED.mean_ic,
        ic_std               = EXCLUDED.ic_std,
        ic_t_stat            = EXCLUDED.ic_t_stat,
        ic_ir                = EXCLUDED.ic_ir,
        quantile_spread_ann  = EXCLUDED.quantile_spread_ann,
        turnover_monthly     = EXCLUDED.turnover_monthly,
        updated_at           = NOW()
"""


def _nan_to_none(x: float | None) -> float | None:
    """Convert NaN (Python float, numpy NaN) or None to None for safe DB storage."""
    if x is None:
        return None
    try:
        if x != x:  # NaN check — NaN is the only value not equal to itself
            return None
    except TypeError:
        return None
    return x


def persist_ic_result(
    engine: Engine,
    *,
    signal_name: str,
    timeframe: str,
    forward_period_days: int,
    rolling_window: str,
    as_of: date,
    result: ICResult,
    quantile_spread_ann: float,
    turnover_monthly: float,
) -> None:
    """UPSERT one IC result row into atlas.atlas_signal_ic."""
    ic_ir = result.mean_ic / result.ic_std if result.ic_std and result.ic_std > 0 else None
    params = {
        "signal_name": signal_name,
        "timeframe": timeframe,
        "forward_period_days": forward_period_days,
        "rolling_window": rolling_window,
        "as_of_date": as_of,
        "n_observations": result.n_observations,
        "mean_ic": _nan_to_none(result.mean_ic),
        "ic_std": _nan_to_none(result.ic_std),
        "ic_t_stat": _nan_to_none(result.ic_t_stat),
        "ic_ir": _nan_to_none(ic_ir),
        "quantile_spread_ann": _nan_to_none(quantile_spread_ann),
        "turnover_monthly": _nan_to_none(turnover_monthly),
    }
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), params)
    log.info(
        "signal_ic_persisted",
        signal=signal_name,
        period_days=forward_period_days,
        as_of=as_of.isoformat(),
        mean_ic=result.mean_ic,
    )


def delete_run(engine: Engine, *, signal_name: str) -> int:
    """Delete all rows for a signal_name. Returns row count deleted."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM atlas.atlas_signal_ic WHERE signal_name = :s"),
            {"s": signal_name},
        )
        return int(result.rowcount or 0)
