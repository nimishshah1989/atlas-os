"""``mark_baskets``' pure accounting — sizing, cash, the total-return mark, and ``replay``
driven as a marker — on the two real SPY closes this repository records verbatim.

Rule #0 leaves no room for an invented price, and there is no OHLCV fixture under
``tests/fixtures/global`` (DTB3 is a yield, the symbology files carry no bars). So every price
below is one of the two Stooq-archive endpoints ``validate_global.py``'s BASIS block records
from its 2026-09-07 measurement and ``test_basis_gate.py`` reuses: SPY closed at **189.162 on
2016-09-06** and **773.17 on 2026-09-03**. Both are archive rows, which carry ``close_tr``
alone (``01_prices.sql``), and that is how they are keyed here. Capital, weights and the cost
rate are read from ``seed_thresholds.SEEDS`` — the FM's inputs, never restated. Instrument
keys are labels for the arithmetic, not names; the calendar dates are calendar facts.

Pure: no DB, no network. The script is loaded by path (``script_loader``).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from tests.unit.global_market.script_loader import LABOR_DAY_WEEK, load_global_script

mb = load_global_script("mark_baskets")
seeds = load_global_script("seed_thresholds")

pytestmark = pytest.mark.unit

ENTRY_DATE, ENTRY_CLOSE = dt.date(2016, 9, 6), Decimal("189.162")
LAST_DATE, LAST_CLOSE = dt.date(2026, 9, 3), Decimal("773.17")
# Plain trading weekdays after Labor Day week — calendar facts (no US holiday falls on them).
SESSIONS_AFTER = [dt.date(2026, 9, d) for d in (9, 10, 11, 14, 15)]

TH = {
    str(r["threshold_key"]): Decimal(str(r["threshold_value"]))
    for r in seeds.SEEDS
    if r["category"] == "basket"
}
CAPITAL = TH["basket_default_capital_usd"]
CAP = TH["basket_max_position_pct"]
FLOOR = TH["basket_min_weight_frac"]
BUY_RATE = mb.rate_from_bps(TH["basket_cost_bps_buy"])

A, B = "a", "b"  # instrument labels


def archive_bar(close_tr: Decimal) -> tuple[None, Decimal]:
    """A Stooq-archive row: close_tr only, close_adj NULL (01_prices.sql)."""
    return None, close_tr


def fill(instrument: str, trade_date: dt.date, price: Decimal, weight: Decimal):
    qty, value, cost = mb.size_fill(CAPITAL, weight, price, BUY_RATE)
    return mb.Fill(
        instrument_id=instrument,
        symbol=instrument.upper(),
        asset_class="etf",
        trade_date=trade_date,
        price=price,
        price_basis="close_tr",
        weight=weight,
        qty=qty,
        value=value,
        cost=cost,
    )


# ── sizing ──


def test_the_seed_rows_this_test_reads_are_the_five_m2_keys() -> None:
    assert set(TH) == set(load_global_script("basket_data").THRESHOLD_KEYS)


def test_size_fill_at_the_real_close_rounds_down_to_the_quantum_and_never_over_allocates() -> None:
    qty, value, cost = mb.size_fill(CAPITAL, CAP, LAST_CLOSE, BUY_RATE)
    target = CAPITAL * CAP
    assert qty == (target / (1 + BUY_RATE) / LAST_CLOSE).quantize(
        mb.QTY_QUANTUM, rounding=mb.ROUND_DOWN
    )
    assert qty == qty.quantize(mb.QTY_QUANTUM)  # six decimals, the column's quantum
    assert value == (qty * LAST_CLOSE).quantize(mb.MONEY)
    assert cost == (value * BUY_RATE).quantize(mb.MONEY)
    # never a cent over the weight; short of it by at most one quantum of a share plus the
    # cent the value was rounded to (and the cost reserve, zero at the seeded rate)
    assert value + cost <= target
    assert target - (value + cost) <= LAST_CLOSE * mb.QTY_QUANTUM + mb.MONEY


def test_inception_leaves_only_the_rounding_residue_in_cash() -> None:
    weight = Decimal(1) / 4
    fills = [
        fill(A, LAST_DATE, LAST_CLOSE, weight),
        fill(B, LAST_DATE, LAST_CLOSE, weight),
        fill("c", ENTRY_DATE, ENTRY_CLOSE, weight),
        fill("d", ENTRY_DATE, ENTRY_CLOSE, weight),
    ]
    cash = mb.cash_after(CAPITAL, fills)
    assert cash == (CAPITAL - sum(f.value + f.cost for f in fills)).quantize(mb.MONEY)
    assert cash >= 0
    assert cash <= sum(f.price * mb.QTY_QUANTUM + mb.MONEY for f in fills)


# ── the constituent rules ──


def test_check_constituents_names_every_violation_and_passes_a_clean_set() -> None:
    import pandas as pd

    clean = pd.DataFrame(
        [
            {"symbol": "SPY", "is_active": True, "target_weight_frac": CAP},
            {"symbol": "QQQ", "is_active": True, "target_weight_frac": CAP},
            {"symbol": "IWM", "is_active": True, "target_weight_frac": CAP},
            {"symbol": "AGG", "is_active": True, "target_weight_frac": CAP},
        ]
    )
    assert mb.check_constituents(clean, TH) == []
    bad = pd.DataFrame(
        [
            {"symbol": "SPY", "is_active": False, "target_weight_frac": CAP + FLOOR},
            {"symbol": "QQQ", "is_active": True, "target_weight_frac": FLOOR / 2},
        ]
    )
    problems = mb.check_constituents(bad, TH)
    assert any("SPY: instrument is not active" in p for p in problems)
    assert any("SPY: weight" in p and "exceeds basket_max_position_pct" in p for p in problems)
    assert any("QQQ: weight" in p and "below basket_min_weight_frac" in p for p in problems)
    assert any(p.startswith("weights sum to") for p in problems)
    assert mb.check_constituents(clean.iloc[0:0], TH) == ["no constituents for the current version"]


# ── the last print, within the look-back window ──


def test_last_print_looks_back_at_most_the_window_and_prefers_close_adj() -> None:
    cal = LABOR_DAY_WEEK + SESSIONS_AFTER
    keyed = {(A, LAST_DATE): archive_bar(LAST_CLOSE)}
    assert mb.last_print(keyed, A, cal, LAST_DATE) == (LAST_DATE, LAST_CLOSE, "close_tr")
    # 09-08 is four sessions on: inside INCEPTION_LOOKBACK_SESSIONS, so the 09-03 print fills
    assert mb.last_print(keyed, A, cal, dt.date(2026, 9, 8)) == (LAST_DATE, LAST_CLOSE, "close_tr")
    # 09-15 is nine sessions on: outside the window, so there is no print to book at
    assert mb.last_print(keyed, A, cal, dt.date(2026, 9, 15)) is None
    # a bar with neither series is not a print
    assert mb.last_print({(A, LAST_DATE): (None, None)}, A, cal, LAST_DATE) is None


# ── the mark: total return since entry, invariant to re-basing ──


def test_mark_grows_the_fill_by_total_return_and_ignores_a_rebasing_of_both_ends() -> None:
    f = fill(A, ENTRY_DATE, ENTRY_CLOSE, CAP)
    keyed = {(A, ENTRY_DATE): archive_bar(ENTRY_CLOSE), (A, LAST_DATE): archive_bar(LAST_CLOSE)}
    panel, fallback = mb.mark_panel([f], keyed, [ENTRY_DATE, LAST_DATE])
    assert fallback == []
    assert panel.at[ENTRY_DATE, A] == ENTRY_CLOSE  # on its own trade date the mark IS the fill
    assert panel.at[LAST_DATE, A] == LAST_CLOSE  # ten years on, the measured growth
    growth = panel.at[LAST_DATE, A] / panel.at[ENTRY_DATE, A]
    assert growth == LAST_CLOSE / ENTRY_CLOSE

    # An ex-date re-bases every EARLIER bar by one factor (ingest_prices, "the re-basing rule").
    # Both ends of the ratio move together, so the mark does not — while a fixed quantity
    # against the level alone would have lost exactly that factor. Half is an arbitrary
    # factor for the identity, not a dividend.
    factor = Decimal("0.5")
    rebased = {k: (None, v[1] * factor) for k, v in keyed.items()}
    again, _ = mb.mark_panel([f], rebased, [ENTRY_DATE, LAST_DATE])
    assert again.at[LAST_DATE, A] == panel.at[LAST_DATE, A]
    assert f.qty * (LAST_CLOSE * factor) != f.qty * LAST_CLOSE


def test_the_close_adj_fallback_is_used_only_without_close_tr_and_is_reported() -> None:
    """The column shape under test, with the real value: an entry row carrying close_adj and
    no close_tr cannot be marked on total return, so the split-only series stands in and every
    such session is returned as evidence."""
    f = fill(A, ENTRY_DATE, ENTRY_CLOSE, CAP)
    keyed = {(A, ENTRY_DATE): (ENTRY_CLOSE, None), (A, LAST_DATE): (LAST_CLOSE, None)}
    panel, fallback = mb.mark_panel([f], keyed, [ENTRY_DATE, LAST_DATE])
    assert panel.at[LAST_DATE, A] == LAST_CLOSE
    assert fallback == [(A.upper(), ENTRY_DATE), (A.upper(), LAST_DATE)]
    with pytest.raises(mb.RefusedError, match="no bar on its own trade date"):
        mb.mark_panel([f], {(A, LAST_DATE): archive_bar(LAST_CLOSE)}, [LAST_DATE])


# ── replay as a pure marker ──


def test_replay_marks_the_book_carries_a_missing_print_forward_and_books_nothing() -> None:
    fa = fill(A, ENTRY_DATE, ENTRY_CLOSE, CAP)
    fb = fill(B, ENTRY_DATE, ENTRY_CLOSE, CAP)
    keyed = {
        (A, ENTRY_DATE): archive_bar(ENTRY_CLOSE),
        (A, LAST_DATE): archive_bar(LAST_CLOSE),
        (B, ENTRY_DATE): archive_bar(ENTRY_CLOSE),  # B never prints again: held at its last close
    }
    sessions = [ENTRY_DATE, LAST_DATE]
    panel, _ = mb.mark_panel([fa, fb], keyed, sessions)
    cash = mb.cash_after(CAPITAL, [fa, fb])
    navs = mb.replay_navs("basket", CAPITAL, CAP, panel, [fa, fb], cash, sessions)
    assert [d for d in navs["date"]] == sessions
    assert list(navs["n_positions"]) == [2, 2]
    first, last = navs.iloc[0], navs.iloc[-1]
    # the NAV identity, both sessions: cash + Σ qty × mark, to the cent
    assert first["cash"] == cash and last["cash"] == cash
    assert first["invested"] == (fa.qty * ENTRY_CLOSE + fb.qty * ENTRY_CLOSE).quantize(mb.MONEY)
    assert last["invested"] == (fa.qty * LAST_CLOSE + fb.qty * ENTRY_CLOSE).quantize(mb.MONEY)
    assert last["nav"] == (cash + last["invested"]).quantize(mb.MONEY)
    # day one: capital, less nothing but the cent-rounding of two fills
    assert abs(first["nav"] - CAPITAL) <= 2 * mb.MONEY


def test_run_id_is_the_same_for_the_same_basket_run_and_anchor() -> None:
    rid = mb.run_id("basket", "live", LAST_DATE)
    assert rid == mb.run_id("basket", "live", LAST_DATE)
    assert rid != mb.run_id("basket", "live", ENTRY_DATE)
    assert rid != mb.run_id("other", "live", LAST_DATE)
    assert rid != mb.run_id("basket", "backtest", LAST_DATE)
