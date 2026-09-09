"""The ETF lens scorers, exercised against the REAL seeded thresholds.

Rule #0: nothing here invents a market number. There are two kinds of input below and both
are real:

* **The thresholds** come from ``seed_thresholds.SEEDS`` — the actual rows that go into
  ``atlas_global.atlas_thresholds``, read here rather than restated, so a seed the FM re-tunes
  cannot leave these assertions asserting a number the product no longer uses.
* **The instrument inputs** are POSITIONS RELATIVE TO THOSE THRESHOLDS, not observations: "a
  percentile above the top-quintile cut", "a relative strength above ``rs_spy_strong``", "a
  beta at the band-1 boundary". What is under test is the LADDER — does a fund on this side of
  a seeded cut get the seeded points — and that question has no market data in it.

The one thing these tests must catch is the failure mode rule #0 exists for: a sub-score
returning 0 (a real, bad score) where it means "no data". A fund is not bad at something we
never measured, and a 0 there would drag a composite down with a number nobody can trace.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

import pytest

from atlas.global_market.scoring.etf_lenses import (
    LensResult,
    quintile_points,
    score_cost_liquidity,
    score_risk,
    score_rs_spy,
    score_technical,
)
from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

seed_thresholds = load_global_script("seed_thresholds")


@pytest.fixture(scope="module")
def th() -> dict[str, Decimal]:
    """The real seed table as ``load_thresholds`` hands it to the scorers."""
    return {
        str(row["threshold_key"]): Decimal(str(row["threshold_value"]))
        for row in seed_thresholds.SEEDS
    }


# ── the shared percentile ladder ──────────────────────────────────────────────


def test_the_quintile_ladder_awards_the_seeded_points_at_each_step(th: dict[str, Decimal]) -> None:
    assert quintile_points(0.95, th) == th["etf_quintile_q1_pts"]
    assert quintile_points(0.70, th) == th["etf_quintile_q2_pts"]
    assert quintile_points(0.50, th) == th["etf_quintile_q3_pts"]
    assert quintile_points(0.30, th) == th["etf_quintile_q4_pts"]
    assert quintile_points(0.05, th) == th["etf_quintile_q5_pts"]


def test_the_ladder_is_monotone_so_a_better_percentile_never_scores_worse(
    th: dict[str, Decimal],
) -> None:
    steps = [quintile_points(p / 100, th) for p in range(0, 101, 5)]
    assert all(a is not None and b is not None and a <= b for a, b in pairwise(steps))


def test_no_percentile_yields_no_points_not_zero_points(th: dict[str, Decimal]) -> None:
    """A fund whose group was too small to rank has no percentile. Zero would be a verdict."""
    assert quintile_points(None, th) is None


# ── relative strength vs SPY ──────────────────────────────────────────────────


def test_clearing_rs_spy_strong_earns_a_window_its_full_seeded_points(
    th: dict[str, Decimal],
) -> None:
    strong = float(th["rs_spy_strong"]) + 0.01
    value, _ = score_rs_spy(strong, strong, strong, th)
    expected = th["etf_rs_spy_3m_pts"] + th["etf_rs_spy_6m_pts"] + th["etf_rs_spy_12m_pts"]
    assert value == expected
    assert expected == Decimal("25"), "the three windows must sum to one full sub-score"


def test_beating_spy_without_clearing_the_bar_earns_the_seeded_fraction(
    th: dict[str, Decimal],
) -> None:
    ahead = float(th["rs_spy_strong"]) / 2
    value, evidence = score_rs_spy(ahead, ahead, ahead, th)
    full = th["etf_rs_spy_3m_pts"] + th["etf_rs_spy_6m_pts"] + th["etf_rs_spy_12m_pts"]
    assert value == (full * th["etf_rs_spy_partial_frac"]).quantize(Decimal("0.01"))
    assert set(evidence.values()) == {"ahead"}


def test_trailing_spy_scores_nothing_but_is_still_a_measurement(th: dict[str, Decimal]) -> None:
    value, evidence = score_rs_spy(-0.10, -0.10, -0.10, th)
    assert value == Decimal("0.00")
    assert set(evidence.values()) == {"behind"}


def test_a_missing_window_is_skipped_and_all_missing_gives_no_score(
    th: dict[str, Decimal],
) -> None:
    """A fund listed four months ago has no 12-month RS. It is scored on what it has — but a
    fund with no window at all has no sub-score, not a zero."""
    strong = float(th["rs_spy_strong"]) + 0.01
    partial, evidence = score_rs_spy(strong, None, None, th)
    assert partial == th["etf_rs_spy_3m_pts"]
    assert evidence["rs_6m"] == "no data"
    assert score_rs_spy(None, None, None, th)[0] is None


# ── the technical lens ────────────────────────────────────────────────────────


def _strong_trend_inputs(th: dict[str, Decimal]) -> dict[str, float]:
    """EMAs stacked, price well above the 200, a positive week — every term at its best side
    of the seeded cut. The numbers are positions relative to thresholds, not a real fund."""
    ema_200 = 100.0
    return {
        "ema_21": 112.0,
        "ema_50": 108.0,
        "ema_200": ema_200,
        "price": ema_200 * (1 + float(th["price_above_ema200_strong"]) + 0.01),
        "ret_1w": float(th["slope_strong_pct"]) + 0.01,
        "rsi_14": 60.0,
    }


def test_a_fund_in_a_clean_uptrend_scores_near_the_top_of_the_technical_lens(
    th: dict[str, Decimal],
) -> None:
    strong = float(th["rs_spy_strong"]) + 0.01
    result = score_technical(
        **_strong_trend_inputs(th),
        rs_3m_spy=strong,
        rs_6m_spy=strong,
        rs_12m_spy=strong,
        peer_pct_6m=0.95,
        th=th,
    )
    assert isinstance(result, LensResult)
    assert result.value is not None and result.value >= Decimal("90")
    assert all(v is not None for v in result.subs.values()), "all four sub-scores had inputs"


def test_the_lens_is_the_mean_of_present_subs_times_four(th: dict[str, Decimal]) -> None:
    """The 0–25 → 0–100 contract: two sub-scores present must scale the same as four, or a
    fund is punished for a metric its listing age denies it."""
    result = score_technical(
        **_strong_trend_inputs(th),
        rs_3m_spy=None,
        rs_6m_spy=None,
        rs_12m_spy=None,
        peer_pct_6m=None,
        th=th,
    )
    present = [v for v in result.subs.values() if v is not None]
    assert len(present) == 2, "trend and structure only — the two RS subs had no inputs"
    expected = (sum(present, Decimal("0")) / Decimal(len(present)) * 4).quantize(Decimal("0.01"))
    assert result.value == expected
    assert result.evidence["subs_present"] == 2


def test_a_fund_with_no_metrics_at_all_scores_none_not_zero(th: dict[str, Decimal]) -> None:
    result = score_technical(
        ema_21=None,
        ema_50=None,
        ema_200=None,
        price=None,
        ret_1w=None,
        rsi_14=None,
        rs_3m_spy=None,
        rs_6m_spy=None,
        rs_12m_spy=None,
        peer_pct_6m=None,
        th=th,
    )
    assert result.value is None
    assert result.evidence["reason"] == "no sub-score had inputs"


# ── the risk lens (computed, deliberately not blended) ────────────────────────


def test_beta_bands_award_the_seeded_points_on_the_right_side_of_each_cut(
    th: dict[str, Decimal],
) -> None:
    at_band_1 = score_risk(
        vol_pct_rank=None,
        mdd_pct_rank=None,
        downside_pct_rank=None,
        beta_spy=float(th["risk_beta_t1"]),
        th=th,
    )
    assert at_band_1.subs["risk_beta"] == th["etf_risk_beta_t1_pts"]
    above_all = score_risk(
        vol_pct_rank=None,
        mdd_pct_rank=None,
        downside_pct_rank=None,
        beta_spy=float(th["risk_beta_t3"]) + 0.5,
        th=th,
    )
    assert above_all.subs["risk_beta"] == th["etf_risk_beta_t4_pts"]


def test_the_calmest_fund_in_its_asset_group_tops_the_risk_lens(th: dict[str, Decimal]) -> None:
    """The caller inverts the volatility percentile before it reaches the ladder, so 1.0 means
    calmest. This pins that orientation: getting it backwards would rank the wildest fund safest
    and nothing downstream would notice."""
    calm = score_risk(
        vol_pct_rank=1.0, mdd_pct_rank=1.0, downside_pct_rank=1.0, beta_spy=0.5, th=th
    )
    wild = score_risk(
        vol_pct_rank=0.0, mdd_pct_rank=0.0, downside_pct_rank=0.0, beta_spy=2.0, th=th
    )
    assert calm.value is not None and wild.value is not None
    assert calm.value > wild.value


# ── cost and liquidity (one sub-score today, by design) ───────────────────────


def test_adv_bands_award_the_seeded_points(th: dict[str, Decimal]) -> None:
    top = score_cost_liquidity(adv_usd_60d=float(th["cost_adv_usd_t1"]), th=th)
    assert top.subs["cost_adv"] == th["etf_cost_adv_t1_pts"]
    thin = score_cost_liquidity(adv_usd_60d=float(th["cost_adv_usd_t4"]) / 2, th=th)
    assert thin.subs["cost_adv"] == th["etf_cost_adv_t5_pts"]


def test_the_three_unbuilt_sub_scores_are_absent_not_zero(th: dict[str, Decimal]) -> None:
    """expense, AUM and concentration need etf_meta and etf_holdings (phase2.md P3-C). Until
    those ingestors exist the lens is honestly the ADV$ read alone."""
    result = score_cost_liquidity(adv_usd_60d=float(th["cost_adv_usd_t2"]), th=th)
    assert result.subs["cost_expense"] is None
    assert result.subs["cost_aum"] is None
    assert result.subs["cost_concentration"] is None
    assert result.value == (result.subs["cost_adv"] or Decimal("0")) * 4


def test_a_missing_threshold_key_fails_by_name_rather_than_defaulting(
    th: dict[str, Decimal],
) -> None:
    """The global convention scoring/blend.py sets: index the table, never ``.get(k, default)``.
    A default is a methodology number hiding in code, and the first anyone would know of it is
    a score nobody can explain."""
    incomplete = {k: v for k, v in th.items() if k != "etf_quintile_q1_pts"}
    with pytest.raises(KeyError, match="etf_quintile_q1_pts"):
        quintile_points(0.95, incomplete)
