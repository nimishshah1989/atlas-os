"""Mutual fund scorecard pipeline — 4-layer composite ranking.

Layers (weights in atlas_thresholds, ``mf_weight_*``):

  1. Risk-adjusted return (50%)
     — Sharpe, Sortino, Alpha vs benchmark, MaxDD, Calmar, up/down capture
     — 3y window where available; flag confidence_low if < 3y history.

  2. Holdings conviction (25%)
     — Aggregate the 24-cell conviction tape across top-N holdings
       (atlas_thresholds.mf_holdings_top_n, default 20), weighted by
       position size. Conviction → numeric: POSITIVE=+1 / NEUTRAL=0 /
       NEGATIVE=-1. Weighted average → linear-mapped to [0, 100].
     — Caveat: if holdings unjoinable (table missing or coverage = 0),
       flag holdings_unjoinable and use category median (50).

  3. Style + sector (15%)
     — Style drift across 3y window (does fund stay in stated box?)
     — Sector tilt bonus for overweighting top-ranked sectors.

  4. Cost + manager (10%)
     — TER (40%), manager_tenure (30% cap 10y), AUM bracket (20%), age (10% cap 10y).

Disclaimers surfaced in API rows:
  * survivorship_exposure_pct — % of fund's NAV held in the curated
    universe (the rest inherits the universe's survivorship caveat).
  * nav_as_of / holdings_as_of — staleness markers.
  * confidence_low — fund < 3y old.
  * holdings_unjoinable — set when the join couldn't be made.

Top ``mf_atlas_leader_pct`` per category → ``is_atlas_leader``.
Bottom ``mf_avoid_pct`` per category → ``is_avoid``.

CLI mirrors conviction_tape.py / etf_scorecard.py: live write when
``.supabase-write-approved`` marker present, else SQL file emission.
"""

# allow-large: end-to-end fund scorecard pipeline. Four layer scorers,
# composite + ranking + caveat machinery, ELI5 and SQL emitter live
# together because they share the FundScoreRow shape and the holdings
# row semantics. Splitting would require duplicating typedicts across
# modules without buying much testability — the layer scorers are
# already pure-function and individually testable.

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundScoreRow:
    """One row of the daily fund scorecard."""

    snapshot_date: date
    scheme_code: str
    isin: str | None
    fund_name: str | None
    fund_category: str
    fund_style: str | None
    amc: str | None
    risk_adjusted_return_score: Decimal | None
    holdings_conviction_score: Decimal | None
    style_sector_score: Decimal | None
    cost_manager_score: Decimal | None
    composite_score: Decimal
    rank_in_category: int | None
    category_size: int | None
    is_atlas_leader: bool
    is_avoid: bool
    confidence_low: bool
    holdings_unjoinable: bool
    survivorship_exposure_pct: Decimal | None
    nav_as_of: date | None
    holdings_as_of: date | None
    eli5: str | None
    sub_metrics: dict[str, Any] = field(default_factory=dict)
    top_holdings: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Threshold loader
# ---------------------------------------------------------------------------


_DEFAULT_THRESHOLDS = {
    "mf_weight_risk_adj": Decimal("0.50"),
    "mf_weight_holdings": Decimal("0.25"),
    "mf_weight_style_sector": Decimal("0.15"),
    "mf_weight_cost_manager": Decimal("0.10"),
    "mf_holdings_top_n": Decimal("20"),
    "mf_aum_sweet_spot_min_cr": Decimal("500"),
    "mf_aum_sweet_spot_max_cr": Decimal("5000"),
    "mf_min_history_years_for_full_confidence": Decimal("3"),
    "mf_atlas_leader_pct": Decimal("25.0"),
    "mf_avoid_pct": Decimal("25.0"),
}


