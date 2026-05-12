"""Compute realized IC of currently-active composite weight sets.

For each active ``weight_set_version``, the tracker:
1. Loads the weights for that version (signal_name, weight, flipped).
2. Loads tier members on ``as_of_date``.
3. Builds the composite signal per (instrument, date) over the lookback
   window using the same percentile-rank-then-weight method as the
   Stage 3 composer.
4. Computes 21-day forward returns over the same window.
5. Calls SP01 ``compute_ic_over_window`` on the composite factor.

The output is one ``LiveICMeasurement`` per active version per night.
``ic_ratio = realized_ic / predicted_ic`` is the surface the drift
detector scans.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.composer import SIGNAL_COLUMNS
from atlas.intelligence.conviction.optimization.ic_monitor import (
    _load_signal_history,
)
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
class LiveICMeasurement:
    """Realized IC of one active composite weight set on one date."""

    weight_set_version: str
    as_of_date: date
    tier: str
    regime: str
    predicted_holdout_ic: float | None
    realized_ic: float
    ic_ratio: float | None
    n_observations: int


def _load_active_weight_sets(engine: Engine, regime: str = "all") -> list[dict[str, Any]]:
    """Return one dict per active (tier, regime) version with its weight rows."""
    sql = text("""
        SELECT tier, regime, signal_name, weight, flipped, holdout_ic, approved_at
        FROM atlas.atlas_signal_weights
        WHERE effective_to IS NULL AND regime = :regime
        ORDER BY tier, weight DESC
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"regime": regime}).fetchall()
    by_version: dict[str, dict[str, Any]] = {}
    for r in rows:
        tier = r[0]
        version = f"{tier}@{r[6].isoformat()}"
        entry = by_version.setdefault(
            version,
            {
                "version": version,
                "tier": tier,
                "regime": r[1],
                "predicted_ic": Decimal(str(r[5])) if r[5] is not None else None,
                "signals": [],
            },
        )
        sig_list: list[tuple[str, Decimal, bool]] = entry["signals"]
        sig_list.append((r[2], Decimal(str(r[3])), bool(r[4])))
    return list(by_version.values())


def measure_live_composite_ic(
    engine: Engine,
    *,
    weight_set: dict[str, Any],
    as_of: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> LiveICMeasurement | None:
    """Compute the realized IC of one composite over its most recent window."""
    tier = str(weight_set["tier"])
    version = str(weight_set["version"])
    regime = str(weight_set["regime"])
    signals: list[tuple[str, Decimal, bool]] = weight_set["signals"]
    predicted_ic = weight_set["predicted_ic"]

    lookback_start = as_of - timedelta(days=lookback_days + forward_horizon + 7)
    price_end = as_of + timedelta(days=forward_horizon + 7)

    # Tier members across the window — same approach as Stage 4a IC monitor.
    with engine.connect() as conn:
        member_rows = conn.execute(
            text("""
                SELECT DISTINCT instrument_id::text AS instrument_id
                FROM atlas.atlas_tier_membership_daily
                WHERE tier = :tier AND date BETWEEN :start AND :end
            """),
            {"tier": tier, "start": lookback_start, "end": as_of},
        ).fetchall()
    members = {r[0] for r in member_rows}
    if len(members) < 5:
        log.warning("live_ic_no_members", tier=tier, as_of=str(as_of))
        return None
    member_list = sorted(members)

    # Build the composite factor per (date, instrument) using the same
    # weighted-percentile method as the Stage 3 composer, applied per date.
    raw_factor_frames: list[pd.DataFrame] = []
    for signal_name, w, flipped in signals:
        if signal_name not in SIGNAL_COLUMNS:
            continue
        history = _load_signal_history(
            engine,
            signal_name=signal_name,
            instrument_ids=member_list,
            start_date=lookback_start,
            end_date=as_of,
        )
        if history.empty:
            continue
        # Per-date percentile rank across instruments in scope.
        ranks = history["factor"].groupby(level="date", group_keys=False).rank(pct=True)
        if flipped:
            ranks = 1.0 - ranks
        weighted = ranks * float(w)
        df = weighted.to_frame(name=f"contrib_{signal_name}")
        raw_factor_frames.append(df)

    if not raw_factor_frames:
        return None

    contrib = pd.concat(raw_factor_frames, axis=1).fillna(0.0)
    composite = contrib.sum(axis=1).to_frame(name="factor")

    prices = load_price_matrix(engine, start_date=lookback_start, end_date=price_end)
    if prices.empty:
        return None
    cols = [c for c in prices.columns if c in members]
    if not cols:
        return None
    prices = prices[cols]
    fwd_multi = compute_forward_returns(prices, periods=[forward_horizon])
    fwd_wide = fwd_multi[f"return_{forward_horizon}d"]

    result = compute_ic_over_window(composite, fwd_wide)
    if result.n_observations < MIN_OBSERVATIONS or pd.isna(result.mean_ic):
        return None

    realized = float(result.mean_ic)
    predicted: float | None = None
    if isinstance(predicted_ic, Decimal | int | float):
        predicted = float(predicted_ic)
    ratio: float | None = None
    if predicted is not None and predicted != 0:
        ratio = realized / predicted

    return LiveICMeasurement(
        weight_set_version=version,
        as_of_date=as_of,
        tier=tier,
        regime=regime,
        predicted_holdout_ic=predicted,
        realized_ic=realized,
        ic_ratio=ratio,
        n_observations=int(result.n_observations),
    )


def measure_all_active_versions(
    engine: Engine, *, as_of: date, regime: str = "all"
) -> list[LiveICMeasurement]:
    """Run live-IC measurement for every active weight set on ``as_of``."""
    sets = _load_active_weight_sets(engine, regime=regime)
    out: list[LiveICMeasurement] = []
    for ws in sets:
        m = measure_live_composite_ic(engine, weight_set=ws, as_of=as_of)
        if m is not None:
            out.append(m)
    log.info(
        "live_ic_complete",
        as_of=str(as_of),
        n_measurements=len(out),
        n_sets=len(sets),
    )
    return out
