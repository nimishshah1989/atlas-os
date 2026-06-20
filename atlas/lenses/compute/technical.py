"""Technical lens scorer — pure function, no I/O.

Computes a 0-100 composite from four subcomponents:
Trend (0-25) | Relative Strength (0-25) | Vol Contraction (0-25) | Volume (0-25)
"""  # allow-large: four dense scoring sub-functions
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

_Q2 = Decimal("0.01")
_cap = lambda v: max(0, min(25, v))  # noqa: E731


@dataclass(frozen=True, slots=True)
class TechnicalResult:
    trend: Decimal | None
    relative_strength: Decimal | None
    vol_contraction: Decimal | None
    volume: Decimal | None
    score: Decimal | None
    evidence: dict[str, Any]


def _score_trend(
    ema_21: float | None, ema_50: float | None, ema_200: float | None,
    price: float | None, rsi_14: float | None, ret_1w: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if ema_21 is None or ema_50 is None or ema_200 is None or price is None:
        return None, {"trend": "insufficient data"}
    pts, ev = 0, {}
    # EMA alignment
    if ema_21 > ema_50 > ema_200:
        pts += th.get("ema_aligned_all", 10); ev["ema_alignment"] = "bullish"
    elif ema_21 > ema_50 or ema_50 > ema_200:
        pts += th.get("ema_aligned_partial", 6); ev["ema_alignment"] = "partial"
    else:
        ev["ema_alignment"] = "inverted"
    # Price vs EMA-200
    pct = (price - ema_200) / ema_200 if ema_200 != 0 else 0
    if pct > th.get("price_above_ema200_strong", 0.05):
        pts += 5; ev["price_vs_ema200"] = "strong_above"
    elif pct > 0:
        pts += 3; ev["price_vs_ema200"] = "above"
    elif pct > th.get("price_below_ema200_weak", -0.05):
        pts += 1; ev["price_vs_ema200"] = "slightly_below"
    else:
        ev["price_vs_ema200"] = "well_below"
    # EMA-21 slope proxy
    if ret_1w is not None:
        if ret_1w > th.get("slope_strong_pct", 0.02):
            pts += 5; ev["ema21_slope"] = "steep_up"
        elif ret_1w > 0:
            pts += 3; ev["ema21_slope"] = "up"
        elif ret_1w < th.get("slope_weak_pct", -0.02):
            ev["ema21_slope"] = "steep_down"
        else:
            pts += 1; ev["ema21_slope"] = "flat_down"
    # RSI context
    if rsi_14 is not None:
        if 50 <= rsi_14 <= 70:
            pts += 5; ev["rsi_zone"] = "healthy"
        elif 30 <= rsi_14 < 50:
            pts += 3; ev["rsi_zone"] = "recovery"
        elif rsi_14 > 70:
            pts += 2; ev["rsi_zone"] = "extended"
        else:
            pts += 1; ev["rsi_zone"] = "oversold"
    return Decimal(_cap(pts)).quantize(_Q2), ev


def _score_relative_strength(
    rs_1m: float | None, rs_3m: float | None,
    rs_6m: float | None, rs_12m: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    wt = th.get("rs_weights", {"3m": 0.40, "1m": 0.30, "6m": 0.20, "12m": 0.10})
    pairs = [(rs_3m, wt.get("3m", .4)), (rs_1m, wt.get("1m", .3)),
             (rs_6m, wt.get("6m", .2)), (rs_12m, wt.get("12m", .1))]
    total_w, comp = 0.0, 0.0
    for val, w in pairs:
        if val is not None:
            comp += val * w; total_w += w
    if total_w == 0:
        return None, {"rs": "no data"}
    comp /= total_w
    ev: dict[str, Any] = {"rs_composite": round(comp, 4)}
    # Tier mapping — RS values are ratios around 1.0
    tiers = [
        (th.get("rs_top10", 1.15), 25, "top10"),
        (th.get("rs_top20", 1.08), 20, "top20"),
        (th.get("rs_top40", 1.02), 15, "top40"),
        (th.get("rs_bot20", 0.92), 10, "mid"),
        (th.get("rs_bot10", 0.85), 5, "bot20"),
    ]
    pts = 0
    for threshold, score, label in tiers:
        if comp >= threshold:
            pts = score; ev["rs_tier"] = label; break
    else:
        ev["rs_tier"] = "bot10"
    return Decimal(pts).quantize(_Q2), ev


def _score_vol_contraction(
    atr_14: float | None, price: float | None, bb_width: float | None,
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
    pts = 5; ev["atr_band"] = "very_wide"
    for cutoff, score, label in bands:
        if atr_pct < cutoff:
            pts = score; ev["atr_band"] = label; break
    # Bollinger bonus
    if bb_width is not None and bb_width < th.get("bb_narrow_threshold", 0.10):
        pts = _cap(pts + th.get("bb_narrow_bonus", 5)); ev["bb_bonus"] = True
    return Decimal(pts).quantize(_Q2), ev


def _score_volume(
    rel_volume_10d: float | None, avg_volume_30d: float | None,
    avg_volume_60d: float | None, price: float | None,
    high_52w: float | None, low_52w: float | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    pts, ev, has = 0, {}, False
    # Relative volume
    if rel_volume_10d is not None:
        has = True
        if rel_volume_10d > th.get("relvol_high", 2.0):
            pts += 10; ev["rel_vol"] = "high"
        elif rel_volume_10d > th.get("relvol_above", 1.2):
            pts += 7; ev["rel_vol"] = "above_avg"
        elif rel_volume_10d > th.get("relvol_normal", 0.8):
            pts += 5; ev["rel_vol"] = "normal"
        else:
            pts += 2
            ev["rel_vol"] = "low" if rel_volume_10d < th.get("relvol_low", 0.5) else "below_avg"
    # Volume trend (30d vs 60d)
    if avg_volume_30d is not None and avg_volume_60d is not None and avg_volume_60d > 0:
        has = True
        ratio = avg_volume_30d / avg_volume_60d
        ev["vol_trend_ratio"] = round(ratio, 4)
        if ratio > th.get("vol_accum_ratio", 1.2):
            pts += 8; ev["vol_trend"] = "accumulation"
        elif ratio > 1.0:
            pts += 5; ev["vol_trend"] = "rising"
        elif ratio < th.get("vol_distrib_ratio", 0.8):
            pts += 2; ev["vol_trend"] = "distribution"
        else:
            pts += 3; ev["vol_trend"] = "flat"
    # 52-week position
    if price is not None and high_52w is not None and low_52w is not None and high_52w > low_52w:
        has = True
        pos = (price - low_52w) / (high_52w - low_52w)
        ev["52w_position"] = round(pos, 4)
        if pos >= 0.80:
            pts += 7; ev["52w_zone"] = "near_high"
        elif pos >= 0.20:
            pts += 5; ev["52w_zone"] = "middle"
        else:
            pts += 3; ev["52w_zone"] = "near_low"
    if not has:
        return None, {"volume": "no data"}
    return Decimal(_cap(pts)).quantize(_Q2), ev


def score_technical(
    ema_21: float | None, ema_50: float | None, ema_200: float | None,
    rsi_14: float | None,
    price: float | None, high_52w: float | None, low_52w: float | None,
    ret_1w: float | None,
    rs_1m_n500: float | None, rs_3m_n500: float | None,
    rs_6m_n500: float | None, rs_12m_n500: float | None,
    atr_14: float | None, bb_width: float | None,
    volume: float | None,  # noqa: ARG001 — reserved for future use
    avg_volume_30d: float | None, avg_volume_60d: float | None,
    rel_volume_10d: float | None,
    thresholds: dict[str, Any],
) -> TechnicalResult:
    """Score a single stock on the Technical lens (0-100).

    Pure function — no I/O, no DB access.  All inputs are pre-loaded scalars.
    """
    th = thresholds
    trend, t_ev = _score_trend(ema_21, ema_50, ema_200, price, rsi_14, ret_1w, th)
    rs, rs_ev = _score_relative_strength(rs_1m_n500, rs_3m_n500, rs_6m_n500, rs_12m_n500, th)
    vc, vc_ev = _score_vol_contraction(atr_14, price, bb_width, th)
    vol, v_ev = _score_volume(rel_volume_10d, avg_volume_30d, avg_volume_60d, price, high_52w, low_52w, th)
    evidence = {"trend": t_ev, "relative_strength": rs_ev, "vol_contraction": vc_ev, "volume": v_ev}
    subs = [s for s in (trend, rs, vc, vol) if s is not None]
    composite = (sum(subs) / len(subs) * Decimal(4)).quantize(_Q2, rounding=ROUND_HALF_UP) if subs else None
    return TechnicalResult(trend=trend, relative_strength=rs, vol_contraction=vc,
                           volume=vol, score=composite, evidence=evidence)
