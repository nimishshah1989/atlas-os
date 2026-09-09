"""The US flow lens, on nine years of real FINRA short interest.

The fixtures are verbatim API responses for Apple, JPMorgan and Verizon — 208 settlement dates
each, 2017-12-29 to 2026-08-14 (provenance in ``tests/fixtures/global/finra/SOURCE.md``). Every
figure asserted below is one FINRA published.

The four ways this lens could be wrong:

* scoring a stale reading as though it were today's positioning — FINRA publishes about eight
  business days after a settlement and settlements are twice a month, so "current" is routinely
  three weeks old;
* reading the days-to-cover ladder the wrong way round, which would score the most crowded
  shorts as the calmest (the same inversion trap the debt/equity bands carry);
* trusting a change percent computed across a stock split, where the two share counts are not
  comparable; and
* turning an absent reading into 50, which claims neutral positioning about a stock nobody
  measured.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
from dataclasses import replace
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from atlas.global_market.providers.finra import DATASET_URL, parse_short_interest
from atlas.global_market.scoring.stock_flow import (
    FLOW_KEYS,
    latest_reading,
    missing_keys,
    score_flow,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "finra"
AS_OF = dt.date(2026, 9, 9)

#: The keys some real reading in these fixtures actually reaches. Everything but the extreme
#: days-to-cover rung — see the test that records why.
READ_BY_REAL_DATA = {
    "flow_si_max_age_days",
    "flow_dtc_low",
    "flow_dtc_ok",
    "flow_dtc_high",
    "flow_dtc_pts_low",
    "flow_dtc_pts_ok",
    "flow_dtc_pts_high",
    "flow_si_change_big",
    "flow_si_change_mod",
    "flow_si_pts_covering_big",
    "flow_si_pts_covering_mod",
    "flow_si_pts_building_mod",
    "flow_si_pts_building_big",
}

# The seeded ladder. Days to cover: two days or fewer is uncrowded, beyond eight is extreme.
# The change bands are gentler than the level ones on purpose — a rising short position has
# innocent explanations (convertible, index and merger arbitrage all short against a hedge).
TH: dict[str, Decimal] = {
    "flow_si_max_age_days": Decimal(45),
    "flow_dtc_low": Decimal(2),
    "flow_dtc_ok": Decimal(4),
    "flow_dtc_high": Decimal(8),
    "flow_dtc_pts_low": Decimal(10),
    "flow_dtc_pts_ok": Decimal(4),
    "flow_dtc_pts_high": Decimal(-6),
    "flow_dtc_pts_extreme": Decimal(-14),
    "flow_si_change_big": Decimal(20),
    "flow_si_change_mod": Decimal(8),
    "flow_si_pts_covering_big": Decimal(8),
    "flow_si_pts_covering_mod": Decimal(4),
    "flow_si_pts_building_mod": Decimal(-4),
    "flow_si_pts_building_big": Decimal(-8),
}


@cache
def history(symbol: str):
    raw = gzip.decompress((FIXTURES / f"short_interest_{symbol}.json.gz").read_bytes())
    return parse_short_interest(json.loads(raw))


# ── the feed ────────────────────────────────────────────────────────────────


def test_the_feed_is_dense_and_deep_which_is_why_the_lens_is_built_on_it() -> None:
    """The measurement behind the design. Form 4 gave zero open-market purchases in a year
    across these same three companies; short interest gives 208 readings each over nine years —
    dense enough to score every name and long enough to IC-test the lens later."""
    for symbol in ("AAPL", "JPM", "VZ"):
        rows = history(symbol)
        assert len(rows) == 208, symbol
        assert rows[0].settlement_date == dt.date(2017, 12, 29), symbol
        assert rows[-1].settlement_date == dt.date(2026, 8, 14), symbol
        assert all(r.symbol == symbol for r in rows), symbol


def test_the_rows_are_ordered_and_carry_finras_own_arithmetic() -> None:
    """`daysToCoverQuantity` and `changePercent` are FINRA's, not ours. Apple's newest reading:
    116,327,753 shares short against 46,065,396 average daily volume — 2.53 days to cover — and
    down 17.85 percent from the previous settlement."""
    newest = history("AAPL")[-1]
    assert newest.short_shares == Decimal("116327753")
    assert newest.previous_short_shares == Decimal("141606163")
    assert newest.average_daily_volume == Decimal("46065396")
    assert newest.days_to_cover == Decimal("2.53")
    assert newest.change_percent == Decimal("-17.85")
    assert [r.settlement_date for r in history("AAPL")] == sorted(
        r.settlement_date for r in history("AAPL")
    )


def test_a_row_that_cannot_be_placed_is_dropped_rather_than_guessed() -> None:
    rows = parse_short_interest(
        [
            {"symbolCode": "", "settlementDate": "2026-08-14"},
            {"symbolCode": "AAPL", "settlementDate": None},
            {"symbolCode": "AAPL", "settlementDate": "not-a-date"},
        ]
    )
    assert rows == []


def test_the_endpoint_is_the_partitioned_dataset_the_ingest_must_query_by_date() -> None:
    assert DATASET_URL.endswith("/consolidatedShortInterest")


# ── the scoring, on real readings ───────────────────────────────────────────


def test_apple_and_jpmorgan_score_differently_on_their_real_crowding() -> None:
    """Apple is 2.53 days to cover and JPMorgan 4.6 — the same ladder, two rungs apart, and the
    difference is the whole point of the sub-score."""
    apple = score_flow(history("AAPL"), AS_OF, TH)
    jpm = score_flow(history("JPM"), AS_OF, TH)
    assert apple.short_level == Decimal(50) + TH["flow_dtc_pts_ok"]
    assert jpm.short_level == Decimal(50) + TH["flow_dtc_pts_high"]
    assert apple.short_level is not None and jpm.short_level is not None
    assert apple.short_level > jpm.short_level


def test_shorts_covering_reads_positive_on_all_three_real_names() -> None:
    """Every one of these three was covering into the last settlement — Apple −17.85 percent,
    JPMorgan −10.43, Verizon −8.44 — so all three change sub-scores sit above neutral."""
    for symbol in ("AAPL", "JPM", "VZ"):
        result = score_flow(history(symbol), AS_OF, TH)
        assert result.short_change is not None
        assert result.short_change > Decimal(50), symbol
        assert Decimal(result.evidence["change_percent"]) < 0, symbol


def test_the_ladder_runs_the_RIGHT_way_round() -> None:
    """The inversion that would score the most crowded shorts as the calmest. Walking a real
    history's own days-to-cover values, more days must never earn more points."""
    readings = sorted(
        (r.days_to_cover for r in history("JPM") if r.days_to_cover is not None), reverse=True
    )
    assert readings[0] > readings[-1], "the fixture must span a range of crowding"
    scores = [
        score_flow(
            [r for r in history("JPM") if r.days_to_cover == value][:1],
            AS_OF,
            {**TH, "flow_si_max_age_days": Decimal(10_000)},
        ).short_level
        for value in (readings[0], readings[-1])
    ]
    crowded, calm = scores
    assert crowded is not None and calm is not None
    assert calm > crowded


