"""Fast bulk backfill for CTS signals.

Replaces the per-date loop in backfill_cts_signals.py.
Loads all OHLCV data in one query, runs detect_signals once,
then bulk-upserts all results in one operation.

Estimated runtime: 5-10 minutes vs. 2.8 hours for the per-date loop.

Usage:
    python -m scripts.backfill_cts_bulk [--days 504] [--dry-run]
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.cts.sector_pivot import compute_sector_pivot
from atlas.compute.cts.signals import detect_signals
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

LOOKBACK_BARS = 210  # SMA-150 + slope buffer


def _load_trading_dates(engine, total_days: int) -> list[date]:
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT date FROM public.de_trading_calendar
                WHERE is_trading = TRUE
                  AND exchange = 'NSE'
                  AND date <= CURRENT_DATE
                  AND date >= CURRENT_DATE - :days
                ORDER BY date
            """),
            {"days": total_days * 2},
        ).fetchall()
    all_dates = [r[0] for r in rows]
    target_dates = all_dates[-total_days:]
    return target_dates


def _load_all_ohlcv(engine, instrument_ids: list[str], start: date, end: date) -> pd.DataFrame:
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT instrument_id, date, open, high, low, close, volume
            FROM public.de_equity_ohlcv
            WHERE instrument_id = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY instrument_id, date
            """,
            conn,
            params={"ids": instrument_ids, "start": start, "end": end},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _load_all_rs_pctile(engine, start: date, end: date) -> pd.DataFrame:
    """Load rs_pctile_3m for all instruments × all dates in [start, end]."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT m.instrument_id,
                   m.date,
                   COALESCE(m.rs_pctile_3m, 0.0)::float AS rs_pctile_cross_sector
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id = m.instrument_id
               AND u.effective_to IS NULL
            WHERE m.date BETWEEN %(start)s AND %(end)s
            """,
            conn,
            params={"start": start, "end": end},
        )


def _load_universe(engine) -> pd.DataFrame:
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT instrument_id, symbol, sector, tier
            FROM atlas.atlas_universe_stocks
            WHERE effective_to IS NULL
            """,
            conn,
        )


def _load_regime(engine, start: date, end: date) -> pd.DataFrame:
    """Load market regime state per date for conviction boost calculation."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT date, regime_state
            FROM atlas.atlas_market_regime_daily
            WHERE date BETWEEN %(start)s AND %(end)s
            ORDER BY date
            """,
            conn,
            params={"start": start, "end": end},
        )


