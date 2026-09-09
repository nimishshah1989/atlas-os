"""ETF lens scorers — pure. Dict in, Decimal out; no database, no clock, no I/O.

The five ETF lenses of ``docs/global/plan.md`` §C. This module implements the three that
today's nightly data can answer honestly, and states plainly why the other two cannot:

    technical       ✅ every sub-score, from technical_daily
    risk            ✅ every sub-score, from technical_daily (weight 0 — an OVERLAY, see below)
    cost_liquidity  ◐  the ADV$ sub-score only; expense, AUM and concentration need etf_meta
                       and etf_holdings, which have no producer yet (phase2.md P3-C)
    flow            ✗  needs etf_shares_daily (P3-C)
    quality         ✗  needs etf_holdings look-through onto scored stocks (P3-C)

A lens with no inputs returns ``None`` and ``blend()`` renormalises over the lenses that are
present. It does NOT return zero: zero is a score, and a fund is not bad because we have not
ingested its expense ratio yet.

WHY INDIA'S SCORERS ARE IMPORTED, NOT COPIED. ``_score_trend`` and ``_score_relative_strength``
are pure functions over EMAs and a weekly return — no market, currency or venue in them — and
they are the exact definitions §C's trend and structure sub-scores name. The modulith edge
``atlas.global_market → atlas.lenses.compute`` exists for precisely this (ADR-0006 Decision 2,
``scripts/hooks/check_module_boundaries.py``). Copying them would give two definitions of a
trend that must drift apart, and the FM would eventually be shown two different answers to the
same question.

RISK IS COMPUTED AND NOT BLENDED. ``etf_lens_weight_risk`` is seeded at 0, so risk renders
beside the score rather than inside it. That is deliberate: fold volatility into a composite
and a dull fund outranks a strong one, which is not what "which fund do I buy" asks. The FM
sets a weight from /admin the day he wants it counted; no code changes when he does.

EVERY NUMBER COMES FROM ``atlas_global.atlas_thresholds`` (rule #4). These functions take a
``th`` mapping and index it with ``[]``, never ``.get(key, default)`` — a missing key raises
KeyError by name, exactly as ``scoring/blend.py`` does. A default here would be a methodology
number hiding in code, and the first anyone knew of it would be a score nobody can explain.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from atlas.lenses.compute.technical import _score_relative_strength, _score_trend

# Every threshold key India's `_score_trend` and `_score_relative_strength` read. Indexed,
# never defaulted — see the module docstring. Kept in sync with India's source by
# test_stock_lenses.test_technical_keys_covers_every_threshold_india_reads.
TECHNICAL_KEYS: tuple[str, ...] = (
    "ema_aligned_all",
    "ema_aligned_partial",
    "price_above_ema200_strong",
    "price_below_ema200_weak",
    "slope_strong_pct",
    "slope_weak_pct",
    "rs_golden_cross_pts",
    "rs_fast_above_mid_pts",
)


def india_thresholds(
    th: Mapping[str, Decimal], keys: Sequence[str] = TECHNICAL_KEYS
) -> dict[str, Any]:
    """The keys one of India's scorers reads, as the floats it does arithmetic in.

    Converting AT THIS BOUNDARY and nowhere else keeps the reuse honest — the values are
    still the global table's rows, and no money or stored score is touched: these are
    dimensionless band edges and point counts. ``etf_lenses.score_technical`` does the same
    at the same boundary, for the same two functions.

    INDEXED, never ``.get(key, default)``. India's scorers fall back to India's own numbers
    when a key is absent, so a missing row here would score this market on a methodology it
    never approved — invisibly, inside a number nobody could explain. Indexing raises
    ``KeyError`` by name at the first scored row instead. ``keys`` defaults to the technical
    lens's; ``stock_lenses.FUNDAMENTAL_KEYS`` passes its own.
    """
    return {key: float(th[key]) for key in keys}


# Each sub-score is 0–25 and a lens is the mean of the PRESENT sub-scores × 4, so a lens is
# 0–100 whether it had four inputs or two. Same shape as India's technical lens.
SUB_MAX = Decimal("25")
LENS_SCALE = Decimal("4")
_Q2 = Decimal("0.01")


@dataclass(frozen=True)
class LensResult:
    """One lens: its 0–100 score (None when nothing could be computed), the sub-scores that
    produced it, and the evidence trail the board's derivation tree renders."""

    value: Decimal | None
    subs: dict[str, Decimal | None]
    evidence: dict[str, Any]


def _cap(value: Decimal, high: Decimal) -> Decimal:
    return max(Decimal("0"), min(high, value))


def _lens(subs: dict[str, Decimal | None], evidence: dict[str, Any]) -> LensResult:
    """Mean of the present sub-scores × 4. All absent → None, never 0."""
    present = [v for v in subs.values() if v is not None]
    if not present:
        return LensResult(None, subs, {**evidence, "reason": "no sub-score had inputs"})
    mean = sum(present, Decimal("0")) / Decimal(len(present))
    score = _cap(mean * LENS_SCALE, Decimal("100")).quantize(_Q2)
    return LensResult(score, subs, {**evidence, "subs_present": len(present)})


