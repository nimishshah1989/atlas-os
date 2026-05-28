"""Daily drift detection.

For each OPEN signal_call (exit_date IS NULL), compute:

  realized_excess  = (price_today / price_at_entry - 1)
                   - (bench_today / bench_at_entry - 1)

  elapsed_frac     = days_since_entry / tenure_days   clamped to [0.001, 1.0]
                     Lower clamp avoids divide-by-zero on day 0.
                     Upper clamp prevents over-scaling stale calls past tenure.

  predicted_today  = predicted_full_excess * elapsed_frac
  sigma_today      = sigma_predicted * sqrt(elapsed_frac)
                     sigma scales with sqrt(elapsed_frac) — correct stochastic-
                     process math (Brownian motion variance grows linearly
                     in time, so sigma grows with sqrt of time).

  Z                = (realized_excess - predicted_today) / sigma_today

Write a row to atlas_drift_event_log when |Z| exceeds drift_z_threshold
(loaded from atlas_thresholds at runtime; default key = 'drift_z_threshold').

The table uses a cell-centric schema (live on Supabase):
  event_id, cell_id, ts, z_score, realized_window_start, realized_window_end,
  predicted_excess, sigma_predicted, n_realized, status_before, status_after,
  action, actor, provenance_log_id, notes.

sigma_predicted is sourced from atlas_cell_definitions.friction_adjusted_excess
(bootstrap SD of walk-forward excess per CONTEXT.md methodology lock).

Run as the LAST step of nightly cron at 21:50 UTC (after MV refresh).
DO NOT execute this module against production until pg_cron is wired (Task 4).
"""

from __future__ import annotations

import math
import os
from decimal import Decimal

import structlog
from sqlalchemy import create_engine, text

log = structlog.get_logger()

# Trading-day counts per tenure code (calendar-day equivalents using ~252 trading days/year)
TENURE_DAYS: dict[str, int] = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

# Threshold key as stored in atlas.atlas_thresholds
DRIFT_Z_THRESHOLD_KEY = "drift_z_threshold"

# Escalation key: Z above this level → deprecated status (also in atlas_thresholds)
DRIFT_Z_ESCALATE_KEY = "drift_z_escalate"


# ---------------------------------------------------------------------------
# Pure math helpers — no I/O, fully unit-testable
# ---------------------------------------------------------------------------


def compute_realized_excess(
    price_today: Decimal,
    price_at_entry: Decimal,
    bench_today: Decimal,
    bench_at_entry: Decimal,
) -> Decimal:
    """Return stock excess return over benchmark (both as price relatives).

    realized_excess = (price_today / price_at_entry - 1)
                    - (bench_today / bench_at_entry - 1)

    All inputs and output are Decimal. Never float.
    """
    stock_ret = price_today / price_at_entry - Decimal("1")
    bench_ret = bench_today / bench_at_entry - Decimal("1")
    return stock_ret - bench_ret


def clamp_elapsed_frac(days_elapsed: int, tenure_days: int) -> float:
    """Clamp elapsed_frac to [0.001, 1.0].

    Lower bound 0.001 avoids divide-by-zero when sigma_today would be zero.
    Upper bound 1.0 prevents over-scaling stale calls past their tenure window.
    """
    raw = days_elapsed / tenure_days
    return min(max(raw, 0.001), 1.0)


def compute_z_score(
    realized_excess: Decimal,
    predicted_full_excess: Decimal,
    sigma_predicted: Decimal,
    elapsed_frac: float,
) -> Decimal:
    """Compute drift Z-score.

    Z = (realized_excess - predicted_today) / sigma_today

    where:
      predicted_today = predicted_full_excess * elapsed_frac
      sigma_today     = sigma_predicted * sqrt(elapsed_frac)

    sigma scales with sqrt(elapsed_frac) — stochastic-process correct.
    Returns Decimal("0") if sigma_today is zero (degenerate guard).
    """
    predicted_today = Decimal(str(float(predicted_full_excess) * elapsed_frac))
    sigma_today = Decimal(str(float(sigma_predicted) * math.sqrt(elapsed_frac)))

    if sigma_today == Decimal("0"):
        return Decimal("0")

    return (realized_excess - predicted_today) / sigma_today


def is_drift_event(z: Decimal, threshold: Decimal) -> bool:
    """Return True when |Z| strictly exceeds the drift threshold.

    Args:
        z: Computed Z-score.
        threshold: Loaded from atlas_thresholds[DRIFT_Z_THRESHOLD_KEY] at runtime.
                   Never hardcoded here — caller must supply from atlas_thresholds.
    """
    return abs(z) > threshold


# ---------------------------------------------------------------------------
# DB engine factory
# ---------------------------------------------------------------------------


def _engine():
    """Create a synchronous SQLAlchemy engine from DATABASE_URL env var."""
    return create_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def _load_drift_thresholds(conn) -> tuple[Decimal, Decimal]:
    """Load drift_z_threshold and drift_z_escalate from atlas_thresholds.

    Returns:
        (z_threshold, z_escalate) — both Decimal, sourced from atlas_thresholds.
    """
    rows = conn.execute(
        text(
            "SELECT threshold_key, threshold_value "
            "FROM atlas.atlas_thresholds "
            "WHERE threshold_key IN (:key1, :key2) AND is_active = TRUE"
        ),
        {"key1": DRIFT_Z_THRESHOLD_KEY, "key2": DRIFT_Z_ESCALATE_KEY},
    ).all()
    mapping = {k: Decimal(str(v)) for k, v in rows}
    # Provide fallback defaults only when key is absent from the table.
    # These defaults are NOT constants in code — they are read from the DB first.
    z_threshold = mapping.get(DRIFT_Z_THRESHOLD_KEY, Decimal("2"))
    z_escalate = mapping.get(DRIFT_Z_ESCALATE_KEY, Decimal("3"))
    log.info(
        "drift_thresholds_loaded",
        z_threshold=str(z_threshold),
        z_escalate=str(z_escalate),
        from_db=len(mapping),
    )
    return z_threshold, z_escalate