def test_the_lens_is_the_mean_of_the_sub_scores_that_are_present() -> None:
    result = score_flow(history("JPM"), AS_OF, TH)
    assert result.short_level is not None and result.short_change is not None
    assert result.value == (result.short_level + result.short_change) / 2


# ── what it refuses ─────────────────────────────────────────────────────────


def test_a_stale_reading_is_refused_rather_than_scored_as_current() -> None:
    """The newest settlement here is 2026-08-14. Asked as of a year later it is nine months old,
    and last year's positioning is not this year's — so every sub-score is None and the evidence
    says why, instead of a confident 54 about a stock nobody has measured since."""
    result = score_flow(history("AAPL"), dt.date(2027, 9, 9), TH)
    assert result.value is None and result.short_level is None and result.short_change is None
    assert result.evidence["reason"] == "the newest settlement is stale"
    assert result.evidence["age_days"] > int(TH["flow_si_max_age_days"])


def test_a_reading_from_after_the_anchor_is_not_visible_on_that_day() -> None:
    """Point-in-time. Asked as of 2020-01-01 the lens must use the settlement before it, not the
    2026 one — a backfilled score that can see the future makes every backtest optimistic."""
    reading = latest_reading(history("AAPL"), dt.date(2020, 1, 1))
    assert reading is not None
    assert reading.settlement_date <= dt.date(2020, 1, 1)
    assert reading.settlement_date.year == 2019
    assert latest_reading(history("AAPL"), dt.date(2000, 1, 1)) is None


