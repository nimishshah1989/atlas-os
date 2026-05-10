#!/usr/bin/env python3
"""M12 — Backend Data Health daily orchestrator.

Runs nightly after m5_daily completes:
  1. Snapshot row counts + latest dates per atlas.* table (freshness).
  2. Compute ~30 metrics per atlas.* table for the latest trading date.
  3. Compare today vs prior-day vs 14-day rolling history; flag anomalies.
  4. Write rows to atlas.atlas_health_daily.
  5. Run validate_m3 + validate_m4 + validate_m5; write to
     atlas.atlas_validator_results.

Records its own run in atlas.atlas_pipeline_runs.

Usage::

    python3 scripts/health_check_daily.py [--date YYYY-MM-DD]

Defaults to the latest trading date present in atlas.atlas_market_regime_daily.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from atlas.compute._session import open_compute_session  # noqa: E402
from atlas.db import get_engine  # noqa: E402
from atlas.health.anomaly import evaluate_categorical, evaluate_numeric  # noqa: E402
from atlas.health.metrics import CATALOG, compute_metric  # noqa: E402
from atlas.health.runs import safe_finish, safe_record  # noqa: E402
from atlas.health.validator_runner import run_and_record  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _latest_trading_date(engine) -> date | None:
    with open_compute_session(engine) as conn:
        row = pd.read_sql(
            "SELECT MAX(date) AS d FROM atlas.atlas_market_regime_daily",
            conn,
        ).iloc[0]
    if row["d"] is None:
        return None
    return pd.to_datetime(row["d"]).date()


def _to_float(v: object | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _compute_history_for_metric(
    engine, mdef, target_date: date
) -> tuple[object | None, list[float]]:
    """Return (prior_day_value, history_14d_values_excluding_target).

    Empty list if no history is available. Numeric metrics: ignores NULLs.
    Categorical metrics: prior_day only (history list is unused).
    """
    with open_compute_session(engine) as conn:
        prev_dates_df = pd.read_sql(
            """
            SELECT DISTINCT date
            FROM atlas.atlas_market_regime_daily
            WHERE date < %(d)s
            ORDER BY date DESC
            LIMIT 14
            """,
            conn,
            params={"d": target_date},
        )
    if prev_dates_df.empty:
        return None, []

    prev_dates = sorted(pd.to_datetime(prev_dates_df["date"]).dt.date.tolist())
    prior_day = prev_dates[-1] if prev_dates else None

    prior_value = compute_metric(engine, mdef, prior_day) if prior_day else None
    if mdef.is_categorical:
        return prior_value, []

    history: list[float] = []
    for d in prev_dates:
        v = compute_metric(engine, mdef, d)
        f = _to_float(v)
        if f is not None:
            history.append(f)
    return prior_value, history


def _write_row(
    engine,
    *,
    data_date: date,
    table_name: str,
    metric_name: str,
    value_today: object | None,
    value_prior: object | None,
    rolling_avg: float | None,
    rolling_std: float | None,
    pct_change_dod: float | None,
    z_score: float | None,
    is_anomaly: bool,
    severity: str | None,
    notes: str | None,
) -> None:
    # Coerce booleans / categoricals to NULL for numeric storage columns.
    def _num(v: object | None) -> float | None:
        return _to_float(v)

    with open_compute_session(engine) as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_health_daily (
                    data_date, table_name, metric_name,
                    value_today, value_prior_day,
                    rolling_14d_avg, rolling_14d_std,
                    pct_change_dod, z_score,
                    is_anomaly, severity, notes,
                    computed_at
                ) VALUES (
                    :data_date, :table_name, :metric_name,
                    :value_today, :value_prior_day,
                    :rolling_avg, :rolling_std,
                    :pct_change_dod, :z_score,
                    :is_anomaly, :severity, :notes,
                    :computed_at
                )
                ON CONFLICT (data_date, table_name, metric_name) DO UPDATE SET
                    value_today      = EXCLUDED.value_today,
                    value_prior_day  = EXCLUDED.value_prior_day,
                    rolling_14d_avg  = EXCLUDED.rolling_14d_avg,
                    rolling_14d_std  = EXCLUDED.rolling_14d_std,
                    pct_change_dod   = EXCLUDED.pct_change_dod,
                    z_score          = EXCLUDED.z_score,
                    is_anomaly       = EXCLUDED.is_anomaly,
                    severity         = EXCLUDED.severity,
                    notes            = EXCLUDED.notes,
                    computed_at      = EXCLUDED.computed_at
            """),
            {
                "data_date": data_date,
                "table_name": table_name,
                "metric_name": metric_name,
                "value_today": _num(value_today),
                "value_prior_day": _num(value_prior),
                "rolling_avg": rolling_avg,
                "rolling_std": rolling_std,
                "pct_change_dod": pct_change_dod,
                "z_score": z_score,
                "is_anomaly": is_anomaly,
                "severity": severity,
                "notes": notes,
                "computed_at": datetime.now(UTC),
            },
        )
        conn.commit()


