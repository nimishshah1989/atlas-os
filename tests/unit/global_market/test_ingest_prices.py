"""``ingest_prices.py`` and the Alpaca action adapter, on REAL vendor records (rule #0).

No fixtures. Every frame these tests reason about is fetched live from the vendor, so the
assertions below are statements about the market, not about something this repo made up.
That has a cost — without ``ALPACA_API_KEY`` the module skips rather than passing vacuously,
which is the same trade ``test_fred_provider.py`` makes for the FRED JSON API. Committing a
cached copy instead is deliberately NOT done: the repo is public and the vendor's terms on
redistributing its data are, as of 2026-09-07, still unverified (`docs/global/data-sources.md`).

The events chosen are ones whose answer is known independently of any code here:

* **AAPL's 2020-08-31 forward split, 4:1.** The raw close falls about three quarters and the
  split-adjusted series does not. This is the check that a technicals basis is genuinely
  split-adjusted; run on raw closes, that day is a −74 % "return".
* **GE's 2021-08-02 reverse split, 1-for-8.** The same test in the OTHER direction, which is
  the one an inverted ratio passes and a correct one fails. Raw octuples; adjusted does not.
* **GE's 2021-06-25 $0.01 dividend, which the vendor returns TWICE** with different record
  ids. It is why :func:`action_rows` exists in the shape it does.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterable
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import pandas as pd
import pytest

from atlas.global_market.providers.alpaca import AlpacaProvider
from atlas.global_market.providers.base import ACTION_COLUMNS

from .script_loader import load_global_script

pytestmark = pytest.mark.unit

HAVE_KEYS = bool(
    os.environ.get("ALPACA_API_KEY", "").strip() and os.environ.get("ALPACA_API_SECRET", "").strip()
)
needs_keys = pytest.mark.skipif(
    not HAVE_KEYS, reason="ALPACA_API_KEY/SECRET not set — live vendor tests skipped"
)

prices = load_global_script("ingest_prices")

# The vendor publishes adjusted closes rounded to the CENT, so a split tie holds at that
# scale and not below it (AAPL: 499.23 / 4 = 124.8075, printed 124.81). Asserting exact
# equality would be asserting more precision than the feed carries.
CENT = Decimal("0.01")


def ids_for(symbols: Iterable[object]) -> dict[str, str]:
    """A distinct instrument id per symbol.

    Mapping every symbol to ONE id would manufacture collisions the real table cannot
    have — three issuers paying a dividend on the same ex-date would land on one key —
    and the duplicate-handling tests would then be testing the fixture, not the code.
    """
    return {str(s): str(uuid5(NAMESPACE_URL, f"test:{s}")) for s in symbols}


# The two splits, and the window around each that shows them.
AAPL_SPLIT = dt.date(2020, 8, 31)
GE_REVERSE = dt.date(2021, 8, 2)


@pytest.fixture(scope="module")
def provider() -> AlpacaProvider:
    return AlpacaProvider()


@pytest.fixture(scope="module")
def split_bars(provider: AlpacaProvider) -> dict[str, pd.DataFrame]:
    """Real bars on all three bases across both split dates."""
    return {
        b: provider.bars(["AAPL", "GE", "SPY"], dt.date(2020, 8, 26), GE_REVERSE, adjustment=b)
        for b in prices.BASES
    }


@pytest.fixture(scope="module")
def real_actions(provider: AlpacaProvider) -> pd.DataFrame:
    return provider.actions(["SPY", "AAPL", "GE"], dt.date(2016, 1, 4), dt.date(2026, 9, 6))


@needs_keys
def test_merge_keeps_one_row_per_symbol_and_session(split_bars: dict[str, pd.DataFrame]) -> None:
    """The three bases merge WITHOUT fanning out.

    A left join on a key the right side duplicates silently multiplies rows, and the symptom
    surfaces far away — as a duplicate-key failure in the upsert, or worse, as a doubled
    volume in the liquidity floor. Assert the shape, not just the absence of an exception.
    """
    merged = prices.merge_bases(split_bars)
    assert len(merged) == len(split_bars["raw"])
    assert not merged.duplicated(["symbol", "date"]).any()
    assert merged["close_adj"].notna().all()
    assert merged["close_tr"].notna().all()


@needs_keys
def test_a_forward_split_moves_raw_and_not_the_adjusted_basis(
    split_bars: dict[str, pd.DataFrame],
) -> None:
    """AAPL 4:1 on 2020-08-31: raw quarters, split-adjusted carries the real move.

    The precise tie is the point — the previous session's raw close divided by the split
    ratio must equal its split-adjusted close AT THE CENT, the scale the vendor publishes.
    A band would pass on a nearby wrong ratio; this does not.
    """
    merged = prices.merge_bases(split_bars)
    aapl = merged[merged["symbol"] == "AAPL"].sort_values("date").reset_index(drop=True)
    before = aapl[aapl["date"] < AAPL_SPLIT].iloc[-1]
    after = aapl[aapl["date"] == AAPL_SPLIT].iloc[0]

    assert (before["close"] / Decimal(4)).quantize(CENT) == before["close_adj"]
    raw_move = after["close"] / before["close"] - 1
    adj_move = after["close_adj"] / before["close_adj"] - 1
    assert raw_move < Decimal("-0.7")  # the artefact: about −74 %
    assert abs(adj_move) < Decimal("0.1")  # the real move, a few per cent


@needs_keys
def test_a_reverse_split_moves_raw_the_other_way(split_bars: dict[str, pd.DataFrame]) -> None:
    """GE 1-for-8 on 2021-08-02 — the direction an inverted ratio gets wrong.

    A sign or reciprocal error that survives the forward-split test above fails here, which
    is the entire reason both directions are tested rather than one.
    """
    merged = prices.merge_bases(split_bars)
    ge = merged[merged["symbol"] == "GE"].sort_values("date").reset_index(drop=True)
    before = ge[ge["date"] < GE_REVERSE].iloc[-1]
    after = ge[ge["date"] == GE_REVERSE].iloc[0]

    assert (before["close"] * Decimal(8)).quantize(CENT) == before["close_adj"]
    assert after["close"] / before["close"] - 1 > Decimal(6)  # about +677 %
    assert abs(after["close_adj"] / before["close_adj"] - 1) < Decimal("0.1")


@needs_keys
def test_split_ratios_read_the_same_way_in_both_directions(real_actions: pd.DataFrame) -> None:
    """``ratio`` is new-shares-per-old, so 4:1 is 4 and 1-for-8 is 0.125 — one column, one
    reading, no per-type sign convention for a caller to get wrong."""
    assert list(real_actions.columns) == list(ACTION_COLUMNS)
    splits = pd.DataFrame(real_actions[real_actions["ratio"].notna()])
    by_key = {(r["symbol"], r["ex_date"]): r for r in splits.to_dict("records")}
    assert by_key[("AAPL", AAPL_SPLIT)]["ratio"] == Decimal(4)
    assert by_key[("AAPL", AAPL_SPLIT)]["action_type"] == "forward_split"
    assert by_key[("GE", GE_REVERSE)]["ratio"] == Decimal("0.125")
    assert by_key[("GE", GE_REVERSE)]["action_type"] == "reverse_split"


@needs_keys
def test_cash_and_share_events_never_share_a_column(real_actions: pd.DataFrame) -> None:
    """A dividend fills ``cash_amount`` and a split fills ``ratio``, never both and never the
    other one. The vendor names both fields ``rate``, so an adapter that keyed on the field
    instead of the event type would land share counts in a dollars column."""
    cash = pd.DataFrame(real_actions[real_actions["action_type"] == "cash_dividend"])
    share = pd.DataFrame(real_actions[real_actions["action_type"].str.endswith("_split")])
    assert len(cash) and len(share)
    assert bool(cash["ratio"].isna().all())
    assert bool(cash["cash_amount"].notna().all())
    assert bool(share["cash_amount"].isna().all())
    assert bool(share["ratio"].notna().all())


@needs_keys
def test_the_vendor_repeats_an_event_and_the_duplicate_collapses(
    real_actions: pd.DataFrame,
) -> None:
    """GE's 2021-06-25 $0.01 dividend comes back twice, identical but for its record id.

    ``corporate_actions`` is keyed (instrument_id, ex_date, action_type), so Postgres refuses
    both inside one statement. Identical records collapse to one — there is no number to
    choose between — and the run proceeds instead of dying.
    """
    dupes = real_actions[real_actions.duplicated(["symbol", "ex_date", "action_type"], keep=False)]
    assert len(dupes) >= 2, "the vendor no longer repeats this event — the guard may be stale"

    ids = ids_for(real_actions["symbol"].unique())
    rows, conflicts = prices.action_rows(real_actions, ids)
    keys = [(r[0], r[1], r[2]) for r in rows]
    assert len(keys) == len(set(keys)), "an upsert batch may not repeat a conflict key"
    assert not conflicts, "these duplicates agree on every value, so none is a conflict"
    assert len(rows) < len(real_actions)


@needs_keys
def test_records_that_disagree_are_withheld_rather_than_guessed(
    real_actions: pd.DataFrame,
) -> None:
    """Two records on one key that disagree on VALUE are written NOWHERE and reported.

    Built by perturbing one real record's amount: picking either, or adding them up, would be
    a number the feed never stated. This is the rule #0 branch of :func:`action_rows`, and it
    is the one that has never fired in production — so it is tested here instead.
    """
    cash = real_actions[real_actions["action_type"] == "cash_dividend"].iloc[0]
    clash = cash.copy()
    clash["cash_amount"] = cash["cash_amount"] + Decimal("0.01")
    frame = pd.concat([real_actions, pd.DataFrame([clash])], ignore_index=True)

    ids = ids_for(frame["symbol"].unique())
    rows, conflicts = prices.action_rows(frame, ids)
    assert len(conflicts) == 1
    (_, ex_date, kind), values = conflicts[0]
    assert ex_date == cash["ex_date"]
    assert kind == cash["action_type"]
    # BOTH amounts are reported: naming one of two numbers cannot be acted on.
    assert sorted(values) == sorted([cash["cash_amount"], clash["cash_amount"]])
    written = {(r[1], r[2]) for r in rows}
    assert (cash["ex_date"], cash["action_type"]) not in written


@needs_keys
def test_impossible_bars_are_refused(split_bars: dict[str, pd.DataFrame]) -> None:
    """Real bars are all valid; a high pushed below its low is refused.

    The mutation is applied to a REAL row rather than a constructed one, so the test proves
    the predicate reads the columns the vendor actually fills.
    """
    merged = prices.merge_bases(split_bars)
    assert prices.invalid_bars(merged).empty

    broken = merged.copy()
    broken.loc[broken.index[0], "high"] = broken.loc[broken.index[0], "low"] - Decimal(1)
    assert len(prices.invalid_bars(broken)) == 1


def test_a_rebasing_instrument_is_pulled_from_the_floor_not_its_watermark() -> None:
    """The rule that keeps a history off two different bases.

    An instrument with a corporate action in the window is re-pulled from the history floor
    even though its watermark is recent; one without takes the short window. Dates and set
    membership only — no market data, so this runs everywhere.
    """
    since = prices.HISTORY_START
    recent = dt.date(2026, 9, 1)
    watermarks = {"AAPL": recent, "SPY": recent}

    assert prices.window_for("AAPL", watermarks, since, {"AAPL"}) == since
    assert prices.window_for("SPY", watermarks, since, {"AAPL"}) > since
    # A name with no bars at all starts at the floor whether or not it re-based.
    assert prices.window_for("NEW", watermarks, since, set()) == since

    groups = prices.by_start(["AAPL", "SPY", "NEW"], watermarks, since, {"AAPL"})
    assert sorted(groups[since]) == ["AAPL", "NEW"]
    assert groups[max(groups)] == ["SPY"]


def test_an_empty_action_list_does_not_rebase_anything() -> None:
    """A quiet night is the normal case, not a reason to rewrite every history.

    Conflating "no events" with "events unknown" would turn each nightly run into a full
    re-backfill of thousands of instruments; the unknown case is handled by the caller, which
    re-bases everything only when the FETCH failed.
    """
    empty = pd.DataFrame(columns=pd.Index(ACTION_COLUMNS))
    assert prices.rebasing_targets(empty, {}, prices.HISTORY_START) == set()


def test_only_actions_newer_than_an_instruments_own_rows_force_a_rewrite() -> None:
    """The per-instrument question, and the reason it is not "anything since 2016".

    An instrument re-bases when an action goes ex AFTER the last date already stored for it,
    because everything stored is then on a base the vendor has moved. An action older than
    every row held changes nothing. Comparing against the history floor instead marks every
    dividend payer on every run — a full ten-year backfill of the universe, nightly.
    """
    old_event = dt.date(2016, 3, 18)
    new_event = dt.date(2026, 9, 3)
    frame = pd.DataFrame(
        [
            ("AAPL", old_event, "cash_dividend", None, Decimal("0.52")),
            ("SPY", new_event, "cash_dividend", None, Decimal("1.90")),
        ],
        columns=pd.Index(ACTION_COLUMNS),
    )
    caught_up = {"AAPL": dt.date(2026, 9, 4), "SPY": dt.date(2026, 9, 4)}

    # SPY's dividend is inside its re-pull buffer; AAPL's is a decade behind its rows.
    assert prices.rebasing_targets(frame, caught_up, prices.HISTORY_START) == {"SPY"}

    # With no rows at all, an instrument is pulled from the floor regardless.
    assert prices.rebasing_targets(frame, {}, prices.HISTORY_START) == {"AAPL", "SPY"}
