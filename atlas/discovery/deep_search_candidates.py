"""Generic candidate generator for the 24-cell deep-search.

Generates ~250-400 candidate rules per cell across the (cap_tier ×
tenure × direction) matrix. POSITIVE direction emits accumulation /
leadership / consolidation archetypes; NEGATIVE direction emits
distribution / breakdown / overextension archetypes.

Each candidate is a flat-AND chain of FeaturePredicate: one tier
liquidity floor followed by 1-3 entry predicates.
"""

# allow-large: cohesive candidate-generation surface across 16 archetype
# families × 4 tenures × 3 tiers × 2 directions = 24 cells. Splitting by
# archetype would obscure cross-archetype threshold consistency.

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from atlas.decisions.rule_dsl import FeaturePredicate

Tier = Literal["Large", "Mid", "Small"]
Tenure = Literal["1m", "3m", "6m", "12m"]
Direction = Literal["POSITIVE", "NEGATIVE"]


@dataclass(frozen=True)
class CandidateRule:
    """One feature/threshold combination to try.

    Attributes:
        name: stable identifier used in the report.
        archetype: which family this is from. POSITIVE archetypes:
            mean_reversion, deep_value, quality_momentum, inflection,
            consolidation_breakout, liquidity_expansion, structural,
            low_vol_carry, breakout_with_pullback.
            NEGATIVE archetypes: mean_reversion_overbought, distribution,
            volatility_spike, breakdown, deep_value_avoid, weak_quality,
            overextension.
        features: flat-AND list of FeaturePredicate.
        rationale: one-line hypothesis.
    """

    name: str
    archetype: str
    features: tuple[FeaturePredicate, ...]
    rationale: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pred(feature: str, cmp: str, value: Decimal | tuple[Decimal, Decimal]) -> FeaturePredicate:
    """Concise FeaturePredicate factory for scalar / in_range comparisons."""
    if cmp == "in_range" and isinstance(value, tuple):
        return FeaturePredicate(feature=feature, cmp="in_range", value=value)
    if isinstance(value, tuple):
        raise ValueError(f"tuple value only valid for in_range, got cmp={cmp!r}")
    return FeaturePredicate(feature=feature, cmp=cmp, value=value)  # type: ignore[arg-type]


def _topq(feature: str, n: int) -> FeaturePredicate:
    """Top-1/n quantile predicate (e.g. n=10 → top decile)."""
    return FeaturePredicate(
        feature=feature, cmp="in_top_quantile", value=Decimal("1"), value_quantile_n=n
    )


_TIER_LIQUIDITY: dict[str, Decimal] = {
    "Large": Decimal("16.5"),
    "Mid": Decimal("15.5"),
    "Small": Decimal("14.5"),
}


def _liquidity_floor(tier: str) -> FeaturePredicate:
    """Standard liquidity gate for the given tier."""
    return _pred("log_med_tv_60d", ">=", _TIER_LIQUIDITY[tier])


def _tag(tier: str, tenure: str) -> str:
    """Short prefix for candidate names — tier+tenure abbreviation."""
    return f"{tier[0]}{tenure}"


# ---------------------------------------------------------------------------
# POSITIVE archetypes
# ---------------------------------------------------------------------------


