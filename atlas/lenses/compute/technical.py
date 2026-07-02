"""Technical lens scorer — pure function, no I/O.

Computes a 0-100 composite from TWO subcomponents (FM 2026-06-30 — Volatility-contraction
and Volume removed; RSI dropped from Trend):
  Trend (0-25, EMA stack + price-vs-EMA200 + slope, rescaled ×1.25)
  Relative Strength (0-25, EMA structure: EMA50>EMA200 → 10, EMA21>EMA50 → 15)
Lens = mean(present subs) × 4 = (Trend + RS) × 2.
"""  # allow-large: dense scoring sub-functions

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_Q2 = Decimal("0.01")
_cap = lambda v: max(0, min(25, v))


@dataclass(frozen=True, slots=True)
class TechnicalResult:
    trend: Decimal | None
    relative_strength: Decimal | None
    vol_contraction: Decimal | None
    volume: Decimal | None
    score: Decimal | None
    evidence: dict[str, Any]


def _score_trend(
    ema_21: float | None,
    ema_50: float | None,
    ema_200: float | None,
    price: float | None,
    rsi_14: float | None,
    ret_1w: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    # Young stocks lack EMA200 — still score on EMA21/50 + slope (the EMA200-dependent terms
    # just don't fire). Need at least EMA21 + EMA50 + price.
    if ema_21 is None or ema_50 is None or price is None:
        return None, {"trend": "insufficient data"}
    pts, ev = 0, {}
    has200 = ema_200 is not None
    # EMA alignment
    if has200 and ema_21 > ema_50 > ema_200:
        pts += th.get("ema_aligned_all", 10)
        ev["ema_alignment"] = "bullish"
    elif ema_21 > ema_50 or (has200 and ema_50 > ema_200):
        pts += th.get("ema_aligned_partial", 6)
        ev["ema_alignment"] = "partial"
    else:
        ev["ema_alignment"] = "inverted"
    # Price vs EMA-200 (only when EMA200 exists)
    if has200:
        pct = (price - ema_200) / ema_200 if ema_200 != 0 else 0
        if pct > th.get("price_above_ema200_strong", 0.05):
            pts += 5
            ev["price_vs_ema200"] = "strong_above"
        elif pct > 0:
            pts += 3
            ev["price_vs_ema200"] = "above"
        elif pct > th.get("price_below_ema200_weak", -0.05):
            pts += 1
            ev["price_vs_ema200"] = "slightly_below"
        else:
            ev["price_vs_ema200"] = "well_below"
    # EMA-21 slope proxy
    if ret_1w is not None:
        if ret_1w > th.get("slope_strong_pct", 0.02):
            pts += 5
            ev["ema21_slope"] = "steep_up"
        elif ret_1w > 0:
            pts += 3
            ev["ema21_slope"] = "up"
        elif ret_1w < th.get("slope_weak_pct", -0.02):
            ev["ema21_slope"] = "steep_down"
        else:
            pts += 1
            ev["ema21_slope"] = "flat_down"
    # RSI term REMOVED (FM 2026-06-30). The remaining components (EMA stack + price-vs-EMA200
    # + slope) max out at 20; rescale ×1.25 so a perfect trend still tops out at 25.
    pts = pts * 1.25
    ev["rescaled_x1_25"] = True
    return Decimal(_cap(pts)).quantize(_Q2), ev


def _score_relative_strength(
    ema_21: float | None,
    ema_50: float | None,
    ema_200: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    """RS sub-score (0-25) — EMA-STRUCTURE based (FM 2026-06-30).

    Redefined from the old return-vs-benchmark RS to a pure moving-average alignment
    read: a stock in a healthy uptrend has its EMAs stacked. EMA50 > EMA200 (golden
    cross / long-term up) → 10; EMA21 > EMA50 (medium-term up) → 15. Max 25. Needs all
    three EMAs; returns None (no data) if any is missing.
    """
    # Young stocks (recent IPOs) lack a 200-day EMA — they should STILL score, not blank.
    # Need at least EMA21 + EMA50; the golden-cross term simply can't fire until EMA200 exists.
    if ema_21 is None or ema_50 is None:
        return None, {"rs": "no ema data"}
    pts = 0
    golden = ema_200 is not None and ema_50 > ema_200
    fast = ema_21 > ema_50
    if golden:
        pts += int(th.get("rs_golden_cross_pts", 10))
    if fast:
        pts += int(th.get("rs_fast_above_mid_pts", 15))
    ev = {
        "ema50_gt_ema200": golden,
        "ema21_gt_ema50": fast,
        "rs_pts": pts,
        "ema200": ema_200 is not None,
    }
    return Decimal(pts).quantize(_Q2), ev


def _score_vol_contraction(
    atr_14: float | None,
    price: float | None,
    bb_width: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if atr_14 is None or price is None or price <= 0:
        return None, {"vol": "insufficient data"}
    atr_pct = atr_14 / price
    ev: dict[str, Any] = {"atr_pct": round(atr_pct, 4)}
    bands = [
        (th.get("atr_pct_very_tight", 0.02), 25, "very_tight"),
        (th.get("atr_pct_tight", 0.03), 20, "tight"),
        (th.get("atr_pct_moderate", 0.04), 15, "moderate"),
        (th.get("atr_pct_wide", 0.06), 10, "wide"),
    ]
    pts = 5
    ev["atr_band"] = "very_wide"
    for cutoff, score, label in bands:
        if atr_pct < cutoff:
            pts = score
            ev["atr_band"] = label
            break
    # Bollinger bonus
    if bb_width is not None and bb_width < th.get("bb_narrow_threshold", 0.10):
        pts = _cap(pts + th.get("bb_narrow_bonus", 5))
        ev["bb_bonus"] = True
    return Decimal(pts).quantize(_Q2), ev


def _score_volume(
    vol_ratio_30d: float | None,
    vol_ratio_60d: float | None,
    pos_52w: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    """Volume / participation sub-score from PIT fields in technical_daily.

    vol_ratio_30d = today's volume ÷ its 30-session SMA; vol_ratio_60d ÷ 60-session
    SMA (both derived as-of in scripts/foundation/technicals.py — NOT the leaky
    tv_metrics snapshot). pos_52w = 52-week price position 0-100. Replaces the old
    (rel_volume_10d, avg_volume_30d, avg_volume_60d, price, high_52w, low_52w)
    inputs, which came from the today-snapshot and made this sub non-PIT.
    """
    pts, ev, has = 0, {}, False
    # Relative volume — today vs its 30-session average (participation).
    if vol_ratio_30d is not None:
        has = True
        if vol_ratio_30d > th.get("relvol_high", 2.0):
            pts += 10
            ev["rel_vol"] = "high"
        elif vol_ratio_30d > th.get("relvol_above", 1.2):
            pts += 7
            ev["rel_vol"] = "above_avg"
        elif vol_ratio_30d > th.get("relvol_normal", 0.8):
            pts += 5
            ev["rel_vol"] = "normal"
        else:
            pts += 2
            ev["rel_vol"] = "low" if vol_ratio_30d < th.get("relvol_low", 0.5) else "below_avg"
    # Volume trend: SMA30/SMA60 = vol_ratio_60d / vol_ratio_30d. >1 ⇒ recent volume
    # accelerating (accumulation); <1 ⇒ fading (distribution).
    if vol_ratio_30d and vol_ratio_60d and vol_ratio_30d > 0:
        has = True
        ratio = vol_ratio_60d / vol_ratio_30d
        ev["vol_trend_ratio"] = round(ratio, 4)
        if ratio > th.get("vol_accum_ratio", 1.2):
            pts += 8
            ev["vol_trend"] = "accumulation"
        elif ratio > 1.0:
            pts += 5
            ev["vol_trend"] = "rising"
        elif ratio < th.get("vol_distrib_ratio", 0.8):
            pts += 2
            ev["vol_trend"] = "distribution"
        else:
            pts += 3
            ev["vol_trend"] = "flat"
    # 52-week position (pos_52w is 0-100, PIT-derived).
    if pos_52w is not None:
        has = True
        pos = pos_52w / 100.0
        ev["52w_position"] = round(pos, 4)
        if pos >= 0.80:
            pts += 7
            ev["52w_zone"] = "near_high"
        elif pos >= 0.20:
            pts += 5
            ev["52w_zone"] = "middle"
        else:
            pts += 3
            ev["52w_zone"] = "near_low"
    if not has:
        return None, {"volume": "no data"}
    return Decimal(_cap(pts)).quantize(_Q2), ev


def score_technical(
    ema_21: float | None,
    ema_50: float | None,
    ema_200: float | None,
    rsi_14: float | None,
    price: float | None,
    ret_1w: float | None,
    rs_1m_n500: float | None,
    rs_3m_n500: float | None,
    rs_6m_n500: float | None,
    rs_12m_n500: float | None,
    atr_14: float | None,
    bb_width: float | None,
    vol_ratio_30d: float | None,
    vol_ratio_60d: float | None,
    pos_52w: float | None,
    thresholds: dict[str, Any],
    rs_1m_sector: float | None = None,
    rs_3m_sector: float | None = None,
    rs_6m_sector: float | None = None,
    rs_12m_sector: float | None = None,
) -> TechnicalResult:
    """Score a single stock on the Technical lens (0-100).

    Pure function — no I/O, no DB access.  All inputs are pre-loaded scalars.
    PIT inputs (Loop C): *price* is the as-of adjusted close; atr_14/bb_width/
    vol_ratio_30d/vol_ratio_60d/pos_52w/rs_*_sector come from technical_daily on
    the scoring date — NOT the tv_metrics snapshot that previously leaked here.
    """
    th = thresholds
    trend, t_ev = _score_trend(ema_21, ema_50, ema_200, price, rsi_14, ret_1w, th)
    # RS is now EMA-structure based; Volatility-contraction and Volume are REMOVED from the
    # Technical lens (FM 2026-06-30). With two present sub-scores (each 0-25), the lens is
    # mean(trend, rs) × 4 = (trend + rs) × 2 → 0-100.
    rs, rs_ev = _score_relative_strength(ema_21, ema_50, ema_200, th)
    vc, vol = None, None
    evidence = {"trend": t_ev, "relative_strength": rs_ev}
    subs = [s for s in (trend, rs) if s is not None]
    composite = (
        (sum(subs) / len(subs) * Decimal(4)).quantize(_Q2, rounding=ROUND_HALF_UP) if subs else None
    )
    return TechnicalResult(
        trend=trend,
        relative_strength=rs,
        vol_contraction=vc,
        volume=vol,
        score=composite,
        evidence=evidence,
    )