def quintile_points(pct_rank: float | None, th: Mapping[str, Decimal]) -> Decimal | None:
    """The shared 5-step ladder every percentile sub-score uses.

    ``pct_rank`` is the fund's position in its comparison group, 0 = worst, 1 = best, already
    oriented by the caller (for volatility the caller inverts it, because low volatility is
    the good end). None → None: a fund whose group was too small to rank has no percentile,
    and putting it in the middle would be inventing one.
    """
    if pct_rank is None:
        return None
    for cut, key in (
        (0.8, "etf_quintile_q1_pts"),
        (0.6, "etf_quintile_q2_pts"),
        (0.4, "etf_quintile_q3_pts"),
        (0.2, "etf_quintile_q4_pts"),
    ):
        if pct_rank >= cut:
            return Decimal(th[key])
    return Decimal(th["etf_quintile_q5_pts"])


def score_rs_spy(
    rs_3m: float | None,
    rs_6m: float | None,
    rs_12m: float | None,
    th: Mapping[str, Decimal],
) -> tuple[Decimal | None, dict[str, Any]]:
    """Relative strength against SPY over three windows (0–25).

    ``rs_*`` are already in the relative form ``(1+r_fund)/(1+r_spy) − 1`` (ADR-0002), so
    +0.08 means "beat the S&P by eight percent", not "rose eight percent". Clearing
    ``rs_spy_strong`` earns the window's full points; merely positive earns the seeded
    fraction of them; behind the index earns nothing. A missing window is skipped and its
    points leave the total — a fund listed four months ago is scored on what it has.
    """
    strong = Decimal(th["rs_spy_strong"])
    partial = Decimal(th["etf_rs_spy_partial_frac"])
    windows = (
        ("3m", rs_3m, Decimal(th["etf_rs_spy_3m_pts"])),
        ("6m", rs_6m, Decimal(th["etf_rs_spy_6m_pts"])),
        ("12m", rs_12m, Decimal(th["etf_rs_spy_12m_pts"])),
    )
    points, evidence, present = Decimal("0"), {}, 0
    for label, value, full in windows:
        if value is None:
            evidence[f"rs_{label}"] = "no data"
            continue
        present += 1
        rs = Decimal(str(value))
        if rs > strong:
            points += full
            evidence[f"rs_{label}"] = "strong"
        elif rs > 0:
            points += full * partial
            evidence[f"rs_{label}"] = "ahead"
        else:
            evidence[f"rs_{label}"] = "behind"
    if present == 0:
        return None, evidence
    return _cap(points, SUB_MAX).quantize(_Q2), evidence


def score_peer_rs(
    pct_rank_6m: float | None, th: Mapping[str, Decimal]
) -> tuple[Decimal | None, dict[str, Any]]:
    """Where this fund's 6-month return sits inside its own peer group (0–25).

    This is the sub-score that makes the ranking mean something: a gold miners fund is not
    measured against the S&P, it is measured against other gold miners funds. The caller
    computes the percentile because it needs the whole group; this only reads the ladder.
    """
    points = quintile_points(pct_rank_6m, th)
    if points is None:
        return None, {"peer_rs": "group too small to rank"}
    return _cap(points, SUB_MAX).quantize(_Q2), {"peer_rs_pct": round(pct_rank_6m or 0.0, 4)}


def score_technical(
    *,
    ema_21: float | None,
    ema_50: float | None,
    ema_200: float | None,
    price: float | None,
    ret_1w: float | None,
    rsi_14: float | None,
    rs_3m_spy: float | None,
    rs_6m_spy: float | None,
    rs_12m_spy: float | None,
    peer_pct_6m: float | None,
    th: Mapping[str, Decimal],
) -> LensResult:
    """The technical lens (0–100) from four sub-scores, §C's definition exactly.

    trend and structure are India's own scorers, unmodified, reading the same threshold keys
    out of the global table. rs_spy and peer_rs are this market's own.
    """
    # india_thresholds INDEXES the eight keys India reads. The earlier version passed the
    # whole table converted to float, which looks equivalent and is not: India's scorer uses
    # `th.get(key, <literal>)`, so a key missing from the global table fell through to INDIA'S
    # number and scored US funds on it, silently. Indexing raises KeyError by name instead.
    thd = india_thresholds(th)
    trend, trend_ev = _score_trend(ema_21, ema_50, ema_200, price, rsi_14, ret_1w, thd)
    structure, structure_ev = _score_relative_strength(ema_21, ema_50, ema_200, thd)
    rs_spy, rs_ev = score_rs_spy(rs_3m_spy, rs_6m_spy, rs_12m_spy, th)
    peer, peer_ev = score_peer_rs(peer_pct_6m, th)
    return _lens(
        {
            "tech_trend": trend,
            "tech_structure": structure,
            "tech_rs_spy": rs_spy,
            "tech_rs_peer": peer,
        },
        {"trend": trend_ev, "structure": structure_ev, "rs_spy": rs_ev, "peer": peer_ev},
    )


