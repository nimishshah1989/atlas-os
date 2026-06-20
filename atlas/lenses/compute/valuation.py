"""Valuation lens scorer — ported from Theta's valuation_scorer.py.

Pure function, no I/O.  Five dimensions (PE-vs-sector, absolute PE,
price-to-book, EV/EBITDA, 52-week position) map to zone + multiplier.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = ["ValuationResult", "score_valuation"]

_DEFAULT_ZONES: list[tuple[int, str, str]] = [
    (75, "DEEP_VALUE", "1.15"),
    (55, "CHEAP", "1.08"),
    (35, "FAIR", "1.00"),
    (20, "EXPENSIVE", "0.90"),
    (0, "OVERVALUED", "0.75"),
]


@dataclass(frozen=True, slots=True)
class ValuationResult:
    pe_vs_sector: Decimal | None
    absolute_pe: Decimal | None
    price_to_book: Decimal | None
    ev_ebitda: Decimal | None
    position_52w: Decimal | None
    score: Decimal | None
    zone: str
    multiplier: Decimal
    evidence: dict[str, Any]


def _d(v: float | int | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None

D = Decimal  # shorthand inside scorers


def _score_pe_vs_sector(pe: D, sector_med: D) -> D:
    if pe <= 0 or sector_med <= 0:
        return D(0)
    r = pe / sector_med
    if r < D("0.5"):   return D(25)
    if r < D("0.75"):  return D(18)
    if r < D("1.0"):   return D(12)
    if r < D("1.5"):   return D(6)
    return D(0)


def _score_absolute_pe(pe: D) -> D:
    if pe <= 0:  return D(0)
    if pe < D(8):   return D(25)
    if pe < D(15):  return D(18)
    if pe < D(25):  return D(10)
    if pe < D(40):  return D(3)
    return D(0)


def _score_price_to_book(pb: D) -> D:
    if pb <= 0:  return D(0)
    if pb < D(1):  return D(15)
    if pb < D(2):  return D(10)
    if pb < D(4):  return D(5)
    if pb < D(6):  return D(2)
    return D(0)


def _score_ev_ebitda(ev_eb: D) -> D:
    if ev_eb <= 0:   return D(0)
    if ev_eb < D(6):   return D(20)
    if ev_eb < D(10):  return D(14)
    if ev_eb < D(15):  return D(8)
    if ev_eb < D(20):  return D(3)
    return D(0)


def _score_52w_position(price: D, high: D, low: D, ema200: D | None) -> D:
    span = high - low
    if span <= 0:
        return D(0)
    pos = (price - low) / span * 100
    if pos <= D(20):    base = D(15)
    elif pos <= D(40):  base = D(10)
    elif pos <= D(60):  base = D(6)
    elif pos <= D(80):  base = D(3)
    else:               base = D(0)
    if ema200 is not None and price < ema200:
        base = min(base + D(3), D(15))
    return base


def _map_zone(score: D, thresholds: dict[str, Any]) -> tuple[str, D]:
    zones = thresholds.get("valuation_zones", _DEFAULT_ZONES)
    for cutoff, zone, mult in zones:
        if score >= cutoff:
            return zone, D(str(mult))
    return "OVERVALUED", D("0.75")


def score_valuation(
    pe_ttm: float | None,
    pb_fbs: float | None,
    ev_ebitda: float | None,
    price: float | None,
    high_52w: float | None,
    low_52w: float | None,
    ema_200: float | None,
    sector_median_pe: float | None,
    thresholds: dict[str, Any],
) -> ValuationResult:
    """Score the Valuation lens across five dimensions."""
    pe, pb = _d(pe_ttm), _d(pb_fbs)
    ev_eb, pr = _d(ev_ebitda), _d(price)
    hi, lo, ema, smed = _d(high_52w), _d(low_52w), _d(ema_200), _d(sector_median_pe)

    evidence: dict[str, Any] = {}
    dims: dict[str, Decimal | None] = {
        "pe_sector": None, "abs_pe": None, "pb": None, "ev": None, "w52": None,
    }
    max_pts: list[int] = []
    scored_pts: list[Decimal] = []

    if pe is not None and pe > 0 and smed is not None and smed > 0:
        dims["pe_sector"] = _score_pe_vs_sector(pe, smed)
        scored_pts.append(dims["pe_sector"])
        max_pts.append(25)
    if pe is not None and pe > 0:
        dims["abs_pe"] = _score_absolute_pe(pe)
        scored_pts.append(dims["abs_pe"])
        max_pts.append(25)
    if pb is not None and pb > 0:
        dims["pb"] = _score_price_to_book(pb)
        scored_pts.append(dims["pb"])
        max_pts.append(15)
    if ev_eb is not None and ev_eb > 0:
        dims["ev"] = _score_ev_ebitda(ev_eb)
        scored_pts.append(dims["ev"])
        max_pts.append(20)
    if pr is not None and hi is not None and lo is not None and hi > lo:
        dims["w52"] = _score_52w_position(pr, hi, lo, ema)
        scored_pts.append(dims["w52"])
        max_pts.append(15)

    n_scored = len(scored_pts)
    evidence["dimensions_scored"] = n_scored

    if n_scored == 0:
        composite = Decimal(35)
        evidence["imputation"] = "no_data_default_fair"
    elif n_scored <= 2:
        total_scored = sum(scored_pts)
        total_max = sum(Decimal(m) for m in max_pts)
        avg_prop = total_scored / total_max if total_max else Decimal(0)
        missing_max = Decimal(100) - total_max
        imputed = missing_max * avg_prop * Decimal("0.6")
        composite = total_scored + imputed
        evidence["imputation"] = "partial_60pct"
        evidence["imputed_points"] = float(imputed)
    else:
        total_scored = sum(scored_pts)
        total_max = sum(Decimal(m) for m in max_pts)
        composite = (total_scored / total_max * 100) if total_max else Decimal(0)

    zone, multiplier = _map_zone(composite, thresholds)

    return ValuationResult(
        pe_vs_sector=dims["pe_sector"],
        absolute_pe=dims["abs_pe"],
        price_to_book=dims["pb"],
        ev_ebitda=dims["ev"],
        position_52w=dims["w52"],
        score=composite,
        zone=zone,
        multiplier=multiplier,
        evidence=evidence,
    )
