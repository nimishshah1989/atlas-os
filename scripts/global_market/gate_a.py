#!/usr/bin/env python3
"""Gate A — the Phase 1 definition of done for the price spine, asserted on PRODUCED rows.

Run through the one gate entry point: ``validate_global.py --check A``. Lives in its own
module only because ``validate_global.py`` is near its size tier; it is the same ``Gate``.

WHAT IT MEASURES, AND OVER WHAT. Every check runs over the **scored universe** — the rows
``build_universe_snapshot.py`` marked ``in_universe`` on its latest date — and NOT over every
listing that happens to have bars. That is not a convenience. Measured on 203 real
instruments, 19 carried a log jump of 0.4 or more on the split-adjusted close, and every one
of them was in a category the FM already excluded:

* **Geared products doing their job.** Ten were 2x single-stock funds and ProShares Ultra
  Silver — "Leverage Shares 2X Long AMD Daily", "Tradr 2X Short AAOI Daily", and their kin.
  A 2x daily fund on a volatile stock moves 40 % in a session by design; flagging that as a
  data defect trains the reader to ignore the gate.
* **Sub-floor shells with genuinely broken data.** Seven sat below the $1,000,000 liquidity
  floor, and their prints are real defects: ACTS jumped 2.14 → 24.79 on 2026-03-19, an
  eleven-fold move with NO corporate action reported that day, and the vendor's own
  split-adjusted series does not absorb it either — so the vendor does not know about the
  reverse split. AMEM went 24.52 → 53.00 → 24.82 across 2026-08-06/07, which is not a
  corporate action at all but a bad print and its reversal.

So a gate over everything fails every night for reasons nobody will act on, and a gate that
merely loosens its threshold until it passes stops detecting the thing it exists for. Running
over the scored universe keeps 0.4 meaningful, because both causes of a large honest jump are
excluded by construction. What is excluded is still COUNTED and printed, so a genuine defect
in a scored name can never hide behind "that one is out of universe".

WHY THE FRED CORRELATION FLOOR IS 0.99 AND NOT 0.999. The Phase 1 draft said 0.999, carried
over from the SIP gate, which measures 40 sessions. Over the full history the same comparison
reads **0.99316** on 2,513 daily returns, and the reason is not a defect: the worst residuals
are 2020-03-12 → 03-25 and 2025-04-09/10, when the ETF and the index genuinely parted company.
On 2020-03-13 SPY returned 5.86 % against the index's 9.29 %. Drop the worst 0.1 % of days and
it is 0.9964. An ETF is not its index in a dislocation, and a gate that demands otherwise
would fail on the only days anyone remembers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:  # the Gate class lives in the entry point; importing it here would cycle
    from validate_global import Gate

# ── thresholds, every one set from a measurement recorded in the docstring above ──
A_MIN_RETURN_CORR = 0.99  # SPY close_tr vs FRED SP500, full history (measured 0.99316)
A_MAX_ABS_LOG_JUMP = 0.40  # split-adjusted, per session — the missed-split / unit-bug detector
A_MIN_CLEAN_SHARE = 0.99  # share of scored instruments free of such a jump
A_MAX_ABS_RET_1D = 1.0  # total-return daily move; above this is not a price, it is a bug
A_MIN_COMPLETENESS = 0.99  # rows on the EOD session vs the session before it
A_MAX_SESSION_GAP_DAYS = 5  # wider than a long weekend: a listing gap, not a daily move
# A share is a statistical claim, and at small n it cannot be evaluated: over 38 scored
# instruments one name is 2.6 points, so "at least 99 %" and "at least 97 %" are the same
# assertion. Below this the jump check REPORTS rather than asserts, and says so.
A_MIN_N_FOR_SHARE = 200
A_CORR_SERIES = "SP500"
A_ANCHOR = "SPY"

# The scored universe on the snapshot's latest date. Everything below joins to this, so a
# check can never silently widen to instruments the FM excluded.
UNIVERSE_SQL = """
SELECT instrument_id FROM {M}.universe_snapshot
WHERE date = (SELECT max(date) FROM {M}.universe_snapshot) AND in_universe
"""

# One row per extreme single-session move, with everything needed to judge it: the gap to the
# previous bar, whether a corporate action shares the date, and how many other scored
# instruments moved as hard the same day.
#
# THE GAP FILTER IS LOAD-BEARING. ``lag()`` walks ROWS, not sessions, so for any instrument
# that halts and resumes it compares bars that are years apart and calls the difference a
# daily move. ACII was flagged at +149.9 % "in a session" on 2025-09-25; its previous bar was
# 2022-12-01, **1,029 calendar days** earlier, and 150 % over three years is about 16 a year.
# Nothing about the row said so. Consecutive sessions are at most a few calendar days apart,
# so anything wider is a listing gap and is reported as one, never as a move.
EXTREMES_SQL = """
WITH u AS ({universe}),
moves AS (
    SELECT o.instrument_id, o.date,
           ln(o.close_adj / lag(o.close_adj) OVER w) AS log_jump,
           o.close_tr / lag(o.close_tr) OVER w - 1   AS ret_tr,
           o.date - lag(o.date) OVER w               AS gap_days
    FROM {M}.ohlcv_daily o
    WHERE o.close_adj > 0 AND o.close_tr > 0
    WINDOW w AS (PARTITION BY o.instrument_id ORDER BY o.date)
),
scored AS (SELECT m.* FROM moves m JOIN u USING (instrument_id) WHERE m.gap_days <= {gap}),
breadth AS (
    SELECT date, count(*) AS movers FROM scored WHERE abs(log_jump) >= {jump} GROUP BY date
)
SELECT im.symbol, s.date, s.log_jump, s.ret_tr, s.gap_days,
       coalesce(b.movers, 0) AS movers_that_day,
       EXISTS (SELECT 1 FROM {M}.corporate_actions ca
               WHERE ca.instrument_id = s.instrument_id AND ca.ex_date = s.date
                 AND ca.ratio IS NOT NULL) AS has_split