def _load_mf_thresholds(engine: Engine | None) -> dict[str, Decimal]:
    """Read all MF tunables. Falls back to defaults if engine is None."""
    if engine is None:
        return dict(_DEFAULT_THRESHOLDS)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT threshold_key, threshold_value
                    FROM atlas.atlas_thresholds
                    WHERE is_active = TRUE AND category IN ('mf_rank','mf')
                    """
                )
            ).all()
        loaded = {k: Decimal(str(v)) for k, v in rows}
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("mf_thresholds_load_failed", error=str(exc))
        loaded = {}
    merged = dict(_DEFAULT_THRESHOLDS)
    merged.update(loaded)
    return merged


# ---------------------------------------------------------------------------
# Risk-adjusted return primitives
# ---------------------------------------------------------------------------


_RF_DAILY = 0.06 / 252.0  # 6% annual → daily risk-free (rough)


def _annualized_return(daily_returns: Sequence[float]) -> float:
    if not daily_returns:
        return 0.0
    mean_d = statistics.fmean(daily_returns)
    return mean_d * 252.0


def _annualized_vol(daily_returns: Sequence[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    return statistics.pstdev(daily_returns) * math.sqrt(252.0)


def _sharpe(daily_returns: Sequence[float], rf_daily: float = _RF_DAILY) -> float:
    """Annualized Sharpe ratio."""
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - rf_daily for r in daily_returns]
    mean_e = statistics.fmean(excess)
    sd = statistics.pstdev(excess)
    if sd == 0:
        return 0.0
    return (mean_e / sd) * math.sqrt(252.0)


def _sortino(daily_returns: Sequence[float], rf_daily: float = _RF_DAILY) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - rf_daily for r in daily_returns]
    downside = [e for e in excess if e < 0]
    if not downside:
        # No downside ever — infinite Sortino. Cap at 5.0 for ranking.
        return 5.0
    mean_e = statistics.fmean(excess)
    dd_sd = math.sqrt(sum(d * d for d in downside) / len(downside))
    if dd_sd == 0:
        return 0.0
    return (mean_e / dd_sd) * math.sqrt(252.0)


def _max_drawdown(daily_returns: Sequence[float]) -> float:
    """Max drawdown from peak as a positive fraction (0.20 = 20% dd)."""
    if not daily_returns:
        return 0.0
    # Build wealth index
    wealth = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        dd = (peak - wealth) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _calmar(daily_returns: Sequence[float]) -> float:
    ann_ret = _annualized_return(daily_returns)
    max_dd = _max_drawdown(daily_returns)
    if max_dd == 0:
        return 0.0
    return ann_ret / max_dd


def _capture_ratios(
    fund_returns: Sequence[float], bench_returns: Sequence[float]
) -> tuple[float, float]:
    """Up-capture and down-capture (% of bench up days and bench down days).

    Returns (up_capture, down_capture). Each is a ratio (1.0 = matched
    benchmark on those days).
    """
    n = min(len(fund_returns), len(bench_returns))
    if n == 0:
        return 1.0, 1.0
    up_fund_sum = 0.0
    up_bench_sum = 0.0
    down_fund_sum = 0.0
    down_bench_sum = 0.0
    for i in range(n):
        b = bench_returns[i]
        f = fund_returns[i]
        if b > 0:
            up_fund_sum += f
            up_bench_sum += b
        elif b < 0:
            down_fund_sum += f
            down_bench_sum += b
    up_capture = up_fund_sum / up_bench_sum if up_bench_sum != 0 else 1.0
    down_capture = down_fund_sum / down_bench_sum if down_bench_sum != 0 else 1.0
    return up_capture, down_capture


def _alpha(fund_returns: Sequence[float], bench_returns: Sequence[float]) -> float:
    """Annualized Jensen alpha (fund - bench)."""
    n = min(len(fund_returns), len(bench_returns))
    if n == 0:
        return 0.0
    diff = [fund_returns[i] - bench_returns[i] for i in range(n)]
    return statistics.fmean(diff) * 252.0


# ---------------------------------------------------------------------------
# Layer 1 — risk-adjusted return
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskAdjustedMetrics:
    sharpe: float
    sortino: float
    alpha: float
    max_dd: float
    calmar: float
    up_capture: float
    down_capture: float
    n_observations: int


def compute_risk_adjusted_metrics(
    fund_daily_returns: Sequence[float],
    benchmark_daily_returns: Sequence[float] | None = None,
) -> RiskAdjustedMetrics:
    """Compute the layer-1 risk-adjusted return primitives."""
    if benchmark_daily_returns is None:
        benchmark_daily_returns = []
    up_cap, dn_cap = _capture_ratios(fund_daily_returns, benchmark_daily_returns)
    return RiskAdjustedMetrics(
        sharpe=_sharpe(fund_daily_returns),
        sortino=_sortino(fund_daily_returns),
        alpha=_alpha(fund_daily_returns, benchmark_daily_returns),
        max_dd=_max_drawdown(fund_daily_returns),
        calmar=_calmar(fund_daily_returns),
        up_capture=up_cap,
        down_capture=dn_cap,
        n_observations=len(fund_daily_returns),
    )


def _normalise(values: Sequence[float], target: float) -> float:
    """Percentile rank of `target` in `values`, returned as 0-100."""
    if not values:
        return 50.0
    below = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    n = len(values)
    return ((below + 0.5 * equal) / n) * 100.0


def score_risk_adjusted_return(
    target: RiskAdjustedMetrics,
    cohort: Sequence[RiskAdjustedMetrics],
) -> Decimal:
    """Score 0-100 from RiskAdjustedMetrics vs same-category cohort.

    Equal-weighted combination of percentile ranks across the six
    sub-metrics (Sharpe, Sortino, Alpha, max_dd inverse, Calmar, up_cap
    inverse-of-distance-from-1, down_cap inverse).
    """
    if not cohort:
        return Decimal("50.00")
    pcts: list[float] = []
    pcts.append(_normalise([c.sharpe for c in cohort], target.sharpe))
    pcts.append(_normalise([c.sortino for c in cohort], target.sortino))
    pcts.append(_normalise([c.alpha for c in cohort], target.alpha))
    # max_dd: lower is better → invert
    pcts.append(100.0 - _normalise([c.max_dd for c in cohort], target.max_dd))
    pcts.append(_normalise([c.calmar for c in cohort], target.calmar))
    # up_capture: higher is better
    pcts.append(_normalise([c.up_capture for c in cohort], target.up_capture))
    # down_capture: lower (less of the downside) is better → invert
    pcts.append(100.0 - _normalise([c.down_capture for c in cohort], target.down_capture))
    score = sum(pcts) / len(pcts)
    return Decimal(f"{score:.2f}")


# ---------------------------------------------------------------------------
# Layer 2 — holdings conviction
# ---------------------------------------------------------------------------


def compute_holdings_conviction(
    holdings: Sequence[Mapping[str, Any]],
    conviction_by_iid: Mapping[str, str],
    top_n: int = 20,
) -> tuple[Decimal, float, list[dict[str, Any]], bool]:
    """Aggregate holdings conviction → score 0-100.

    Args:
        holdings: list of {instrument_id, weight_pct, symbol} (weight as
            % out of 100). Will be sorted by weight desc and truncated to
            top_n before aggregation.
        conviction_by_iid: {instrument_id: verdict}
            verdict ∈ {"POSITIVE","NEUTRAL","NEGATIVE"}
        top_n: number of holdings to aggregate.

    Returns:
        (score, survivorship_exposure_pct, top_holdings_drilldown,
         holdings_unjoinable)
    """
    if not holdings:
        return Decimal("50.00"), 0.0, [], True
    sorted_h = sorted(holdings, key=lambda r: float(r.get("weight_pct") or 0), reverse=True)
    top = sorted_h[:top_n]
    total_weight = sum(float(r.get("weight_pct") or 0) for r in top)
    if total_weight <= 0:
        return Decimal("50.00"), 0.0, [], True

    score_signed_sum = 0.0
    drilldown: list[dict[str, Any]] = []
    cov_weight = 0.0
    surv_weight = 0.0
    for r in top:
        iid = str(r.get("instrument_id"))
        w = float(r.get("weight_pct") or 0)
        verdict = conviction_by_iid.get(iid)
        sign = (
            1
            if verdict == "POSITIVE"
            else -1
            if verdict == "NEGATIVE"
            else 0
            if verdict == "NEUTRAL"
            else None
        )
        if sign is not None:
            score_signed_sum += sign * w
            cov_weight += w
            surv_weight += w
        drilldown.append(
            {
                "instrument_id": iid,
                "symbol": r.get("symbol"),
                "weight_pct": round(w, 4),
                "verdict": verdict,
            }
        )

    # Average signed conviction in [-1, +1] when fully covered
    if cov_weight > 0:
        avg_signed = score_signed_sum / cov_weight
    else:
        avg_signed = 0.0
    score = (avg_signed + 1.0) * 50.0  # [-1,+1] -> [0,100]
    survivorship_exposure_pct = (surv_weight / total_weight) * 100.0
    unjoinable = cov_weight == 0
    return (
        Decimal(f"{score:.2f}"),
        survivorship_exposure_pct,
        drilldown,
        unjoinable,
    )


# ---------------------------------------------------------------------------
# Layer 3 — style + sector
# ---------------------------------------------------------------------------


def score_style_sector(
    style_drift_pct: float | None,
    sector_tilt_bonus: float | None,
) -> Decimal:
    """Score 0-100 from style consistency + sector tilt.

    style_drift_pct: 0 = perfectly consistent, 100 = fully drifted.
    sector_tilt_bonus: -10..+10 (overweight strong sectors = +ve).

    Score = 100 - style_drift_pct + sector_tilt_bonus, clipped to [0,100].
    """
    sd = style_drift_pct if style_drift_pct is not None else 30.0
    sb = sector_tilt_bonus if sector_tilt_bonus is not None else 0.0
    score = 100.0 - sd + sb
    return Decimal(f"{max(0.0, min(100.0, score)):.2f}")


# ---------------------------------------------------------------------------
# Layer 4 — cost + manager
# ---------------------------------------------------------------------------


def score_cost_manager(
    ter_pct: float | None,
    cohort_ter: Sequence[float],
    manager_tenure_years: float | None,
    aum_cr: float | None,
    fund_age_years: float | None,
    sweet_min_cr: float,
    sweet_max_cr: float,
) -> Decimal:
    """4-sub-score blended layer.

    Weights (within layer): TER 40%, manager_tenure 30%, aum 20%, age 10%.
    """
    # TER — inverse percentile (lower = better)
    if ter_pct is None or not cohort_ter:
        ter_score = 50.0
    else:
        ter_score = 100.0 - _normalise(list(cohort_ter), float(ter_pct))
    # Manager tenure — cap 10y, then linear to 100
    if manager_tenure_years is None:
        tenure_score = 50.0
    else:
        tenure_score = min(100.0, (float(manager_tenure_years) / 10.0) * 100.0)
    # AUM bracket
    if aum_cr is None or aum_cr <= 0:
        aum_score = 50.0
    elif sweet_min_cr <= aum_cr <= sweet_max_cr:
        aum_score = 100.0
    elif aum_cr < sweet_min_cr:
        aum_score = max(0.0, (aum_cr / sweet_min_cr) * 100.0)
    else:
        over = math.log10(aum_cr / sweet_max_cr)
        aum_score = max(40.0, 100.0 - over * 30.0)
    # Fund age — cap 10y
    if fund_age_years is None:
        age_score = 50.0
    else:
        age_score = min(100.0, (float(fund_age_years) / 10.0) * 100.0)
    score = ter_score * 0.4 + tenure_score * 0.3 + aum_score * 0.2 + age_score * 0.1
    return Decimal(f"{max(0.0, min(100.0, score)):.2f}")


# ---------------------------------------------------------------------------
# ELI5
# ---------------------------------------------------------------------------


def _eli5_fund(row: FundScoreRow) -> str:
    """Render fund ELI5 string. Routes to template library based on outcome."""
    from atlas.inference.eli5_fund_etf import (
        eli5_fund_avoid,
        eli5_fund_leader,
        eli5_fund_low_confidence,
    )

    if row.confidence_low:
        # Approximate months until 3y from observation count (252 trading days = 1y).
        n_obs = int((row.sub_metrics or {}).get("n_observations", 0))
        approx_years = n_obs / 252.0
        months_to_3y = max(0, round((3.0 - approx_years) * 12))
        return eli5_fund_low_confidence(months_to_3y)
    if row.is_atlas_leader:
        sharpe = float((row.sub_metrics or {}).get("sharpe", 0.0))
        max_dd = float((row.sub_metrics or {}).get("max_dd", 0.0))
        hc = float(row.holdings_conviction_score or 50)
        return eli5_fund_leader(
            category=row.fund_category,
            sharpe=sharpe,
            max_dd=max_dd,
            hc_score=hc,
        )
    if row.is_avoid:
        primary = _pick_primary_weakness(row)
        return eli5_fund_avoid(category=row.fund_category, primary_weakness=primary)
    if row.holdings_unjoinable:
        return (
            f"{row.fund_category} — composite {row.composite_score:.0f}/100; "
            f"holdings conviction unavailable (using category median)."
        )
    return (
        f"{row.fund_category} — composite {row.composite_score:.0f}/100, "
        f"rank {row.rank_in_category} of {row.category_size}."
    )


def _pick_primary_weakness(row: FundScoreRow) -> str | None:
    """Return the layer name with the lowest score (for is_avoid ELI5)."""
    candidates: list[tuple[str, Decimal | None]] = [
        ("risk_adjusted", row.risk_adjusted_return_score),
        ("holdings", row.holdings_conviction_score),
        ("style_sector", row.style_sector_score),
        ("cost_manager", row.cost_manager_score),
    ]
    scored = [(label, float(score)) for label, score in candidates if score is not None]
    if not scored:
        return None
    return min(scored, key=lambda t: t[1])[0]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _compute_composite(
    components: dict[str, Decimal | None],
    weights: dict[str, Decimal],
) -> Decimal:
    weight_map = {
        "risk_adjusted_return_score": weights["mf_weight_risk_adj"],
        "holdings_conviction_score": weights["mf_weight_holdings"],
        "style_sector_score": weights["mf_weight_style_sector"],
        "cost_manager_score": weights["mf_weight_cost_manager"],
    }
    total_weight = Decimal("0")
    weighted_sum = Decimal("0")
    for k, w in weight_map.items():
        v = components.get(k)
        if v is None:
            continue
        weighted_sum += Decimal(str(v)) * w
        total_weight += w
    if total_weight == 0:
        return Decimal("50.00")
    return (weighted_sum / total_weight).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class FundInput:
    """Per-fund payload for the scorecard pipeline.

    Test path constructs these directly; the engine-load path builds them
    from the live MF data. Keeping it explicit ensures the layer math is
    100% testable without DB access.
    """

    scheme_code: str
    isin: str | None
    fund_name: str | None
    fund_category: str
    fund_style: str | None
    amc: str | None
    daily_returns: Sequence[float]
    benchmark_daily_returns: Sequence[float]
    nav_as_of: date | None
    holdings_as_of: date | None
    holdings: Sequence[Mapping[str, Any]]
    style_drift_pct: float | None
    sector_tilt_bonus: float | None
    ter_pct: float | None
    manager_tenure_years: float | None
    aum_cr: float | None
    fund_age_years: float | None


def compute_fund_scorecard(
    snapshot_date: date,
    *,
    fund_inputs: Sequence[FundInput],
    conviction_by_iid: Mapping[str, str],
    thresholds: dict[str, Decimal] | None = None,
    cohort_ters_by_category: Mapping[str, Sequence[float]] | None = None,
) -> list[FundScoreRow]:
    """Compute the fund scorecard for one snapshot.

    Pure-functional core — pass pre-loaded inputs. The DB-backed wrapper
    ``compute_fund_scorecard_from_engine`` (further down) handles the
    live data path.
    """
    if thresholds is None:
        thresholds = dict(_DEFAULT_THRESHOLDS)
    if cohort_ters_by_category is None:
        cohort_ters_by_category = {}

    sweet_min = float(thresholds.get("mf_aum_sweet_spot_min_cr", Decimal("500")))
    sweet_max = float(thresholds.get("mf_aum_sweet_spot_max_cr", Decimal("5000")))
    min_history_years = float(
        thresholds.get("mf_min_history_years_for_full_confidence", Decimal("3"))
    )
    top_n = int(thresholds.get("mf_holdings_top_n", Decimal("20")))
    leader_pct = float(thresholds.get("mf_atlas_leader_pct", Decimal("25.0")))
    avoid_pct = float(thresholds.get("mf_avoid_pct", Decimal("25.0")))

    # First pass — compute layer 1 metrics, build cohorts per category
    by_cat: dict[str, list[tuple[int, RiskAdjustedMetrics]]] = {}
    layer1_metrics: list[RiskAdjustedMetrics] = []
    for i, fi in enumerate(fund_inputs):
        m = compute_risk_adjusted_metrics(fi.daily_returns, fi.benchmark_daily_returns)
        layer1_metrics.append(m)
        by_cat.setdefault(fi.fund_category, []).append((i, m))

    # Second pass — score each fund
    pre_rows: list[FundScoreRow] = []
    for i, fi in enumerate(fund_inputs):
        cohort = [m for (j, m) in by_cat.get(fi.fund_category, []) if j != i]
        risk_score = score_risk_adjusted_return(layer1_metrics[i], cohort)

        (
            holdings_score,
            survivorship_pct,
            top_holdings,
            holdings_unjoinable,
        ) = compute_holdings_conviction(fi.holdings, conviction_by_iid, top_n=top_n)

        style_score = score_style_sector(fi.style_drift_pct, fi.sector_tilt_bonus)
        cohort_ter = cohort_ters_by_category.get(fi.fund_category, [])
        cost_score = score_cost_manager(
            fi.ter_pct,
            cohort_ter,
            fi.manager_tenure_years,
            fi.aum_cr,
            fi.fund_age_years,
            sweet_min,
            sweet_max,
        )

        components: dict[str, Decimal | None] = {
            "risk_adjusted_return_score": risk_score,
            "holdings_conviction_score": holdings_score,
            "style_sector_score": style_score,
            "cost_manager_score": cost_score,
        }
        composite = _compute_composite(components, thresholds)

        # confidence_low if too few observations (< 3y trading days ≈ 750)
        n_obs = layer1_metrics[i].n_observations
        min_obs = int(min_history_years * 252)
        confidence_low = n_obs < min_obs

        m = layer1_metrics[i]
        sub_metrics = {
            "sharpe": m.sharpe,
            "sortino": m.sortino,
            "alpha": m.alpha,
            "max_dd": m.max_dd,
            "calmar": m.calmar,
            "up_capture": m.up_capture,
            "down_capture": m.down_capture,
            "n_observations": n_obs,
            "ter_pct": fi.ter_pct,
            "aum_cr": fi.aum_cr,
            "manager_tenure_years": fi.manager_tenure_years,
            "fund_age_years": fi.fund_age_years,
        }

        pre_rows.append(
            FundScoreRow(
                snapshot_date=snapshot_date,
                scheme_code=fi.scheme_code,
                isin=fi.isin,
                fund_name=fi.fund_name,
                fund_category=fi.fund_category,
                fund_style=fi.fund_style,
                amc=fi.amc,
                risk_adjusted_return_score=risk_score,
                holdings_conviction_score=holdings_score,
                style_sector_score=style_score,
                cost_manager_score=cost_score,
                composite_score=composite,
                rank_in_category=None,
                category_size=None,
                is_atlas_leader=False,
                is_avoid=False,
                confidence_low=confidence_low,
                holdings_unjoinable=holdings_unjoinable,
                survivorship_exposure_pct=Decimal(f"{survivorship_pct:.2f}"),
                nav_as_of=fi.nav_as_of,
                holdings_as_of=fi.holdings_as_of,
                eli5=None,
                sub_metrics=sub_metrics,
                top_holdings=top_holdings,
            )
        )

    # Rank within category, set Atlas Leader + Avoid + ELI5
    rows: list[FundScoreRow] = []
    by_cat_idx: dict[str, list[int]] = {}
    for idx, r in enumerate(pre_rows):
        by_cat_idx.setdefault(r.fund_category, []).append(idx)
    for _cat, idxs in by_cat_idx.items():
        sorted_idxs = sorted(idxs, key=lambda i: float(pre_rows[i].composite_score), reverse=True)
        n = len(sorted_idxs)
        leader_cutoff = max(1, round(n * leader_pct / 100.0))
        avoid_cutoff = max(1, round(n * avoid_pct / 100.0))
        for rank, i in enumerate(sorted_idxs, start=1):
            r = pre_rows[i]
            is_leader = rank <= leader_cutoff
            is_avoid = rank > (n - avoid_cutoff)
            ranked = FundScoreRow(
                **{
                    **asdict(r),
                    "rank_in_category": rank,
                    "category_size": n,
                    "is_atlas_leader": is_leader and not r.confidence_low,
                    "is_avoid": is_avoid and not r.confidence_low,
                }
            )
            ranked = FundScoreRow(**{**asdict(ranked), "eli5": _eli5_fund(ranked)})
            rows.append(ranked)
    return rows


# ---------------------------------------------------------------------------
# Engine-backed loader (best-effort; degrades if tables missing)
# ---------------------------------------------------------------------------


def _try_load_fund_inputs_from_engine(
    engine: Engine, snapshot_date: date
) -> tuple[list[FundInput], dict[str, list[float]]]:
    """Load FundInput rows from the live DB.

    Schema expectations:
      * ``atlas.atlas_universe_funds`` (mstar_id, scheme_name, amc, category_name, ...)
      * ``public.de_mf_nav_daily`` (mstar_id, nav_date, nav)
      * ``public.de_mf_holdings`` (mstar_id, as_of_date, instrument_id, weight_pct)
      * ``public.de_mf_master`` (extended fields: TER, AUM, inception_date)

    Returns ([], {}) if any of these are missing — caller handles it.
    """
    funds: list[FundInput] = []
    cohort_ters: dict[str, list[float]] = {}
    try:
        with engine.connect() as conn:
            fund_rows = (
                conn.execute(
                    text(
                        """
                        SELECT
                            u.mstar_id,
                            u.scheme_name,
                            u.amc,
                            u.category_name,
                            u.broad_category,
                            u.inception_date,
                            u.benchmark_code
                        FROM atlas.atlas_universe_funds u
                        WHERE u.effective_to IS NULL
                        """
                    )
                )
                .mappings()
                .all()
            )
    except Exception as exc:
        log.info("fund_scorecard_universe_unavailable", error=str(exc))
        return [], {}

    if not fund_rows:
        return [], {}

    # Best-effort per-fund payload — we accept partial data and let the
    # layer scorers degrade gracefully when fields are missing.
    for fr in fund_rows[:1000]:  # cap as safety; production has ~500
        mstar_id = str(fr["mstar_id"])
        category = str(fr["category_name"])
        inception = fr.get("inception_date")
        fund_age = None
        if inception is not None:
            fund_age = max(0.0, (snapshot_date - inception).days / 365.25)

        # NAV daily returns (best-effort)
        daily_returns: list[float] = []
        nav_as_of: date | None = None
        try:
            with engine.connect() as conn:
                navs = (
                    conn.execute(
                        text(
                            """
                            SELECT nav_date, nav
                            FROM public.de_mf_nav_daily
                            WHERE mstar_id = :m
                              AND nav_date <= :d
                            ORDER BY nav_date
                            """
                        ),
                        {"m": mstar_id, "d": snapshot_date},
                    )
                    .mappings()
                    .all()
                )
            prev: float | None = None
            for nv in navs:
                nav_val = float(nv["nav"]) if nv["nav"] is not None else None
                if nav_val is None or nav_val <= 0:
                    continue
                if prev is not None and prev > 0:
                    daily_returns.append((nav_val - prev) / prev)
                prev = nav_val
                nav_as_of = nv["nav_date"]
        except Exception as exc:
            log.info("fund_nav_load_failed", mstar_id=mstar_id, error=str(exc))

        holdings_rows: list[Mapping[str, Any]] = []
        holdings_as_of: date | None = None
        try:
            with engine.connect() as conn:
                hr = (
                    conn.execute(
                        text(
                            """
                            SELECT instrument_id::text AS instrument_id,
                                   weight_pct,
                                   holding_name AS symbol,
                                   as_of_date
                            FROM public.de_mf_holdings
                            WHERE mstar_id = :m
                              AND as_of_date <= :d
                              AND as_of_date = (
                                  SELECT MAX(as_of_date)
                                  FROM public.de_mf_holdings
                                  WHERE mstar_id = :m AND as_of_date <= :d
                              )
                            ORDER BY weight_pct DESC
                            """
                        ),
                        {"m": mstar_id, "d": snapshot_date},
                    )
                    .mappings()
                    .all()
                )
            for h in hr:
                holdings_rows.append(dict(h))
                if h.get("as_of_date") is not None:
                    holdings_as_of = h["as_of_date"]
        except Exception as exc:
            log.info("fund_holdings_load_failed", mstar_id=mstar_id, error=str(exc))

        funds.append(
            FundInput(
                scheme_code=mstar_id,
                isin=None,
                fund_name=fr.get("scheme_name"),
                fund_category=category,
                fund_style=None,
                amc=fr.get("amc"),
                daily_returns=daily_returns,
                benchmark_daily_returns=[],
                nav_as_of=nav_as_of,
                holdings_as_of=holdings_as_of,
                holdings=holdings_rows,
                style_drift_pct=None,
                sector_tilt_bonus=None,
                ter_pct=None,
                manager_tenure_years=None,
                aum_cr=None,
                fund_age_years=fund_age,
            )
        )
    return funds, cohort_ters


def _load_conviction_for_date(engine: Engine, snapshot_date: date) -> dict[str, str]:
    """Return {instrument_id -> best-tenure verdict} for snapshot_date.

    Prefers the 6m verdict (the canonical mid-tenure view).
    """
    out: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT instrument_id::text AS instrument_id, verdict
                    FROM atlas.atlas_conviction_daily
                    WHERE snapshot_date = :d AND tenure = '6m'
                    """
                ),
                {"d": snapshot_date},
            ).mappings()
            for r in rows:
                out[r["instrument_id"]] = r["verdict"]
    except Exception as exc:
        log.info("fund_conviction_load_failed", error=str(exc))
    return out


