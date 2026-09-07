# ruff: noqa: S608 -- SQL here is assembled from the schema constant _gdb.M; every value is bound.
"""``ingest_prices.py``'s WRITTEN rows (rule #0): what landed in Postgres, not what a pure
function returned.

Needs ``ATLAS_DB_URL`` pointing at a Postgres carrying the atlas_global DDL with real
``ohlcv_daily`` rows that ``ingest_prices.py`` has already written, and identity rows from
``build_identity.py``. Unset, the module skips; it never passes vacuously. Nothing here
writes.

The unit suite proves the merge and the action mapping in memory. It cannot see the half of
this chunk that only exists once rows cross into ``numeric(18,6)`` columns through an upsert
with fourteen value slots: a column list off by one puts every price one column left, which
no in-memory test notices and every chart does. So these assertions deliberately re-derive
their expected values from something OTHER than the writer's own path — a known corporate
action, or another column of the same row.
"""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration

pytest.importorskip("psycopg2")

if not os.environ.get("ATLAS_DB_URL", "").strip():
    pytest.skip("ATLAS_DB_URL not set — the prices DB suite is skipped", allow_module_level=True)

from tests.unit.global_market.script_loader import load_global_script  # noqa: E402

_gdb = load_global_script("_gdb")

M = _gdb.M
CENT = Decimal("0.01")

# Two splits in opposite directions, and the ratio each applies to prices BEFORE its ex-date.
# Public corporate history, not market data: AAPL split 4:1 on 2020-08-31, GE 1-for-8 on
# 2021-08-02. The expected adjusted close is therefore raw x ratio, computed here rather than
# read from anything ingest_prices produced.
SPLITS = [
    ("AAPL", dt.date(2020, 8, 31), Decimal("0.25")),
    ("GE", dt.date(2021, 8, 2), Decimal("8")),
]

BARS_SQL = f"""
SELECT o.date, o.close, o.close_adj, o.close_tr, o.open, o.high, o.low, o.volume
FROM {M}.ohlcv_daily o JOIN {M}.instrument_master im USING (instrument_id)
WHERE im.symbol = %(symbol)s AND o.source = 'alpaca'
  AND o.date BETWEEN %(start)s AND %(end)s
ORDER BY o.date
"""


def rows(sql: str, params: dict[str, object]) -> list[tuple]:
    import psycopg2

    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def have(symbol: str) -> bool:
    got = rows(
        f"SELECT count(*) FROM {M}.ohlcv_daily o JOIN {M}.instrument_master im USING "
        f"(instrument_id) WHERE im.symbol = %(symbol)s AND o.source = 'alpaca'",
        {"symbol": symbol},
    )
    return bool(got and got[0][0])


@pytest.mark.parametrize(("symbol", "ex_date", "ratio"), SPLITS)
def test_the_split_only_basis_absorbs_a_split_and_the_raw_basis_does_not(
    symbol: str, ex_date: dt.date, ratio: Decimal
) -> None:
    """The session before an ex-date: ``close_adj`` == ``close`` x ratio, to the cent.

    The ratio comes from public corporate history, so this compares the stored row against
    the outside world rather than against another thing this repo computed. It fails if the
    two bases were ever swapped, if the split pull was silently served the raw one, or if the
    upsert's column list shifted.
    """
    if not have(symbol):
        pytest.skip(f"no vendor bars for {symbol} in this database")
    got = rows(
        BARS_SQL,
        {"symbol": symbol, "start": ex_date - dt.timedelta(days=7), "end": ex_date},
    )
    before = [r for r in got if r[0] < ex_date]
    assert before, f"no session before {ex_date} for {symbol}"
    date, close, close_adj, *_ = before[-1]
    assert (close * ratio).quantize(CENT) == close_adj.quantize(CENT), (
        f"{symbol} {date}: raw {close} x {ratio} != stored close_adj {close_adj}"
    )


@pytest.mark.parametrize(("symbol", "ex_date", "ratio"), SPLITS)
def test_a_split_is_invisible_in_the_adjusted_return_and_glaring_in_the_raw_one(
    symbol: str, ex_date: dt.date, ratio: Decimal
) -> None:
    """The reason two bases exist at all.

    On its ex-date a split moves the raw close by roughly the ratio and leaves the adjusted
    one carrying only the day's real trading. An EMA or a 52-week high computed on the raw
    column would take that artefact as a price move; ``max_abs_log_jump < 0.4``, the gate-A
    detector, is looking for exactly this.
    """
    if not have(symbol):
        pytest.skip(f"no vendor bars for {symbol} in this database")
    got = rows(
        BARS_SQL,
        {"symbol": symbol, "start": ex_date - dt.timedelta(days=7), "end": ex_date},
    )
    before = [r for r in got if r[0] < ex_date][-1]
    on = next(r for r in got if r[0] == ex_date)

    raw_move = on[1] / before[1] - 1
    adj_move = on[2] / before[2] - 1
    assert abs(raw_move) > Decimal("0.5"), f"{symbol}: raw did not jump across its split"
    assert abs(adj_move) < Decimal("0.15"), f"{symbol}: the adjusted basis carried the artefact"


