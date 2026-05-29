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
    # Price / OHLCV
    "close",
    "volume",
    "High.All",
    "Low.All",
    # TV recommendations
    "Recommend.All",
    "Recommend.MA",
    "Recommend.Other",
    # Core indicators
    "RSI",
    "MACD.macd",
    "MACD.signal",
    "MACD.hist",
    "EMA20",
    "EMA50",
    "EMA200",
    "ATR",
    # Stochastic + ADX
    "Stoch.K",
    "Stoch.D",
    "ADX",
    "ADX+DI",
    "ADX-DI",
    # Other oscillators
    "CCI20",
    "W.R",
    "MFI",
    "AO",
    "UO",
    "Mom",
    "ROC",
    # Bollinger
    "BB.lower",
    "BB.upper",
    # MAs
    "VWAP",
    "SMA20",
    "SMA50",
    "SMA200",
    # Performance
    "Perf.W",
    "Perf.1M",
    "Perf.3M",
    "Perf.6M",
    "Perf.YTD",
    "Perf.Y",
    "Perf.5Y",
    # Volatility / beta
    "Volatility.D",
    "Volatility.W",
    "Volatility.M",
    "Beta.1Y",
    # Volume metrics
    "average_volume_10d_calc",
    "average_volume_30d_calc",
    "average_volume_60d_calc",
    "relative_volume_10d_calc",
    # Fundamentals (migration 118)
    "price_earnings_ttm",
    "price_sales_current",
    "price_book_fbs",
    "debt_to_equity",
    "return_on_equity",
    # Expanded fundamentals (migration 119)
    "earnings_per_share_diluted_ttm",
    "earnings_per_share_diluted_yoy_growth_ttm",
    "revenue",
    "revenue_yoy_growth_ttm",
    "market_cap_basic",
    "enterprise_value_fq",
    "gross_profit_margin_ttm",
    "operating_margin_ttm",
    "net_margin_ttm",
    "dividends_yield_current",
    "payout_ratio_ttm",
    "book_value_per_share_fq",
    "current_ratio_fq",
    "quick_ratio_fq",
    "return_on_assets",
    "return_on_invested_capital_fq",
    "enterprise_value_ebitda_ttm",
    "enterprise_value_revenue_ttm",
    "price_free_cash_flow_ttm",
    "price_earnings_growth_ttm",
    "shares_outstanding",
    "float_shares_outstanding",
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
    from tradingview_screener import Scanner  # type: ignore[import-untyped]

    qualified = [f"NSE:{s}" for s in symbols]
    _, df = Scanner.get_scanner_data(  # type: ignore[reportAttributeAccessIssue]
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
            rsi_14, macd_macd, macd_signal, macd_hist,
            ema_20, ema_50, ema_200, atr_14,
            volume, volume_10d_avg, avg_volume_30d, avg_volume_60d, rel_volume_10d,
            price, high_52w, low_52w,
            pe_ttm, ps_current, pb_fbs, debt_to_equity, roe,
            stoch_k, stoch_d, adx, adx_plus_di, adx_minus_di,
            cci_20, williams_r, mfi, ao, uo, momentum, roc,
            bb_lower, bb_upper,
            vwap, sma_20, sma_50, sma_200,
            perf_1w, perf_1m, perf_3m, perf_6m, perf_ytd, perf_1y, perf_5y,
            volatility_d, volatility_w, volatility_m, beta_1y,
            eps_diluted_ttm, eps_growth_yoy, revenue_ttm, revenue_growth_yoy,
            market_cap, enterprise_value,
            gross_margin, operating_margin, net_margin,
            dividend_yield, payout_ratio, book_value_per_share,
            current_ratio, quick_ratio, roa, roic,
            ev_ebitda, ev_sales, price_fcf, peg_ratio,
            shares_outstanding, float_shares,
            raw_payload
        ) VALUES (
            :symbol, :instrument_id, NOW(),
            :tv_recommend_label, :recommend_all, :recommend_ma, :recommend_other,
            :rsi_14, :macd_macd, :macd_signal, :macd_hist,
            :ema_20, :ema_50, :ema_200, :atr_14,
            :volume, :volume_10d_avg, :avg_volume_30d, :avg_volume_60d, :rel_volume_10d,
            :price, :high_52w, :low_52w,
            :pe_ttm, :ps_current, :pb_fbs, :debt_to_equity, :roe,
            :stoch_k, :stoch_d, :adx, :adx_plus_di, :adx_minus_di,
            :cci_20, :williams_r, :mfi, :ao, :uo, :momentum, :roc,
            :bb_lower, :bb_upper,
            :vwap, :sma_20, :sma_50, :sma_200,
            :perf_1w, :perf_1m, :perf_3m, :perf_6m, :perf_ytd, :perf_1y, :perf_5y,
            :volatility_d, :volatility_w, :volatility_m, :beta_1y,
            :eps_diluted_ttm, :eps_growth_yoy, :revenue_ttm, :revenue_growth_yoy,
            :market_cap, :enterprise_value,
            :gross_margin, :operating_margin, :net_margin,
            :dividend_yield, :payout_ratio, :book_value_per_share,
            :current_ratio, :quick_ratio, :roa, :roic,
            :ev_ebitda, :ev_sales, :price_fcf, :peg_ratio,
            :shares_outstanding, :float_shares,
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
            macd_signal      = EXCLUDED.macd_signal,
            macd_hist        = EXCLUDED.macd_hist,
            ema_20           = EXCLUDED.ema_20,
            ema_50           = EXCLUDED.ema_50,
            ema_200          = EXCLUDED.ema_200,
            atr_14           = EXCLUDED.atr_14,
            volume           = EXCLUDED.volume,
            volume_10d_avg   = EXCLUDED.volume_10d_avg,
            avg_volume_30d   = EXCLUDED.avg_volume_30d,
            avg_volume_60d   = EXCLUDED.avg_volume_60d,
            rel_volume_10d   = EXCLUDED.rel_volume_10d,
            price            = EXCLUDED.price,
            high_52w         = EXCLUDED.high_52w,
            low_52w          = EXCLUDED.low_52w,
            pe_ttm           = EXCLUDED.pe_ttm,
            ps_current       = EXCLUDED.ps_current,
            pb_fbs           = EXCLUDED.pb_fbs,
            debt_to_equity   = EXCLUDED.debt_to_equity,
            roe              = EXCLUDED.roe,
            stoch_k          = EXCLUDED.stoch_k,
            stoch_d          = EXCLUDED.stoch_d,
            adx              = EXCLUDED.adx,
            adx_plus_di      = EXCLUDED.adx_plus_di,
            adx_minus_di     = EXCLUDED.adx_minus_di,
            cci_20           = EXCLUDED.cci_20,
            williams_r       = EXCLUDED.williams_r,
            mfi              = EXCLUDED.mfi,
            ao               = EXCLUDED.ao,
            uo               = EXCLUDED.uo,
            momentum         = EXCLUDED.momentum,
            roc              = EXCLUDED.roc,
            bb_lower         = EXCLUDED.bb_lower,
            bb_upper         = EXCLUDED.bb_upper,
            vwap             = EXCLUDED.vwap,
            sma_20           = EXCLUDED.sma_20,
            sma_50           = EXCLUDED.sma_50,
            sma_200          = EXCLUDED.sma_200,
            perf_1w          = EXCLUDED.perf_1w,
            perf_1m          = EXCLUDED.perf_1m,
            perf_3m          = EXCLUDED.perf_3m,
            perf_6m          = EXCLUDED.perf_6m,
            perf_ytd         = EXCLUDED.perf_ytd,
            perf_1y          = EXCLUDED.perf_1y,
            perf_5y          = EXCLUDED.perf_5y,
            volatility_d     = EXCLUDED.volatility_d,
            volatility_w     = EXCLUDED.volatility_w,
            volatility_m     = EXCLUDED.volatility_m,
            beta_1y          = EXCLUDED.beta_1y,
            eps_diluted_ttm  = EXCLUDED.eps_diluted_ttm,
            eps_growth_yoy   = EXCLUDED.eps_growth_yoy,
            revenue_ttm      = EXCLUDED.revenue_ttm,
            revenue_growth_yoy = EXCLUDED.revenue_growth_yoy,
            market_cap       = EXCLUDED.market_cap,
            enterprise_value = EXCLUDED.enterprise_value,
            gross_margin     = EXCLUDED.gross_margin,
            operating_margin = EXCLUDED.operating_margin,
            net_margin       = EXCLUDED.net_margin,
            dividend_yield   = EXCLUDED.dividend_yield,
            payout_ratio     = EXCLUDED.payout_ratio,
            book_value_per_share = EXCLUDED.book_value_per_share,
            current_ratio    = EXCLUDED.current_ratio,
            quick_ratio      = EXCLUDED.quick_ratio,
            roa              = EXCLUDED.roa,
            roic             = EXCLUDED.roic,
            ev_ebitda        = EXCLUDED.ev_ebitda,
            ev_sales         = EXCLUDED.ev_sales,
            price_fcf        = EXCLUDED.price_fcf,
            peg_ratio        = EXCLUDED.peg_ratio,
            shares_outstanding = EXCLUDED.shares_outstanding,
            float_shares     = EXCLUDED.float_shares,
            raw_payload      = EXCLUDED.raw_payload,
            updated_at       = NOW()
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

        records = df.to_dict(orient="records")
        rows = []
        for rec in records:
            sym: str = str(rec.get("ticker", ""))
            recommend_all = rec.get("Recommend.All")
            vol = rec.get("volume")
            vol10d = rec.get("average_volume_10d_calc")
            rows.append(
                {
                    "symbol": sym,
                    "instrument_id": inst_map.get(sym),
                    "tv_recommend_label": _label(recommend_all),
                    "recommend_all": recommend_all,
                    "recommend_ma": rec.get("Recommend.MA"),
                    "recommend_other": rec.get("Recommend.Other"),
                    "rsi_14": rec.get("RSI"),
                    "macd_macd": rec.get("MACD.macd"),
                    "ema_20": rec.get("EMA20"),
                    "ema_50": rec.get("EMA50"),
                    "ema_200": rec.get("EMA200"),
                    "atr_14": rec.get("ATR"),
                    "volume": int(rec["volume"]) if bool(pd.notna(vol)) else None,
                    "volume_10d_avg": (
                        int(rec["average_volume_10d_calc"]) if bool(pd.notna(vol10d)) else None
                    ),
                    "price": rec.get("close"),
                    "high_52w": rec.get("High.All"),
                    "low_52w": rec.get("Low.All"),
                    "pe_ttm": rec.get("price_earnings_ttm"),
                    "ps_current": rec.get("price_sales_current"),
                    "pb_fbs": rec.get("price_book_fbs"),
                    "debt_to_equity": rec.get("debt_to_equity"),
                    "roe": rec.get("return_on_equity"),
                    # Migration 119: MACD additional
                    "macd_signal": rec.get("MACD.signal"),
                    "macd_hist": rec.get("MACD.hist"),
                    # Migration 119: Stochastic + ADX
                    "stoch_k": rec.get("Stoch.K"),
                    "stoch_d": rec.get("Stoch.D"),
                    "adx": rec.get("ADX"),
                    "adx_plus_di": rec.get("ADX+DI"),
                    "adx_minus_di": rec.get("ADX-DI"),
                    # Migration 119: Other oscillators
                    "cci_20": rec.get("CCI20"),
                    "williams_r": rec.get("W.R"),
                    "mfi": rec.get("MFI"),
                    "ao": rec.get("AO"),
                    "uo": rec.get("UO"),
                    "momentum": rec.get("Mom"),
                    "roc": rec.get("ROC"),
                    # Migration 119: Bollinger
                    "bb_lower": rec.get("BB.lower"),
                    "bb_upper": rec.get("BB.upper"),
                    # Migration 119: MAs
                    "vwap": rec.get("VWAP"),
                    "sma_20": rec.get("SMA20"),
                    "sma_50": rec.get("SMA50"),
                    "sma_200": rec.get("SMA200"),
                    # Migration 119: Performance
                    "perf_1w": rec.get("Perf.W"),
                    "perf_1m": rec.get("Perf.1M"),
                    "perf_3m": rec.get("Perf.3M"),
                    "perf_6m": rec.get("Perf.6M"),
                    "perf_ytd": rec.get("Perf.YTD"),
                    "perf_1y": rec.get("Perf.Y"),
                    "perf_5y": rec.get("Perf.5Y"),
                    # Migration 119: Volatility / beta
                    "volatility_d": rec.get("Volatility.D"),
                    "volatility_w": rec.get("Volatility.W"),
                    "volatility_m": rec.get("Volatility.M"),
                    "beta_1y": rec.get("Beta.1Y"),
                    # Migration 119: Volume metrics
                    "rel_volume_10d": rec.get("relative_volume_10d_calc"),
                    "avg_volume_30d": (
                        int(rec["average_volume_30d_calc"])
                        if bool(pd.notna(rec.get("average_volume_30d_calc")))
                        else None
                    ),
                    "avg_volume_60d": (
                        int(rec["average_volume_60d_calc"])
                        if bool(pd.notna(rec.get("average_volume_60d_calc")))
                        else None
                    ),
                    # Migration 119: Expanded fundamentals
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
                    "raw_payload": str(rec),
                }
            )

        _upsert_rows(rows, engine)
        total_upserted += len(rows)
        log.info("tv_screener.batch_done", batch_start=i, rows=len(rows))

    log.info("tv_screener.complete", total_upserted=total_upserted)
    if total_upserted == 0 and symbols:
        raise RuntimeError("tv_screener: zero rows upserted — all batches failed or returned empty")
