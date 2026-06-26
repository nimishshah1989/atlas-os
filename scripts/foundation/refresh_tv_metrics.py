#!/usr/bin/env python3
"""Widen TV metrics to full ~2000 stock universe.

Calls the existing atlas.tv.screener._fetch_tv_batch for all stocks in
foundation_staging.instrument_master and upserts into atlas.tv_metrics.
Uses the production screener's column set and upsert logic — this is just
a wider universe driver, not a reimplementation.

Run: python refresh_tv_metrics.py [--limit N]
"""

from __future__ import annotations

import argparse
import os
import sys

# Add atlas package root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import _db
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA


def run(limit: int | None = None) -> dict:
    # Load full universe from staging
    df = _db.read_df(
        f"select instrument_id, symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null order by symbol"
    )
    symbols = list(df["symbol"])
    iid_map = dict(zip(df["symbol"], df["instrument_id"].astype(str), strict=False))
    if limit:
        symbols = symbols[:limit]
    print(f"[tv_metrics] universe={len(symbols)}", flush=True)

    # Import the atlas screener to reuse its fetch and upsert logic
    import pandas as pd

    from atlas.db import get_engine
    from atlas.tv.screener import _fetch_tv_batch, _json_dumps, _label, _upsert_rows

    engine = get_engine()
    batch_size = 100
    total = 0

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            tvdf = _fetch_tv_batch(batch)
        except Exception as e:
            print(f"[tv_metrics] batch {i} failed: {e}", flush=True)
            continue
        if tvdf.empty:
            continue

        records = tvdf.to_dict(orient="records")
        rows = []
        for rec in records:
            sym = str(rec.get("ticker", ""))
            recommend_all = rec.get("Recommend.All")
            vol = rec.get("volume")
            vol10d = rec.get("average_volume_10d_calc")
            rows.append(
                {
                    "symbol": sym,
                    "instrument_id": iid_map.get(sym),
                    "tv_recommend_label": _label(recommend_all),
                    "recommend_all": recommend_all,
                    "recommend_ma": rec.get("Recommend.MA"),
                    "recommend_other": rec.get("Recommend.Other"),
                    "rsi_14": rec.get("RSI"),
                    "macd_macd": rec.get("MACD.macd"),
                    "macd_signal": rec.get("MACD.signal"),
                    "macd_hist": rec.get("MACD.hist"),
                    "ema_20": rec.get("EMA20"),
                    "ema_50": rec.get("EMA50"),
                    "ema_200": rec.get("EMA200"),
                    "atr_14": rec.get("ATR"),
                    "volume": int(rec["volume"]) if bool(pd.notna(vol)) else None,
                    "volume_10d_avg": int(rec["average_volume_10d_calc"])
                    if bool(pd.notna(vol10d))
                    else None,
                    "price": rec.get("close"),
                    "high_52w": rec.get("High.All"),
                    "low_52w": rec.get("Low.All"),
                    "pe_ttm": rec.get("price_earnings_ttm"),
                    "ps_current": rec.get("price_sales_current"),
                    "pb_fbs": rec.get("price_book_fbs"),
                    "debt_to_equity": rec.get("debt_to_equity"),
                    "roe": rec.get("return_on_equity"),
                    "stoch_k": rec.get("Stoch.K"),
                    "stoch_d": rec.get("Stoch.D"),
                    "adx": rec.get("ADX"),
                    "adx_plus_di": rec.get("ADX+DI"),
                    "adx_minus_di": rec.get("ADX-DI"),
                    "cci_20": rec.get("CCI20"),
                    "williams_r": rec.get("W.R"),
                    "mfi": rec.get("MFI"),
                    "ao": rec.get("AO"),
                    "uo": rec.get("UO"),
                    "momentum": rec.get("Mom"),
                    "roc": rec.get("ROC"),
                    "bb_lower": rec.get("BB.lower"),
                    "bb_upper": rec.get("BB.upper"),
                    "vwap": rec.get("VWAP"),
                    "sma_20": rec.get("SMA20"),
                    "sma_50": rec.get("SMA50"),
                    "sma_200": rec.get("SMA200"),
                    "perf_1w": rec.get("Perf.W"),
                    "perf_1m": rec.get("Perf.1M"),
                    "perf_3m": rec.get("Perf.3M"),
                    "perf_6m": rec.get("Perf.6M"),
                    "perf_ytd": rec.get("Perf.YTD"),
                    "perf_1y": rec.get("Perf.Y"),
                    "perf_5y": rec.get("Perf.5Y"),
                    "volatility_d": rec.get("Volatility.D"),
                    "volatility_w": rec.get("Volatility.W"),
                    "volatility_m": rec.get("Volatility.M"),
                    "beta_1y": rec.get("Beta.1Y"),
                    "rel_volume_10d": rec.get("relative_volume_10d_calc"),
                    "avg_volume_30d": int(rec["average_volume_30d_calc"])
                    if bool(pd.notna(rec.get("average_volume_30d_calc")))
                    else None,
                    "avg_volume_60d": int(rec["average_volume_60d_calc"])
                    if bool(pd.notna(rec.get("average_volume_60d_calc")))
                    else None,
                    "eps_diluted_ttm": rec.get("earnings_per_share_diluted_ttm"),
                    "eps_growth_yoy": rec.get("earnings_per_share_diluted_yoy_growth_ttm"),
                    "revenue_ttm": rec.get("revenue"),
                    "revenue_growth_yoy": rec.get("revenue_yoy_growth_ttm"),
                    "market_cap": rec.get("market_cap_basic"),
                    "enterprise_value": rec.get("enterprise_value_fq"),
                    "gross_margin": rec.get("gross_profit_margin_ttm"),
                    "operating_margin": rec.get("operating_margin_ttm"),
                    "net_margin": rec.get("net_margin_ttm"),
                    "dividend_yield": rec.get("dividends_yield_current"),
                    "payout_ratio": rec.get("payout_ratio_ttm"),
                    "book_value_per_share": rec.get("book_value_per_share_fq"),
                    "current_ratio": rec.get("current_ratio_fq"),
                    "quick_ratio": rec.get("quick_ratio_fq"),
                    "roa": rec.get("return_on_assets"),
                    "roic": rec.get("return_on_invested_capital_fq"),
                    "ev_ebitda": rec.get("enterprise_value_ebitda_ttm"),
                    "ev_sales": rec.get("enterprise_value_revenue_ttm"),
                    "price_fcf": rec.get("price_free_cash_flow_ttm"),
                    "peg_ratio": rec.get("price_earnings_growth_ttm"),
                    "shares_outstanding": rec.get("shares_outstanding"),
                    "float_shares": rec.get("float_shares_outstanding"),
                    "raw_payload": _json_dumps(rec),
                }
            )
        _upsert_rows(rows, engine)
        total += len(rows)
        if (i // batch_size) % 5 == 0 or i + batch_size >= len(symbols):
            print(
                f"[tv_metrics] {min(i + batch_size, len(symbols))}/{len(symbols)} upserted={total}",
                flush=True,
            )

    print(f"[tv_metrics] COMPLETE total={total}", flush=True)
    return {"universe": len(symbols), "upserted": total}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    run(limit=a.limit)
