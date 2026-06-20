"""Fundamental lens scorer — merges quality + operating-leverage into one lens.

Pure function, no I/O.  Consumes tv_metrics snapshot fields and a thresholds
dict; emits a FundamentalResult with five subcomponents (each 0-20) and a
composite 0-100 score.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_D = Decimal


@dataclass(frozen=True, slots=True)
class FundamentalResult:
    profitability: Decimal | None
    margin: Decimal | None
    growth: Decimal | None
    balance_sheet: Decimal | None
    op_leverage: Decimal | None
    score: Decimal | None
    evidence: dict[str, Any]


def _d(v: float | None) -> Decimal | None:
    """Safe float -> Decimal (returns None on None / non-finite)."""
    if v is None:
        return None
    try:
        d = _D(str(v))
        return d if d.is_finite() else None
    except Exception:
        return None


def _cap(val: int | float, ceiling: int = 20) -> int:
    return min(int(val), ceiling)


def _t(th: dict[str, Any], key: str, default: float) -> float:
    return float(th.get(key, default))


def _profitability(
    roe: Decimal | None, roic: Decimal | None, th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if roe is None:
        return None, {"reason": "roe missing"}
    if roe >= _t(th, "prof_roe_high", 20):
        base = 20
    elif roe >= _t(th, "prof_roe_good", 15):
        base = 16
    elif roe >= _t(th, "prof_roe_ok", 12):
        base = 12
    elif roe >= _t(th, "prof_roe_low", 8):
        base = 8
    else:
        base = 4
    bonus = 2 if (roic is not None and roic > _t(th, "prof_roic_bonus", 15)) else 0
    return _D(_cap(base + bonus)), {"roe": str(roe), "roic_bonus": bonus}


def _margin(
    op_margin: Decimal | None, net_margin: Decimal | None, th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if op_margin is None and net_margin is None:
        return None, {"reason": "margins missing"}
    pts, ev = 0, {}
    if op_margin is not None:
        if op_margin > _t(th, "margin_op_high", 20):
            pts += 14
        elif op_margin > _t(th, "margin_op_good", 15):
            pts += 11
        elif op_margin > _t(th, "margin_op_ok", 10):
            pts += 8
        elif op_margin > _t(th, "margin_op_low", 5):
            pts += 5
        else:
            pts += 2
        ev["op_margin"] = str(op_margin)
    if net_margin is not None:
        if net_margin > _t(th, "margin_net_high", 15):
            pts += 6
        elif net_margin > _t(th, "margin_net_good", 10):
            pts += 4
        elif net_margin > _t(th, "margin_net_ok", 5):
            pts += 2
        ev["net_margin"] = str(net_margin)
    return _D(_cap(pts)), ev


def _growth(
    rev_g: Decimal | None, eps_g: Decimal | None, th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if rev_g is None and eps_g is None:
        return None, {"reason": "growth metrics missing"}
    pts, ev = 0, {}
    if rev_g is not None:
        if rev_g > _t(th, "growth_rev_high", 25):
            pts += 12
        elif rev_g > _t(th, "growth_rev_good", 15):
            pts += 9
        elif rev_g > _t(th, "growth_rev_ok", 8):
            pts += 6
        elif rev_g > 0:
            pts += 3
        ev["revenue_growth"] = str(rev_g)
    if eps_g is not None:
        if eps_g > _t(th, "growth_eps_high", 30):
            pts += 8
        elif eps_g > _t(th, "growth_eps_good", 15):
            pts += 6
        elif eps_g > _t(th, "growth_eps_ok", 5):
            pts += 4
        elif eps_g > 0:
            pts += 2
        ev["eps_growth"] = str(eps_g)
    return _D(_cap(pts)), ev


def _balance_sheet(
    de: Decimal | None, cr: Decimal | None, qr: Decimal | None,
    th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if de is None and cr is None and qr is None:
        return None, {"reason": "balance sheet metrics missing"}
    pts, ev = 0, {}
    if de is not None:
        if de < 0:
            pts += 10; ev["de_note"] = "net_cash"
        elif de < _t(th, "bs_de_low", 0.3):
            pts += 10
        elif de < _t(th, "bs_de_ok", 0.5):
            pts += 8
        elif de < _t(th, "bs_de_med", 1.0):
            pts += 6
        elif de < _t(th, "bs_de_high", 1.5):
            pts += 4
        else:
            pts += 2
        ev["debt_to_equity"] = str(de)
    if cr is not None:
        if cr > _t(th, "bs_cr_high", 2.0):
            pts += 5
        elif cr > _t(th, "bs_cr_good", 1.5):
            pts += 4
        elif cr > _t(th, "bs_cr_ok", 1.0):
            pts += 3
        else:
            pts += 1
        ev["current_ratio"] = str(cr)
    if qr is not None:
        if qr > _t(th, "bs_qr_high", 1.5):
            pts += 5
        elif qr > _t(th, "bs_qr_good", 1.0):
            pts += 4
        elif qr > _t(th, "bs_qr_ok", 0.5):
            pts += 2
        else:
            pts += 1
        ev["quick_ratio"] = str(qr)
    return _D(_cap(pts)), ev


def _op_leverage(
    rev_g: Decimal | None, op_margin: Decimal | None,
    de: Decimal | None, th: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    if rev_g is None:
        return None, {"reason": "revenue growth missing"}
    ev: dict[str, Any] = {"revenue_growth": str(rev_g)}
    high_growth = rev_g > _t(th, "olev_rev_high", 15)
    mod_growth = rev_g > _t(th, "olev_rev_mod", 8)
    expanding = op_margin is not None and op_margin > _t(th, "olev_margin_expand", 15)
    low_de = de is not None and (de < 0 or de < _D(str(_t(th, "olev_de_low", 0.5))))
    if high_growth and expanding and low_de:
        pts, ev["band"] = 20, "full"
    elif high_growth and (expanding or low_de):
        pts, ev["band"] = 15, "high_partial"
    elif mod_growth and (low_de or expanding):
        pts, ev["band"] = 10, "moderate"
    elif rev_g > 0:
        pts, ev["band"] = 5, "positive_only"
    else:
        pts, ev["band"] = 0, "declining"
    return _D(pts), ev


def score_fundamental(
    roe: float | None, roa: float | None, roic: float | None,
    operating_margin: float | None, net_margin: float | None,
    gross_margin: float | None,
    revenue_growth_yoy: float | None, eps_growth_yoy: float | None,
    debt_to_equity: float | None, current_ratio: float | None,
    quick_ratio: float | None,
    revenue_ttm: float | None, eps_diluted_ttm: float | None,
    thresholds: dict[str, Any],
) -> FundamentalResult:
    """Score a stock on the Fundamental lens (0-100).

    All numeric inputs are raw floats from tv_metrics; *thresholds* supplies
    tunables (missing keys fall back to coded defaults).
    """
    th = thresholds or {}
    d_roe, d_roic = _d(roe), _d(roic)
    d_op, d_net = _d(operating_margin), _d(net_margin)
    d_rev_g, d_eps_g = _d(revenue_growth_yoy), _d(eps_growth_yoy)
    d_de, d_cr, d_qr = _d(debt_to_equity), _d(current_ratio), _d(quick_ratio)

    evidence: dict[str, Any] = {}
    prof, evidence["profitability"] = _profitability(d_roe, d_roic, th)
    mar, evidence["margin"] = _margin(d_op, d_net, th)
    gro, evidence["growth"] = _growth(d_rev_g, d_eps_g, th)
    bs, evidence["balance_sheet"] = _balance_sheet(d_de, d_cr, d_qr, th)
    olev, evidence["op_leverage"] = _op_leverage(d_rev_g, d_op, d_de, th)

    # Composite: sum non-None subcomponents, renormalise to 0-100
    present = [p for p in (prof, mar, gro, bs, olev) if p is not None]
    if present:
        composite = (sum(present) * _D(100) / (_D(20) * _D(len(present)))).quantize(_D("0.1"))
    else:
        composite = None

    return FundamentalResult(
        profitability=prof, margin=mar, growth=gro,
        balance_sheet=bs, op_leverage=olev,
        score=composite, evidence=evidence,
    )
