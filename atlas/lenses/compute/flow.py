"""Flow lens scorer — promoter + institutional / smart-money signals.

Pure function, no I/O.  Consumes insider transactions, shareholding snapshots,
and bulk-deal dicts; emits a FlowResult with promoter, institutional, and
smart_money subcomponents plus a composite 0-100 score.
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
    """Score flow signals into a 0-100 composite.

    Sub-components: promoter (holding level + insider txns), smart-money (bulk deals +
    institutional QoQ), and accumulation (delivery-% trend/asymmetry). The composite is
    a weight-normalised average over the PRESENT sub-components — so a name without a
    delivery signal renormalises over promoter+smart (its prior behaviour), never imputed.
    """
    has_insiders = bool(insider_transactions)
    has_sh = shareholding_current is not None or bool(bulk_deals)
    has_mf = mf_delta is not None
    accum_raw, accum_ev = _score_accumulation(delivery, thresholds)
    has_accum = accum_raw is not None

    if not has_insiders and not has_sh and not has_accum and not has_mf:
        return FlowResult(
            promoter=None,
            institutional=None,
            smart_money=None,
            accumulation=None,
            score=None,
            evidence={"reason": "no flow data"},
        )

    # Promoter + smart-money base — only when there is real insider / shareholding /
    # bulk-deal data (else promoter defaults to 0 and smart to neutral 50, which would
    # wrongly dilute a delivery-only name). Accumulation rides on top when present.
    base_present = has_insiders or has_sh
    has_inst = base_present or has_mf  # smart-money present via bulk/SH OR mutual-fund flow
    w_promo = float(thresholds.get("flow_w_promoter", 0.70))
    w_sm = float(thresholds.get("flow_w_smart_money", 0.30))
    w_accum = float(thresholds.get("flow_w_accumulation", 0.25))

    parts: list[tuple[float, float]] = []
    promo_raw = sm_raw = sm_scaled = None
    promo_ev = sm_ev = {"reason": "no base flow data"}
    if base_present:
        promo_raw, promo_ev = _score_promoter(
            insider_transactions or [], shareholding_current, thresholds
        )
        parts.append((promo_raw, w_promo))
    if has_inst:
        sm_raw, sm_ev = _score_institutional(
            shareholding_current,
            shareholding_previous,
            bulk_deals or [],
            thresholds,
            mf_delta=mf_delta,
        )
        # Rescale smart money [-10, +15] -> [0, 100], centered so 0 -> 50
        sm_scaled = 50.0 + (sm_raw / 15.0) * 50.0 if sm_raw >= 0 else 50.0 + (sm_raw / 10.0) * 50.0
        parts.append((sm_scaled, w_sm))
    if has_accum:
        parts.append((accum_raw, w_accum))

    # Weight-normalised over PRESENT sub-components. With base present and no delivery
    # this is exactly the prior 70/30; delivery only renormalises, never imputes.
    tw = sum(w for _, w in parts)
    composite = _clamp(sum(s * w for s, w in parts) / tw, 0, 100) if tw > 0 else 0.0

    return FlowResult(
        promoter=Decimal(str(round(promo_raw, 2))) if promo_raw is not None else None,
        institutional=Decimal(str(round(sm_scaled, 2))) if sm_scaled is not None else None,
        smart_money=Decimal(str(round(sm_raw, 2))) if sm_raw is not None else None,
        accumulation=Decimal(str(round(accum_raw, 2))) if has_accum else None,
        score=Decimal(str(round(composite, 2))),
        evidence={
            "promoter": promo_ev,
            "smart_money": sm_ev,
            "accumulation": accum_ev,
            "weights": {
                "promoter": w_promo if base_present else 0.0,
                "smart_money": w_sm if base_present else 0.0,
                "accumulation": w_accum if has_accum else 0.0,
            },
        },
    )