def main() -> int:
    p = argparse.ArgumentParser(description="Daily health-check orchestrator")
    p.add_argument("--date", type=_parse_date, default=None, help="Target date YYYY-MM-DD")
    args = p.parse_args()

    engine = get_engine()
    target_date = args.date or _latest_trading_date(engine)
    if target_date is None:
        print("ERROR: no trading dates found in atlas_market_regime_daily.")
        return 1

    print(f"Health check for {target_date}")
    run_id = safe_record("health_check_daily", milestone="OPS", engine=engine)

    rows_written = 0
    errors: list[str] = []

    # ----- Phase 1: metrics + anomaly detection -----------------------------
    for mdef in CATALOG:
        try:
            value = compute_metric(engine, mdef, target_date)
            prior, history = _compute_history_for_metric(engine, mdef, target_date)

            if mdef.is_categorical:
                result = evaluate_categorical(
                    today=value,
                    prior_day=prior,
                    severity_critical=mdef.severity_critical,
                )
                _write_row(
                    engine,
                    data_date=target_date,
                    table_name=mdef.table,
                    metric_name=mdef.name,
                    value_today=value,
                    value_prior=prior,
                    rolling_avg=None,
                    rolling_std=None,
                    pct_change_dod=None,
                    z_score=None,
                    is_anomaly=result.is_anomaly,
                    severity=result.severity,
                    notes=result.notes,
                )
            else:
                today_f = _to_float(value)
                prior_f = _to_float(prior)
                result = evaluate_numeric(today_f, prior_f, history)

                rolling_avg = sum(history) / len(history) if history else None
                rolling_std: float | None = None
                if history and len(history) >= 2:
                    avg = rolling_avg or 0.0
                    var = sum((x - avg) ** 2 for x in history) / (len(history) - 1)
                    rolling_std = var**0.5

                _write_row(
                    engine,
                    data_date=target_date,
                    table_name=mdef.table,
                    metric_name=mdef.name,
                    value_today=value,
                    value_prior=prior,
                    rolling_avg=rolling_avg,
                    rolling_std=rolling_std,
                    pct_change_dod=result.pct_change_dod,
                    z_score=result.z_score,
                    is_anomaly=result.is_anomaly,
                    severity=result.severity,
                    notes=result.notes,
                )
            rows_written += 1
        except Exception as exc:
            msg = f"{mdef.table}.{mdef.name}: {exc}"
            errors.append(msg)
            print(f"  WARN  {msg}")

    print(f"  metrics written: {rows_written}")
    if errors:
        print(f"  metric errors:   {len(errors)}")

    # ----- Phase 2: validators ----------------------------------------------
    print("\nRunning validators…")
    for v in ("M3", "M4", "M5"):
        try:
            res = run_and_record(v, engine=engine)
            print(f"  {v}: {res.status}  {res.total_checks - res.failures}/{res.total_checks}")
        except Exception as exc:
            errors.append(f"validator {v}: {exc}")
            print(f"  WARN validator {v} crashed: {exc}")

    safe_finish(
        run_id,
        status="failed" if errors else "success",
        rows_written=rows_written,
        error="\n".join(errors) if errors else None,
        engine=engine,
    )

    print(f"\nDone. {rows_written} metric rows, {len(errors)} errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
