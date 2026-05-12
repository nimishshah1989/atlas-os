"""Compute Spearman IC between ppc_strength / npc_strength / atr_slope and forward returns.

Usage: python scripts/compute_timing_ic.py [--date YYYY-MM-DD] [--persist]
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import pandas as pd
import structlog

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine
from atlas.intelligence.validation.ic_engine import compute_ic_over_window

log = structlog.get_logger()

SIGNAL_CONFIGS = [
    ("ppc_strength", "fwd_ret_20d"),
    ("npc_strength", "fwd_ret_20d"),
    ("atr_slope", "fwd_ret_20d"),
    ("ppc_strength", "fwd_ret_10d"),
]
LOOKBACK_DAYS = 90
MIN_OBS = 20


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, instrument_id, ppc_strength, npc_strength, atr_slope,
                   fwd_ret_5d, fwd_ret_10d, fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_20d IS NOT NULL
            """,
            conn,
            params={
                "start": as_of_date - timedelta(days=LOOKBACK_DAYS),
                "end": as_of_date,
            },
        )

    if df.empty:
        log.warning("timing_ic_no_data", date=str(as_of_date))
        return

    df["date"] = pd.to_datetime(df["date"])

    results = []
    for signal_col, fwd_col in SIGNAL_CONFIGS:
        horizon = int(fwd_col.split("_")[-1].replace("d", ""))
        sub = df[["date", "instrument_id", signal_col, fwd_col]].dropna()
        if len(sub) < MIN_OBS:
            continue

        returns_wide = sub.pivot(index="date", columns="instrument_id", values=fwd_col)
        # ic_engine expects factor column named 'factor'
        factor_df = sub[["date", "instrument_id", signal_col]].copy()  # type: ignore[index]  # pandas stubs widen df[list]
        factor_df = factor_df.rename(columns={signal_col: "factor"})  # type: ignore[union-attr]
        factor = factor_df.set_index(["date", "instrument_id"])
        try:
            ic_result = compute_ic_over_window(factor, returns_wide)
        except Exception as e:
            log.warning("timing_ic_failed", signal=signal_col, error=str(e))
            continue

        results.append(
            {
                "as_of_date": as_of_date,
                "signal_name": signal_col,
                "lookback_window": LOOKBACK_DAYS,
                "forward_horizon": horizon,
                "n_observations": ic_result.n_observations,
                "ic": ic_result.mean_ic,
                "t_stat": ic_result.ic_t_stat,
            }
        )
        log.info(
            "timing_ic_computed",
            signal=signal_col,
            horizon=horizon,
            ic=round(ic_result.mean_ic, 4),
            n=ic_result.n_observations,
        )

    if results and persist:
        df_out = pd.DataFrame(results)
        cols = list(df_out.columns)
        rows = df_to_pg_rows(df_out)  # type: ignore[arg-type]
        bulk_upsert(
            engine,
            "atlas.atlas_cts_timing_ic",
            cols,
            rows,
            ["as_of_date", "signal_name", "lookback_window", "forward_horizon"],
        )
        log.info("timing_ic_persisted", count=len(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