def test_a_stock_with_no_reading_at_all_is_unscored_rather_than_neutral() -> None:
    result = score_flow([], AS_OF, TH)
    assert result.value is None
    assert result.subs == {
        "flow_promoter": None,
        "flow_institutional": None,
        "flow_smart_money": None,
    }


def test_a_change_across_a_SPLIT_is_not_a_change_in_positioning() -> None:
    """A split makes the two share counts incomparable, so FINRA's own change percent is
    meaningless across one; its flag is the only warning there is. The level sub-score survives
    (days to cover is a ratio and a split moves both sides), the change sub-score does not."""
    newest = history("AAPL")[-1]
    split = [replace(newest, split_flag=True)]
    result = score_flow(split, AS_OF, TH)
    assert result.short_level is not None, "a ratio survives a split"
    assert result.short_change is None, "a percent change across a split does not"
    assert result.evidence["split_between_settlements"] is True


# ── the contract with the table ─────────────────────────────────────────────


def test_removing_any_key_a_real_run_READS_raises_rather_than_defaulting() -> None:
    """No defaults. The keys under test are the ones 624 real readings actually reach — each
    scored as of its own settlement date, so every rung the data touches is exercised."""
    every = [r for s in ("AAPL", "JPM", "VZ") for r in history(s)]
    assert len(every) == 624
    for key in sorted(READ_BY_REAL_DATA):
        short = {k: v for k, v in TH.items() if k != key}
        assert missing_keys(short) == [key]
        raised = False
        for reading in every:
            try:
                score_flow([reading], reading.settlement_date, short)
            except KeyError:
                raised = True
                break
        assert raised, f"no real reading exercises {key}"


def test_the_declared_keys_and_the_seeded_table_agree_exactly() -> None:
    """A key the scorer reads and the table lacks is a crash in prod; a key the table carries and
    nothing reads is a row the FM can tune with no effect — which is why `flow_dtc_extreme` was
    removed from the list rather than left in it."""
    assert set(FLOW_KEYS) == set(TH)
    assert missing_keys(TH) == []


def test_the_rung_these_three_names_never_reach_is_declared_but_UNEXERCISED() -> None:
    """The honest limit, recorded rather than hidden. Across 624 real readings the days-to-cover
    ladder reaches low (310), ok (290) and high (24) — and never extreme. Three healthy megacaps
    are never crowded shorts, which is exactly why they are poor witnesses for that rung. It is
    asserted to EXIST and to be the harshest; whether it is the right size is a question only a
    heavily shorted name can answer, and this file does not pretend otherwise."""
    unexercised = set(FLOW_KEYS) - READ_BY_REAL_DATA
    assert unexercised == {"flow_dtc_pts_extreme"}
    assert TH["flow_dtc_pts_extreme"] < TH["flow_dtc_pts_high"] < 0
    crowded = max(
        (r.days_to_cover for s in ("AAPL", "JPM", "VZ") for r in history(s) if r.days_to_cover),
        default=Decimal(0),
    )
    assert crowded <= TH["flow_dtc_high"], "no reading here is beyond the high rung"
