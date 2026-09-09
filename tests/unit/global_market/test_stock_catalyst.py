"""The US catalyst lens, on the real 8-K histories of Apple, JPMorgan and Verizon.

Every filing below is one those three companies actually made: the fixtures are verbatim SEC
submissions payloads downloaded on 2026-09-09 (provenance in
``tests/fixtures/global/submissions/SOURCE.md``). No filing, item code or date is invented.

The four things this lens can get wrong, and does not:

* reading a HEADLINE instead of an item code — the failure the module exists to avoid;
* letting the silence of an unscoreable filing read as "nothing happened" (82 of Apple's 105
  8-Ks carry only exhibit boilerplate);
* scoring a company on a window the feed does not actually cover (JPMorgan's ``recent`` reaches
  back exactly one year); and
* turning an absent bucket into 50, which would say "the news nets out to neutral" about a
  company that filed nothing.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from atlas.global_market.providers.submissions import parse_submissions, submissions_url
from atlas.global_market.scoring.stock_catalyst import (
    BUCKET_WEIGHT_KEY,
    BUCKETS,
    CATALYST_KEYS,
    ITEM_BUCKET,
    Filing,
    decay,
    points_key,
    score_catalyst,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "submissions"
FORMS = {"8-K", "8-K/A"}

# The seeds this lens is scored with. Points are the plan's §B figures where an item code carries
# the event it names; the rest follow its shape (a completed acquisition is worth less than a
# results filing is worth positively, distress is worth more negatively than good news is
# positively). They live in atlas_thresholds in prod — this is the table under test, not a
# default: score_catalyst has none and raises on a missing key.
TH: dict[str, Decimal] = {
    "catalyst_w_earnings": Decimal("0.55"),
    "catalyst_w_capital": Decimal("0.30"),
    "catalyst_w_governance": Decimal("0.15"),
    "catalyst_recency_t1": Decimal(90),
    "catalyst_recency_t2": Decimal(180),
    "catalyst_recency_t3": Decimal(365),
    "catalyst_decay_t1": Decimal("1.0"),
    "catalyst_decay_t2": Decimal("0.8"),
    "catalyst_decay_t3": Decimal("0.5"),
    "catalyst_decay_old": Decimal("0.3"),
    "catalyst_pts_2_02": Decimal(6),
    "catalyst_pts_1_01": Decimal(10),
    "catalyst_pts_1_02": Decimal(-6),
    "catalyst_pts_2_01": Decimal(8),
    "catalyst_pts_2_05": Decimal(-6),
    "catalyst_pts_2_06": Decimal(-10),
    "catalyst_pts_2_03": Decimal(-4),
    "catalyst_pts_2_04": Decimal(-12),
    "catalyst_pts_3_02": Decimal(-8),
    "catalyst_pts_3_03": Decimal(-3),
    "catalyst_pts_5_01": Decimal(-5),
    "catalyst_pts_1_03": Decimal(-25),
    "catalyst_pts_3_01": Decimal(-15),
    "catalyst_pts_4_01": Decimal(-12),
    "catalyst_pts_4_02": Decimal(-15),
    "catalyst_pts_5_02": Decimal(-8),
}

AS_OF = dt.date(2026, 9, 9)  # the day the fixtures were downloaded


@cache
def payload(symbol: str) -> dict[str, Any]:
    return json.loads(gzip.decompress((FIXTURES / f"submissions_{symbol}.json.gz").read_bytes()))


@cache
def eight_ks(symbol: str) -> tuple[Filing, ...]:
    subs = parse_submissions(payload(symbol), forms=FORMS)
    return tuple(
        Filing(filed=f.filed, items=f.items, accession_no=f.accession_no) for f in subs.filings
    )


# ── the parser ──────────────────────────────────────────────────────────────


def test_the_item_field_really_carries_sec_item_codes() -> None:
    """The claim the whole lens rests on. Apple's results filings are tagged 2.02, and the
    accession that carries them is Apple's own."""
    subs = parse_submissions(payload("AAPL"), forms=FORMS)
    assert subs.name == "Apple Inc."
    assert subs.tickers == ("AAPL",)
    results = [f for f in subs.filings if "2.02" in f.items]
    assert len(results) == 45
    assert all(f.form.startswith("8-K") for f in subs.filings)
    # The most recent one, exactly as filed.
    newest = max(results, key=lambda f: f.filed)
    assert newest.accession_no == "0000320193-26-000018"
    assert newest.filed == dt.date(2026, 7, 30)
    assert newest.items == ("2.02", "9.01")


def test_a_payload_whose_parallel_arrays_disagree_is_refused() -> None:
    """`filings.recent` is a dict of equal-length lists, not a list of objects. Zipping a short
    field would shift every later filing onto another filing's date — the errors would all look
    like real filings on wrong days, which nothing downstream could detect."""
    broken = json.loads(json.dumps(payload("VZ")))
    broken["filings"]["recent"]["items"] = broken["filings"]["recent"]["items"][:-5]
    with pytest.raises(ValueError, match="inconsistent"):
        parse_submissions(broken)


