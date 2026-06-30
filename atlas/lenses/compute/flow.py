"""Flow lens scorer — DELIVERY ONLY (FM 2026-06-30).

Pure function, no I/O. Flow = the delivery-% accumulation sub-score (sustained level +
30d/60d trend + up/down-day asymmetry). Promoter and institutional/smart-money signals
were removed from the lens; their scorers remain below only because the pipeline still
passes those inputs, but they no longer contribute to the score. None below the
liquidity floor (no 30d delivery average), never a stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlowResult:
    promoter: Decimal | None
    institutional: Decimal | None
    smart_money: Decimal | None  # raw -10 to +15
    accumulation: Decimal | None  # delivery-% accumulation 0-100; None below liquidity floor
    score: Decimal | None
    evidence: dict[str, Any]


# ---------------------------------------------------------------------------
# Constants — base weights & caps for promoter subcomponent
# ---------------------------------------------------------------------------

_BASE_WEIGHTS: dict[str, int] = {
    "open_market_buy": 9,
    "warrant_allotment": 7,
    "creeping_acquisition": 7,
    "pledge_decrease": 6,
    "preferential_allotment": 3,
    "esop_exercise": 2,
    "off_market": 1,
    "open_market_sell": -5,
    "pledge_increase": -8,
}

_TYPE_CAPS: dict[str, tuple[float, float]] = {
    "open_market_buy": (-999, 25),
    "warrant_allotment": (-999, 20),
    "creeping_acquisition": (-999, 20),
    "pledge_decrease": (-999, 15),
    "open_market_sell": (-20, 999),
    "pledge_increase": (-20, 999),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Promoter subcomponent
# ---------------------------------------------------------------------------


def _score_promoter(
    transactions: list[dict[str, Any]],
    shareholding_current: dict[str, Any] | None,
    thresholds: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Return (raw 0-100, evidence dict) for the promoter subcomponent.

    Uses a base score from promoter holding level (skin-in-the-game) plus
    transaction-level signals.
    """
    # Base score from promoter holding level (0-30 range)
    holding_base = 0.0
    promo_pct = float(shareholding_current.get("promoter_pct") or 0) if shareholding_current else 0
    if promo_pct >= 70:
        holding_base = 30.0
    elif promo_pct >= 55:
        holding_base = 22.0
    elif promo_pct >= 40:
        holding_base = 15.0
    elif promo_pct >= 25:
        holding_base = 8.0
    elif promo_pct > 0:
        holding_base = 3.0

    if not transactions:
        return _clamp(holding_base, 0, 100), {
            "reason": "shareholding level only",
            "promoter_pct": promo_pct,
            "base": holding_base,
        }

    type_totals: dict[str, float] = {}
    buy_count = 0
    details: list[dict[str, Any]] = []

    for txn in transactions:
        sig = (txn.get("signal_type") or "").lower().strip()
        base = _BASE_WEIGHTS.get(sig)
        if base is None:
            continue

        value_cr = float(txn.get("value_cr") or 0)
        pledge_pct = float(txn.get("pledge_pct_after") or 100)

        multiplier = 1.0

        if sig == "open_market_buy":
            buy_count += 1
            if value_cr >= float(thresholds.get("flow_buy_amp_t2", 5)):
                multiplier *= 1.3 * 1.2
            elif value_cr >= float(thresholds.get("flow_buy_amp_t1", 2)):
                multiplier *= 1.3

        if sig == "pledge_decrease" and pledge_pct < float(
            thresholds.get("flow_pledge_low_pct", 2)
        ):
            multiplier *= 1.5

        score = base * multiplier
        type_totals[sig] = type_totals.get(sig, 0.0) + score
        details.append({"signal": sig, "base": base, "mult": round(multiplier, 2)})

    # Buy-count amplifier applied after accumulation
    if buy_count >= int(thresholds.get("flow_buy_count_amp", 5)):
        type_totals["open_market_buy"] = type_totals.get("open_market_buy", 0.0) * 1.2

    # Apply per-type caps
    for sig, total in list(type_totals.items()):
        lo, hi = _TYPE_CAPS.get(sig, (-999, 999))
        type_totals[sig] = _clamp(total, lo, hi)

    raw = _clamp(holding_base + sum(type_totals.values()), 0, 100)

    evidence = {
        "buy_count": buy_count,
        "type_totals": {k: round(v, 2) for k, v in type_totals.items()},
        "transaction_count": len(details),
        "promoter_pct": promo_pct,
        "base": holding_base,
    }
    return raw, evidence


