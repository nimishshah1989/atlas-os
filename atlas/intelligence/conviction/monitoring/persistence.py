"""UPSERT helpers for the monitoring tables.

Three batch helpers, each idempotent on its natural key:
- ``upsert_live_perf_batch`` keyed on (weight_set_version, as_of_date)
- ``upsert_hit_rates_batch`` keyed on (instrument_id, date, lookback_window)
- ``write_revert_log`` is INSERT-only (audit trail)
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.monitoring.hit_rate_engine import HitRateRow
from atlas.intelligence.conviction.monitoring.live_ic_tracker import (
    LiveICMeasurement,
)

log = structlog.get_logger()


_UPSERT_LIVE_PERF_SQL = text("""
    INSERT INTO atlas.atlas_signal_weights_live_perf
        (weight_set_version, as_of_date, tier, regime,
         predicted_holdout_ic, realized_ic, ic_ratio, n_observations)
    VALUES
        (:weight_set_version, :as_of_date, :tier, :regime,
         :predicted_holdout_ic, :realized_ic, :ic_ratio, :n_observations)
    ON CONFLICT (weight_set_version, as_of_date) DO UPDATE SET
        realized_ic = EXCLUDED.realized_ic,
        ic_ratio = EXCLUDED.ic_ratio,
        n_observations = EXCLUDED.n_observations,
        predicted_holdout_ic = EXCLUDED.predicted_holdout_ic
""")


def upsert_live_perf_batch(engine: Engine, measurements: list[LiveICMeasurement]) -> int:
    if not measurements:
        return 0
    records = [
        {
            "weight_set_version": m.weight_set_version,
            "as_of_date": m.as_of_date,
            "tier": m.tier,
            "regime": m.regime,
            "predicted_holdout_ic": m.predicted_holdout_ic,
            "realized_ic": m.realized_ic,
            "ic_ratio": m.ic_ratio,
            "n_observations": m.n_observations,
        }
        for m in measurements
    ]
    with engine.begin() as conn:
        conn.execute(_UPSERT_LIVE_PERF_SQL, records)
    log.info("live_perf_batch_persisted", n=len(records))
    return len(records)


_UPSERT_HIT_RATE_SQL = text("""
    INSERT INTO atlas.atlas_stock_hit_rate_daily
        (instrument_id, date, lookback_window,
         n_high_conviction_days, n_positive_outcomes, hit_rate, tier_at_as_of)
    VALUES
        (CAST(:instrument_id AS uuid), :date, :lookback_window,
         :n_high, :n_pos, :hit_rate, :tier_at_as_of)
    ON CONFLICT (instrument_id, date, lookback_window) DO UPDATE SET
        n_high_conviction_days = EXCLUDED.n_high_conviction_days,
        n_positive_outcomes = EXCLUDED.n_positive_outcomes,
        hit_rate = EXCLUDED.hit_rate,
        tier_at_as_of = EXCLUDED.tier_at_as_of
""")


def upsert_hit_rates_batch(engine: Engine, rows: list[HitRateRow]) -> int:
    if not rows:
        return 0
    records = [
        {
            "instrument_id": r.instrument_id,
            "date": r.date,
            "lookback_window": r.lookback_window,
            "n_high": r.n_high_conviction_days,
            "n_pos": r.n_positive_outcomes,
            "hit_rate": r.hit_rate,
            "tier_at_as_of": r.tier_at_as_of,
        }
        for r in rows
    ]
    with engine.begin() as conn:
        conn.execute(_UPSERT_HIT_RATE_SQL, records)
    log.info("hit_rate_batch_persisted", n=len(records))
    return len(records)


def write_revert_log(
    engine: Engine,
    *,
    tier: str,
    regime: str,
    reverted_from_version: str,
    restored_to_version: str | None,
    days_below_threshold: int,
    realized_ic_avg: float | None,
    predicted_holdout_ic: float | None,
    triggered_by: str,
    notes: str | None = None,
) -> str:
    """INSERT-only — audit row for one revert event."""
    sql = text("""
        INSERT INTO atlas.atlas_weight_revert_log
            (tier, regime, reverted_from_version, restored_to_version,
             days_below_threshold, realized_ic_avg,
             predicted_holdout_ic, triggered_by, notes)
        VALUES
            (:tier, :regime, :from_v, :to_v,
             :days, :real_avg, :pred, :trigger, :notes)
        RETURNING id::text
    """)
    with engine.begin() as conn:
        row = conn.execute(
            sql,
            {
                "tier": tier,
                "regime": regime,
                "from_v": reverted_from_version,
                "to_v": restored_to_version,
                "days": days_below_threshold,
                "real_avg": realized_ic_avg,
                "pred": predicted_holdout_ic,
                "trigger": triggered_by,
                "notes": notes,
            },
        ).fetchone()
    if row is None:
        raise RuntimeError("revert log INSERT returned no id")
    return str(row[0])
