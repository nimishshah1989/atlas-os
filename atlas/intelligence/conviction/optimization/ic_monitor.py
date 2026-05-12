"""Compute rolling out-of-sample IC per (tier, signal) over a lookback
window, anchored on ``as_of_date``.

Reuses SP01 primitives:
- ``forward_returns.load_price_matrix`` for adjusted-close prices
- ``forward_returns.compute_forward_returns`` for forward-return matrix
- ``ic_engine.compute_ic_over_window`` for Spearman IC + t-stat

Per tier, for each signal in SIGNAL_COLUMNS:
1. Load tier members from atlas_tier_membership_daily on as_of_date.
2. Pull historical (date, instrument, signal_value) for the lookback.
3. Pull forward-return matrix and trim to those instruments.
4. Compute IC + t-stat.

Output rows go into atlas_signal_ic_rolling (one row per
(as_of_date, tier, signal, lookback_window, forward_horizon)).

Skip-not-crash: if a tier has < 5 instruments or a signal has < 20 valid
observations, return ``None`` for that combination — the persistence
layer skips ``None`` rows so we never insert garbage IC values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.composer import SIGNAL_COLUMNS
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import compute_ic_over_window

log = structlog.get_logger()

DEFAULT_LOOKBACK_DAYS: Final[int] = 90
DEFAULT_FORWARD_HORIZON: Final[int] = 21
MIN_OBSERVATIONS: Final[int] = 20


@dataclass(frozen=True)
class ICMeasurement:
    """One (tier, signal, window) IC measurement."""

    as_of_date: date
    tier: str
    signal_name: str
    lookback_window: int
    forward_horizon: int
    n_observations: int
    ic: float
    t_stat: float | None


def _load_tier_members_history(
    engine: Engine,
    *,
    tier: str,
    start_date: date,
    end_date: date,
) -> set[str]:
    """Return the union of instrument_ids that appeared in ``tier`` between
    ``start_date`` and ``end_date``.

    This is intentionally wide: we want to include instruments that were
    in the tier at any point during the lookback, not just on as_of_date,
    so that IC measurement reflects the tier as it was lived.
    """
    sql = text("""
        SELECT DISTINCT instrument_id::text AS instrument_id
        FROM atlas.atlas_tier_membership_daily
        WHERE tier = :tier
          AND date BETWEEN :start_date AND :end_date
    """)
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"tier": tier, "start_date": start_date, "end_date": end_date},
        ).fetchall()
    return {r[0] for r in rows}


def _load_signal_history(
    engine: Engine,
    *,
    signal_name: str,
    instrument_ids: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load (date, instrument_id) → signal_value as a MultiIndex factor frame.

    Returns DataFrame indexed by (date, instrument_id) with a single
    column 'factor'. ``signal_name`` is taken from the SIGNAL_COLUMNS
    whitelist so it is safe to interpolate.
    """
    if signal_name not in SIGNAL_COLUMNS:
        raise ValueError(f"signal_name {signal_name!r} not in SIGNAL_COLUMNS whitelist")
    # signal_name is verified against the SIGNAL_COLUMNS module-constant
    # whitelist above, so the f-string substitution is injection-safe.
    sql_text = f"""
        SELECT date, instrument_id::text AS instrument_id, {signal_name} AS factor
        FROM atlas.atlas_stock_metrics_daily
        WHERE date BETWEEN :start_date AND :end_date
          AND instrument_id = ANY(CAST(:iids AS uuid[]))
          AND {signal_name} IS NOT NULL
    """  # noqa: S608
    sql = text(sql_text)
    with engine.connect() as conn:
        df = pd.read_sql(
            sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "iids": instrument_ids,
            },
        )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["factor"] = pd.to_numeric(df["factor"], errors="coerce")
    df = df.dropna(subset=["factor"])
    result: pd.DataFrame = df.set_index(["date", "instrument_id"]).loc[:, ["factor"]]
    return result


def measure_ic_for_signal(
    engine: Engine,
    *,
    as_of: date,
    tier: str,
    signal_name: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> ICMeasurement | None:
    """Compute IC for one (tier, signal) pair anchored on ``as_of``.

    Returns ``None`` if there's insufficient data to compute IC reliably
    (n_observations < MIN_OBSERVATIONS). The CLI / persistence layer
    treats ``None`` as a skip. Raises ``ValueError`` if ``signal_name``
    is not in the SIGNAL_COLUMNS whitelist (fast fail on caller bugs).
    """
    if signal_name not in SIGNAL_COLUMNS:
        raise ValueError(f"signal_name {signal_name!r} not in SIGNAL_COLUMNS whitelist")
    # Lookback window for prices needs forward_horizon extra days to compute
    # the last forward return; we pull start = lookback + forward.
    lookback_start = as_of - timedelta(days=lookback_days + forward_horizon + 7)
    price_end = as_of + timedelta(days=forward_horizon + 7)

    members = _load_tier_members_history(
        engine, tier=tier, start_date=lookback_start, end_date=as_of
    )
    if not members:
        log.warning("ic_monitor_no_members", tier=tier, as_of=str(as_of))
        return None

    instrument_ids = sorted(members)
    factor = _load_signal_history(
        engine,
        signal_name=signal_name,
        instrument_ids=instrument_ids,
        start_date=lookback_start,
        end_date=as_of,
    )
    if factor.empty:
        return None

    prices = load_price_matrix(engine, start_date=lookback_start, end_date=price_end)
    if prices.empty:
        return None
    # Restrict to tier members
    cols = [c for c in prices.columns if c in members]
    if not cols:
        return None
    prices = prices[cols]

    fwd_returns_multi = compute_forward_returns(prices, periods=[forward_horizon])
    fwd_returns_wide = fwd_returns_multi[f"return_{forward_horizon}d"]

    result = compute_ic_over_window(factor, fwd_returns_wide)
    if result.n_observations < MIN_OBSERVATIONS or pd.isna(result.mean_ic):
        return None

    return ICMeasurement(
        as_of_date=as_of,
        tier=tier,
        signal_name=signal_name,
        lookback_window=lookback_days,
        forward_horizon=forward_horizon,
        n_observations=int(result.n_observations),
        ic=float(result.mean_ic),
        t_stat=None if pd.isna(result.ic_t_stat) else float(result.ic_t_stat),
    )


_TIERS: Final[tuple[str, ...]] = (
    "tier_1_megacap",
    "tier_2_largecap",
    "tier_3_uppermid",
    "tier_4_lowermid",
    "tier_5_smallcap",
)


def measure_all_tiers(
    engine: Engine,
    *,
    as_of: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> list[ICMeasurement]:
    """Run IC measurement for every (tier, signal) combination on ``as_of``.

    Returns a flat list; callers persist this via ``persistence.upsert_ic_batch``.
    """
    out: list[ICMeasurement] = []
    for tier in _TIERS:
        for signal in SIGNAL_COLUMNS:
            m = measure_ic_for_signal(
                engine,
                as_of=as_of,
                tier=tier,
                signal_name=signal,
                lookback_days=lookback_days,
                forward_horizon=forward_horizon,
            )
            if m is not None:
                out.append(m)
    log.info(
        "ic_monitor_complete",
        as_of=str(as_of),
        n_measurements=len(out),
        n_combinations=len(_TIERS) * len(SIGNAL_COLUMNS),
    )
    return out