# ---------------------------------------------------------------------------
# Institutional / smart-money subcomponent
# ---------------------------------------------------------------------------


def _score_institutional(
    sh_current: dict[str, Any] | None,
    sh_previous: dict[str, Any] | None,
    bulk_deals: list[dict[str, Any]],
    thresholds: dict[str, Any],
    mf_delta: float | None = None,
) -> tuple[float, dict[str, Any]]:
    """Return (raw -10 to +15, evidence dict) for smart-money subcomponent.

    Primary real signal = the matched-fund mutual-fund MoM weight delta (mf_delta,
    in percentage points; see load_mf_flow). It is continuous, so the institutional
    sub-score becomes a real distribution instead of the old ~8 discrete buckets.
    Bulk-deal + shareholding-QoQ signals add on top. mf_delta None ⇒ no MF data for
    this name ⇒ contributes nothing (genuine neutral, never a stub).
    """
    total = 0.0
    signals: list[str] = []

    # Mutual-fund matched accumulation/distribution (continuous, the main signal).
    if mf_delta is not None:
        scale = float(thresholds.get("flow_mf_scale", 1.0))
        mf_pts = _clamp(mf_delta * scale, -10.0, 12.0)
        total += mf_pts
        signals.append(f"mf_mom_delta={round(mf_delta, 2)}pp")

    # Superstar / institutional bulk-deal signals
    for deal in bulk_deals:
        buy_sell = (deal.get("buy_sell") or "").lower()
        is_super = bool(deal.get("is_superstar"))
        is_inst = bool(deal.get("is_institutional"))

        if is_super:
            if buy_sell == "buy":
                # Distinguish new entry vs increased — simple heuristic:
                # if no previous holding info treat as new entry
                total += float(thresholds.get("flow_superstar_new", 10))
                signals.append("superstar_new_entry")
            elif buy_sell == "sell":
                total += float(thresholds.get("flow_superstar_exit", -8))
                signals.append("superstar_exited")
        elif is_inst:
            if buy_sell == "buy":
                total += float(thresholds.get("flow_inst_bulk_buy", 5))
                signals.append("institutional_bulk_buy")
            elif buy_sell == "sell":
                total += float(thresholds.get("flow_inst_bulk_sell", -5))
                signals.append("institutional_bulk_sell")

    # Shareholding QoQ change
    if sh_current and sh_previous:
        curr_pct = float(sh_current.get("promoter_pct") or 0)
        prev_pct = float(sh_previous.get("promoter_pct") or 0)
        # Institutional = 100 - promoter (simplified proxy)
        inst_curr = 100.0 - curr_pct
        inst_prev = 100.0 - prev_pct
        delta = inst_curr - inst_prev

        strong_thr = float(thresholds.get("flow_inst_strong_pp", 1.0))
        mod_thr = float(thresholds.get("flow_inst_mod_pp", 0.3))
        exit_thr = float(thresholds.get("flow_inst_exit_pp", -0.5))

        if delta >= strong_thr:
            total += 6
            signals.append("inst_accumulation_strong")
        elif delta >= mod_thr:
            total += 3
            signals.append("inst_accumulation_moderate")
        elif delta <= exit_thr:
            total -= 4
            signals.append("inst_exit")
        # Mild signal for very small changes
        elif delta > 0.1:
            total += 1
            signals.append("inst_trickle_in")
        elif delta < -0.1:
            total -= 1
            signals.append("inst_trickle_out")

    raw = _clamp(total, -10, 15)
    return raw, {"signals": signals, "raw_total": round(total, 2)}


# ---------------------------------------------------------------------------
# Accumulation subcomponent (delivery-%)
# ---------------------------------------------------------------------------


