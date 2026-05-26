"""Compute Spearman IC between CTS signals and forward returns.

v2 improvements:
- Primary horizon: 5d (PPC is a short-term signal; 20d dilutes with macro noise)
- Window: 365 days (~252 trading days) — statistically meaningful vs prior n=39
- Segments: full universe AND Stage 2-only to measure quality-filter lift
- Adds cts_conviction_score IC vs fwd_ret_5d

Usage: python -m scripts.compute_timing_ic [--date YYYY-MM-DD] [--persist]
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import cast

import pandas as pd
import structlog

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine
from atlas.intelligence.validation.ic_engine import compute_ic_over_window

log = structlog.get_logger()

# (signal_col, fwd_col, stage_filter: int|None)  — None = all stages
SIGNAL_CONFIGS = [
    ("ppc_strength", "fwd_ret_5d", None),  # primary: all PPC
    ("ppc_strength", "fwd_ret_5d", 2),  # Stage 2 PPC only — quality lift
    ("ppc_strength", "fwd_ret_10d", None),
    ("npc_strength", "fwd_ret_5d", None),
    ("cts_conviction_score", "fwd_ret_5d", None),  # conviction vs short return
    ("cts_conviction_score", "fwd_ret_5d", 2),  # Stage 2 conviction
    ("atr_slope", "fwd_ret_5d", None),
]
LOOKBACK_DAYS = 365  # ~252 trading days
MIN_OBS = 30


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, instrument_id, stage,
                   ppc_strength, npc_strength, atr_slope, cts_conviction_score,
                   fwd_ret_5d, fwd_ret_10d, fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_5d IS NOT NULL
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
    for signal_col, fwd_col, stage_filter in SIGNAL_CONFIGS:
        if signal_col not in df.columns or fwd_col not in df.columns:
            continue
        horizon = int(fwd_col.split("_")[-1].replace("d", ""))
        sub = cast(
            pd.DataFrame,
            df[["date", "instrument_id", "stage", signal_col, fwd_col]].dropna(),  # type: ignore[call-overload]
        )
        # Re-apply per-column NaN filter after cast (dropna() without subset drops all-NaN rows)
        sub = sub[sub[signal_col].notna() & sub[fwd_col].notna()]
        if stage_filter is not None:
            sub = cast(pd.DataFrame, sub[sub["stage"] == stage_filter])
        if len(sub) < MIN_OBS:
            log.info("timing_ic_skip", signal=signal_col, stage=stage_filter, n=len(sub))
            continue

        returns_wide = cast(
            pd.DataFrame, sub.pivot(index="date", columns="instrument_id", values=fwd_col)
        )
        factor_df = cast(
            pd.DataFrame,
            sub[["date", "instrument_id", signal_col]]
            .copy()
            .rename(columns={signal_col: "factor"})  # type: ignore[call-overload]
            .set_index(["date", "instrument_id"]),
        )

        try:
            ic_result = compute_ic_over_window(factor_df, returns_wide)
        except Exception as e:
            log.warning("timing_ic_failed", signal=signal_col, stage=stage_filter, error=str(e))
            continue

        stage_label = f"stage{stage_filter}" if stage_filter is not None else "all"
        signal_label = f"{signal_col}_{stage_label}"

        log.info(
            "timing_ic_computed",
            signal=signal_label,
            horizon=horizon,
            ic=round(ic_result.mean_ic, 4),
            t_stat=round(ic_result.ic_t_stat, 2),
            n=ic_result.n_observations,
        )

        results.append(
            {
                "as_of_date": as_of_date,
                "signal_name": signal_label,
                "lookback_window": LOOKBACK_DAYS,
                "forward_horizon": horizon,
                "n_observations": ic_result.n_observations,
                "ic": ic_result.mean_ic,
                "t_stat": ic_result.ic_t_stat,
            }
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
