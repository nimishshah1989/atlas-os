"""EmaCross entry-confirmation selection (crossover v2, spec §A).

The FM's buy rule and the 2026-07-22 approved rule disagree, and on real MRPL the
gap is 9.2% of entry, so neither is hardcoded — the book picks, and the 8-year
backtest decides:

  * ``entry_confirm="intraday"`` (default) — the intraday breach of P* alone opens
    the position. Earliest possible entry; buys spikes that reverse. This is the
    behaviour already merged, so it MUST stay the default.
  * ``entry_confirm="close"`` — the breach only alerts; the position opens on the
    first close that actually confirms fast > slow. Filters the reversal, and on
    MRPL cost the whole move (fill ₹172.00 instead of ₹157.47).

``entry_fill`` derives from it the way ``same_day_fill`` already derives from
``intraday`` — an explicit value always wins.
"""

from __future__ import annotations

import pytest

from atlas.portfolio.strategies import EmaCross

pytestmark = pytest.mark.unit


def test_default_entry_confirm_is_the_intraday_breach() -> None:
    # Preserves the already-merged intraday behaviour. Changing this default
    # silently re-times every entry in the 4 stock crossover books.
    assert EmaCross(13, 34, intraday=True).entry_confirm == "intraday"


def test_close_confirmation_is_selectable() -> None:
    assert EmaCross(13, 34, intraday=True, entry_confirm="close").entry_confirm == "close"


def test_unknown_entry_confirm_is_rejected() -> None:
    with pytest.raises(ValueError, match="entry_confirm"):
        EmaCross(13, 34, entry_confirm="eod")


def test_intraday_confirmation_implies_a_same_session_fill() -> None:
    # breach-alone entry is known before that close, so it fills that same close
    assert EmaCross(13, 34, intraday=True).same_day_fill is True


def test_close_confirmation_defers_the_fill_to_the_next_session() -> None:
    # the confirming close IS the signal, so filling at it would be lookahead —
    # the fill belongs to the next session's open.
    assert EmaCross(13, 34, intraday=True, entry_confirm="close").same_day_fill is False


def test_explicit_same_day_fill_still_overrides() -> None:
    s = EmaCross(13, 34, intraday=True, entry_confirm="close", same_day_fill=True)
    assert s.same_day_fill is True


# ── derived engine fill timing ─────────────────────────────────────────────
# The runner reads these off the strategy the same way it already reads
# same_day_fill, so the books stay declarative and the engine stays dumb.


def test_legacy_daily_close_book_fills_next_close_on_both_sides() -> None:
    # The 9 pre-v2 books. Any drift here re-times every one of their trades.
    s = EmaCross(13, 34)
    assert (s.entry_fill, s.exit_fill) == ("next_close", "next_close")


def test_intraday_breach_book_fills_same_close_on_both_sides() -> None:
    s = EmaCross(13, 34, intraday=True)
    assert (s.entry_fill, s.exit_fill) == ("same_close", "same_close")


def test_crossover_v2_book_buys_at_the_next_open_and_sells_at_the_same_close() -> None:
    # The FM's rule: buys wait for tomorrow's open, sells go out today because
    # tomorrow can gap down. This asymmetry is the whole point of the pair.
    s = EmaCross(13, 34, intraday=True, entry_confirm="close")
    assert (s.entry_fill, s.exit_fill) == ("next_open", "same_close")