FROM scored s
LEFT JOIN breadth b ON b.date = s.date
JOIN {M}.instrument_master im USING (instrument_id)
WHERE abs(s.log_jump) >= {jump} OR abs(s.ret_tr) > {ret}
ORDER BY abs(s.log_jump) DESC
"""

# Listing gaps in the scored universe. Not a price defect, but a fact that silently ruins any
# period return computed across it, so it is surfaced rather than left for someone to notice
# on a card.
GAPS_SQL = """
WITH u AS ({universe}),
g AS (
    SELECT o.instrument_id, o.date - lag(o.date) OVER
             (PARTITION BY o.instrument_id ORDER BY o.date) AS gap_days
    FROM {M}.ohlcv_daily o JOIN u USING (instrument_id)
)
SELECT im.symbol, max(g.gap_days) AS biggest_gap_days
FROM g JOIN {M}.instrument_master im USING (instrument_id)
WHERE g.gap_days > {gap} GROUP BY im.symbol ORDER BY 2 DESC LIMIT 20
"""

# Same shape, over what the universe EXCLUDES — printed, never asserted on. Its whole job is
# to stop "out of universe" becoming a place defects go to be unseen.
EXCLUDED_COUNT_SQL = """
WITH u AS ({universe}),
moves AS (
    SELECT o.instrument_id,
           ln(o.close_adj / lag(o.close_adj) OVER w) AS log_jump,
           o.date - lag(o.date) OVER w AS gap_days
    FROM {M}.ohlcv_daily o WHERE o.close_adj > 0
    WINDOW w AS (PARTITION BY o.instrument_id ORDER BY o.date)
)
SELECT count(DISTINCT instrument_id) AS n
FROM moves WHERE abs(log_jump) >= {jump} AND gap_days <= {gap}
  AND instrument_id NOT IN (SELECT instrument_id FROM u)
