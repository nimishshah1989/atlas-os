"""Unit tests for atlas/compute/signal_eval.py — the rank-IC and decile-spread math.

Every number below is a REAL row pulled from atlas_foundation and pasted as a literal so
the test needs no DB. Rule #0: not one of them is invented.

  * `_LARGE` / `_MICRO` — (symbol, technical, fwd_21) for the first 25 names by symbol in
    each cap cohort on 2024-06-14. Forward returns are `lead(close_adj, 21)` exactly as
    scripts/foundation/eval_signal.forward_returns computes them.
  * `_EDGE` — the same query on 2026-08-24, the last scored date. Every fwd_21 there is
    genuinely NULL: the 21-session horizon runs past the end of the price data.
  * `_ONE_POLICY_VALUE` — the two small-caps whose sector-level `policy` score is 20.00 on
    2024-06-14. policy is a sector score broadcast to constituents, so a cohort of them is
    one tie block with no variance to rank.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
import pytest

from atlas.compute.signal_eval import evaluate, summarise

pytestmark = pytest.mark.unit

_LARGE = [
    ("ABB", 87, -0.08732815964523281596),
    ("ADANIENSOL", 35, 0.0024024318493822),
    ("ADANIENT", 56, -0.04673961166276642844),
    ("ADANIGREEN", 55, -0.02566018933731938216),
    ("ADANIPORTS", 67, 0.0477738170126511),
    ("ADANIPOWER", 73, -0.04586541680616002678),
    ("APOLLOHOSP", 66, 0.0396449513499581),
    ("ASIANPAINT", 50, 0.0119455093099671),
    ("AXISBANK", 68, 0.1041022818678295),
    ("BAJAJ-AUTO", 74, -0.02444547372754876229),
    ("BAJAJFINSV", 51, 0.0111826605936862),
    ("BAJAJHLDNG", 60, 0.1799442360153441),
    ("BAJFINANCE", 62, -0.03814713896457765668),
    ("BANKBARODA", 67, -0.07338570607396052884),
    ("BEL", 80, 0.0534560723514212),
    ("BHARTIARTL", 70, 0.0071458596048760),
    ("BHEL", 74, 0.0467778868171410),
    ("BOSCHLTD", 77, 0.08602657774423251814),
    ("BPCL", 64, 0.0083001902126924),
    ("BRITANNIA", 70, 0.0868984824747620),
    ("BSE", 81, -0.14029363784665579119),
    ("CANBK", 77, -0.03950048711363032504),
    ("CGPOWER", 77, 0.0606852497096400),
    ("CHOLAFIN", 80, -0.02681409813407049067),
    ("CIPLA", 82, -0.03038824093305639879),
]

_MICRO = [
    ("AAVAS", 76, -0.03533282986298414068),
    ("ABFRL", 70, 0.0048250904704463),
    ("ACE", 73, -0.02210711625702484935),
    ("BALRAMCHIN", 71, 0.0464900046490005),
    ("BATAINDIA", 48, 0.0538641686182670),
    ("BBTC", 69, 0.3735275414105321),
    ("BLS", 59, 0.0429922613929493),
    ("BLUEDART", 67, 0.1255455971178616),
    ("BLUEJET", 62.67, 0.0637836458731981),
    ("BSOFT", 57, 0.0724242200752268),
    ("CANFINHOME", 70, 0.0632411067193676),
    ("CLEAN", 49, 0.0932790224032587),
    ("CYIENT", 45, -0.02518984997221707724),
    ("ELECON", 80, -0.01195520581113801453),
    ("HOMEFIRST", 70, 0.0020050359041313),
    ("IEX", 74, -0.01296821951355262426),
    ("INDIACEM", 41, 0.4594435913648270),
    ("INDIAMART", 38, 0.1105895132975112),
    ("INOXWIND", 65, 0.1449801158166469),
    ("INTELLECT", 70, 0.0172958899014320),
    ("IRCON", 74, 0.2030466282741965),
    ("JKTYRE", 50, 0.1863322884012539),
    ("JMFINANCIL", 36, 0.1864548494983278),
    ("JPPOWER", 80, -0.05763397371081900910),
    ("JUBLINGREA", 60, 0.1547314578005115),
]

_EDGE = [
    ("ABB", 87.5, None),
    ("ADANIENSOL", 87.5, None),
    ("ADANIENT", 90, None),
    ("ADANIGREEN", 50, None),
    ("ADANIPORTS", 50, None),
    ("ADANIPOWER", 55, None),
    ("APOLLOHOSP", 90, None),
    ("ASIANPAINT", 85, None),
    ("AXISBANK", 45, None),
    ("BAJAJ-AUTO", 95, None),
    ("BAJAJFINSV", 95, None),
    ("BAJAJHLDNG", 85, None),
    ("BAJFINANCE", 95, None),
    ("BANKBARODA", 10, None),
    ("BEL", 15, None),
    ("BHARTIARTL", 85, None),
    ("BHEL", 87.5, None),
    ("BOSCHLTD", 100, None),
    ("BPCL", 50, None),
    ("BRITANNIA", 47.5, None),
    ("BSE", 37.5, None),
    ("CANBK", 55, None),
]

_ONE_POLICY_VALUE = [
    ("EIDPARRY", 20.00, 0.0903159340659341),
    ("PARADEEP", 20.00, 0.2355501155990752),
]


def _frame(rows: Sequence[tuple[str, float, float | None]], date: str, cap: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "date": date,
            "score": [float(r[1]) for r in rows],
            "fwd_21": pd.Series([r[2] for r in rows], dtype="float64"),
            "cap": cap,
        }
    )


LARGE = _frame(_LARGE, "2024-06-14", "large")
MICRO = _frame(_MICRO, "2024-06-14", "micro")
BOTH = pd.concat([LARGE, MICRO], ignore_index=True)


def test_rank_ic_matches_an_independent_spearman_on_a_real_cross_section() -> None:
    """The engine ranks by hand then takes Pearson. pandas' own `method="spearman"` is a
    separate code path over the same real rows; the two must agree exactly."""
    out = evaluate(BOTH, horizon=21, deciles=4).set_index("cohort")
    for cohort, src in (("large", LARGE), ("micro", MICRO)):
        expected = pd.Series(src["score"]).corr(pd.Series(src["fwd_21"]), method="spearman")
        assert out.loc[cohort, "n"] == 25
        assert out.loc[cohort, "rank_ic"] == pytest.approx(expected, abs=1e-12)


def test_ic_flips_sign_when_the_score_is_reversed() -> None:
    """The single most important property: reverse the score and the IC must invert.
    A metric that does not is measuring something other than what it claims."""
    fwd = evaluate(BOTH, horizon=21, deciles=4).set_index("cohort")["rank_ic"]
    rev = evaluate(BOTH.assign(score=100.0 - BOTH["score"]), horizon=21, deciles=4)
    back = rev.set_index("cohort")["rank_ic"]
    for cohort in ("large", "micro"):
        assert back[cohort] == pytest.approx(-fwd[cohort], abs=1e-12)


def test_shuffled_scores_have_near_zero_ic() -> None:
    """The null test. A score bearing no relation to the outcome must produce ~0 IC.

    Averaged over 200 seeded permutations of the real scores rather than judged on one
    draw: a single permutation of 25 names has a sampling SD near 0.2, so a lone draw
    proves nothing and a threshold loose enough to hold it would prove less.
    """
    rng = np.random.default_rng(20240614)
    scores = LARGE["score"].to_numpy()
    ics = [
        float(
            evaluate(LARGE.assign(score=rng.permutation(scores)), horizon=21, deciles=4).iloc[0][
                "rank_ic"
            ]
        )
        for _ in range(200)
    ]
    mean = float(np.mean(ics))
    assert abs(mean) < 0.05, f"a scrambled score should be near-zero, got {mean}"


def test_decile_spread_is_top_minus_bottom_mean_return() -> None:
    out = evaluate(LARGE, horizon=21, deciles=4).iloc[0]
    k = len(LARGE) // 4
    top = LARGE.nlargest(k, "score")["fwd_21"].mean()
    bot = LARGE.nsmallest(k, "score")["fwd_21"].mean()
    assert out["decile_spread"] == pytest.approx(top - bot, abs=1e-12)


def test_rows_with_a_missing_forward_return_are_dropped_not_zeroed() -> None:
    """A NULL forward return means the horizon runs past the end of the data. It is not a
    0% return, and treating it as one drags every IC toward the mean.

    _EDGE is 2026-08-24, the last scored date, where that is true of every name. Zero-fill
    it and you get a second row with a fabricated IC; drop it and the date vanishes.
    """
    out = evaluate(pd.concat([LARGE, _frame(_EDGE, "2026-08-24", "large")]), horizon=21, deciles=4)
    assert list(out["date"]) == ["2024-06-14"]
    assert out.iloc[0]["n"] == 25


def test_a_date_below_the_minimum_cross_section_is_skipped() -> None:
    """Ranking 5 names produces a number, not a signal."""
    assert evaluate(LARGE.head(5), horizon=21, deciles=4).empty


def test_cohorts_are_evaluated_separately() -> None:
    """Deciles are cut WITHIN cohort. Pooling large-caps with micro-caps measures the size
    effect, not the lens."""
    out = evaluate(BOTH, horizon=21, deciles=4)
    assert len(out) == 2
    assert set(out["cohort"]) == {"large", "micro"}
    pooled = evaluate(BOTH.assign(cap="all"), horizon=21, deciles=4).iloc[0]["rank_ic"]
    per_cohort = out["rank_ic"].tolist()
    assert pooled != pytest.approx(per_cohort[0]) and pooled != pytest.approx(per_cohort[1])


def test_a_score_with_no_variance_yields_no_ic_rather_than_a_number() -> None:
    """`policy` is a sector score broadcast to constituents, so a cohort can be one tie
    block. There is no ordering to correlate — the answer is NULL, not 0.0."""
    out = evaluate(_frame(_ONE_POLICY_VALUE, "2024-06-14", "small"), horizon=21, deciles=4, min_n=2)
    assert len(out) == 1
    assert pd.isna(out.iloc[0]["rank_ic"])
    assert pd.isna(out.iloc[0]["decile_spread"])


def test_ties_are_ranked_by_average_not_by_row_order() -> None:
    """CGPOWER, CANBK and BOSCHLTD all score 77. `method="first"` would invent an ordering
    inside the tie block that the data does not contain, and the IC would then depend on
    the order rows came back from the query."""
    shuffled = LARGE.iloc[::-1].reset_index(drop=True)
    assert evaluate(shuffled, horizon=21, deciles=4).iloc[0]["rank_ic"] == pytest.approx(
        evaluate(LARGE, horizon=21, deciles=4).iloc[0]["rank_ic"], abs=1e-12
    )


def test_summarise_collapses_the_per_date_frame() -> None:
    per_date = evaluate(BOTH, horizon=21, deciles=4)
    got = summarise(per_date)
    ic = per_date["rank_ic"]
    assert got["n_dates"] == 2
    assert got["mean_ic"] == pytest.approx(float(ic.mean()), abs=1e-12)
    assert got["hit_rate"] == pytest.approx(float((ic > 0).mean()), abs=1e-12)
    assert got["mean_spread"] == pytest.approx(float(per_date["decile_spread"].mean()), abs=1e-12)


def test_summarise_of_nothing_reports_null_not_zero() -> None:
    """No observations is not a mean IC of zero."""
    got = summarise(evaluate(LARGE.head(5), horizon=21, deciles=4))
    assert got["n_dates"] == 0
    assert got["mean_ic"] is None and got["hit_rate"] is None and got["mean_spread"] is None