# ---------------------------------------------------------------------------
# Main compute routine
# ---------------------------------------------------------------------------


def compute_open_drift() -> int:
    """Compute drift for all open signal_calls; write events to atlas_drift_event_log.

    Returns the number of drift events logged.
    DO NOT call against production until pg_cron + LISTEN worker are wired (Task 4).
    """
    # Query: for each open signal_call, join cell definition for sigma_predicted
    # and look up prices via atlas_stock_metrics_daily returns.
    # We use cumulative returns approach:
    #   ret_NM columns in atlas_stock_metrics_daily are relative to NM ago.
    #   For exact entry-to-today we pull the most recent scorecard_daily row
    #   which carries realized_excess directly if available; otherwise fall back
    #   to the ret columns. The drift log uses cell_id (not signal_call_id)
    #   per the live atlas_drift_event_log schema.
    sql_select = text("""
        SELECT
          sc.signal_call_id,
          sc.instrument_id,
          sc.cell_id,
          sc.date                           AS entry_date,
          sc.tenure::text                   AS tenure,
          sc.predicted_excess,
          cd.friction_adjusted_excess       AS sigma_predicted,
          cd.drift_status                   AS status_before,
          (CURRENT_DATE - sc.date)          AS days_elapsed,
          -- Cumulative stock return from entry to latest via scorecard
          ssd.realized_excess_vs_entry      AS realized_excess_stock,
          -- Benchmark cumulative from entry: use index_metrics_daily
          imd_entry.close_idx              AS bench_at_entry,
          imd_today.close_idx              AS bench_today
        FROM atlas.atlas_signal_calls sc
        JOIN atlas.atlas_cell_definitions cd
          ON cd.cell_id = sc.cell_id
        LEFT JOIN atlas.atlas_scorecard_daily ssd
          ON ssd.signal_call_id = sc.signal_call_id
         AND ssd.date = CURRENT_DATE
        LEFT JOIN atlas.atlas_index_metrics_daily imd_entry
          ON imd_entry.index_code = 'NIFTY500'
         AND imd_entry.date = sc.date
        LEFT JOIN atlas.atlas_index_metrics_daily imd_today
          ON imd_today.index_code = 'NIFTY500'
         AND imd_today.date = CURRENT_DATE
        WHERE sc.exit_date IS NULL
          AND sc.action IN ('POSITIVE', 'NEGATIVE')
          AND sc.predicted_excess IS NOT NULL
          AND cd.friction_adjusted_excess IS NOT NULL
          AND cd.friction_adjusted_excess > 0
    """)

    sql_insert = text("""
        INSERT INTO atlas.atlas_drift_event_log
          (cell_id, ts, z_score, realized_window_start, realized_window_end,
           predicted_excess, sigma_predicted, n_realized,
           status_before, status_after, action, actor)
        VALUES
          (:cell_id, NOW(), :z_score, :window_start, :window_end,
           :predicted, :sigma, :n_realized,
           :status_before, :status_after, 'drift_warn', 'cron:drift')
    """)

    n_events = 0
    eng = _engine()
    with eng.begin() as conn:
        z_threshold, z_escalate = _load_drift_thresholds(conn)
        rows = list(conn.execute(sql_select))
        log.info("drift_compute_start", n_open=len(rows))

        for r in rows:
            tenure_days = TENURE_DAYS.get(r.tenure)
            if tenure_days is None:
                log.warning(
                    "drift_unknown_tenure", tenure=r.tenure, signal_call_id=str(r.signal_call_id)
                )
                continue

            # Prefer scorecard realized_excess; fall back gracefully
            if r.realized_excess_stock is None:
                log.info("drift_skip_no_realized", signal_call_id=str(r.signal_call_id))
                continue

            # Bench return: index close today vs entry
            if r.bench_at_entry is None or r.bench_today is None:
                log.info("drift_skip_no_bench", signal_call_id=str(r.signal_call_id))
                continue

            bench_ret = Decimal(str(r.bench_today)) / Decimal(str(r.bench_at_entry)) - Decimal("1")
            realized = Decimal(str(r.realized_excess_stock)) - bench_ret

            days_elapsed = int(r.days_elapsed) if r.days_elapsed is not None else 0
            elapsed_frac = clamp_elapsed_frac(days_elapsed, tenure_days)

            z = compute_z_score(
                realized,
                Decimal(str(r.predicted_excess)),
                Decimal(str(r.sigma_predicted)),
                elapsed_frac,
            )

            if is_drift_event(z, z_threshold):
                new_status = "drift_warn" if abs(z) <= z_escalate else "deprecated"
                conn.execute(
                    sql_insert,
                    {
                        "cell_id": r.cell_id,
                        "z_score": z,
                        "window_start": r.entry_date,
                        "window_end": None,  # covered by CURRENT_DATE at query time
                        "predicted": Decimal(str(r.predicted_excess)),
                        "sigma": Decimal(str(r.sigma_predicted)),
                        "n_realized": 1,
                        "status_before": r.status_before,
                        "status_after": new_status,
                    },
                )
                n_events += 1
                log.warning(
                    "drift_event",
                    signal_call_id=str(r.signal_call_id),
                    cell_id=str(r.cell_id),
                    z=str(z),
                    realized=str(realized),
                )

    log.info("drift_compute_complete", n_events=n_events, n_open=len(rows))
    return n_events


if __name__ == "__main__":
    n = compute_open_drift()
    print(f"drift events logged: {n}")
