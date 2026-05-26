from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta  # type: ignore[import-untyped]  # noqa: F401 — registers df.ta accessor
import structlog
from scipy.signal import find_peaks

log = structlog.get_logger()


@dataclass
class TechnicalSnapshot:
    rsi_14: Decimal
    # 'bullish_cross' | 'bearish_cross' | 'above_zero' | 'below_zero' | 'neutral'
    macd_signal: str
    ema_alignment: str  # 'all_bullish' | 'above_200' | 'mixed' | 'all_bearish'
    hh_hl_state: str  # 'confirmed_uptrend' | 'hh_only' | 'hl_only' | 'downtrend' | 'neutral'
    volume_vs_avg: Decimal  # current_vol / sma_vol_20
    pattern_label: str


def _fetch_ohlcv(ticker: str, lookback_days: int, conn: Any) -> pd.DataFrame:
    """Fetch OHLCV from public.de_equity_ohlcv (the NSE Kite-sourced price table).
    Joins through atlas_universe_stocks to resolve ticker symbol to instrument_id.
    """
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT o.date, o.open, o.high, o.low, o.close, o.volume "
            "FROM public.de_equity_ohlcv o "
            "JOIN atlas.atlas_universe_stocks u ON u.instrument_id = o.instrument_id "
            "WHERE u.symbol = :ticker AND u.effective_to IS NULL "
            "ORDER BY o.date DESC LIMIT :n"
        ),
        {"ticker": ticker, "n": lookback_days},
    ).fetchall()
    if not rows:
        raise ValueError(f"No OHLCV data for {ticker}")
    df = pd.DataFrame(
        [
            dict(zip(["date", "open", "high", "low", "close", "volume"], r, strict=False))
            for r in rows
        ]
    )
    return df.sort_values("date").reset_index(drop=True)


def _classify_ema_alignment(close: float, ema20: float, ema50: float, ema200: float) -> str:
    if close > ema20 > ema50 > ema200:
        return "all_bullish"
    if close > ema200:
        return "above_200"
    if close < ema20 < ema50 < ema200:
        return "all_bearish"
    return "mixed"


def _classify_macd(macd: float, signal: float, prev_macd: float, prev_signal: float) -> str:
    crossed_up = prev_macd < prev_signal and macd > signal
    crossed_dn = prev_macd > prev_signal and macd < signal
    if crossed_up:
        return "bullish_cross"
    if crossed_dn:
        return "bearish_cross"
    if macd > 0:
        return "above_zero"
    if macd < 0:
        return "below_zero"
    return "neutral"


def _classify_hh_hl(hh: bool, hl: bool) -> str:
    if hh and hl:
        return "confirmed_uptrend"
    if hh:
        return "hh_only"
    if hl:
        return "hl_only"
    return "downtrend"


def compute_technical_snapshot(ticker: str, conn: Any) -> TechnicalSnapshot:
    df = _fetch_ohlcv(ticker, lookback_days=300, conn=conn)

    na_count = df["close"].isna().sum()
    if na_count:
        log.warning("ohlcv_gaps_technical", ticker=ticker, count=int(na_count))
        df["close"] = df["close"].ffill()

    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.sma(length=20, close="volume", prefix="vol", append=True)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    rsi_col = "RSI_14"
    macd_col, signal_col = "MACD_12_26_9", "MACDs_12_26_9"
    ema20_col, ema50_col, ema200_col = "EMA_20", "EMA_50", "EMA_200"
    vol_sma_col = "vol_SMA_20"

    rsi_val = float(last[rsi_col]) if not pd.isna(last[rsi_col]) else 50.0

    macd_sig = _classify_macd(
        macd=float(last[macd_col] or 0),
        signal=float(last[signal_col] or 0),
        prev_macd=float(prev[macd_col] or 0),
        prev_signal=float(prev[signal_col] or 0),
    )

    ema_align = _classify_ema_alignment(
        close=float(last["close"]),
        ema20=float(last[ema20_col] or last["close"]),
        ema50=float(last[ema50_col] or last["close"]),
        ema200=float(last[ema200_col] or last["close"]),
    )

    close_arr = df["close"].to_numpy(dtype=float)
    highs_idx, _ = find_peaks(close_arr, distance=10, prominence=0.02)
    lows_idx, _ = find_peaks(-close_arr, distance=10, prominence=0.02)

    hh = len(highs_idx) >= 2 and df["close"].iloc[highs_idx[-1]] > df["close"].iloc[highs_idx[-2]]
    hl = len(lows_idx) >= 2 and df["close"].iloc[lows_idx[-1]] > df["close"].iloc[lows_idx[-2]]
    hh_hl = _classify_hh_hl(bool(hh), bool(hl))

    vol_avg = float(last[vol_sma_col]) if not pd.isna(last.get(vol_sma_col, np.nan)) else 1.0
    vol_ratio = float(last["volume"]) / vol_avg if vol_avg > 0 else 1.0

    pattern = _build_pattern_label(ema_align, hh_hl, rsi_val)

    return TechnicalSnapshot(
        rsi_14=Decimal(str(round(rsi_val, 2))),
        macd_signal=macd_sig,
        ema_alignment=ema_align,
        hh_hl_state=hh_hl,
        volume_vs_avg=Decimal(str(round(vol_ratio, 4))),
        pattern_label=pattern,
    )


def _build_pattern_label(ema_alignment: str, hh_hl_state: str, rsi: float) -> str:
    parts = []
    if hh_hl_state == "confirmed_uptrend":
        parts.append("Confirmed uptrend (HH+HL)")
    elif hh_hl_state == "hh_only":
        parts.append("Higher high — awaiting HL")
    if ema_alignment == "all_bullish":
        parts.append("all EMAs aligned bullish")
    elif ema_alignment == "above_200":
        parts.append("above 200 EMA")
    if rsi > 60:
        parts.append(f"RSI strong ({rsi:.0f})")
    return "; ".join(parts) if parts else "No clear pattern"