def _score_accumulation(
    delivery: dict[str, Any] | None,
    thresholds: dict[str, Any],
) -> tuple[float | None, dict[str, Any]]:
    """Delivery-% accumulation sub-score (0-100), or None below the liquidity floor.

    MEDIUM-TERM by construction (matches Flow's quarterly cadence + the 3-6m atom
    horizon, NOT daily noise): it reads SMOOTHED quantities only — this month's delivery
    average vs the prior two-month average (is structural accumulation building?), the
    sustained level, and the month-long up/down-day asymmetry (delivery clustering on
    up-days = real buying that settles). It deliberately does NOT use today's raw
    delivery_pct, so Flow stays a slow conviction signal that merely fills the gap
    between quarterly shareholding updates. Liquidity floor = trailing-average
    availability (no avg_30d -> None, never a stub). Cutoffs in atlas_thresholds.
    """
    if not delivery:
        return None, {"reason": "no delivery data"}
    avg30 = delivery.get("delivery_avg_30d")
    if avg30 is None or float(avg30) <= 0:
        return None, {"reason": "illiquid_or_insufficient_history"}
    avg30 = float(avg30)
    avg60 = delivery.get("delivery_avg_60d")
    asym = delivery.get("delivery_updown_asym")
    # Smoothed trend: recent-month avg vs prior two-month avg (weekly/monthly cadence).
    trend = (avg30 / float(avg60) - 1.0) if (avg60 and float(avg60) > 0) else None
    score = 50.0
    # sustained delivery LEVEL (sticky holders vs traders)
    if avg30 >= float(thresholds.get("flow_deliv_high_pct", 60)):
        score += 8.0
    elif avg30 <= float(thresholds.get("flow_deliv_low_pct", 25)):
        score -= 8.0
    # TREND: 30d avg vs 60d avg (accumulation building / fading) — smooth, medium-term
    t_strong = float(thresholds.get("flow_deliv_trend_strong", 0.12))
    t_mod = float(thresholds.get("flow_deliv_trend_mod", 0.05))
    if trend is not None:
        if trend >= t_strong:
            score += 20.0
        elif trend >= t_mod:
            score += 10.0
        elif trend <= -t_strong:
            score -= 20.0
        elif trend <= -t_mod:
            score -= 10.0
    # UP/DOWN-day asymmetry (the accumulation signature)
    a_strong = float(thresholds.get("flow_deliv_asym_strong", 8))
    a_mod = float(thresholds.get("flow_deliv_asym_mod", 3))
    if asym is not None:
        a = float(asym)
        if a >= a_strong:
            score += 15.0
        elif a >= a_mod:
            score += 8.0
        elif a <= -a_strong:
            score -= 15.0
        elif a <= -a_mod:
            score -= 8.0
    return _clamp(score, 0.0, 100.0), {
        "avg30": round(float(avg30), 2),
        "trend": None if trend is None else round(float(trend), 4),
        "asym": None if asym is None else round(float(asym), 2),
    }


# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


def score_flow(
    insider_transactions: list[dict[str, Any]],
    shareholding_current: dict[str, Any] | None,
    shareholding_previous: dict[str, Any] | None,
    bulk_deals: list[dict[str, Any]],
    thresholds: dict[str, Any],
    delivery: dict[str, Any] | None = None,
    mf_delta: float | None = None,
) -> FlowResult:
    """Score the Flow lens — DELIVERY ONLY (FM 2026-06-30).

    Promoter and smart-money/institutional sub-components were REMOVED from the Flow lens.
    Flow is now exactly the delivery-% accumulation sub-score (level + 30d/60d trend +
    up/down-day asymmetry; see _score_accumulation). A name with no delivery history (below
    the liquidity floor) has NO flow reading → None, never a stub. The other arguments are
    retained for signature compatibility with the pipeline but are no longer scored.
    """
    accum_raw, accum_ev = _score_accumulation(delivery, thresholds)
    if accum_raw is None:
        return FlowResult(
            promoter=None,
            institutional=None,
            smart_money=None,
            accumulation=None,
            score=None,
            evidence={"reason": "no delivery data — flow is delivery-only"},
        )
    score = Decimal(str(round(accum_raw, 2)))
    return FlowResult(
        promoter=None,
        institutional=None,
        smart_money=None,
        accumulation=score,
        score=score,
        evidence={"accumulation": accum_ev, "components": "delivery_only"},
    )
