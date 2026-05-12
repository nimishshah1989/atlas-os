"""Compute binary hit rates + lift ratios for PPC/NPC/Contraction signals.

Usage: python scripts/compute_cts_hit_rates.py [--date YYYY-MM-DD] [--persist]
"""

from __future__ import annotations

import argparse
from datetime import date

import pandas as pd
import structlog

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine
from atlas.intelligence.cts.hit_rate import compute_hit_rate

log = structlog.get_logger()

CONFIGS = [
    # (signal_col, stage_filter, forward_col, return_threshold)
    ("is_ppc", 2, "fwd_ret_20d", 0.05),
    ("is_ppc", 2, "fwd_ret_10d", 0.03),
    ("is_ppc", None, "fwd_ret_20d", 0.05),
    ("is_npc", None, "fwd_ret_20d", -0.05),
    ("is_contraction", 2, "fwd_ret_20d", 0.05),
]
LOOKBACK_DAYS = 90


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, instrument_id, is_ppc, is_npc, is_contraction,
                   stage, fwd_ret_5d, fwd_ret_10d, fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_20d IS NOT NULL
            """,
            conn,
            params={
                "start": as_of_date - pd.Timedelta(days=LOOKBACK_DAYS),
                "end": as_of_date,
            },
        )

    results = []
    for signal_col, stage_filter, fwd_col, threshold in CONFIGS:
        horizon = int(fwd_col.split("_")[-1].replace("d", ""))
        metrics = compute_hit_rate(
            df,
            signal_col=signal_col,
            stage_filter=stage_filter,
            forward_col=fwd_col,
            return_threshold=abs(threshold),
        )
        if metrics["total_signals"] < 10:
            continue
        results.append(
            {
                "as_of_date": as_of_date,
                "signal_type": signal_col.replace("is_", ""),
                "stage_filter": stage_filter,
                "forward_horizon": horizon,
                "return_threshold": threshold,
                **metrics,
            }
        )
        log.info(
            "hit_rate_computed",
            signal=signal_col,
            stage=stage_filter,
            lift=round(metrics["lift_ratio"] or 0, 3),
        )

    if results and persist:
        df_out = pd.DataFrame(results)
        cols = list(df_out.columns)
        rows = df_to_pg_rows(df_out)  # type: ignore[arg-type]
        bulk_upsert(
            engine,
            "atlas.atlas_cts_hit_rates",
            cols,
            rows,
            ["as_of_date", "signal_type", "stage_filter", "forward_horizon", "return_threshold"],
        )
    log.info("hit_rates_done", count=len(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