def score_risk(
    *,
    vol_pct_rank: float | None,
    mdd_pct_rank: float | None,
    downside_pct_rank: float | None,
    beta_spy: float | None,
    th: Mapping[str, Decimal],
) -> LensResult:
    """The risk lens (0–100): three percentile sub-scores plus a beta band.

    The three percentiles are ranked within the ASSET GROUP, not the peer group — a bond
    fund's volatility belongs beside other bond funds, and there are not enough funds in a
    narrow strategy to rank a distribution. The caller orients them so 1 = calmest.

    Beta is banded rather than ranked because its meaningful cut points are absolute: 1.0 is
    "moves with the index" whatever else is in the group. Non-equity funds still get the
    band — a commodity fund's beta to SPY is a real, informative number.
    """
    subs: dict[str, Decimal | None] = {
        "risk_vol": quintile_points(vol_pct_rank, th),
        "risk_mdd": quintile_points(mdd_pct_rank, th),
        "risk_downside": quintile_points(downside_pct_rank, th),
        "risk_beta": _beta_points(beta_spy, th),
    }
    return _lens(subs, {"beta": beta_spy})


def _beta_points(beta: float | None, th: Mapping[str, Decimal]) -> Decimal | None:
    if beta is None:
        return None
    value = Decimal(str(beta))
    for cut_key, pts_key in (
        ("risk_beta_t1", "etf_risk_beta_t1_pts"),
        ("risk_beta_t2", "etf_risk_beta_t2_pts"),
        ("risk_beta_t3", "etf_risk_beta_t3_pts"),
    ):
        if value <= Decimal(th[cut_key]):
            return Decimal(th[pts_key])
    return Decimal(th["etf_risk_beta_t4_pts"])


def score_cost_liquidity(
    *,
    adv_usd_60d: float | None,
    expense_pct_rank: float | None = None,
    aum_usd: float | None = None,
    top10_weight: float | None = None,
    th: Mapping[str, Decimal],
) -> LensResult:
    """The cost-and-liquidity lens (0–100).

    Only ``cost_adv`` can be computed from today's data. ``expense_pct_rank``, ``aum_usd`` and
    ``top10_weight`` are accepted now so that the P3-C ingestors light the other three
    sub-scores up without touching this function or its tests — and until they do, those subs
    are ``None`` and the lens is honestly the ADV$ read alone, which ``lenses_active`` and the
    board's "n of 5 lenses" label both disclose.

    ADV$ is a band, not a percentile: the question "can I get in and out of this" has absolute
    answers in dollars, and a percentile would call the most liquid fund in an illiquid corner
    liquid.
    """
    subs: dict[str, Decimal | None] = {
        "cost_adv": _adv_points(adv_usd_60d, th),
        "cost_expense": quintile_points(expense_pct_rank, th),
        "cost_aum": _aum_points(aum_usd, th),
        "cost_concentration": _concentration_points(top10_weight, th),
    }
    return _lens(subs, {"adv_usd_60d": adv_usd_60d})


def _adv_points(adv: float | None, th: Mapping[str, Decimal]) -> Decimal | None:
    if adv is None:
        return None
    value = Decimal(str(adv))
    for cut_key, pts_key in (
        ("cost_adv_usd_t1", "etf_cost_adv_t1_pts"),
        ("cost_adv_usd_t2", "etf_cost_adv_t2_pts"),
        ("cost_adv_usd_t3", "etf_cost_adv_t3_pts"),
        ("cost_adv_usd_t4", "etf_cost_adv_t4_pts"),
    ):
        if value >= Decimal(th[cut_key]):
            return Decimal(th[pts_key])
    return Decimal(th["etf_cost_adv_t5_pts"])


def _aum_points(aum: float | None, th: Mapping[str, Decimal]) -> Decimal | None:
    """P3-C: NULL until etf_meta carries AUM. The bands are already seeded, so this lights up
    on the day the ingestor lands, with no change here."""
    if aum is None:
        return None
    value = Decimal(str(aum))
    for cut_key, pts_key in (
        ("cost_aum_usd_t1", "etf_cost_adv_t1_pts"),
        ("cost_aum_usd_t2", "etf_cost_adv_t2_pts"),
        ("cost_aum_usd_t3", "etf_cost_adv_t3_pts"),
        ("cost_aum_usd_t4", "etf_cost_adv_t4_pts"),
    ):
        if value >= Decimal(th[cut_key]):
            return Decimal(th[pts_key])
    return Decimal(th["etf_cost_adv_t5_pts"])


def _concentration_points(top10: float | None, th: Mapping[str, Decimal]) -> Decimal | None:
    """P3-C: NULL until etf_holdings exists. Lower top-10 weight is the good end."""
    if top10 is None:
        return None
    value = Decimal(str(top10))
    for cut_key, pts_key in (
        ("cost_top10_t1", "etf_quintile_q1_pts"),
        ("cost_top10_t2", "etf_quintile_q2_pts"),
        ("cost_top10_t3", "etf_quintile_q3_pts"),
    ):
        if value <= Decimal(th[cut_key]):
            return Decimal(th[pts_key])
    return Decimal(th["etf_quintile_q5_pts"])