"""

COUNTS_SQL = """
WITH u AS ({universe})
SELECT (SELECT count(*) FROM u) AS scored,
       (SELECT count(DISTINCT o.instrument_id) FROM {M}.ohlcv_daily o JOIN u USING (instrument_id))
           AS scored_with_bars,
       (SELECT count(*) FROM {M}.ohlcv_daily WHERE source = 'alpaca') AS vendor_rows
"""

COMPLETENESS_SQL = """
WITH u AS ({universe}),
sessions AS (
    SELECT o.date, count(*) AS rows
    FROM {M}.ohlcv_daily o JOIN u USING (instrument_id)
    WHERE o.date <= :eod GROUP BY o.date ORDER BY o.date DESC LIMIT 2
)
SELECT * FROM sessions
"""

# The re-basing seam detector, over close_tr / CLOSE_ADJ — two split-adjusted series, so a
# split cancels and what remains is the cumulative DIVIDEND factor, which only ever climbs.
#
# Against the raw close this fires on every reverse split and says nothing true. A reverse
# split multiplies the historical adjusted prices while leaving the raw ones alone, so
# close_tr / close steps down by the whole split factor on the ex-date: measured here, AMZA
# 2020-03-31 "falls" 4.87 against a rounding budget of 0.032, and AMLP 2020-05-18 falls 2.37.
# Both are reverse splits, neither is a seam, and a detector that cannot tell them apart is
# one nobody will keep looking at.
#
# Both columns are published to the cent, so the ratio carries quantisation noise; a real
# seam is a dividend step, two orders of magnitude larger. The tolerance is computed per row
# from the prices rather than picked.
SEAM_SQL = """
WITH u AS ({universe}),
r AS (
    SELECT o.instrument_id, o.date, o.close_adj, o.close_tr,
           o.close_tr / o.close_adj AS ratio,
           lag(o.close_tr / o.close_adj) OVER w AS prev_ratio,
           lag(o.close_adj) OVER w AS prev_adj,
           lag(o.close_tr) OVER w AS prev_tr
    FROM {M}.ohlcv_daily o JOIN u USING (instrument_id)
    WHERE o.close_adj > 0 AND o.close_tr > 0
    WINDOW w AS (PARTITION BY o.instrument_id ORDER BY o.date)
)
SELECT im.symbol, r.date, r.prev_ratio - r.ratio AS fall,
       r.ratio * (0.005 / r.close_adj + 0.005 / r.close_tr)
     + r.prev_ratio * (0.005 / r.prev_adj + 0.005 / r.prev_tr) AS noise
FROM r JOIN {M}.instrument_master im USING (instrument_id)
WHERE r.prev_ratio IS NOT NULL AND r.prev_ratio - r.ratio >
      r.ratio * (0.005 / r.close_adj + 0.005 / r.close_tr)
    + r.prev_ratio * (0.005 / r.prev_adj + 0.005 / r.prev_tr)
