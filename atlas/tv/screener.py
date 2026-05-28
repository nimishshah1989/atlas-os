"""Nightly fetch from tradingview-screener → upsert into atlas.tv_metrics."""

from __future__ import annotations

import math

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

_BATCH_SIZE = 100

_COLUMNS = [
    "close",
    "volume",
    "Recommend.All",
    "Recommend.MA",
    "Recommend.Other",
    "RSI",
    "MACD.macd",
    "EMA20",
    "EMA50",
    "EMA200",
    "ATR",
    "average_volume_10d_calc",
    "High.All",
    "Low.All",
]


def _load_universe_symbols(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = (
            conn.execute(text("SELECT symbol FROM atlas.atlas_universe_stocks ORDER BY symbol"))
            .mappings()
            .all()
        )
    return [r["symbol"] for r in rows]


def _fetch_tv_batch(symbols: list[str]) -> pd.DataFrame:
    from tradingview_screener import Scanner

    qualified = [f"NSE:{s}" for s in symbols]
    _, df = Scanner.get_scanner_data(
        symbols=qualified,
        columns=_COLUMNS,
    )
    if df.empty:
        return df
    df["ticker"] = df["ticker"].str.replace("NSE:", "", regex=False)
    return df


def _resolve_instrument_ids(symbols: list[str], engine: Engine) -> dict[str, str]:
    """Return {symbol: instrument_id_str} for symbols that exist in atlas_universe_stocks."""
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT symbol, instrument_id::text FROM atlas.atlas_universe_stocks "
                    "WHERE symbol = ANY(:syms)"
                ),
                {"syms": symbols},
            )
            .mappings()
            .all()
        )
    return {r["symbol"]: r["instrument_id"] for r in rows}


def _upsert_rows(rows: list[dict], engine: Engine) -> None:
    if not rows:
        return
    upsert_sql = text("""
        INSERT INTO atlas.tv_metrics (
            symbol, instrument_id, fetched_at,
            tv_recommend_label, recommend_all, recommend_ma, recommend_other,
            rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
            volume, volume_10d_avg, price, high_52w, low_52w, raw_payload
        ) VALUES (
            :symbol, :instrument_id, NOW(),
            :tv_recommend_label, :recommend_all, :recommend_ma, :recommend_other,
            :rsi_14, :macd_macd, :ema_20, :ema_50, :ema_200, :atr_14,
            :volume, :volume_10d_avg, :price, :high_52w, :low_52w,
            CAST(:raw_payload AS jsonb)
        )
        ON CONFLICT (symbol) DO UPDATE SET
            instrument_id    = EXCLUDED.instrument_id,
            fetched_at       = EXCLUDED.fetched_at,
            tv_recommend_label = EXCLUDED.tv_recommend_label,
            recommend_all    = EXCLUDED.recommend_all,
            recommend_ma     = EXCLUDED.recommend_ma,
            recommend_other  = EXCLUDED.recommend_other,
            rsi_14           = EXCLUDED.rsi_14,
            macd_macd        = EXCLUDED.macd_macd,
            ema_20           = EXCLUDED.ema_20,
            ema_50           = EXCLUDED.ema_50,
            ema_200          = EXCLUDED.ema_200,
            atr_14           = EXCLUDED.atr_14,
            volume           = EXCLUDED.volume,
            volume_10d_avg   = EXCLUDED.volume_10d_avg,
            price            = EXCLUDED.price,
            high_52w         = EXCLUDED.high_52w,
            low_52w          = EXCLUDED.low_52w,
            raw_payload      = EXCLUDED.raw_payload
    """)
    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)


def _label(score: float | None) -> str | None:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return None
    if score >= 0.5:
        return "STRONG_BUY"
    if score >= 0.1:
        return "BUY"
    if score > -0.1:
        return "NEUTRAL"
    if score > -0.5:
        return "SELL"
    return "STRONG_SELL"


def fetch_and_upsert_all(engine: Engine | None = None) -> None:
    """Entry point for pg_cron: fetch TV metrics for all ~750 universe symbols."""
    engine = engine or get_engine()
    symbols = _load_universe_symbols(engine)
    log.info("tv_screener.start", total_symbols=len(symbols))

    inst_map = _resolve_instrument_ids(symbols, engine)

    total_upserted = 0
    for i in range(0, len(symbols), _BATCH_SIZE):
        batch = symbols[i : i + _BATCH_SIZE]
        try:
            df = _fetch_tv_batch(batch)
        except Exception:
            log.exception("tv_screener.batch_failed", batch_start=i, batch_size=len(batch))
            continue

        if df.empty:
            log.warning("tv_screener.empty_batch", batch_start=i)
            continue

        rows = []
        for _, row in df.iterrows():
            sym = row.get("ticker", "")
            recommend_all = row.get("Recommend.All")
            rows.append(
                {
                    "symbol": sym,
                    "instrument_id": inst_map.get(sym),
                    "tv_recommend_label": _label(recommend_all),
                    "recommend_all": recommend_all,
                    "recommend_ma": row.get("Recommend.MA"),
                    "recommend_other": row.get("Recommend.Other"),
                    "rsi_14": row.get("RSI"),
                    "macd_macd": row.get("MACD.macd"),
                    "ema_20": row.get("EMA20"),
                    "ema_50": row.get("EMA50"),
                    "ema_200": row.get("EMA200"),
                    "atr_14": row.get("ATR"),
                    "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                    "volume_10d_avg": (
                        int(row["average_volume_10d_calc"])
                        if pd.notna(row.get("average_volume_10d_calc"))
                        else None
                    ),
                    "price": row.get("close"),
                    "high_52w": row.get("High.All"),
                    "low_52w": row.get("Low.All"),
                    "raw_payload": row.to_json(),
                }
            )

        _upsert_rows(rows, engine)
        total_upserted += len(rows)
        log.info("tv_screener.batch_done", batch_start=i, rows=len(rows))

    log.info("tv_screener.complete", total_upserted=total_upserted)
