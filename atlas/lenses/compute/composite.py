"""Composite engine — six-lens scoring + conviction tier + fractal roll-ups.

Ported from Theta's gem_scorer.py, adapted for the six-lens architecture.
Pure function, no I/O.
"""  # allow-large: composite is the most complex scoring module

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

__all__ = [
    "CompositeResult",
    "compute_composite",
    "rollup_holdings",
    "rollup_index",
    "rollup_sector",
]

_Q2 = Decimal("0.01")
_ZERO = Decimal(0)
_HUNDRED = Decimal(100)

# Conviction-forming lenses (weighted average). POLICY is deliberately EXCLUDED
# (Loop C, FM decision): it is a STATIC, hand-curated, selection-biased sector tilt
# (15 themes = this decade's winners), so it is kept as an FYI overlay only — still
# computed/stored and shown as context, but it does NOT drive the composite,
# conviction tier, or convergence. Valuation is also not here — it acts as a
# multiplier, not an averaged lens.
_LENS_NAMES = ("technical", "fundamental", "catalyst", "flow")
_ALL_LENS_NAMES = ("technical", "fundamental", "valuation", "catalyst", "flow", "policy")
# Lenses excluded from the convergence count (FYI / modifier, not conviction drivers).
_NON_CONVICTION = frozenset({"policy", "valuation"})

BREAKPOINTS: dict[str, list[tuple[int, int]]] = {
    "technical": [(0, 0), (15, 25), (30, 50), (45, 70), (60, 85), (80, 95), (100, 100)],
    "fundamental": [(0, 0), (10, 25), (20, 50), (30, 70), (50, 85), (75, 95), (100, 100)],
    "valuation": [(0, 0), (15, 25), (30, 50), (45, 70), (60, 85), (80, 95), (100, 100)],
    "catalyst": [(0, 0), (8, 20), (18, 50), (30, 70), (45, 85), (70, 95), (100, 100)],
    "flow": [(0, 0), (10, 25), (20, 50), (30, 70), (50, 85), (75, 95), (100, 100)],
    "policy": [(0, 0), (10, 25), (20, 50), (35, 70), (50, 85), (75, 95), (100, 100)],
}


def _rescale(raw: float, breakpoints: list[tuple[int, int]]) -> float:
    """Piecewise-linear interpolation between breakpoint boundaries."""
    if raw <= breakpoints[0][0]:
        return float(breakpoints[0][1])
    if raw >= breakpoints[-1][0]:
        return float(breakpoints[-1][1])
    for i in range(len(breakpoints) - 1):
        x0, y0 = breakpoints[i]
        x1, y1 = breakpoints[i + 1]
        if x0 <= raw <= x1:
            if x1 == x0:
                return float(y0)
            t = (raw - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return float(breakpoints[-1][1])  # pragma: no cover


_DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.222,
    "fundamental": 0.222,
    "catalyst": 0.278,
    "flow": 0.278,
}

_DEFAULT_CONVERGENCE = {
    "threshold": 40,
    "4plus": 1.15,
    "3": 1.10,
    "2": 1.06,
}

_DEFAULT_CONVICTION = {
    "HIGHEST": {"min_score": 70, "min_lenses": 3},
    "HIGH": {"min_score": 58, "min_lenses": 2},
    "MEDIUM": {"min_score": 45, "min_lenses": 0},
    "WATCH": {"min_score": 30, "min_lenses": 0},
    "BELOW_THRESHOLD": {"min_score": 0, "min_lenses": 0},
}

_CONVICTION_ORDER = ["HIGHEST", "HIGH", "MEDIUM", "WATCH", "BELOW_THRESHOLD"]


