"""Compute PPC/NPC/Contraction/Stage for all ~750 stocks for today's date.

Run nightly after the M2-M5 pipeline (which writes de_equity_ohlcv).
Usage:
    python scripts/compute_cts_signals.py [--date YYYY-MM-DD] [--persist]
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import pandas as pd
import structlog

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.cts.sector_pivot import compute_sector_pivot
from atlas.compute.cts.signals import detect_signals
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

LOOKBACK_BARS = 210  # need 200 bars for SMA-150 + slope buffer


def _load_universe(engine):
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT u.instrument_id, u.symbol, u.sector, u.tier
            FROM atlas.atlas_universe_stocks u
            WHERE u.effective_to IS NULL
            """,
            conn,
        )


def _load_ohlcv(engine, instrument_ids: list[str], end: date) -> pd.DataFrame:
    start = end - timedelta(days=int(LOOKBACK_BARS * 1.5))  # calendar days buffer
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


def _load_rs_pctile(engine, as_of_date: date) -> pd.DataFrame:
    """Load cross-sector RS percentile from the latest sector rotation MV."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT i.id AS instrument_id,
                   COALESCE(m.rs_pctile_3m_nifty500, 0.0)::float AS rs_pctile_cross_sector
            FROM atlas.atlas_instruments i
            LEFT JOIN atlas.atlas_stock_metrics_daily m
                ON m.instrument_id = i.id AND m.date = %(d)s
            WHERE i.is_active
            """,
            conn,
            params={"d": as_of_date},
        )


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()
    thresholds = load_thresholds(engine)

    log.info("cts_compute_start", date=str(as_of_date))
    universe = _load_universe(engine)
    ids = universe["instrument_id"].tolist()

    ohlcv = _load_ohlcv(engine, ids, as_of_date)
    log.info("ohlcv_loaded", rows=len(ohlcv), instruments=ohlcv["instrument_id"].nunique())

    rs_pctile = _load_rs_pctile(engine, as_of_date)
    ohlcv = ohlcv.merge(rs_pctile, on="instrument_id", how="left")
    ohlcv["rs_pctile_cross_sector"] = ohlcv["rs_pctile_cross_sector"].fillna(0.0)

    signals = detect_signals(ohlcv, thresholds=thresholds)

    # Keep only today's rows
    today_signals = signals[signals["date"] == as_of_date].copy()
    today_signals = today_signals.merge(
        universe[["instrument_id", "sector", "tier"]], on="instrument_id", how="left"
    )

    trp_min = float(thresholds["cts_trp_tradeable_min"])
    today_signals["is_tradeable"] = today_signals["avg_trp"].fillna(0) >= trp_min

    log.info(
        "signals_computed",
        total=len(today_signals),
        ppc=int(today_signals["is_ppc"].sum()),
        npc=int(today_signals["is_npc"].sum()),
        contraction=int(today_signals["is_contraction"].sum()),
        stage2=int((today_signals["stage"] == 2).sum()),
    )

    if persist:
        _upsert_signals(engine, today_signals)
        pivot = compute_sector_pivot(today_signals)
        _upsert_pivot(engine, pivot)
        log.info("cts_compute_persisted", date=str(as_of_date))


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
    ]
    rows = df_to_pg_rows(df[cols])  # type: ignore[arg-type]  # pandas stubs: df[list] -> DataFrame|Series|Unknown, runtime always DataFrame
    bulk_upsert(engine, "atlas.atlas_cts_signals_daily", cols, rows, ["date", "instrument_id"])


def _upsert_pivot(engine, df: pd.DataFrame) -> None:
    cols = ["date", "sector", "ppc_count", "npc_count", "total_tradeable", "pivot_balance"]
    rows = df_to_pg_rows(df[cols])  # type: ignore[arg-type]  # pandas stubs: df[list] -> DataFrame|Series|Unknown, runtime always DataFrame
    bulk_upsert(engine, "atlas.atlas_cts_sector_pivot_daily", cols, rows, ["date", "sector"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