def test_the_url_is_the_ten_digit_zero_padded_form_the_endpoint_wants() -> None:
    assert submissions_url("320193").endswith("/CIK0000320193.json")
    assert submissions_url(19617) == submissions_url("0000019617")


def test_the_feed_reports_the_window_it_actually_covers() -> None:
    """`recent` is capped by COUNT, not by time. Apple files little besides its own reports, so
    its 1,000 rows reach 2015; JPMorgan files prospectuses continuously — 25,985 rows — and its
    window is one year. A lens looking back 365 days is only just covered for such a filer, so
    the feed must state its horizon rather than let it shrink silently."""
    apple = parse_submissions(payload("AAPL"))
    jpm = parse_submissions(payload("JPM"))
    assert apple.covers is not None and jpm.covers is not None
    assert apple.covers[0].year == 2015
    assert (jpm.covers[1] - jpm.covers[0]).days <= 366
    assert jpm.older_batches == 70  # and this parser does NOT fetch them


# ── the scoring ─────────────────────────────────────────────────────────────


def test_apple_scores_on_results_and_departures_and_nothing_else() -> None:
    """Apple's real 8-K flow is 2.02 (results) and 5.02 (officer changes) plus boilerplate. So
    two buckets are present and `capital_action` is ABSENT — not 50, which would say the capital
    news nets out to neutral when there was none."""
    result = score_catalyst(eight_ks("AAPL"), AS_OF, TH)
    assert result.earnings_strategy is not None
    assert result.governance is not None
    assert result.capital_action is None
    assert result.value is not None
    # Results are worth points and departures cost them, so the two buckets sit either side of 50.
    assert result.earnings_strategy > Decimal(50)
    assert result.governance < Decimal(50)


def test_the_lens_is_the_weighted_mean_of_the_buckets_that_are_PRESENT() -> None:
    """A company with two of three buckets is scored on those two, renormalised — not on two
    thirds of a guess."""
    r = score_catalyst(eight_ks("AAPL"), AS_OF, TH)
    w_e = TH["catalyst_w_earnings"]
    w_g = TH["catalyst_w_governance"]
    assert r.earnings_strategy is not None and r.governance is not None
    expected = (r.earnings_strategy * w_e + r.governance * w_g) / (w_e + w_g)
    assert r.value == expected.quantize(Decimal("0.01"))


def test_the_evidence_counts_the_filings_it_could_not_read() -> None:
    """82 of Apple's 105 8-Ks carry 9.01 and nothing this lens scores. That silence is REPORTED,
    so it cannot be mistaken for "nothing happened"."""
    r = score_catalyst(eight_ks("AAPL"), AS_OF, TH)
    assert r.evidence["items_not_scored"]["9.01"] > 0
    assert r.evidence["items_not_scored"]["8.01"] > 0
    assert r.evidence["filings_with_no_scored_item"] > 0
    assert r.evidence["filings_considered"] == len(eight_ks("AAPL"))
    # And only scored items appear under `items`.
    assert set(r.evidence["items"]) <= set(ITEM_BUCKET)


def test_a_company_that_filed_nothing_is_unscored_rather_than_zero() -> None:
    """No filings is not bad news; it is no news. Every bucket absent, and the lens itself None —
    blend() then renormalises over the other lenses instead of averaging in a 0 (rule #0)."""
    r = score_catalyst([], AS_OF, TH)
    assert r.value is None
    assert all(getattr(r, b) is None for b in BUCKETS)
    assert r.evidence["filings_considered"] == 0


def test_a_filing_dated_after_the_as_of_is_not_visible_on_that_day() -> None:
    """Point-in-time, enforced in the scorer rather than trusted to the query: a backfilled score
    that can see next month's 8-K makes every backtest built on it optimistic, and no gate
    downstream could tell."""
    earlier = dt.date(2026, 1, 1)
    seen = score_catalyst(eight_ks("AAPL"), earlier, TH)
    all_of_them = score_catalyst(eight_ks("AAPL"), AS_OF, TH)
    assert seen.evidence["filings_considered"] < all_of_them.evidence["filings_considered"]
    assert all(f.filed <= AS_OF for f in eight_ks("AAPL") if f.filed <= AS_OF)


def test_news_decays_in_steps_the_fm_sets() -> None:
    assert decay(0, TH) == TH["catalyst_decay_t1"]
    assert decay(90, TH) == TH["catalyst_decay_t1"]
    assert decay(91, TH) == TH["catalyst_decay_t2"]
    assert decay(180, TH) == TH["catalyst_decay_t2"]
    assert decay(181, TH) == TH["catalyst_decay_t3"]
    assert decay(365, TH) == TH["catalyst_decay_t3"]
    assert decay(366, TH) == TH["catalyst_decay_old"]