@dataclass(frozen=True, slots=True)
class CompositeResult:
    base_composite: Decimal
    final_score: Decimal
    conviction_tier: str
    lenses_active: int
    coverage_factor: Decimal
    rescaled: dict[str, Decimal]
    convergence_multiplier: Decimal
    evidence: dict[str, Any]


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _determine_conviction(
    score: float,
    active: int,
    th: dict[str, Any],
) -> str:
    tiers = th.get("conviction_tiers", _DEFAULT_CONVICTION)
    for tier in _CONVICTION_ORDER:
        cfg = tiers.get(tier, {})
        min_score = cfg.get("min_score", 0)
        min_lenses = cfg.get("min_lenses", 0)
        if score >= min_score and active >= min_lenses:
            return tier
    return "BELOW_THRESHOLD"


def compute_composite(
    technical: float | None,
    fundamental: float | None,
    valuation_score: float | None,
    catalyst: float | None,
    flow: float | None,
    policy: float | None,
    valuation_multiplier: float,
    smart_money_score: float,
    degradation_score: float,
    thresholds: dict[str, Any],
) -> CompositeResult:
    """Compute final composite score from six lens scores + modifiers.

    Pure function — no I/O, no DB access.  All inputs pre-loaded.
    """
    th = thresholds
    weights = th.get("lens_weights", _DEFAULT_WEIGHTS)
    conv_cfg = th.get("convergence", _DEFAULT_CONVERGENCE)

    raw_scores: dict[str, float | None] = {
        "technical": technical,
        "fundamental": fundamental,
        "valuation": valuation_score,
        "catalyst": catalyst,
        "flow": flow,
        "policy": policy,
    }

    # Step 1: rescale all available lens scores
    rescaled: dict[str, Decimal] = {}
    for lens in _ALL_LENS_NAMES:
        raw = raw_scores.get(lens)
        if raw is not None and raw > 0:
            bps = th.get(f"breakpoints_{lens}", BREAKPOINTS.get(lens, []))
            rescaled[lens] = Decimal(str(round(_rescale(raw, bps), 4))).quantize(_Q2)

    # Step 2: coverage-adjusted weighted average (valuation excluded from avg)
    active_weights: dict[str, float] = {}
    for lens in _LENS_NAMES:
        if lens in rescaled:
            active_weights[lens] = weights.get(lens, _DEFAULT_WEIGHTS.get(lens, 0.0))

    lenses_active = len(active_weights)
    evidence: dict[str, Any] = {"lenses_active_names": list(active_weights.keys())}

    if lenses_active == 0:
        return CompositeResult(
            base_composite=_ZERO,
            final_score=_ZERO,
            conviction_tier="BELOW_THRESHOLD",
            lenses_active=0,
            coverage_factor=_ZERO,
            rescaled=rescaled,
            convergence_multiplier=Decimal(1),
            evidence=evidence,
        )

    total_active_weight = sum(active_weights.values())
    normalized_avg = sum(
        float(rescaled[lens]) * (w / total_active_weight) for lens, w in active_weights.items()
    )
    coverage_factor = math.sqrt(total_active_weight)
    weighted_avg = normalized_avg * coverage_factor

    evidence["normalized_avg"] = round(normalized_avg, 4)
    evidence["coverage_factor"] = round(coverage_factor, 4)
    evidence["weighted_avg"] = round(weighted_avg, 4)

    # Step 3: convergence bonus
    conv_threshold = conv_cfg.get("threshold", 40)
    converging = sum(
        1
        for lens, v in rescaled.items()
        if lens not in _NON_CONVICTION and float(v) >= conv_threshold
    )

    if converging >= 4:
        conv_mult = conv_cfg.get("4plus", 1.15)
    elif converging >= 3:
        conv_mult = conv_cfg.get("3", 1.10)
    elif converging >= 2:
        conv_mult = conv_cfg.get("2", 1.06)
    else:
        conv_mult = 1.0

    base_composite = _clamp(weighted_avg * conv_mult, 0.0, 100.0)
    evidence["converging_lenses"] = converging
    evidence["convergence_multiplier"] = conv_mult

    # Step 4: apply modifiers
    val_mult = _clamp(valuation_multiplier, 0.75, 1.15)
    final = _clamp(
        base_composite * val_mult + smart_money_score + degradation_score,
        0.0,
        100.0,
    )
    evidence["valuation_multiplier"] = val_mult
    evidence["smart_money_score"] = smart_money_score
    evidence["degradation_score"] = degradation_score

    # Step 5: conviction tier
    conviction = _determine_conviction(final, lenses_active, th)

    return CompositeResult(
        base_composite=Decimal(str(round(base_composite, 4))).quantize(_Q2, ROUND_HALF_UP),
        final_score=Decimal(str(round(final, 4))).quantize(_Q2, ROUND_HALF_UP),
        conviction_tier=conviction,
        lenses_active=lenses_active,
        coverage_factor=Decimal(str(round(coverage_factor, 4))).quantize(_Q2, ROUND_HALF_UP),
        rescaled=rescaled,
        convergence_multiplier=Decimal(str(conv_mult)).quantize(_Q2),
        evidence=evidence,
    )