def compute_fund_scorecard_from_engine(
    snapshot_date: date,
    engine: Engine,
) -> list[FundScoreRow]:
    """Production path — read all inputs from the live DB and score."""
    thresholds = _load_mf_thresholds(engine)
    fund_inputs, cohort_ters = _try_load_fund_inputs_from_engine(engine, snapshot_date)
    if not fund_inputs:
        log.warning("fund_scorecard_no_inputs", date=str(snapshot_date))
        return []
    conviction = _load_conviction_for_date(engine, snapshot_date)
    return compute_fund_scorecard(
        snapshot_date,
        fund_inputs=fund_inputs,
        conviction_by_iid=conviction,
        thresholds=thresholds,
        cohort_ters_by_category=cohort_ters,
    )


# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------


def _sql_quote(s: Any) -> str:
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def _sql_decimal(d: Decimal | None) -> str:
    if d is None:
        return "NULL"
    return f"{float(d):.4f}"


def _sql_date(d: date | None) -> str:
    if d is None:
        return "NULL"
    return f"'{d.isoformat()}'"


def emit_upsert_sql(rows: list[FundScoreRow]) -> str:
    """Build a multi-row INSERT...ON CONFLICT statement."""
    if not rows:
        return "-- (no rows)\n"
    values_lines: list[str] = []
    for r in rows:
        sub_json = _sql_quote(json.dumps(r.sub_metrics, default=str)) + "::jsonb"
        top_json = _sql_quote(json.dumps(r.top_holdings, default=str)) + "::jsonb"
        values_lines.append(
            "  ("
            f"'{r.snapshot_date.isoformat()}', "
            f"'{r.scheme_code}', "
            f"{_sql_quote(r.isin)}, "
            f"{_sql_quote(r.fund_name)}, "
            f"{_sql_quote(r.fund_category)}, "
            f"{_sql_quote(r.fund_style)}, "
            f"{_sql_quote(r.amc)}, "
            f"{_sql_decimal(r.risk_adjusted_return_score)}, "
            f"{_sql_decimal(r.holdings_conviction_score)}, "
            f"{_sql_decimal(r.style_sector_score)}, "
            f"{_sql_decimal(r.cost_manager_score)}, "
            f"{_sql_decimal(r.composite_score)}, "
            f"{r.rank_in_category if r.rank_in_category is not None else 'NULL'}, "
            f"{r.category_size if r.category_size is not None else 'NULL'}, "
            f"{'TRUE' if r.is_atlas_leader else 'FALSE'}, "
            f"{'TRUE' if r.is_avoid else 'FALSE'}, "
            f"{'TRUE' if r.confidence_low else 'FALSE'}, "
            f"{'TRUE' if r.holdings_unjoinable else 'FALSE'}, "
            f"{_sql_decimal(r.survivorship_exposure_pct)}, "
            f"{_sql_date(r.nav_as_of)}, "
            f"{_sql_date(r.holdings_as_of)}, "
            f"{_sql_quote(r.eli5)}, "
            f"{sub_json}, "
            f"{top_json}"
            ")"
        )
    return (
        "INSERT INTO atlas.atlas_fund_scorecard "
        "(snapshot_date, scheme_code, isin, fund_name, fund_category, fund_style, "
        "amc, risk_adjusted_return_score, holdings_conviction_score, "
        "style_sector_score, cost_manager_score, composite_score, rank_in_category, "
        "category_size, is_atlas_leader, is_avoid, confidence_low, "
        "holdings_unjoinable, survivorship_exposure_pct, nav_as_of, holdings_as_of, "
        "eli5, sub_metrics, top_holdings) VALUES\n"
        + ",\n".join(values_lines)
        + "\nON CONFLICT (snapshot_date, scheme_code) DO UPDATE SET\n"
        "  fund_category = EXCLUDED.fund_category,\n"
        "  risk_adjusted_return_score = EXCLUDED.risk_adjusted_return_score,\n"
        "  holdings_conviction_score = EXCLUDED.holdings_conviction_score,\n"
        "  style_sector_score = EXCLUDED.style_sector_score,\n"
        "  cost_manager_score = EXCLUDED.cost_manager_score,\n"
        "  composite_score = EXCLUDED.composite_score,\n"
        "  rank_in_category = EXCLUDED.rank_in_category,\n"
        "  category_size = EXCLUDED.category_size,\n"
        "  is_atlas_leader = EXCLUDED.is_atlas_leader,\n"
        "  is_avoid = EXCLUDED.is_avoid,\n"
        "  confidence_low = EXCLUDED.confidence_low,\n"
        "  holdings_unjoinable = EXCLUDED.holdings_unjoinable,\n"
        "  survivorship_exposure_pct = EXCLUDED.survivorship_exposure_pct,\n"
        "  nav_as_of = EXCLUDED.nav_as_of,\n"
        "  holdings_as_of = EXCLUDED.holdings_as_of,\n"
        "  eli5 = EXCLUDED.eli5,\n"
        "  sub_metrics = EXCLUDED.sub_metrics,\n"
        "  top_holdings = EXCLUDED.top_holdings;\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _has_write_marker(repo_root: Path) -> bool:
    return (repo_root / ".supabase-write-approved").exists()


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", required=True)
    p.add_argument("--backfill", action="store_true")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    snapshot_date = date.fromisoformat(args.date)

    from atlas.db import get_engine

    engine = get_engine()
    rows = compute_fund_scorecard_from_engine(snapshot_date, engine)
    log.info("fund_scorecard_computed", date=str(snapshot_date), n_rows=len(rows))

    if _has_write_marker(args.repo_root):
        sql = emit_upsert_sql(rows)
        if sql.strip().startswith("--"):
            print("Nothing to write.")
            return 0
        with engine.begin() as conn:
            conn.execute(text(sql))
        print(f"Wrote {len(rows)} rows to atlas_fund_scorecard")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"fund_scorecard_{snapshot_date.isoformat()}.sql"
    out_path.write_text(emit_upsert_sql(rows))
    print(f"Wrote {len(rows)} rows to {out_path}")
    print("Live DB write skipped — .supabase-write-approved marker not present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