def test_the_total_return_basis_is_below_the_traded_price_and_converges_to_it() -> None:
    """``close_tr`` is a dividend-back-adjusted series anchored to the present.

    So for a dividend payer it sits BELOW the traded price in the past and rises to meet it
    at the latest bar, and the ratio between them only ever climbs. A history written half on
    an old base and half on a new one puts a STEP in that ratio — the re-basing seam this
    chunk exists to prevent, and the one thing about it that nothing on the row itself says.

    The ratio is not exactly monotone, and expecting it to be would be a bug in the test:
    both columns are published to the CENT, so their ratio carries quantisation noise of
    roughly ``ratio x (half a cent / price)`` on each side — about 5e-5 for SPY near $200,
    and measured wobbling by ~4e-5. A dividend step is two orders of magnitude bigger (SPY's
    ~$1.08 on a ~$200 price is 5.4e-3), so the two are never in danger of being confused.
    The tolerance below is computed per row from the prices themselves rather than picked.
    """
    if not have("SPY"):
        pytest.skip("no vendor bars for SPY in this database")
    got = rows(
        BARS_SQL, {"symbol": "SPY", "start": dt.date(2016, 1, 4), "end": dt.date(2100, 1, 1)}
    )
    assert len(got) > 250, "too few SPY sessions to say anything about the basis"

    ratios = [(r[0], r[3] / r[1], r[1], r[3]) for r in got if r[1] and r[3]]
    assert ratios[0][1] < Decimal("0.95"), "the oldest total-return close is not below the price"
    assert ratios[-1][1] > Decimal("0.99"), "the newest total-return close has not met the price"

    half_cent = CENT / 2
    seams = []
    for (date, ratio, close, tr), (_, prev, prev_c, prev_tr) in zip(
        ratios[1:], ratios, strict=False
    ):
        if ratio >= prev:
            continue
        # What a pure rounding artefact could account for across these two sessions.
        noise = ratio * (half_cent / close + half_cent / tr) + prev * (
            half_cent / prev_c + half_cent / prev_tr
        )
        if prev - ratio > noise:
            seams.append((date, str(prev - ratio), str(noise)))
    assert not seams, f"close_tr/close falls further than rounding can explain at {seams[:3]}"


def test_every_vendor_row_says_which_pulls_produced_its_adjusted_columns() -> None:
    """Provenance is on the row, not in the operator's memory.

    A bar whose adjusted columns are filled but unlabelled is indistinguishable later from
    one the Stooq path guessed at, which is the confusion ``adjustment_source`` exists to
    prevent.
    """
    bad = rows(
        f"SELECT count(*) FROM {M}.ohlcv_daily WHERE source = 'alpaca' "
        f"AND (adjustment_source IS DISTINCT FROM 'alpaca:split+all')",
        {},
    )
    assert bad[0][0] == 0, f"{bad[0][0]} vendor bars carry the wrong adjustment_source"


def test_corporate_actions_never_mix_a_share_ratio_with_a_cash_amount() -> None:
    """One column per kind of event, as written — the vendor names both fields ``rate``."""
    mixed = rows(
        f"SELECT count(*) FROM {M}.corporate_actions "
        f"WHERE (ratio IS NOT NULL AND cash_amount IS NOT NULL) "
        f"   OR (ratio IS NULL AND cash_amount IS NULL)",
        {},
    )
    assert mixed[0][0] == 0, f"{mixed[0][0]} action rows fill both value columns or neither"

    stored = rows(
        f"SELECT im.symbol, ca.ex_date, ca.ratio FROM {M}.corporate_actions ca "
        f"JOIN {M}.instrument_master im USING (instrument_id) "
        f"WHERE ca.action_type IN ('forward_split', 'reverse_split')",
        {},
    )
    known = {(s, d): r for s, d, r in stored}
    for symbol, ex_date, ratio in SPLITS:
        if (symbol, ex_date) in known:
            # SPLITS holds the factor applied to EARLIER prices; the stored ratio is its
            # reciprocal, new shares per old. Checking that tie catches an inverted ratio.
            assert known[(symbol, ex_date)] == (Decimal(1) / ratio).normalize()