def _weighted_lens_avg(items: list[dict[str, Any]], wk: str) -> dict[str, float]:
    """Weight-normalized average of lens scores across items."""
    totals: dict[str, float] = {}
    tw = 0.0
    for item in items:
        w = float(item.get(wk, 0))
        if w <= 0:
            continue
        tw += w
        for lens in _ALL_LENS_NAMES:
            val = item.get(lens)
            if val is not None:
                totals[lens] = totals.get(lens, 0.0) + float(val) * w
    return {lens: v / tw for lens, v in totals.items()} if tw > 0 else {}


def _breadth_stats(items: list[dict[str, Any]], key: str = "final_score") -> dict[str, Any]:
    """Breadth and dispersion metrics."""
    scores = [float(item[key]) for item in items if item.get(key) is not None]
    if not scores:
        return {"count": 0, "breadth_above_50": 0.0, "dispersion": 0.0}
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    return {
        "count": n,
        "breadth_above_50": round(sum(1 for s in scores if s >= 50) / n, 4),
        "mean_score": round(mean, 4),
        "dispersion": round(math.sqrt(variance), 4),
    }


def _weighted_final(items: list[dict[str, Any]], wk: str) -> tuple[float, float]:
    """Return (weighted_final_score, total_weight)."""
    tw = sum(float(it.get(wk, 0)) for it in items)
    if tw <= 0:
        return 0.0, 0.0
    wf = sum(
        float(it.get("final_score", 0)) * float(it.get(wk, 0)) / tw
        for it in items
        if it.get("final_score") is not None and float(it.get(wk, 0)) > 0
    )
    return round(wf, 4), round(tw, 4)


def rollup_sector(stock_scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Cap-weighted average of stock lens vectors within a sector + breadth + dispersion."""
    wf, tc = _weighted_final(stock_scores, "market_cap")
    return {
        "lens_averages": _weighted_lens_avg(stock_scores, "market_cap"),
        "weighted_final_score": wf,
        "breadth": _breadth_stats(stock_scores),
        "total_market_cap": tc,
        "stock_count": len(stock_scores),
    }


def rollup_holdings(
    holding_scores: list[dict[str, Any]],
    benchmark_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Holdings-weighted roll-up for ETF/fund + active tilt vs benchmark."""
    lens_avg = _weighted_lens_avg(holding_scores, "weight")
    wf, tw = _weighted_final(holding_scores, "weight")
    result: dict[str, Any] = {
        "lens_averages": lens_avg,
        "weighted_final_score": wf,
        "breadth": _breadth_stats(holding_scores),
        "total_weight": tw,
        "holding_count": len(holding_scores),
    }
    if benchmark_scores is not None:
        result["active_tilt"] = {
            lens: round(avg - benchmark_scores[lens], 4)
            for lens, avg in lens_avg.items()
            if lens in benchmark_scores
        }
    return result


def rollup_index(constituent_scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Constituent-weighted roll-up for indices."""
    wf, tw = _weighted_final(constituent_scores, "weight")
    return {
        "lens_averages": _weighted_lens_avg(constituent_scores, "weight"),
        "weighted_final_score": wf,
        "breadth": _breadth_stats(constituent_scores),
        "total_weight": tw,
        "constituent_count": len(constituent_scores),
    }