def _gen_mean_reversion(tier: str, tenure: str) -> list[CandidateRule]:
    """Pullback-flavored: top-RS leaders that pulled back from peak."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)

    mr_dd_bands_52w: list[tuple[Decimal, Decimal]] = [
        (Decimal("-0.20"), Decimal("-0.05")),
        (Decimal("-0.15"), Decimal("-0.03")),
        (Decimal("-0.12"), Decimal("-0.05")),
        (Decimal("-0.25"), Decimal("-0.05")),
        (Decimal("-0.30"), Decimal("-0.10")),
        (Decimal("-0.10"), Decimal("-0.02")),
        (Decimal("-0.08"), Decimal("-0.02")),
    ]
    for low, high in mr_dd_bands_52w:
        for q in (10, 4):  # top decile, top quartile
            out.append(
                CandidateRule(
                    name=f"MR_{tag}_rs6m_topq{q}_dd52w_{int(float(low) * 100)}_{int(float(high) * 100)}",  # noqa: E501
                    archetype="mean_reversion",
                    features=(
                        floor,
                        _topq("rs_residual_6m", q),
                        _pred("dd_from_52w_high", "in_range", (low, high)),
                    ),
                    rationale=f"{tier} + top-1/{q} 6m RS + dd_52w in [{low},{high}] — leader pullback",  # noqa: E501
                )
            )
    for low, high in mr_dd_bands_52w[:5]:
        out.append(
            CandidateRule(
                name=f"MR_{tag}_rs12m_topd_dd52w_{int(float(low) * 100)}_{int(float(high) * 100)}",
                archetype="mean_reversion",
                features=(
                    floor,
                    _topq("rs_residual_12m", 10),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + top-decile 12m RS + dd_52w in [{low},{high}]",
            )
        )
    for low, high in mr_dd_bands_52w[:5]:
        out.append(
            CandidateRule(
                name=f"MR_{tag}_rs3m_topq_dd52w_{int(float(low) * 100)}_{int(float(high) * 100)}",
                archetype="mean_reversion",
                features=(
                    floor,
                    _topq("rs_residual_3m", 4),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + top-Q 3m RS + dd_52w in [{low},{high}]",
            )
        )
    for low, high in [
        (Decimal("-0.40"), Decimal("-0.15")),
        (Decimal("-0.30"), Decimal("-0.10")),
        (Decimal("-0.50"), Decimal("-0.20")),
        (Decimal("-0.35"), Decimal("-0.12")),
    ]:
        out.append(
            CandidateRule(
                name=f"MR_{tag}_rs6m_topd_dd3y_{int(float(low) * 100)}_{int(float(high) * 100)}",
                archetype="mean_reversion",
                features=(
                    floor,
                    _topq("rs_residual_6m", 10),
                    _pred("dd_from_3y_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + top-decile 6m RS + dd_3y in [{low},{high}]",
            )
        )
    # Add RSI-pullback variants (oversold reversion within leaders)
    for rsi_lo, rsi_hi in [
        (Decimal("30"), Decimal("45")),
        (Decimal("25"), Decimal("40")),
        (Decimal("35"), Decimal("50")),
    ]:
        out.append(
            CandidateRule(
                name=f"MR_{tag}_rs6m_topq_rsi_{int(float(rsi_lo))}_{int(float(rsi_hi))}",
                archetype="mean_reversion",
                features=(
                    floor,
                    _topq("rs_residual_6m", 4),
                    _pred("rsi_14", "in_range", (rsi_lo, rsi_hi)),
                ),
                rationale=f"{tier} + top-quartile 6m RS + RSI in [{rsi_lo},{rsi_hi}] — oversold leader",  # noqa: E501
            )
        )
    # dd_recovery_pct bands — at lower 30-60% of 52w range
    for r_lo, r_hi in [
        (Decimal("0.30"), Decimal("0.60")),
        (Decimal("0.20"), Decimal("0.50")),
        (Decimal("0.40"), Decimal("0.70")),
    ]:
        out.append(
            CandidateRule(
                name=f"MR_{tag}_rs6m_topd_rec_{int(float(r_lo) * 100)}_{int(float(r_hi) * 100)}",
                archetype="mean_reversion",
                features=(
                    floor,
                    _topq("rs_residual_6m", 10),
                    _pred("dd_recovery_pct", "in_range", (r_lo, r_hi)),
                ),
                rationale=f"{tier} + top-decile 6m RS + 52w-range pos in [{r_lo},{r_hi}]",
            )
        )
    # Within-tier rank variants (red-team gap 5) — top-quintile within tier.
    for low, high in mr_dd_bands_52w[:5]:
        out.append(
            CandidateRule(
                name=f"MR_{tag}_wt_rs6m_topq_dd52w_{int(float(low) * 100)}_{int(float(high) * 100)}",  # noqa: E501
                archetype="mean_reversion",
                features=(
                    floor,
                    _pred("rs_rank_within_tier_6m", ">=", Decimal("0.80")),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + within-tier top-quintile 6m RS + dd_52w in [{low},{high}]",
            )
        )
        out.append(
            CandidateRule(
                name=f"MR_{tag}_wt_rs12m_topq_dd52w_{int(float(low) * 100)}_{int(float(high) * 100)}",  # noqa: E501
                archetype="mean_reversion",
                features=(
                    floor,
                    _pred("rs_rank_within_tier_12m", ">=", Decimal("0.80")),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + within-tier top-quintile 12m RS + dd_52w in [{low},{high}]",
            )
        )
    return out


def _gen_deep_value(tier: str, tenure: str) -> list[CandidateRule]:
    """Severely-broken-as-reversal-fuel: very-deep drawdowns."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for low, high in [
        (Decimal("-0.60"), Decimal("-0.40")),
        (Decimal("-0.50"), Decimal("-0.30")),
        (Decimal("-0.70"), Decimal("-0.40")),
        (Decimal("-0.45"), Decimal("-0.25")),
    ]:
        out.append(
            CandidateRule(
                name=f"DV_{tag}_neg6m_dd52w_{int(float(low) * 100)}_{int(float(high) * 100)}",
                archetype="deep_value",
                features=(
                    floor,
                    _pred("rs_residual_6m", "<", Decimal("0")),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + neg 6m RS + dd_52w in [{low},{high}]",
            )
        )
    for low, high in [
        (Decimal("-0.70"), Decimal("-0.40")),
        (Decimal("-0.80"), Decimal("-0.50")),
        (Decimal("-0.60"), Decimal("-0.30")),
    ]:
        out.append(
            CandidateRule(
                name=f"DV_{tag}_neg12m_dd5y_{int(float(low) * 100)}_{int(float(high) * 100)}",
                archetype="deep_value",
                features=(
                    floor,
                    _pred("rs_residual_12m", "<", Decimal("0")),
                    _pred("dd_from_5y_high", "in_range", (low, high)),
                ),
                rationale=f"{tier} + neg 12m RS + dd_5y in [{low},{high}]",
            )
        )
    # Deep value with early recovery (dd_recovery_pct rising off the low)
    for rec_lo, rec_hi in [
        (Decimal("0.10"), Decimal("0.35")),
        (Decimal("0.05"), Decimal("0.25")),
        (Decimal("0.15"), Decimal("0.40")),
    ]:
        out.append(
            CandidateRule(
                name=f"DV_{tag}_recovery_{int(float(rec_lo) * 100)}_{int(float(rec_hi) * 100)}",
                archetype="deep_value",
                features=(
                    floor,
                    _pred("dd_from_52w_high", "<=", Decimal("-0.30")),
                    _pred("dd_recovery_pct", "in_range", (rec_lo, rec_hi)),
                ),
                rationale=f"{tier} + dd ≥30% + recovery pct in [{rec_lo},{rec_hi}]",
            )
        )
    # Deep dd with RSI bottoming
    for dd_max, rsi_max in [
        (Decimal("-0.30"), Decimal("35")),
        (Decimal("-0.40"), Decimal("30")),
        (Decimal("-0.50"), Decimal("40")),
    ]:
        out.append(
            CandidateRule(
                name=f"DV_{tag}_dd{int(float(dd_max) * 100)}_rsi{int(float(rsi_max))}",
                archetype="deep_value",
                features=(
                    floor,
                    _pred("dd_from_52w_high", "<=", dd_max),
                    _pred("rsi_14", "<=", rsi_max),
                ),
                rationale=f"{tier} + dd <= {dd_max} + RSI <= {rsi_max} — washout",
            )
        )
    # Deep value + dist from 52w low recovering
    for low_dist_min in [Decimal("0.05"), Decimal("0.10"), Decimal("0.15")]:
        out.append(
            CandidateRule(
                name=f"DV_{tag}_off_low_{int(float(low_dist_min) * 100)}",
                archetype="deep_value",
                features=(
                    floor,
                    _pred("dd_from_52w_high", "<=", Decimal("-0.30")),
                    _pred("dist_from_52w_low", ">=", low_dist_min),
                ),
                rationale=f"{tier} + deep dd + lifted off low by {low_dist_min}",
            )
        )
    return out


def _gen_quality_momentum(tier: str, tenure: str) -> list[CandidateRule]:
    """Sustained leaders compounding institutional demand."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    # Vol caps scale with tier (small-caps need wider).
    vol_bands_by_tier: dict[str, list[Decimal]] = {
        "Large": [Decimal("0.018"), Decimal("0.022"), Decimal("0.025"), Decimal("0.030")],
        "Mid": [Decimal("0.022"), Decimal("0.028"), Decimal("0.033"), Decimal("0.040")],
        "Small": [Decimal("0.028"), Decimal("0.035"), Decimal("0.045"), Decimal("0.055")],
    }
    for vol_cap in vol_bands_by_tier[tier]:
        for q in (10, 4):
            out.append(
                CandidateRule(
                    name=f"QM_{tag}_rs6m_topq{q}_lowvol_{int(float(vol_cap) * 1000)}",
                    archetype="quality_momentum",
                    features=(
                        floor,
                        _topq("rs_residual_6m", q),
                        _pred("realized_vol_60d", "<=", vol_cap),
                    ),
                    rationale=f"{tier} + top-1/{q} 6m RS + vol_60d <= {vol_cap}",
                )
            )
        out.append(
            CandidateRule(
                name=f"QM_{tag}_rs12m_topd_lowvol_{int(float(vol_cap) * 1000)}",
                archetype="quality_momentum",
                features=(
                    floor,
                    _topq("rs_residual_12m", 10),
                    _pred("realized_vol_60d", "<=", vol_cap),
                ),
                rationale=f"{tier} + top-decile 12m RS + vol_60d <= {vol_cap}",
            )
        )
    # Mega-liquid (higher liquidity floor) variants
    extra_tv = {"Large": Decimal("17.5"), "Mid": Decimal("16.0"), "Small": Decimal("15.0")}[tier]
    out.append(
        CandidateRule(
            name=f"QM_{tag}_rs12m_topd_megaliq",
            archetype="quality_momentum",
            features=(_pred("log_med_tv_60d", ">=", extra_tv), _topq("rs_residual_12m", 10)),
            rationale=f"Mega-liquid (tv >= {extra_tv}) {tier} + top-decile 12m RS",
        )
    )
    # Age gates
    for age_min in [Decimal("1825"), Decimal("2520"), Decimal("3650")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_rs6m_topd_mature_{int(age_min)}d",
                archetype="quality_momentum",
                features=(
                    floor,
                    _topq("rs_residual_6m", 10),
                    _pred("listing_age_days", ">=", age_min),
                ),
                rationale=f"Mature (>= {age_min}d) {tier} + top-decile 6m RS",
            )
        )
    # rs_alignment_count
    for align_min in [Decimal("2"), Decimal("3")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_align{int(align_min)}_lowvol",
                archetype="quality_momentum",
                features=(
                    floor,
                    _pred("rs_alignment_count", ">=", align_min),
                    _pred("realized_vol_60d", "<=", vol_bands_by_tier[tier][2]),
                ),
                rationale=f"{tier} + rs_alignment >= {align_min} + moderate vol",
            )
        )
    # pos_months_12m
    for pos_min in [Decimal("0.58"), Decimal("0.67"), Decimal("0.75")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_pos12m_{int(float(pos_min) * 100)}",
                archetype="quality_momentum",
                features=(
                    floor,
                    _pred("pos_months_12m", ">=", pos_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + pos_months_12m >= {pos_min} + top-quartile 6m RS",
            )
        )
    # momentum_quality_6m (risk-adjusted RS)
    for mq_min in [Decimal("3"), Decimal("5"), Decimal("8"), Decimal("12")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_mq6m_{int(float(mq_min))}",
                archetype="quality_momentum",
                features=(
                    floor,
                    _pred("momentum_quality_6m", ">=", mq_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + momentum_quality_6m >= {mq_min} (risk-adj RS)",
            )
        )
    # max-consec-pos-months (run-length)
    for run_min in [Decimal("4"), Decimal("5"), Decimal("6"), Decimal("8")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_run_{int(float(run_min))}",
                archetype="quality_momentum",
                features=(
                    floor,
                    _pred("max_consec_pos_months_12m", ">=", run_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + max-consec-pos-months >= {run_min} + top-Q 6m RS",
            )
        )
    # Within-tier rank variants (red-team gap 5)
    for rk_min in [Decimal("0.75"), Decimal("0.85"), Decimal("0.90")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_wt_rs6m_{int(float(rk_min) * 100)}",
                archetype="quality_momentum",
                features=(floor, _pred("rs_rank_within_tier_6m", ">=", rk_min)),
                rationale=f"{tier} + within-tier 6m RS >= {rk_min}",
            )
        )
        out.append(
            CandidateRule(
                name=f"QM_{tag}_wt_rs6m_{int(float(rk_min) * 100)}_lowvol",
                archetype="quality_momentum",
                features=(
                    floor,
                    _pred("rs_rank_within_tier_6m", ">=", rk_min),
                    _pred("realized_vol_60d", "<=", vol_bands_by_tier[tier][2]),
                ),
                rationale=f"{tier} + within-tier 6m RS >= {rk_min} + vol cap",
            )
        )
    # pos_weeks_12m (weekly version)
    for wpos_min in [Decimal("0.55"), Decimal("0.60"), Decimal("0.65")]:
        out.append(
            CandidateRule(
                name=f"QM_{tag}_posw{int(float(wpos_min) * 100)}",
                archetype="quality_momentum",
                features=(
                    floor,
                    _pred("pos_weeks_12m", ">=", wpos_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + pos_weeks_12m >= {wpos_min} + top-Q 6m RS",
            )
        )
    return out


def _gen_inflection(tier: str, tenure: str) -> list[CandidateRule]:
    """Trend-change candidates: crosses, acceleration."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for dist_min, dist_max in [
        (Decimal("0.00"), Decimal("0.05")),
        (Decimal("-0.02"), Decimal("0.03")),
        (Decimal("0.00"), Decimal("0.10")),
        (Decimal("-0.05"), Decimal("0.02")),
    ]:
        out.append(
            CandidateRule(
                name=f"INF_{tag}_sma200_x_{int(float(dist_min) * 100)}_{int(float(dist_max) * 100)}",  # noqa: E501
                archetype="inflection",
                features=(
                    floor,
                    _pred("dist_above_sma200", "in_range", (dist_min, dist_max)),
                    _pred("rs_acceleration_63d", ">=", Decimal("0.10")),
                ),
                rationale=f"{tier} + near-SMA200 [{dist_min},{dist_max}] + accel RS",
            )
        )
    # Golden cross — SMA50 above SMA200
    out.append(
        CandidateRule(
            name=f"INF_{tag}_gx_recent",
            archetype="inflection",
            features=(
                floor,
                _pred("sma50_gt_sma200", ">=", Decimal("1")),
                _pred("dist_above_sma50", ">=", Decimal("0.00")),
                _pred("dist_above_sma200", "in_range", (Decimal("0.00"), Decimal("0.15"))),
            ),
            rationale=f"{tier} + golden cross + price modestly above SMA200",
        )
    )
    for accel_min in [Decimal("0.20"), Decimal("0.30"), Decimal("0.40"), Decimal("0.50")]:
        out.append(
            CandidateRule(
                name=f"INF_{tag}_accel_{int(float(accel_min) * 100)}",
                archetype="inflection",
                features=(
                    floor,
                    _pred("rs_acceleration_63d", ">=", accel_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + RS accel >= {accel_min} + positive 6m RS",
            )
        )
    # rs_rank shifts (3m better than 6m by Y)
    for diff_min in [Decimal("0.10"), Decimal("0.15"), Decimal("0.20"), Decimal("0.25")]:
        out.append(
            CandidateRule(
                name=f"INF_{tag}_rsshift_{int(float(diff_min) * 100)}",
                archetype="inflection",
                features=(
                    floor,
                    _pred("rs_rank_6m_3m_diff", "<=", -diff_min),
                    _pred("rs_residual_3m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + 3m rank improved by >= {diff_min} over 6m",
            )
        )
    # consecutive_above_sma50 starting (small streak, RS positive)
    for streak_lo, streak_hi in [
        (Decimal("5"), Decimal("20")),
        (Decimal("10"), Decimal("30")),
        (Decimal("15"), Decimal("40")),
    ]:
        out.append(
            CandidateRule(
                name=f"INF_{tag}_sma50_streak_{int(float(streak_lo))}_{int(float(streak_hi))}",
                archetype="inflection",
                features=(
                    floor,
                    _pred("consecutive_above_sma50", "in_range", (streak_lo, streak_hi)),
                    _topq("rs_residual_3m", 4),
                ),
                rationale=f"{tier} + above-SMA50 streak [{streak_lo},{streak_hi}] + top-Q 3m RS",
            )
        )
    # consecutive_above_sma200 (medium-term inflection)
    for streak_min in [Decimal("20"), Decimal("40"), Decimal("60")]:
        out.append(
            CandidateRule(
                name=f"INF_{tag}_sma200_{int(float(streak_min))}",
                archetype="inflection",
                features=(
                    floor,
                    _pred("consecutive_above_sma200", ">=", streak_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + above-SMA200 streak >= {streak_min} + top-Q 6m RS",
            )
        )
    # roc_63d positive + acceleration
    for roc_min in [Decimal("0.05"), Decimal("0.10"), Decimal("0.15")]:
        out.append(
            CandidateRule(
                name=f"INF_{tag}_roc63_{int(float(roc_min) * 100)}",
                archetype="inflection",
                features=(
                    floor,
                    _pred("roc_63d", ">=", roc_min),
                    _pred("rs_acceleration_63d", ">=", Decimal("0.10")),
                ),
                rationale=f"{tier} + roc_63d >= {roc_min} + RS accel",
            )
        )
    return out


def _gen_consolidation_breakout(tier: str, tenure: str) -> list[CandidateRule]:
    """Low-vol base + breakout to new highs."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    vol_caps = {"Large": Decimal("0.018"), "Mid": Decimal("0.025"), "Small": Decimal("0.030")}[tier]
    for vol_cap in [vol_caps - Decimal("0.005"), vol_caps, vol_caps + Decimal("0.005")]:
        out.append(
            CandidateRule(
                name=f"CB_{tag}_lowvol_60dhi_{int(float(vol_cap) * 1000)}",
                archetype="consolidation_breakout",
                features=(
                    floor,
                    _pred("realized_vol_60d", "<=", vol_cap),
                    _pred("close_over_60d_high", ">=", Decimal("1")),
                ),
                rationale=f"{tier} + vol <= {vol_cap} + at 60d high",
            )
        )
    for dd_min in [
        Decimal("-0.08"),
        Decimal("-0.05"),
        Decimal("-0.10"),
        Decimal("-0.12"),
        Decimal("-0.06"),
    ]:
        out.append(
            CandidateRule(
                name=f"CB_{tag}_shallow_30dhi_{int(float(dd_min) * 100)}",
                archetype="consolidation_breakout",
                features=(
                    floor,
                    _pred("formation_max_dd", ">=", dd_min),
                    _pred("close_over_30d_high", ">=", Decimal("1")),
                ),
                rationale=f"{tier} + shallow base >= {dd_min} + at 30d high",
            )
        )
    out.append(
        CandidateRule(
            name=f"CB_{tag}_pos12m_60dhi",
            archetype="consolidation_breakout",
            features=(
                floor,
                _pred("pos_months_12m", ">=", Decimal("0.58")),
                _pred("close_over_60d_high", ">=", Decimal("1")),
            ),
            rationale=f"{tier} + >= 7/12 pos months + at 60d high",
        )
    )
    # Range compression + breakout
    for compr_max in [Decimal("0.80"), Decimal("0.70"), Decimal("0.60")]:
        out.append(
            CandidateRule(
                name=f"CB_{tag}_rngcompr_{int(float(compr_max) * 100)}",
                archetype="consolidation_breakout",
                features=(
                    floor,
                    _pred("range_compression_60_252", "<=", compr_max),
                    _pred("close_over_60d_high", ">=", Decimal("1")),
                ),
                rationale=f"{tier} + range compression <= {compr_max} + breakout",
            )
        )
    # Volume thrust + breakout
    for vz_min in [Decimal("1.0"), Decimal("1.5"), Decimal("2.0")]:
        out.append(
            CandidateRule(
                name=f"CB_{tag}_volz_{int(float(vz_min) * 10)}_30dhi",
                archetype="consolidation_breakout",
                features=(
                    floor,
                    _pred("volume_zscore_60d", ">=", vz_min),
                    _pred("close_over_30d_high", ">=", Decimal("1")),
                ),
                rationale=f"{tier} + vol_z >= {vz_min} + breakout",
            )
        )
    # BB squeeze + breakout — red-team feature
    out.append(
        CandidateRule(
            name=f"CB_{tag}_bbsq_60dhi",
            archetype="consolidation_breakout",
            features=(
                floor,
                _pred("bb_squeeze_20d", ">=", Decimal("1")),
                _pred("close_over_60d_high", ">=", Decimal("1")),
            ),
            rationale=f"{tier} + bb_squeeze + at 60d high",
        )
    )
    out.append(
        CandidateRule(
            name=f"CB_{tag}_bbsq_topq_rs",
            archetype="consolidation_breakout",
            features=(
                floor,
                _pred("bb_squeeze_20d", ">=", Decimal("1")),
                _topq("rs_residual_6m", 4),
            ),
            rationale=f"{tier} + bb_squeeze + top-Q 6m RS",
        )
    )
    # New-high streak (re-broken-out market)
    for streak_min in [Decimal("3"), Decimal("5"), Decimal("8")]:
        out.append(
            CandidateRule(
                name=f"CB_{tag}_newhi_{int(float(streak_min))}",
                archetype="consolidation_breakout",
                features=(
                    floor,
                    _pred("new_high_streak_60d", ">=", streak_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + new_high_streak >= {streak_min} + top-Q RS",
            )
        )
    # roc_21d positive + low vol — fresh thrust
    for roc_min in [Decimal("0.03"), Decimal("0.05"), Decimal("0.08")]:
        out.append(
            CandidateRule(
                name=f"CB_{tag}_roc21_{int(float(roc_min) * 100)}",
                archetype="consolidation_breakout",
                features=(
                    floor,
                    _pred("roc_21d", ">=", roc_min),
                    _pred("realized_vol_60d", "<=", vol_caps + Decimal("0.01")),
                ),
                rationale=f"{tier} + roc_21d >= {roc_min} + low vol",
            )
        )
    return out


def _gen_liquidity_expansion(tier: str, tenure: str) -> list[CandidateRule]:
    """Rising liquidity / volume — institutional accumulation."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for vz_min in [
        Decimal("0.5"),
        Decimal("1.0"),
        Decimal("1.5"),
        Decimal("2.0"),
        Decimal("2.5"),
        Decimal("3.0"),
    ]:
        out.append(
            CandidateRule(
                name=f"LE_{tag}_vz_{int(float(vz_min) * 10)}_rs6m_pos",
                archetype="liquidity_expansion",
                features=(
                    floor,
                    _pred("volume_zscore_60d", ">=", vz_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + vol_z >= {vz_min} + pos 6m RS",
            )
        )
    # Vol z with 3m RS variant
    for vz_min in [Decimal("1.0"), Decimal("1.5"), Decimal("2.0")]:
        out.append(
            CandidateRule(
                name=f"LE_{tag}_vz_{int(float(vz_min) * 10)}_rs3m_pos",
                archetype="liquidity_expansion",
                features=(
                    floor,
                    _pred("volume_zscore_60d", ">=", vz_min),
                    _pred("rs_residual_3m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + vol_z >= {vz_min} + pos 3m RS",
            )
        )
    out.append(
        CandidateRule(
            name=f"LE_{tag}_vz2_topq",
            archetype="liquidity_expansion",
            features=(
                floor,
                _pred("volume_zscore_60d", ">=", Decimal("2.0")),
                _topq("rs_residual_6m", 4),
            ),
            rationale=f"{tier} + vol_z >= 2 + top-Q 6m RS",
        )
    )
    # tv_momentum_21_63: short-term TV expansion
    for tvm_min in [Decimal("1.2"), Decimal("1.4"), Decimal("1.6"), Decimal("1.8")]:
        out.append(
            CandidateRule(
                name=f"LE_{tag}_tvmom_{int(float(tvm_min) * 10)}",
                archetype="liquidity_expansion",
                features=(
                    floor,
                    _pred("tv_momentum_21_63", ">=", tvm_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + 21/63 TV mom >= {tvm_min} + top-Q 6m RS",
            )
        )
    # volume_zscore_252d (longer-term expansion)
    for vz_min in [Decimal("0.5"), Decimal("1.0"), Decimal("1.5")]:
        out.append(
            CandidateRule(
                name=f"LE_{tag}_vz252_{int(float(vz_min) * 10)}",
                archetype="liquidity_expansion",
                features=(
                    floor,
                    _pred("volume_zscore_252d", ">=", vz_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + 252d vol_z >= {vz_min} + pos 6m RS",
            )
        )
    # Amihud illiq dropping (becoming liquid) + RS pos
    for amihud_max in [Decimal("1e-10"), Decimal("1e-9"), Decimal("1e-8")]:
        out.append(
            CandidateRule(
                name=f"LE_{tag}_amihud_low_{int(float(amihud_max) * 1e12)}",
                archetype="liquidity_expansion",
                features=(
                    floor,
                    _pred("amihud_illiq_21d", "<=", amihud_max),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + amihud_illiq <= {amihud_max} + top-Q 6m RS",
            )
        )
    return out


def _gen_structural(tier: str, tenure: str) -> list[CandidateRule]:
    """Multi-year structural setups."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for dd_min, dd_max in [
        (Decimal("-0.40"), Decimal("-0.15")),
        (Decimal("-0.50"), Decimal("-0.20")),
    ]:
        out.append(
            CandidateRule(
                name=f"STR_{tag}_mature_dd5y_{int(float(dd_min) * 100)}_{int(float(dd_max) * 100)}",
                archetype="structural",
                features=(
                    floor,
                    _pred("listing_age_days", ">=", Decimal("3650")),
                    _pred("dd_from_5y_high", "in_range", (dd_min, dd_max)),
                    _pred("rs_residual_12m", ">", Decimal("0")),
                ),
                rationale=f"Mature {tier} + dd_5y in [{dd_min},{dd_max}] + pos 12m RS",
            )
        )
    for slope_min in [Decimal("0.0005"), Decimal("0.001"), Decimal("0.0015"), Decimal("0.002")]:
        out.append(
            CandidateRule(
                name=f"STR_{tag}_slope_{int(float(slope_min) * 10000)}_sma200",
                archetype="structural",
                features=(
                    floor,
                    _pred("trend_slope_60d", ">=", slope_min),
                    _pred("dist_above_sma200", ">=", Decimal("0.05")),
                ),
                rationale=f"{tier} + slope >= {slope_min} + above SMA200",
            )
        )
    out.append(
        CandidateRule(
            name=f"STR_{tag}_age_rs12m_slope",
            archetype="structural",
            features=(
                floor,
                _pred("listing_age_days", ">=", Decimal("3650")),
                _topq("rs_residual_12m", 10),
                _pred("trend_slope_60d", ">=", Decimal("0.0005")),
            ),
            rationale=f"10y+ {tier} + top-decile 12m RS + positive slope",
        )
    )
    # trend_strength_60d (r^2)
    for ts_min in [Decimal("0.50"), Decimal("0.65"), Decimal("0.80")]:
        out.append(
            CandidateRule(
                name=f"STR_{tag}_trendstr_{int(float(ts_min) * 100)}",
                archetype="structural",
                features=(
                    floor,
                    _pred("trend_strength_60d", ">=", ts_min),
                    _pred("trend_slope_60d", ">=", Decimal("0.0005")),
                ),
                rationale=f"{tier} + trend r^2 >= {ts_min} + positive slope",
            )
        )
    # roc_126d positive + mature + low ulcer
    for roc_min in [Decimal("0.10"), Decimal("0.20"), Decimal("0.30")]:
        out.append(
            CandidateRule(
                name=f"STR_{tag}_roc126_{int(float(roc_min) * 100)}",
                archetype="structural",
                features=(
                    floor,
                    _pred("roc_126d", ">=", roc_min),
                    _pred("ulcer_index_60d", "<=", Decimal("0.05")),
                ),
                rationale=f"{tier} + roc_126d >= {roc_min} + ulcer <= 5%",
            )
        )
    # Pos_weeks high + above SMA200
    for pw_min in [Decimal("0.55"), Decimal("0.60"), Decimal("0.65")]:
        out.append(
            CandidateRule(
                name=f"STR_{tag}_posw_{int(float(pw_min) * 100)}",
                archetype="structural",
                features=(
                    floor,
                    _pred("pos_weeks_12m", ">=", pw_min),
                    _pred("dist_above_sma200", ">=", Decimal("0.05")),
                ),
                rationale=f"{tier} + pos_weeks >= {pw_min} + above SMA200",
            )
        )
    return out


def _gen_low_vol_carry(tier: str, tenure: str) -> list[CandidateRule]:
    """Pure low-vol defensive carry — Large/Mid leaning."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    vol_max = {"Large": Decimal("0.015"), "Mid": Decimal("0.020"), "Small": Decimal("0.025")}[tier]
    for vc in [vol_max - Decimal("0.003"), vol_max, vol_max + Decimal("0.003")]:
        out.append(
            CandidateRule(
                name=f"LVC_{tag}_vol_{int(float(vc) * 1000)}",
                archetype="low_vol_carry",
                features=(
                    floor,
                    _pred("realized_vol_60d", "<=", vc),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + vol <= {vc} + positive 6m RS",
            )
        )
    # downside-vol-focused
    for dvc in [Decimal("0.010"), Decimal("0.013"), Decimal("0.016")]:
        out.append(
            CandidateRule(
                name=f"LVC_{tag}_dvol_{int(float(dvc) * 1000)}",
                archetype="low_vol_carry",
                features=(
                    floor,
                    _pred("downside_vol_60d", "<=", dvc),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + downside_vol <= {dvc} + positive 6m RS",
            )
        )
    # excess-vol negative (relatively lower than universe)
    for ev_max in [Decimal("-0.005"), Decimal("-0.002"), Decimal("0")]:
        out.append(
            CandidateRule(
                name=f"LVC_{tag}_exvol_{int(float(ev_max) * 1000)}",
                archetype="low_vol_carry",
                features=(floor, _pred("excess_vol_60d", "<=", ev_max), _topq("rs_residual_6m", 4)),
                rationale=f"{tier} + excess_vol <= {ev_max} + top-Q 6m RS",
            )
        )
    # Ulcer-flavored low-vol
    for ulcer_max in [Decimal("0.03"), Decimal("0.05"), Decimal("0.08")]:
        out.append(
            CandidateRule(
                name=f"LVC_{tag}_ulcer_{int(float(ulcer_max) * 100)}",
                archetype="low_vol_carry",
                features=(
                    floor,
                    _pred("ulcer_index_60d", "<=", ulcer_max),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + ulcer <= {ulcer_max} + pos 6m RS",
            )
        )
    return out


def _gen_bab_low_beta(tier: str, tenure: str) -> list[CandidateRule]:
    """Frazzini-Pedersen Betting-Against-Beta: low-beta winners outperform.

    Bottom-tercile beta_60d + positive RS + low excess vol → risk-adjusted
    leaders that mean-revert toward beta=1 net of carry.
    """
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for beta_max in [Decimal("0.50"), Decimal("0.70"), Decimal("0.85"), Decimal("1.00")]:
        out.append(
            CandidateRule(
                name=f"BAB_{tag}_beta_{int(float(beta_max) * 100)}_rs6m_pos",
                archetype="bab_low_beta",
                features=(
                    floor,
                    _pred("beta_60d", "<=", beta_max),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + beta_60d <= {beta_max} + pos 6m RS — BAB candidate",
            )
        )
    for beta_max, ev_max in [
        (Decimal("0.70"), Decimal("0")),
        (Decimal("0.85"), Decimal("-0.002")),
        (Decimal("0.50"), Decimal("0")),
        (Decimal("0.60"), Decimal("-0.003")),
    ]:
        out.append(
            CandidateRule(
                name=f"BAB_{tag}_beta_{int(float(beta_max) * 100)}_exvol_{int(float(ev_max) * 1000)}",  # noqa: E501
                archetype="bab_low_beta",
                features=(
                    floor,
                    _pred("beta_60d", "<=", beta_max),
                    _pred("excess_vol_60d", "<=", ev_max),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + low beta + low excess vol + top-Q 6m RS",
            )
        )
    # BAB + within-tier rank
    for beta_max in [Decimal("0.70"), Decimal("0.85"), Decimal("1.00")]:
        for rk in [Decimal("0.70"), Decimal("0.80"), Decimal("0.90")]:
            out.append(
                CandidateRule(
                    name=f"BAB_{tag}_beta_{int(float(beta_max) * 100)}_wt_{int(float(rk) * 100)}",
                    archetype="bab_low_beta",
                    features=(
                        floor,
                        _pred("beta_60d", "<=", beta_max),
                        _pred("rs_rank_within_tier_6m", ">=", rk),
                    ),
                    rationale=f"{tier} + beta low + within-tier rank >= {rk}",
                )
            )
    return out


def _gen_idio_high_rs(tier: str, tenure: str) -> list[CandidateRule]:
    """High idiosyncratic vol + top-quartile RS = idiosyncratic winners."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for ev_min in [Decimal("0.005"), Decimal("0.010"), Decimal("0.015")]:
        out.append(
            CandidateRule(
                name=f"IDIO_{tag}_exvol_{int(float(ev_min) * 1000)}_rs6m_topq",
                archetype="idio_high_RS",
                features=(
                    floor,
                    _pred("excess_vol_60d", ">=", ev_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + excess_vol >= {ev_min} + top-Q 6m RS — idio winner",
            )
        )
    out.append(
        CandidateRule(
            name=f"IDIO_{tag}_corr_lo_rs_topd",
            archetype="idio_high_RS",
            features=(
                floor,
                _pred("corr_to_nifty_60d", "<=", Decimal("0.40")),
                _topq("rs_residual_6m", 10),
            ),
            rationale=f"{tier} + corr_to_nifty <= 0.40 + top-decile 6m RS",
        )
    )
    # Excess vol with 12m RS variant
    for ev_min in [Decimal("0.005"), Decimal("0.010"), Decimal("0.015")]:
        out.append(
            CandidateRule(
                name=f"IDIO_{tag}_ev_{int(float(ev_min) * 1000)}_rs12m_topq",
                archetype="idio_high_RS",
                features=(
                    floor,
                    _pred("excess_vol_60d", ">=", ev_min),
                    _topq("rs_residual_12m", 4),
                ),
                rationale=f"{tier} + excess_vol >= {ev_min} + top-Q 12m RS",
            )
        )
    # High beta + high RS (counter-BAB momentum)
    for ev_min, q in [(Decimal("0.005"), 4), (Decimal("0.010"), 10)]:
        out.append(
            CandidateRule(
                name=f"IDIO_{tag}_hibeta_{int(float(ev_min) * 1000)}_topq{q}",
                archetype="idio_high_RS",
                features=(
                    floor,
                    _pred("beta_60d", ">=", Decimal("1.10")),
                    _pred("excess_vol_60d", ">=", ev_min),
                    _topq("rs_residual_6m", q),
                ),
                rationale=f"{tier} + beta >= 1.10 + excess_vol >= {ev_min} + top-1/{q} 6m RS",
            )
        )
    for corr_max in [Decimal("0.30"), Decimal("0.50"), Decimal("0.60")]:
        out.append(
            CandidateRule(
                name=f"IDIO_{tag}_corr_{int(float(corr_max) * 100)}_rs6m_pos",
                archetype="idio_high_RS",
                features=(
                    floor,
                    _pred("corr_to_nifty_60d", "<=", corr_max),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + corr_to_nifty <= {corr_max} + pos 6m RS",
            )
        )
    # High idio (excess vol) + within-tier rank
    for ev_min in [Decimal("0.005"), Decimal("0.010")]:
        for rk in [Decimal("0.80"), Decimal("0.90")]:
            out.append(
                CandidateRule(
                    name=f"IDIO_{tag}_ev_{int(float(ev_min) * 1000)}_wt_{int(float(rk) * 100)}",
                    archetype="idio_high_RS",
                    features=(
                        floor,
                        _pred("excess_vol_60d", ">=", ev_min),
                        _pred("rs_rank_within_tier_6m", ">=", rk),
                    ),
                    rationale=f"{tier} + excess_vol >= {ev_min} + within-tier rank >= {rk}",
                )
            )
    return out


def _gen_sector_relative_leadership(tier: str, tenure: str) -> list[CandidateRule]:
    """Top RS within top-3 sectors by sector_strength_rank + high breadth."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    rank_floors: list[Decimal] = [
        Decimal("0.80"),
        Decimal("0.85"),
        Decimal("0.90"),
        Decimal("0.95"),
    ]
    sector_caps: list[Decimal] = [Decimal("3"), Decimal("5"), Decimal("8"), Decimal("10")]
    breadth_mins: list[Decimal] = [Decimal("0.35"), Decimal("0.45"), Decimal("0.55")]
    for rk in rank_floors:
        for sc in sector_caps:
            for br in breadth_mins:
                out.append(
                    CandidateRule(
                        name=f"SRL_{tag}_secrnk{int(float(sc))}_rk{int(float(rk) * 100)}_br{int(float(br) * 100)}",  # noqa: E501
                        archetype="sector_relative_leadership",
                        features=(
                            floor,
                            _pred("sector_rs_rank_6m", ">=", rk),
                            _pred("sector_strength_rank", "<=", sc),
                            _pred("sector_breadth_pos", ">=", br),
                        ),
                        rationale=(
                            f"{tier} + within-sector rank >= {rk} + sector rank <= {sc}"
                            f" + sector breadth >= {br}"
                        ),
                    )
                )
    # 2-predicate sector variants (looser) — captures wider populations.
    for rk in rank_floors:
        for sc in sector_caps:
            out.append(
                CandidateRule(
                    name=f"SRL2_{tag}_rk{int(float(rk) * 100)}_sc{int(float(sc))}",
                    archetype="sector_relative_leadership",
                    features=(
                        floor,
                        _pred("sector_rs_rank_6m", ">=", rk),
                        _pred("sector_strength_rank", "<=", sc),
                    ),
                    rationale=f"{tier} + sector-RS-rank >= {rk} + sector-rank <= {sc}",
                )
            )
    return out


def _gen_liquidity_thrust_mfi(tier: str, tenure: str) -> list[CandidateRule]:
    """MFI > 70 + positive RS = money flowing in."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for mfi_min in [Decimal("60"), Decimal("65"), Decimal("70"), Decimal("75"), Decimal("80")]:
        out.append(
            CandidateRule(
                name=f"MFI_{tag}_thrust_{int(float(mfi_min))}",
                archetype="liquidity_thrust_mfi",
                features=(
                    floor,
                    _pred("mfi_14", ">=", mfi_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"{tier} + MFI >= {mfi_min} + pos 6m RS — money inflow",
            )
        )
    for mfi_min in [Decimal("65"), Decimal("70"), Decimal("75")]:
        out.append(
            CandidateRule(
                name=f"MFI_{tag}_thrust_topq_{int(float(mfi_min))}",
                archetype="liquidity_thrust_mfi",
                features=(
                    floor,
                    _pred("mfi_14", ">=", mfi_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + MFI >= {mfi_min} + top-Q 6m RS",
            )
        )
    # MFI + within-tier rank
    for mfi_min, rk in [
        (Decimal("65"), Decimal("0.80")),
        (Decimal("70"), Decimal("0.85")),
        (Decimal("75"), Decimal("0.90")),
    ]:
        out.append(
            CandidateRule(
                name=f"MFI_{tag}_wt_{int(float(mfi_min))}_{int(float(rk) * 100)}",
                archetype="liquidity_thrust_mfi",
                features=(
                    floor,
                    _pred("mfi_14", ">=", mfi_min),
                    _pred("rs_rank_within_tier_6m", ">=", rk),
                ),
                rationale=f"{tier} + MFI >= {mfi_min} + within-tier rank >= {rk}",
            )
        )
    return out


def _gen_obv_thrust(tier: str, tenure: str) -> list[CandidateRule]:
    """OBV slope in top quartile + positive RS — accumulation visible."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    out.append(
        CandidateRule(
            name=f"OBV_{tag}_topq_rs6m_pos",
            archetype="obv_thrust",
            features=(floor, _topq("obv_slope_60d", 4), _pred("rs_residual_6m", ">", Decimal("0"))),
            rationale=f"{tier} + OBV slope top-Q + pos 6m RS — accumulation",
        )
    )
    out.append(
        CandidateRule(
            name=f"OBV_{tag}_topd_rs6m_topq",
            archetype="obv_thrust",
            features=(floor, _topq("obv_slope_60d", 10), _topq("rs_residual_6m", 4)),
            rationale=f"{tier} + OBV slope top-decile + top-Q 6m RS",
        )
    )
    # Combine OBV with MFI for a stronger flow read.
    for mfi_min in [Decimal("60"), Decimal("65"), Decimal("70")]:
        out.append(
            CandidateRule(
                name=f"OBV_{tag}_topq_mfi{int(float(mfi_min))}",
                archetype="obv_thrust",
                features=(floor, _topq("obv_slope_60d", 4), _pred("mfi_14", ">=", mfi_min)),
                rationale=f"{tier} + OBV top-Q + MFI >= {mfi_min}",
            )
        )
    # OBV + close at 60d high
    out.append(
        CandidateRule(
            name=f"OBV_{tag}_topd_60dhi",
            archetype="obv_thrust",
            features=(
                floor,
                _topq("obv_slope_60d", 10),
                _pred("close_over_60d_high", ">=", Decimal("1")),
            ),
            rationale=f"{tier} + OBV top-decile + at 60d high",
        )
    )
    # OBV variants by RS tenure
    for tenure_feat in ["rs_residual_3m", "rs_residual_12m"]:
        for q in (4, 10):
            out.append(
                CandidateRule(
                    name=f"OBV_{tag}_{tenure_feat[-3:]}_topq{q}",
                    archetype="obv_thrust",
                    features=(floor, _topq("obv_slope_60d", 4), _topq(tenure_feat, q)),
                    rationale=f"{tier} + OBV top-Q + top-1/{q} {tenure_feat}",
                )
            )
    return out


def _gen_breakout_with_pullback(tier: str, tenure: str) -> list[CandidateRule]:
    """At-52w-high recently + small pullback off the peak."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for low, high in [
        (Decimal("-0.05"), Decimal("-0.01")),
        (Decimal("-0.07"), Decimal("-0.02")),
        (Decimal("-0.04"), Decimal("0.00")),
    ]:
        out.append(
            CandidateRule(
                name=f"BP_{tag}_pull_{int(float(low) * 100)}_{int(float(high) * 100)}",
                archetype="breakout_with_pullback",
                features=(
                    floor,
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                    _pred("new_high_streak_60d", ">=", Decimal("5")),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + small pullback [{low},{high}] off 52w high + top-Q 6m RS",
            )
        )
    for streak_min in [Decimal("3"), Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")]:
        out.append(
            CandidateRule(
                name=f"BP_{tag}_newhi_streak_{int(float(streak_min))}",
                archetype="breakout_with_pullback",
                features=(
                    floor,
                    _pred("new_high_streak_60d", ">=", streak_min),
                    _topq("rs_residual_6m", 4),
                ),
                rationale=f"{tier} + new_high_streak_60d >= {streak_min} + top-Q 6m RS",
            )
        )
    # Pullback + above-sma50 streak (still trending)
    for low, high in [
        (Decimal("-0.08"), Decimal("-0.02")),
        (Decimal("-0.05"), Decimal("0.00")),
    ]:
        for streak_min in [Decimal("20"), Decimal("40")]:
            out.append(
                CandidateRule(
                    name=f"BP_{tag}_pull_{int(float(low) * 100)}_sma50_{int(float(streak_min))}",
                    archetype="breakout_with_pullback",
                    features=(
                        floor,
                        _pred("dd_from_52w_high", "in_range", (low, high)),
                        _pred("consecutive_above_sma50", ">=", streak_min),
                    ),
                    rationale=f"{tier} + pullback [{low},{high}] + above SMA50 streak >= {streak_min}",  # noqa: E501
                )
            )
    return out


# ---------------------------------------------------------------------------
# NEGATIVE archetypes (predicate fires on stocks that subsequently underperform)
# ---------------------------------------------------------------------------


def _gen_mean_reversion_overbought(tier: str, tenure: str) -> list[CandidateRule]:
    """High-RSI + extended above SMA200 + extreme RS top-decile."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for rsi_min in [Decimal("70"), Decimal("75"), Decimal("80")]:
        for dist_min in [Decimal("0.15"), Decimal("0.25"), Decimal("0.40")]:
            out.append(
                CandidateRule(
                    name=f"MRO_{tag}_rsi{int(float(rsi_min))}_sma200_{int(float(dist_min) * 100)}",
                    archetype="mean_reversion_overbought",
                    features=(
                        floor,
                        _pred("rsi_14", ">=", rsi_min),
                        _pred("dist_above_sma200", ">=", dist_min),
                    ),
                    rationale=f"{tier} + RSI >= {rsi_min} + dist_sma200 >= {dist_min} — overbought",
                )
            )
    # Extreme RS + low vol regime (mean revert)
    for vrg_max in [Decimal("0.80"), Decimal("0.90"), Decimal("1.00")]:
        out.append(
            CandidateRule(
                name=f"MRO_{tag}_rs6m_topd_lowregime_{int(float(vrg_max) * 100)}",
                archetype="mean_reversion_overbought",
                features=(
                    floor,
                    _topq("rs_residual_6m", 10),
                    _pred("vol_regime_60_252", "<=", vrg_max),
                    _pred("rsi_14", ">=", Decimal("65")),
                ),
                rationale=f"{tier} + top-decile 6m RS + suppressed vol regime <= {vrg_max} + RSI > 65",  # noqa: E501
            )
        )
    # Bollinger overshoot
    for bb_min in [Decimal("1.5"), Decimal("2.0"), Decimal("2.5")]:
        out.append(
            CandidateRule(
                name=f"MRO_{tag}_bb_{int(float(bb_min) * 10)}",
                archetype="mean_reversion_overbought",
                features=(
                    floor,
                    _pred("bb_pct_20d", ">=", bb_min),
                    _pred("rs_residual_6m", ">", Decimal("0.05")),
                ),
                rationale=f"{tier} + Bollinger pos >= {bb_min} stds + pos 6m RS",
            )
        )
    # Within-tier rank top-quintile + extended
    for dist_min in [Decimal("0.20"), Decimal("0.30"), Decimal("0.45")]:
        out.append(
            CandidateRule(
                name=f"MRO_{tag}_wt_topq_sma200_{int(float(dist_min) * 100)}",
                archetype="mean_reversion_overbought",
                features=(
                    floor,
                    _pred("rs_rank_within_tier_6m", ">=", Decimal("0.90")),
                    _pred("dist_above_sma200", ">=", dist_min),
                ),
                rationale=f"{tier} + within-tier top-decile + dist_sma200 >= {dist_min}",
            )
        )
    return out


def _gen_distribution(tier: str, tenure: str) -> list[CandidateRule]:
    """Volume rising + RS deteriorating + near peak — distribution."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for vz_min in [Decimal("1.0"), Decimal("1.5"), Decimal("2.0")]:
        for diff_max in [Decimal("-0.05"), Decimal("-0.10"), Decimal("-0.15")]:
            out.append(
                CandidateRule(
                    name=f"DIST_{tag}_vz{int(float(vz_min) * 10)}_rsdrop_{int(float(diff_max) * 100)}",  # noqa: E501
                    archetype="distribution",
                    features=(
                        floor,
                        _pred("volume_zscore_60d", ">=", vz_min),
                        _pred("rs_rank_6m_3m_diff", "<=", diff_max),
                        _pred("dd_from_52w_high", ">=", Decimal("-0.05")),
                    ),
                    rationale=f"{tier} + vol_z >= {vz_min} + rank shift <= {diff_max} + near 52w high",  # noqa: E501
                )
            )
    # Volume up + RSI rolling over
    for rsi_lo, rsi_hi in [
        (Decimal("55"), Decimal("70")),
        (Decimal("50"), Decimal("65")),
        (Decimal("60"), Decimal("75")),
    ]:
        out.append(
            CandidateRule(
                name=f"DIST_{tag}_vz_rsiroll_{int(float(rsi_lo))}",
                archetype="distribution",
                features=(
                    floor,
                    _pred("volume_zscore_60d", ">=", Decimal("1.0")),
                    _pred("rsi_14", "in_range", (rsi_lo, rsi_hi)),
                    _pred("dd_from_52w_high", ">=", Decimal("-0.08")),
                ),
                rationale=f"{tier} + vol_z up + RSI in [{rsi_lo},{rsi_hi}] off peak",
            )
        )
    # OBV/MFI divergence at peak — red-team companion
    for obv_max in [Decimal("0"), Decimal("-1000000")]:
        out.append(
            CandidateRule(
                name=f"DIST_{tag}_obvneg_topq_rs",
                archetype="distribution",
                features=(
                    floor,
                    _pred("obv_slope_60d", "<=", obv_max),
                    _topq("rs_residual_6m", 10),
                    _pred("dd_from_52w_high", ">=", Decimal("-0.05")),
                ),
                rationale=f"{tier} + OBV slope <= {obv_max} + top-decile RS near 52w high",
            )
        )
    return out


def _gen_volatility_spike(tier: str, tenure: str) -> list[CandidateRule]:
    """Vol regime expanding + RS deteriorating + breakdown from SMA50."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for vrg_min in [Decimal("1.3"), Decimal("1.5"), Decimal("1.8"), Decimal("2.0")]:
        out.append(
            CandidateRule(
                name=f"VS_{tag}_volregime_{int(float(vrg_min) * 100)}",
                archetype="volatility_spike",
                features=(
                    floor,
                    _pred("vol_regime_60_252", ">=", vrg_min),
                    _pred("rs_residual_3m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + vol regime expansion >= {vrg_min} + neg 3m RS",
            )
        )
    # Vol spike + breakdown from SMA50
    for dist_max in [Decimal("-0.02"), Decimal("-0.05"), Decimal("-0.10")]:
        out.append(
            CandidateRule(
                name=f"VS_{tag}_brkdwn50_{int(float(dist_max) * 100)}",
                archetype="volatility_spike",
                features=(
                    floor,
                    _pred("vol_regime_60_252", ">=", Decimal("1.3")),
                    _pred("dist_above_sma50", "<=", dist_max),
                ),
                rationale=f"{tier} + vol regime > 1.3 + below SMA50 by {dist_max}",
            )
        )
    # Downside vol spike
    for dv_min in [Decimal("0.018"), Decimal("0.025"), Decimal("0.035")]:
        out.append(
            CandidateRule(
                name=f"VS_{tag}_dvol_{int(float(dv_min) * 1000)}",
                archetype="volatility_spike",
                features=(
                    floor,
                    _pred("downside_vol_60d", ">=", dv_min),
                    _pred("rs_residual_3m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + downside_vol >= {dv_min} + neg 3m RS",
            )
        )
    # Vol regime + already breaking down
    for vrg_min, dd_max in [
        (Decimal("1.3"), Decimal("-0.05")),
        (Decimal("1.5"), Decimal("-0.10")),
        (Decimal("1.8"), Decimal("-0.15")),
    ]:
        out.append(
            CandidateRule(
                name=f"VS_{tag}_vrg{int(float(vrg_min) * 100)}_dd{int(float(dd_max) * 100)}",
                archetype="volatility_spike",
                features=(
                    floor,
                    _pred("vol_regime_60_252", ">=", vrg_min),
                    _pred("dd_from_52w_high", "<=", dd_max),
                ),
                rationale=f"{tier} + vol regime >= {vrg_min} + dd <= {dd_max}",
            )
        )
    return out


def _gen_breakdown(tier: str, tenure: str) -> list[CandidateRule]:
    """Below SMA200, deepening dd, accelerating losses."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for dist_max in [Decimal("-0.05"), Decimal("-0.10"), Decimal("-0.20"), Decimal("-0.30")]:
        out.append(
            CandidateRule(
                name=f"BD_{tag}_sma200_{int(float(dist_max) * 100)}",
                archetype="breakdown",
                features=(
                    floor,
                    _pred("dist_above_sma200", "<=", dist_max),
                    _pred("rs_residual_12m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + below SMA200 by {dist_max} + neg 12m RS",
            )
        )
    for accel_max in [Decimal("-0.20"), Decimal("-0.30"), Decimal("-0.40"), Decimal("-0.50")]:
        out.append(
            CandidateRule(
                name=f"BD_{tag}_accel_{int(float(accel_max) * 100)}",
                archetype="breakdown",
                features=(
                    floor,
                    _pred("rs_acceleration_63d", "<=", accel_max),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + RS accel <= {accel_max} + neg 6m RS",
            )
        )
    # roc breakdowns
    for roc_max in [Decimal("-0.05"), Decimal("-0.10"), Decimal("-0.15"), Decimal("-0.25")]:
        out.append(
            CandidateRule(
                name=f"BD_{tag}_roc63_{int(float(roc_max) * 100)}",
                archetype="breakdown",
                features=(
                    floor,
                    _pred("roc_63d", "<=", roc_max),
                    _pred("rs_residual_12m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + roc_63d <= {roc_max} + neg 12m RS",
            )
        )
    # Close at 252d-low band
    for dist_lo, dist_hi in [
        (Decimal("0.00"), Decimal("0.05")),
        (Decimal("0.00"), Decimal("0.10")),
    ]:
        out.append(
            CandidateRule(
                name=f"BD_{tag}_nearlow_{int(float(dist_hi) * 100)}",
                archetype="breakdown",
                features=(
                    floor,
                    _pred("dist_from_52w_low", "in_range", (dist_lo, dist_hi)),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + near 52w low + neg 6m RS",
            )
        )
    # Ulcer high + RS negative
    for ulcer_min in [Decimal("0.08"), Decimal("0.12"), Decimal("0.18")]:
        out.append(
            CandidateRule(
                name=f"BD_{tag}_ulcer_{int(float(ulcer_min) * 100)}",
                archetype="breakdown",
                features=(
                    floor,
                    _pred("ulcer_index_60d", ">=", ulcer_min),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + ulcer >= {ulcer_min} + neg 6m RS",
            )
        )
    return out


def _gen_deep_value_avoid(tier: str, tenure: str) -> list[CandidateRule]:
    """Bottom RS + deepening dd + no recovery yet."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for dd_max in [Decimal("-0.30"), Decimal("-0.40"), Decimal("-0.50")]:
        for rec_max in [Decimal("0.15"), Decimal("0.25"), Decimal("0.35")]:
            out.append(
                CandidateRule(
                    name=f"DVA_{tag}_dd{int(float(dd_max) * 100)}_rec_{int(float(rec_max) * 100)}",
                    archetype="deep_value_avoid",
                    features=(
                        floor,
                        _pred("dd_from_52w_high", "<=", dd_max),
                        _pred("dd_recovery_pct", "<=", rec_max),
                    ),
                    rationale=f"{tier} + dd <= {dd_max} + recovery <= {rec_max}",
                )
            )
    # Deep dd + still-falling RS
    for dd_max in [Decimal("-0.40"), Decimal("-0.50"), Decimal("-0.60")]:
        out.append(
            CandidateRule(
                name=f"DVA_{tag}_dd{int(float(dd_max) * 100)}_negrs",
                archetype="deep_value_avoid",
                features=(
                    floor,
                    _pred("dd_from_52w_high", "<=", dd_max),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                    _pred("rs_acceleration_63d", "<", Decimal("0")),
                ),
                rationale=f"{tier} + dd <= {dd_max} + neg + decelerating RS",
            )
        )
    return out


def _gen_weak_quality(tier: str, tenure: str) -> list[CandidateRule]:
    """Bottom-RS + high downside vol + worsening trend strength."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for dv_min in [Decimal("0.018"), Decimal("0.025"), Decimal("0.035")]:
        out.append(
            CandidateRule(
                name=f"WQ_{tag}_dvol_{int(float(dv_min) * 1000)}",
                archetype="weak_quality",
                features=(
                    floor,
                    _pred("downside_vol_60d", ">=", dv_min),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + downside_vol >= {dv_min} + neg 6m RS",
            )
        )
    for mq_max in [Decimal("-1"), Decimal("-3"), Decimal("-5"), Decimal("-8")]:
        out.append(
            CandidateRule(
                name=f"WQ_{tag}_mq6m_{int(float(mq_max))}",
                archetype="weak_quality",
                features=(
                    floor,
                    _pred("momentum_quality_6m", "<=", mq_max),
                ),
                rationale=f"{tier} + momentum_quality_6m <= {mq_max}",
            )
        )
    # Trend strength low + neg RS
    for ts_max in [Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]:
        out.append(
            CandidateRule(
                name=f"WQ_{tag}_trendlo_{int(float(ts_max) * 100)}",
                archetype="weak_quality",
                features=(
                    floor,
                    _pred("trend_strength_60d", "<=", ts_max),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + trend r^2 <= {ts_max} + neg 6m RS",
            )
        )
    # Bottom within-tier rank (red-team gap 5)
    for rk_max in [Decimal("0.20"), Decimal("0.10")]:
        out.append(
            CandidateRule(
                name=f"WQ_{tag}_wt_bot_{int(float(rk_max) * 100)}",
                archetype="weak_quality",
                features=(floor, _pred("rs_rank_within_tier_6m", "<=", rk_max)),
                rationale=f"{tier} + within-tier RS rank <= {rk_max} — bottom slice",
            )
        )
    # Ulcer high + neg RS
    for ulcer_min in [Decimal("0.10"), Decimal("0.15")]:
        out.append(
            CandidateRule(
                name=f"WQ_{tag}_ulcer_{int(float(ulcer_min) * 100)}",
                archetype="weak_quality",
                features=(
                    floor,
                    _pred("ulcer_index_60d", ">=", ulcer_min),
                    _pred("rs_residual_3m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + ulcer >= {ulcer_min} + neg 3m RS",
            )
        )
    return out


def _gen_overextension(tier: str, tenure: str) -> list[CandidateRule]:
    """Bollinger >2 std + low pos_months + high vol regime."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for bb_min in [Decimal("1.5"), Decimal("2.0"), Decimal("2.5")]:
        for pos_max in [Decimal("0.42"), Decimal("0.50")]:
            out.append(
                CandidateRule(
                    name=f"OE_{tag}_bb_{int(float(bb_min) * 10)}_pos_{int(float(pos_max) * 100)}",
                    archetype="overextension",
                    features=(
                        floor,
                        _pred("bb_pct_20d", ">=", bb_min),
                        _pred("pos_months_12m", "<=", pos_max),
                    ),
                    rationale=f"{tier} + bb >= {bb_min}std + pos_months <= {pos_max}",
                )
            )
    for vrg_min in [Decimal("1.3"), Decimal("1.5"), Decimal("1.8")]:
        out.append(
            CandidateRule(
                name=f"OE_{tag}_vrg_{int(float(vrg_min) * 100)}",
                archetype="overextension",
                features=(
                    floor,
                    _pred("vol_regime_60_252", ">=", vrg_min),
                    _pred("bb_pct_20d", ">=", Decimal("1.5")),
                ),
                rationale=f"{tier} + vol regime >= {vrg_min} + bb >= 1.5std",
            )
        )
    # roc_126d very high → mean revert
    for roc_min in [Decimal("0.40"), Decimal("0.60"), Decimal("1.00")]:
        out.append(
            CandidateRule(
                name=f"OE_{tag}_roc126_{int(float(roc_min) * 100)}",
                archetype="overextension",
                features=(
                    floor,
                    _pred("roc_126d", ">=", roc_min),
                    _pred("rsi_14", ">=", Decimal("65")),
                ),
                rationale=f"{tier} + roc_126d >= {roc_min} + RSI >= 65",
            )
        )
    # New high streak too long + RSI elevated
    for streak_min in [Decimal("15"), Decimal("25"), Decimal("35")]:
        out.append(
            CandidateRule(
                name=f"OE_{tag}_newhi_{int(float(streak_min))}",
                archetype="overextension",
                features=(
                    floor,
                    _pred("new_high_streak_60d", ">=", streak_min),
                    _pred("rsi_14", ">=", Decimal("70")),
                ),
                rationale=f"{tier} + new_high_streak >= {streak_min} + RSI >= 70",
            )
        )
    return out


def _gen_bab_high_beta_short(tier: str, tenure: str) -> list[CandidateRule]:
    """BAB short side: top-tercile beta + bottom RS = high-beta losers."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for beta_min in [Decimal("1.20"), Decimal("1.40"), Decimal("1.60")]:
        out.append(
            CandidateRule(
                name=f"BABS_{tag}_beta_{int(float(beta_min) * 100)}_neg_rs6m",
                archetype="bab_high_beta_short",
                features=(
                    floor,
                    _pred("beta_60d", ">=", beta_min),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                ),
                rationale=f"{tier} + beta >= {beta_min} + neg 6m RS — high-beta loser",
            )
        )
    out.append(
        CandidateRule(
            name=f"BABS_{tag}_beta_high_exvol_high",
            archetype="bab_high_beta_short",
            features=(
                floor,
                _pred("beta_60d", ">=", Decimal("1.40")),
                _pred("excess_vol_60d", ">=", Decimal("0.005")),
                _pred("rs_residual_3m", "<", Decimal("0")),
            ),
            rationale=f"{tier} + beta high + excess_vol high + neg 3m RS",
        )
    )
    return out


def _gen_mfi_overbought_distrib(tier: str, tenure: str) -> list[CandidateRule]:
    """MFI > 80 + RS deteriorating = distribution at top."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    for mfi_min in [Decimal("75"), Decimal("80"), Decimal("85")]:
        for diff_max in [Decimal("-0.05"), Decimal("-0.10")]:
            out.append(
                CandidateRule(
                    name=f"MOD_{tag}_mfi{int(float(mfi_min))}_shift_{int(float(diff_max) * 100)}",
                    archetype="mfi_overbought_distrib",
                    features=(
                        floor,
                        _pred("mfi_14", ">=", mfi_min),
                        _pred("rs_rank_6m_3m_diff", "<=", diff_max),
                    ),
                    rationale=f"{tier} + MFI >= {mfi_min} + rank-shift <= {diff_max}",
                )
            )
    return out


def _gen_obv_divergence_neg(tier: str, tenure: str) -> list[CandidateRule]:
    """Positive RS but OBV slope in bottom quartile = stealth distribution."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    out.append(
        CandidateRule(
            name=f"OBVD_{tag}_pos_rs_bot_obv",
            archetype="obv_divergence_neg",
            features=(
                floor,
                _pred("rs_residual_6m", ">", Decimal("0")),
                _pred("obv_slope_60d", "<=", Decimal("0")),
            ),
            rationale=f"{tier} + pos 6m RS + OBV slope <= 0 — bearish divergence",
        )
    )
    # Top-decile RS with bottom-decile OBV → stronger divergence
    out.append(
        CandidateRule(
            name=f"OBVD_{tag}_topd_rs_obv_neg",
            archetype="obv_divergence_neg",
            features=(
                floor,
                _topq("rs_residual_6m", 10),
                _pred("obv_slope_60d", "<", Decimal("0")),
            ),
            rationale=f"{tier} + top-decile RS + OBV slope negative — divergence",
        )
    )
    # MFI rolling lower while RS up
    out.append(
        CandidateRule(
            name=f"OBVD_{tag}_pos_rs_mfi_lo",
            archetype="obv_divergence_neg",
            features=(
                floor,
                _pred("rs_residual_3m", ">", Decimal("0")),
                _pred("mfi_14", "<=", Decimal("40")),
            ),
            rationale=f"{tier} + pos 3m RS + MFI <= 40 — money flow weakening",
        )
    )
    return out


def _gen_sector_breakdown(tier: str, tenure: str) -> list[CandidateRule]:
    """Bottom-3 sectors by strength rank + low sector breadth."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    rank_floors: list[Decimal] = [Decimal("15"), Decimal("18"), Decimal("22"), Decimal("25")]
    breadth_max: list[Decimal] = [
        Decimal("0.30"),
        Decimal("0.25"),
        Decimal("0.20"),
        Decimal("0.15"),
    ]
    rs_floors: list[Decimal] = [Decimal("0.80"), Decimal("0.85"), Decimal("0.90")]
    for rk in rank_floors:
        for br in breadth_max:
            for rs in rs_floors:
                out.append(
                    CandidateRule(
                        name=f"SBD_{tag}_secrnk{int(float(rk))}_br{int(float(br) * 100)}_rs{int(float(rs) * 100)}",  # noqa: E501
                        archetype="sector_breakdown",
                        features=(
                            floor,
                            _pred("sector_rs_rank_6m", ">=", rs),
                            _pred("sector_strength_rank", ">=", rk),
                            _pred("sector_breadth_pos", "<=", br),
                        ),
                        rationale=f"{tier} + in-sector RS >= {rs} + sector rank >= {rk} + breadth <= {br}",  # noqa: E501
                    )
                )
    return out


def _gen_sector_drag(tier: str, tenure: str) -> list[CandidateRule]:
    """Any high in-tier RS but in collapsing sector + market-wide drag."""
    out: list[CandidateRule] = []
    tag = _tag(tier, tenure)
    floor = _liquidity_floor(tier)
    rank_floors: list[Decimal] = [Decimal("18"), Decimal("22"), Decimal("25"), Decimal("28")]
    cross_caps: list[Decimal] = [Decimal("0.35"), Decimal("0.30"), Decimal("0.25"), Decimal("0.20")]
    for rk in rank_floors:
        for cs in cross_caps:
            out.append(
                CandidateRule(
                    name=f"SDR_{tag}_secrnk{int(float(rk))}_cross{int(float(cs) * 100)}",
                    archetype="sector_drag",
                    features=(
                        floor,
                        _pred("sector_strength_rank", ">=", rk),
                        _pred("cross_sector_breadth", "<=", cs),
                    ),
                    rationale=f"{tier} + sector rank >= {rk} + cross-sector breadth <= {cs}",
                )
            )
    # Sector vol regime expansion overlay
    for rk in rank_floors:
        for vol_min in [Decimal("0.020"), Decimal("0.025"), Decimal("0.030")]:
            out.append(
                CandidateRule(
                    name=f"SDR_{tag}_secrnk{int(float(rk))}_secvol{int(float(vol_min) * 1000)}",
                    archetype="sector_drag",
                    features=(
                        floor,
                        _pred("sector_strength_rank", ">=", rk),
                        _pred("sector_vol_regime", ">=", vol_min),
                    ),
                    rationale=f"{tier} + sector rank >= {rk} + sector vol regime >= {vol_min}",
                )
            )
    return out


# ---------------------------------------------------------------------------
# Master entry point
# ---------------------------------------------------------------------------


def generate_candidates(
    tier: Tier,
    tenure: Tenure,
    direction: Direction,
) -> list[CandidateRule]:
    """Generate the full per-cell candidate list.

    Args:
        tier: Large / Mid / Small.
        tenure: 1m / 3m / 6m / 12m.
        direction: POSITIVE or NEGATIVE.

    Returns:
        ~250-400 CandidateRule for POSITIVE; ~150-250 for NEGATIVE.
        Order-stable across re-runs.
    """
    if tier not in ("Large", "Mid", "Small"):
        raise ValueError(f"unknown tier {tier!r}")
    if tenure not in ("1m", "3m", "6m", "12m"):
        raise ValueError(f"unknown tenure {tenure!r}")
    if direction not in ("POSITIVE", "NEGATIVE"):
        raise ValueError(f"unknown direction {direction!r}")

    out: list[CandidateRule] = []
    if direction == "POSITIVE":
        out.extend(_gen_mean_reversion(tier, tenure))
        out.extend(_gen_deep_value(tier, tenure))
        out.extend(_gen_quality_momentum(tier, tenure))
        out.extend(_gen_inflection(tier, tenure))
        out.extend(_gen_consolidation_breakout(tier, tenure))
        out.extend(_gen_liquidity_expansion(tier, tenure))
        out.extend(_gen_structural(tier, tenure))
        out.extend(_gen_low_vol_carry(tier, tenure))
        out.extend(_gen_breakout_with_pullback(tier, tenure))
        out.extend(_gen_bab_low_beta(tier, tenure))
        out.extend(_gen_idio_high_rs(tier, tenure))
        out.extend(_gen_sector_relative_leadership(tier, tenure))
        out.extend(_gen_liquidity_thrust_mfi(tier, tenure))
        out.extend(_gen_obv_thrust(tier, tenure))
    else:
        out.extend(_gen_mean_reversion_overbought(tier, tenure))
        out.extend(_gen_distribution(tier, tenure))
        out.extend(_gen_volatility_spike(tier, tenure))
        out.extend(_gen_breakdown(tier, tenure))
        out.extend(_gen_deep_value_avoid(tier, tenure))
        out.extend(_gen_weak_quality(tier, tenure))
        out.extend(_gen_overextension(tier, tenure))
        out.extend(_gen_bab_high_beta_short(tier, tenure))
        out.extend(_gen_mfi_overbought_distrib(tier, tenure))
        out.extend(_gen_obv_divergence_neg(tier, tenure))
        out.extend(_gen_sector_breakdown(tier, tenure))
        out.extend(_gen_sector_drag(tier, tenure))

    # De-dupe by name (defensive — should never collide).
    seen: set[str] = set()
    deduped: list[CandidateRule] = []
    for c in out:
        if c.name in seen:
            continue
        seen.add(c.name)
        deduped.append(c)
    return deduped
