"""Risk-flags overlay — ported from Theta's degradation_monitor.py.

Pure function, no I/O.  Derives ten red flags from pre-loaded instrument data
and produces a degradation_score that dampens the composite.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

__all__ = ["RiskFlagsResult", "compute_risk_flags"]

_Q2 = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class RiskFlagsResult:
    degradation_score: Decimal
    is_degrading: bool
    flags: list[dict[str, Any]]  # [{name, penalty, description}, ...]
    flags_firing: int


# ---------------------------------------------------------------------------
# Individual flag detectors
# ---------------------------------------------------------------------------


def _net_insider_selling(
    signals: list[dict[str, Any]], th: dict[str, Any]
) -> dict[str, Any] | None:
    net = Decimal(0)
    for s in signals:
        kind = (s.get("type") or "").lower()
        amt = Decimal(str(s.get("amount_cr", 0)))
        if kind == "sell":
            net += amt
        elif kind == "buy":
            net -= amt
    if net > Decimal(str(th.get("insider_net_sell_cr", 0.5))):
        return {
            "name": "net_insider_selling",
            "penalty": th.get("penalty_net_insider_selling", -8),
            "description": f"Net insider selling {net} Cr in 90d",
        }
    return None


def _pledge_increasing(signals: list[dict[str, Any]], th: dict[str, Any]) -> dict[str, Any] | None:
    for s in signals:
        if (s.get("type") or "").lower() == "pledge_increase":
            return {
                "name": "pledge_increasing",
                "penalty": th.get("penalty_pledge_increasing", -6),
                "description": "Promoter pledge increasing",
            }
    return None


def _multiple_insiders_selling(
    signals: list[dict[str, Any]], th: dict[str, Any]
) -> dict[str, Any] | None:
    sellers = {
        s.get("name") for s in signals if (s.get("type") or "").lower() == "sell" and s.get("name")
    }
    if len(sellers) >= th.get("insider_min_distinct_sellers", 3):
        return {
            "name": "multiple_insiders_selling",
            "penalty": th.get("penalty_multiple_insiders_selling", -5),
            "description": f"{len(sellers)} distinct insider sellers in 90d",
        }
    return None


def _margin_declining(margins: list[float | None], th: dict[str, Any]) -> dict[str, Any] | None:
    min_consec = th.get("margin_decline_consecutive", 2)
    valid = [m for m in margins if m is not None]
    if len(valid) < min_consec + 1:
        return None
    consec = 0
    for i in range(len(valid) - 1):
        if valid[i] < valid[i + 1]:
            consec += 1
        else:
            break
    if consec >= min_consec:
        return {
            "name": "margin_declining",
            "penalty": th.get("penalty_margin_declining", -6),
            "description": f"{consec} consecutive qtr margin declines",
        }
    return None


def _revenue_declining(fin: dict[str, Any], th: dict[str, Any]) -> dict[str, Any] | None:
    rev, rev_prev = fin.get("revenue"), fin.get("revenue_prev")
    if rev is None or rev_prev is None or rev_prev <= 0:
        return None
    if rev < rev_prev:
        return {
            "name": "revenue_declining",
            "penalty": th.get("penalty_revenue_declining", -5),
            "description": f"Revenue fell YoY ({rev} < {rev_prev})",
        }
    return None


def _leverage_up_margins_down(fin: dict[str, Any], th: dict[str, Any]) -> dict[str, Any] | None:
    de, de_prev = fin.get("debt_to_equity"), fin.get("debt_to_equity_prev")
    em, em_prev = fin.get("ebitda_margin"), fin.get("ebitda_margin_prev")
    if de is None or de_prev is None or em is None or em_prev is None:
        return None
    if de > de_prev and em < em_prev:
        return {
            "name": "leverage_up_margins_down",
            "penalty": th.get("penalty_leverage_up_margins_down", -5),
            "description": "D/E up + EBITDA margin down YoY",
        }
    return None


def _check_filings(
    filings: list[dict[str, Any]],
    th: dict[str, Any],
) -> list[dict[str, Any]]:
    """Auditor change, CFO/CEO resignation, credit downgrade — filing scans."""
    results: list[dict[str, Any]] = []
    roles = th.get("resignation_roles", ["cfo", "ceo", "md", "managing director"])
    resign_kw = th.get("resignation_keywords", ["resign", "cessation", "stepping down"])
    auditor_kw = th.get("auditor_keywords", ["auditor"])
    found_aud = found_res = found_crd = False
    for f in filings:
        subj = (f.get("subject") or "").lower()
        if not found_aud and any(kw in subj for kw in auditor_kw):
            results.append(
                {
                    "name": "auditor_change",
                    "penalty": th.get("penalty_auditor_change", -8),
                    "description": "Auditor change filing detected",
                }
            )
            found_aud = True
        if not found_res and any(r in subj for r in roles) and any(w in subj for w in resign_kw):
            results.append(
                {
                    "name": "cfo_ceo_resignation",
                    "penalty": th.get("penalty_cfo_ceo_resignation", -6),
                    "description": "Key management resignation detected",
                }
            )
            found_res = True
        if not found_crd and "credit rating" in subj and "downgrade" in subj:
            results.append(
                {
                    "name": "credit_downgrade",
                    "penalty": th.get("penalty_credit_downgrade", -5),
                    "description": "Credit rating downgrade filing",
                }
            )
            found_crd = True
    return results


def _price_below_200dma(
    price: float | None, ema_200: float | None, th: dict[str, Any]
) -> dict[str, Any] | None:
    if price is None or ema_200 is None or ema_200 <= 0:
        return None
    if price < ema_200 * th.get("price_below_200dma_pct", 0.85):
        return {
            "name": "price_below_200dma",
            "penalty": th.get("penalty_price_below_200dma", -3),
            "description": f"Price {price} > 15% below EMA200 {ema_200}",
        }
    return None


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def compute_risk_flags(
    insider_signals: list[dict[str, Any]],
    quarterly_margins: list[float | None],
    annual_financials: dict[str, Any],
    filings: list[dict[str, Any]],
    price: float | None,
    ema_200: float | None,
    thresholds: dict[str, Any],
) -> RiskFlagsResult:
    """Compute degradation overlay from ten risk flags.

    Pure function — no I/O, no DB access.  All inputs pre-loaded.
    Returns a RiskFlagsResult with degradation_score in [-30, 0].
    """
    th = thresholds
    floor = th.get("degradation_floor", -30)
    degradation_threshold = th.get("degradation_is_degrading", -15)

    checks = [
        _net_insider_selling(insider_signals, th),
        _pledge_increasing(insider_signals, th),
        _multiple_insiders_selling(insider_signals, th),
        _margin_declining(quarterly_margins, th),
        _revenue_declining(annual_financials, th),
        _leverage_up_margins_down(annual_financials, th),
        _price_below_200dma(price, ema_200, th),
    ]
    flags = [f for f in checks if f is not None]
    flags.extend(_check_filings(filings, th))
    raw = sum(f["penalty"] for f in flags)
    score = max(floor, raw)

    return RiskFlagsResult(
        degradation_score=Decimal(str(score)).quantize(_Q2),
        is_degrading=score <= degradation_threshold,
        flags=flags,
        flags_firing=len(flags),
    )