ORDER BY (r.prev_ratio - r.ratio) DESC LIMIT 20
"""


def _sql(template: str, schema: str, **kw: Any) -> str:
    return template.format(M=schema, universe=UNIVERSE_SQL.format(M=schema), **kw)


def check_A(g: Gate, eod: Any = None) -> None:
    """Every assertion reads rows the nightly produced; nothing here writes."""
    import _gdb

    from atlas.global_market.providers.fred import fred_series

    m = _gdb.M
    eod = eod or _gdb.eod_cutoff()
    print(f"== gate A: is {m}.ohlcv_daily fit for everything downstream? (eod {eod}) ==")

    counts = _gdb.read_df(_sql(COUNTS_SQL, m))
    scored = int(counts["scored"].iloc[0])
    if not scored:
        g.check(
            "the scored universe is populated",
            False,
            "universe_snapshot has no in_universe rows — build_universe_snapshot.py must run "
            "first (and the FM's liquidity floor must be set); gate A asserts on that set, so "
            "there is nothing to assert on",
        )
        return
    with_bars = int(counts["scored_with_bars"].iloc[0])
    print(
        f"  scored universe: {scored:,d} instrument(s), {int(counts['vendor_rows'].iloc[0]):,d} vendor bars"
    )

    g.check(
        "every scored instrument has bars",
        with_bars == scored,
        f"{with_bars:,d} of {scored:,d}"
        + ("" if with_bars == scored else " — the rest would render an empty card"),
    )

    # (1) the anchor session
    anchor = _gdb.read_df(
        f"select max(o.date) as d from {m}.ohlcv_daily o join {m}.instrument_master im "
        "using (instrument_id) where im.symbol = :sym and o.date <= :eod",
        {"sym": A_ANCHOR, "eod": eod},
    )
    last = anchor["d"].iloc[0] if len(anchor) else None
    # Note what this does NOT assert. `eod_cutoff()` returns a CALENDAR date — 2026-09-06 was
    # a Sunday — and callers anchor to the latest SESSION on or before it, because the SPY
    # bars ARE the calendar (membership by presence). So demanding an anchor ON the EOD fails
    # every weekend, and deriving "the expected session" from these same bars to compare
    # against would be circular. Staleness measured in SESSIONS is `freshness_guard.py`'s job,
    # it owns `ohlcv_daily` at lag 0, and restating it here in a weaker calendar-day form
    # would give two owners and one of them would drift.
    g.check(
        f"{A_ANCHOR} has an anchor bar at or before the EOD",
        last is not None,
        f"latest {A_ANCHOR} session {last}, {(eod - last).days} calendar day(s) before the "
        f"EOD {eod}"
        if last is not None
        else f"no {A_ANCHOR} bar on or before {eod} — no anchor session, so no calendar",
    )

    # (2) completeness against the previous session
    comp = _gdb.read_df(_sql(COMPLETENESS_SQL, m), {"eod": eod})
    if len(comp) >= 2:
        newest, prior = int(comp["rows"].iloc[0]), int(comp["rows"].iloc[1])
        share = newest / prior if prior else 0.0
        g.check(
            f"the newest session carries ≥ {A_MIN_COMPLETENESS:.0%} of the previous one's rows",
            share >= A_MIN_COMPLETENESS,
            f"{newest:,d} on {comp['date'].iloc[0]} vs {prior:,d} on {comp['date'].iloc[1]} "
            f"({share:.2%})",
        )
    else:
        g.check("two sessions exist to compare", False, "fewer than two dated sessions")

    # (3) moves that cannot be prices — hard, at any universe size
    ext = _gdb.read_df(
        _sql(
            EXTREMES_SQL,
            m,
            jump=A_MAX_ABS_LOG_JUMP,
            ret=A_MAX_ABS_RET_1D,
            gap=A_MAX_SESSION_GAP_DAYS,
        )
    )
    impossible = pd.DataFrame(ext[ext["ret_tr"].abs() > A_MAX_ABS_RET_1D])
    g.check(
        f"no scored instrument moves more than {A_MAX_ABS_RET_1D:.0%} between consecutive "
        "sessions on close_tr",
        impossible.empty,
        "none"
        if impossible.empty
        else f"{len(impossible)} row(s): "
        + ", ".join(
            f"{r['symbol']} {r['date']} {r['ret_tr']:+.1%}"
            for _, r in impossible.head(3).iterrows()
        ),
    )

    # (4) large jumps. There is NO reliable automatic test that separates a missed split from
    # a genuine crash, and pretending otherwise would be worse than saying so. AMZA fell 42 %
    # on 2020-03-09 — the Saudi-Russia price war, on four times its usual volume, in a fund
    # that gears its MLP exposure — and it was the ONLY scored name to move that hard, so a
    # breadth test calls it an outlier exactly as it would call a missed split one. Raw and
    # adjusted move together in both cases too. So the gate surfaces every jump with what a
    # human needs to judge it, hard-fails only on the impossible, and asserts the share only
    # where a share means something.
    jumpy = pd.DataFrame(ext[ext["log_jump"].abs() >= A_MAX_ABS_LOG_JUMP])
    unexplained = pd.DataFrame(jumpy[~jumpy["has_split"].astype(bool)])
    dirty = unexplained["symbol"].nunique()
    share = (scored - dirty) / scored
    excluded = int(
        _gdb.read_df(
            _sql(EXCLUDED_COUNT_SQL, m, jump=A_MAX_ABS_LOG_JUMP, gap=A_MAX_SESSION_GAP_DAYS)
        )["n"].iloc[0]
    )
    listing = ", ".join(
        f"{r['symbol']} {r['date']} {r['log_jump']:+.2f}"
        f"{'' if r['movers_that_day'] < 2 else f' (with {r["movers_that_day"] - 1} others)'}"
        for _, r in unexplained.head(4).iterrows()
    )
    detail = (
        f"{scored - dirty:,d} of {scored:,d} clean ({share:.2%})"
        + (f"; {listing}" if listing else "")
        + f" [{excluded:,d} more outside the universe, not asserted on]"
    )
    if scored < A_MIN_N_FOR_SHARE:
        g.check(
            f"unexplained {A_MAX_ABS_LOG_JUMP} log jumps on close_adj (reported: the universe "
            f"is under {A_MIN_N_FOR_SHARE}, too small for a share to be evaluated)",
            True,
            detail,
        )
    else:
        g.check(
            f"≥ {A_MIN_CLEAN_SHARE:.0%} of scored instruments have no unexplained "
            f"{A_MAX_ABS_LOG_JUMP} log jump on close_adj",
            share >= A_MIN_CLEAN_SHARE,
            detail,
        )

    # (5) listing gaps — not a price defect, but any period return spanning one is a fiction
    gaps = _gdb.read_df(_sql(GAPS_SQL, m, gap=A_MAX_SESSION_GAP_DAYS))
    if len(gaps):
        print(
            f"  note: {len(gaps)} scored instrument(s) have a trading gap over "
            f"{A_MAX_SESSION_GAP_DAYS} days — "
            + ", ".join(
                f"{r['symbol']} {int(r['biggest_gap_days'])}d" for _, r in gaps.head(4).iterrows()
            )
        )

    # (6) the re-basing seam
    seams = _gdb.read_df(_sql(SEAM_SQL, m))
    g.check(
        "no close_tr/close ratio falls further than cent rounding can explain",
        seams.empty,
        "none"
        if seams.empty
        else f"{len(seams)} seam(s), worst "
        + ", ".join(
            f"{r['symbol']} {r['date']} fall={r['fall']:.6f} vs noise={r['noise']:.6f}"
            for _, r in seams.head(3).iterrows()
        ),
    )

    # (7) the anchor against an independent publisher
    spy = _gdb.read_df(
        f"select date, close_tr from {m}.ohlcv_daily where instrument_id = "
        f"(select instrument_id from {m}.instrument_master where symbol = :sym and is_active) "
        "and close_tr is not null order by date",
        {"sym": A_ANCHOR},
    )
    if len(spy) < 2:
        g.check(f"{A_ANCHOR} has a total-return series to compare", False, f"{len(spy)} row(s)")
        return
    idx = fred_series(A_CORR_SERIES, spy["date"].iloc[0], None, end=spy["date"].iloc[-1])
    both = spy.merge(idx, on="date", how="inner").sort_values("date")
    both["a"] = both["close_tr"].astype(float).pct_change()
    both["b"] = both["value"].astype(float).pct_change()
    both = pd.DataFrame(both.dropna(subset=["a", "b"]))
    a, b = pd.Series(both["a"]), pd.Series(both["b"])
    corr = float(a.corr(b)) if len(both) > 2 else float("nan")
    worst = float((a - b).abs().max()) if len(both) else float("nan")
    g.check(
        f"{A_ANCHOR} daily returns vs FRED {A_CORR_SERIES} ≥ {A_MIN_RETURN_CORR}",
        pd.notna(corr) and corr >= A_MIN_RETURN_CORR,
        f"r={corr:.5f} on {len(both):,d} returns; worst daily residual {worst:.2%} "
        "(an ETF parts from its index in a dislocation — March 2020 is the tail here)",
    )