def _boost_conviction(
    signals: pd.DataFrame,
    sector_pivot: pd.DataFrame,
    regime_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add sector (+10) and regime (+10) bonus to cts_conviction_score (vectorized).

    Sector bonus: pivot_balance > 0.10 for the stock's (date, sector) → +10 pts
    Regime bonus: regime_state == 'Risk-On' on that date → +10 pts
    Also recomputes cts_action_confidence with the full 100-pt scale (threshold 55).

    All operations are vectorized — no iterrows.
    """
    df = signals.copy()

    # --- Sector bonus (vectorized via merge) ---
    if (
        not sector_pivot.empty
        and "pivot_balance" in sector_pivot.columns
        and "sector" in df.columns
    ):
        pivot_lookup = sector_pivot[["date", "sector", "pivot_balance"]].copy()
        pivot_lookup["date"] = pd.to_datetime(pivot_lookup["date"]).dt.date
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.merge(pivot_lookup, on=["date", "sector"], how="left", suffixes=("", "_pivot"))
        sector_bonus = np.where(df["pivot_balance"].fillna(0.0) > 0.10, 10.0, 0.0)
        df.drop(columns=["pivot_balance"], inplace=True, errors="ignore")
    else:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        sector_bonus = np.zeros(len(df))

    # --- Regime bonus (vectorized via merge) ---
    if not regime_df.empty and "regime_state" in regime_df.columns:
        regime_lookup = regime_df[["date", "regime_state"]].copy()
        regime_lookup["date"] = pd.to_datetime(regime_lookup["date"]).dt.date
        df = df.merge(regime_lookup, on="date", how="left")
        regime_bonus = np.where(df["regime_state"].fillna("") == "Risk-On", 10.0, 0.0)
        df.drop(columns=["regime_state"], inplace=True, errors="ignore")
    else:
        regime_bonus = np.zeros(len(df))

    df["cts_conviction_score"] = (
        df["cts_conviction_score"].fillna(0.0) + sector_bonus + regime_bonus
    ).clip(0, 100)

    rs_col = "rs_pctile_cross_sector"
    rs_series = df[rs_col].fillna(0.0) if rs_col in df.columns else pd.Series(0.0, index=df.index)
    df["cts_action_confidence"] = (
        (df["stage"] == 2)
        & df["is_ppc"].fillna(False)
        & (rs_series >= 0.60)
        & (df["cts_conviction_score"] >= 55)
    )
    return df


def run_bulk(total_days: int = 504, *, dry_run: bool = False) -> None:
    engine = get_engine()
    thresholds = load_thresholds(engine)

    log.info("cts_bulk_backfill_start", total_days=total_days, dry_run=dry_run)

    target_dates = _load_trading_dates(engine, total_days)
    if not target_dates:
        log.error("no_trading_dates_found")
        return

    earliest_target = min(target_dates)
    today = max(target_dates)
    # Give enough lookback before the earliest target date
    data_start = earliest_target - timedelta(days=int(LOOKBACK_BARS * 1.5))

    log.info(
        "date_range",
        data_start=str(data_start),
        earliest_target=str(earliest_target),
        latest_target=str(today),
        target_count=len(target_dates),
    )

    universe = _load_universe(engine)
    ids = universe["instrument_id"].tolist()

    log.info("loading_ohlcv", instruments=len(ids))
    ohlcv = _load_all_ohlcv(engine, ids, data_start, today)
    log.info("ohlcv_loaded", rows=len(ohlcv), instruments=ohlcv["instrument_id"].nunique())

    # Load rs_pctile for all dates in the data window (outer join so OHLCV rows
    # in the lookback buffer that pre-date the metrics table just get 0.0).
    log.info("loading_rs_pctile")
    rs_all = _load_all_rs_pctile(engine, data_start, today)
    rs_all["date"] = pd.to_datetime(rs_all["date"]).dt.date
    log.info("rs_pctile_loaded", rows=len(rs_all))

    # Merge rs_pctile by (instrument_id, date) — each bar gets its own day's RS rank
    ohlcv = ohlcv.merge(rs_all, on=["instrument_id", "date"], how="left")
    ohlcv["rs_pctile_cross_sector"] = ohlcv["rs_pctile_cross_sector"].fillna(0.0)

    log.info("running_detect_signals")
    signals = detect_signals(ohlcv, thresholds=thresholds)

    # Filter to target dates only and attach universe metadata
    target_set = set(target_dates)
    today_signals = signals[signals["date"].isin(target_set)].copy()
    today_signals = today_signals.merge(
        universe[["instrument_id", "sector", "tier"]], on="instrument_id", how="left"
    )

    trp_min = float(thresholds["cts_trp_tradeable_min"])
    today_signals["is_tradeable"] = today_signals["avg_trp"].fillna(0) >= trp_min

    log.info(
        "signals_computed",
        rows=len(today_signals),
        dates=today_signals["date"].nunique(),
        ppc=int(today_signals["is_ppc"].sum()),
        npc=int(today_signals["is_npc"].sum()),
        contraction=int(today_signals["is_contraction"].sum()),
        stage2=int((today_signals["stage"] == 2).sum()),
    )

    if dry_run:
        log.info("dry_run_complete_no_writes")
        return

    log.info("computing_sector_pivots")
    pivot = compute_sector_pivot(today_signals)

    log.info("boosting_conviction_scores")
    regime_df = _load_regime(engine, min(target_dates), max(target_dates))
    log.info("regime_loaded", rows=len(regime_df))
    today_signals = _boost_conviction(today_signals, pivot, regime_df)
    log.info(
        "conviction_boosted",
        action_confidence_count=int(today_signals["cts_action_confidence"].sum()),
        mean_conviction=round(float(today_signals["cts_conviction_score"].mean()), 2),
    )

    log.info("upserting_signals", rows=len(today_signals))
    _upsert_signals(engine, today_signals)

    _upsert_pivot(engine, pivot)

    log.info("cts_bulk_backfill_complete", signal_rows=len(today_signals), pivot_rows=len(pivot))


def _upsert_signals(engine, df: pd.DataFrame) -> None:
    cols = [
        "date",
        "instrument_id",
        "stage",
        "is_stage1b",
        "sma_150",
        "sma_150_slope",
        "trp",
        "avg_trp",
        "trp_ratio",
        "is_tradeable",
        "is_ppc",
        "ppc_strength",
        "is_npc",
        "npc_strength",
        "is_contraction",
        "is_trigger_bar",
        "trigger_level",
        "atr_14",
        "atr_slope",
        "cts_conviction_score",
        "cts_action_confidence",
    ]
    rows = df_to_pg_rows(df[cols])  # type: ignore[arg-type]
    bulk_upsert(engine, "atlas.atlas_cts_signals_daily", cols, rows, ["date", "instrument_id"])


def _upsert_pivot(engine, df: pd.DataFrame) -> None:
    cols = [
        "date",
        "sector",
        "ppc_count",
        "npc_count",
        "total_tradeable",
        "pivot_balance",
        "stage2_count",
        "stage2_pct",
        "avg_ppc_conviction",
        "action_alert_count",
    ]
    # Fill any missing columns gracefully (for partial pivot output)
    pivot_df = df.copy()
    for c in cols:
        if c not in pivot_df.columns:
            pivot_df[c] = None
    rows = df_to_pg_rows(pivot_df[cols])  # type: ignore[arg-type]
    bulk_upsert(engine, "atlas.atlas_cts_sector_pivot_daily", cols, rows, ["date", "sector"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=504)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_bulk(total_days=args.days, dry_run=args.dry_run)
