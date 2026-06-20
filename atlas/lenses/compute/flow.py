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
    thresholds: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Return (raw 0-100, evidence dict) for the promoter subcomponent."""
    if not transactions:
        return 0.0, {"reason": "no transactions"}

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

    raw = _clamp(sum(type_totals.values()), 0, 100)

    evidence = {
        "buy_count": buy_count,
        "type_totals": {k: round(v, 2) for k, v in type_totals.items()},
        "transaction_count": len(details),
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
) -> tuple[float, dict[str, Any]]:
    """Return (raw -10 to +15, evidence dict) for smart-money subcomponent."""
    total = 0.0
    signals: list[str] = []

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
        mod_thr = float(thresholds.get("flow_inst_mod_pp", 0.5))
        exit_thr = float(thresholds.get("flow_inst_exit_pp", -1.0))

        if delta >= strong_thr:
            total += 6
            signals.append("inst_accumulation_strong")
        elif delta >= mod_thr:
            total += 3
            signals.append("inst_accumulation_moderate")
        elif delta <= exit_thr:
            total -= 4
            signals.append("inst_exit")

    raw = _clamp(total, -10, 15)
    return raw, {"signals": signals, "raw_total": round(total, 2)}


# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


def score_flow(
    insider_transactions: list[dict[str, Any]],
    shareholding_current: dict[str, Any] | None,
    shareholding_previous: dict[str, Any] | None,
    bulk_deals: list[dict[str, Any]],
    thresholds: dict[str, Any],
) -> FlowResult:
    """Score flow signals into a 0-100 composite."""
    has_insiders = bool(insider_transactions)
    has_sh = shareholding_current is not None or bool(bulk_deals)

    if not has_insiders and not has_sh:
        return FlowResult(
            promoter=None,
            institutional=None,
            smart_money=None,
            score=None,
            evidence={"reason": "no flow data"},
        )

    # Promoter subcomponent (0-100)
    promo_raw, promo_ev = _score_promoter(insider_transactions or [], thresholds)

    # Smart-money subcomponent (-10 to +15)
    sm_raw, sm_ev = _score_institutional(
        shareholding_current, shareholding_previous, bulk_deals or [], thresholds,
    )

    # Rescale smart money [-10, +15] -> [0, 100]
    sm_scaled = (sm_raw + 10.0) / 25.0 * 100.0

    # Composite: 70% promoter + 30% smart money
    w_promo = float(thresholds.get("flow_w_promoter", 0.70))
    w_sm = float(thresholds.get("flow_w_smart_money", 0.30))
    composite = promo_raw * w_promo + sm_scaled * w_sm
    composite = _clamp(composite, 0, 100)

    return FlowResult(
        promoter=Decimal(str(round(promo_raw, 2))),
        institutional=Decimal(str(round(sm_scaled, 2))),
        smart_money=Decimal(str(round(sm_raw, 2))),
        score=Decimal(str(round(composite, 2))),
        evidence={
            "promoter": promo_ev,
            "smart_money": sm_ev,
            "weights": {"promoter": w_promo, "smart_money": w_sm},
        },
    )