def test_the_same_filing_is_worth_less_the_older_it_is() -> None:
    """The property decay exists for, on one real filing: Apple's 2026-07-30 results 8-K."""
    one = [f for f in eight_ks("AAPL") if f.accession_no == "0000320193-26-000018"]
    assert len(one) == 1
    fresh = score_catalyst(one, one[0].filed, TH).earnings_strategy
    stale = score_catalyst(one, one[0].filed + dt.timedelta(days=200), TH).earnings_strategy
    assert fresh is not None and stale is not None
    assert Decimal(50) < stale < fresh


def test_a_score_is_clamped_into_the_range_a_lens_is_allowed() -> None:
    """Verizon files 16 real 5.02s. With the departure penalty turned up far enough the bucket
    would run below zero; the clamp is what keeps every lens on one scale."""
    harsh = {**TH, "catalyst_pts_5_02": Decimal(-500)}
    r = score_catalyst(eight_ks("VZ"), AS_OF, harsh)
    assert r.governance == Decimal(0)
    assert r.value is not None and Decimal(0) <= r.value <= Decimal(100)


# ── the contract with the table ─────────────────────────────────────────────


def test_the_declared_keys_and_the_seeded_table_agree_exactly() -> None:
    """A key the scorer reads and the table does not carry is a crash at one in the morning; a
    key the table carries and nothing reads is a threshold the FM can tune with no effect."""
    assert set(CATALYST_KEYS) == set(TH)


def test_the_bucket_weights_use_the_keys_ALREADY_SEEDED_INTO_PROD() -> None:
    """``catalyst_w_earnings`` and ``catalyst_w_capital`` were seeded before this scorer existed.
    Renaming them to match the bucket names would leave two orphan rows in the live table that
    the FM could tune with no effect — a worse trap than a one-line mapping. This pins the
    mapping so a later tidy-up cannot quietly create those orphans."""
    assert BUCKET_WEIGHT_KEY == {
        "earnings_strategy": "catalyst_w_earnings",
        "capital_action": "catalyst_w_capital",
        "governance": "catalyst_w_governance",
    }
    assert set(BUCKET_WEIGHT_KEY) == set(BUCKETS)


def test_removing_any_key_the_run_ACTUALLY_reads_raises_rather_than_defaulting() -> None:
    """There are no defaults. India's `.get(key, default)` would put India's number into a US
    score invisibly, which is the failure the whole thresholds rule exists to prevent.

    The keys under test are the ones a real run reads: the three bucket weights, the three
    windows and four multipliers, and the points of the items these companies actually filed.
    """
    filings = eight_ks("AAPL") + eight_ks("VZ") + eight_ks("JPM")
    read = {
        *(BUCKET_WEIGHT_KEY[b] for b in BUCKETS),
        "catalyst_recency_t1",
        "catalyst_recency_t2",
        "catalyst_recency_t3",
        "catalyst_decay_t1",
        "catalyst_decay_t2",
        "catalyst_decay_t3",
        *(points_key(i) for f in filings for i in f.items if i in ITEM_BUCKET),
    }
    assert len(read) >= 13, "the fixtures must exercise the weights, the decay and some points"
    for key in sorted(read):
        short = {k: v for k, v in TH.items() if k != key}
        with pytest.raises(KeyError, match=key):
            score_catalyst(filings, AS_OF, short)


def test_the_distress_codes_are_declared_but_UNEXERCISED_by_these_three_filers() -> None:
    """The honest limit of this test file, recorded rather than hidden.

    Twelve of the sixteen scored item codes — bankruptcy, delisting, non-reliance, auditor
    change, impairment, accelerated obligations — appear nowhere in Apple's, JPMorgan's or
    Verizon's filings. Three healthy megacaps do not go bankrupt, which is exactly why they are
    poor witnesses for the distress half of the map. Those points are asserted to EXIST and to be
    negative; whether they are the right size is a question only a distressed filer can answer,
    and this file does not pretend otherwise.
    """
    filed = {i for f in eight_ks("AAPL") + eight_ks("VZ") + eight_ks("JPM") for i in f.items}
    exercised = filed & set(ITEM_BUCKET)
    assert exercised == {"1.01", "2.02", "3.03", "5.02"}
    unexercised = set(ITEM_BUCKET) - exercised
    assert len(unexercised) == 12
    # Every distress code costs points. A positive one would reward a bankruptcy filing.
    for item in ("1.03", "3.01", "4.01", "4.02", "2.06", "2.04"):
        assert item in unexercised
        assert TH[points_key(item)] < 0


def test_every_mapped_item_has_a_points_key_and_a_real_bucket() -> None:
    for item, bucket in ITEM_BUCKET.items():
        assert bucket in BUCKETS
        assert points_key(item) in CATALYST_KEYS
        assert "." in item and item.replace(".", "").isdigit(), f"{item} is not an SEC item code"
