#!/usr/bin/env python3
"""Signal evaluation — does a lens score precede a return?

Loaders live here; the math lives in atlas/compute/signal_eval.py (pure, no I/O).

TWO THINGS THIS FILE EXISTS TO GET RIGHT:

1. Forward returns are computed IN POSTGRES. ohlcv_stock is 6.1M rows and the box has
   2 vCPUs — pandas must receive a reduced frame, never raw prices to shift. Both date
   bounds are SQL-side; see forward_returns() for why the lookahead is not capped by
   calendar days.

2. A no-signal row is excluded, never coerced. compute_composite() returns 0.00 when no
   weighted lens is present, so an unscored row reads composite = 0.00 /
   BELOW_THRESHOLD. 839 instruments carry such rows for dates predating their listing
   (CMRGREEN listed 2026-06-10, rows back to 2019-01-01). Ranking those zeros would put
   ~750 names at the bottom of every date and produce a large, entirely fake IC.

   The criterion is NOT `composite > 0` — that conflates "no signal" with "genuinely
   scored zero", and a genuine zero is a real observation.

   Nor is it the tested lens's own nullability alone. `policy` (a sector-level tailwind)
   and `composite` (the 0.00 sentinel) are non-NULL on EVERY row, placeholders included —
   measured 2026-08-25: 2,093 of 2,093 rows on 2019-06-28, of which 755 predate their
   instrument's listing. For those two lenses `IS NOT NULL` is a no-op that lets the whole
   fake cross-section through. A row carries signal iff at least one of the five
   per-instrument lenses is non-NULL; that is the filter, applied to every lens.
"""

from __future__ import annotations

from collections.abc import Sequence

import _db
import pandas as pd

M = "atlas_foundation"

LENSES = ("technical", "fundamental", "valuation", "catalyst", "flow", "policy", "composite")
HORIZONS = (21, 63, 126)

# The lenses populated only where real per-instrument data existed. Their presence is what
# separates a genuinely scored row from a pre-listing placeholder. policy and composite are
# deliberately absent — both are populated on placeholders too.
_SIGNAL_LENSES = ("technical", "fundamental", "valuation", "catalyst", "flow")
_HAS_SIGNAL = " OR ".join(f"{c} IS NOT NULL" for c in _SIGNAL_LENSES)


def forward_returns(start: str, end: str, horizons: Sequence[int] = HORIZONS) -> pd.DataFrame:
    """Forward returns per (instrument_id, date), computed with SQL window functions.

    `lead(close_adj, h)` steps h TRADING sessions ahead (rows are one per session), which
    is what a horizon means here — not h calendar days.

    An instrument with no session h rows ahead (delisted, or past the data edge) gets
    NULL, never 0.0.
    """
    steps = [int(h) for h in horizons]
    if not steps or any(h < 1 for h in steps):
        raise ValueError(f"horizons must be positive session counts; got {horizons!r}")
    cols = ",\n".join(
        f"           lead(close_adj, {h}) OVER w / close_adj - 1 AS fwd_{h}" for h in steps
    )
    out_cols = ", ".join(f"fwd_{h}" for h in steps)
    # The window the caller asked for is enforced by the OUTER `WHERE date <= :b`, so the
    # frame that crosses the wire is exactly [start, end] — that is the bound the 2-vCPU
    # rule cares about, and it is in SQL.
    #
    # The inner CTE deliberately has NO upper bound. A calendar-day cap (end + h * 1.6d)
    # looks like a cheap way to let lead() see just far enough ahead, but it converts a
    # REAL forward return into a NULL for any instrument that trades fewer sessions than
    # the calendar implies. Measured on 2024-Q1: the true NULL count at h=126 is 0, a
    # 1.6d/session cap invents 243 and a 3.0d/session cap still invents 56 — and every
    # one of them is a thinly-traded name. Silently dropping the illiquid tail from an IC
    # study biases exactly the cohort most likely to show extreme returns.
    #
    # Cost of exactness, same window, identical 104,769 rows transferred: 16.9s vs 4.9s.
    # ponytail: if the unbounded scan ever hurts, bound it per-instrument off the trading
    # calendar (the h-th session after `end` PER instrument) — never by calendar days.
    return _db.read_df(
        f"""
        WITH px AS (
            SELECT instrument_id, date, close_adj
            FROM {M}.ohlcv_stock
            WHERE close_adj IS NOT NULL AND close_adj > 0
              AND date >= :a
        ), fwd AS (
            SELECT instrument_id, date,
{cols}
            FROM px
            WINDOW w AS (PARTITION BY instrument_id ORDER BY date)
        )
        SELECT instrument_id::text AS instrument_id, date, {out_cols}
        FROM fwd
        WHERE date <= :b
        """,
        {"a": start, "b": end},
    )


def lens_scores(lens: str, start: str, end: str) -> pd.DataFrame:
    """One lens's genuinely-scored rows. No-signal rows are excluded, not zero-filled.

    See the module docstring: the exclusion tests the five per-instrument lenses, not the
    requested lens alone, because policy and composite are non-NULL even on placeholders.
    """
    if lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r}; expected one of {LENSES}")
    return _db.read_df(
        f"""SELECT instrument_id::text AS instrument_id, date, {lens}::float AS score
            FROM {M}.atlas_lens_scores_daily
            WHERE asset_class = 'stock' AND date BETWEEN :a AND :b
              AND {lens} IS NOT NULL AND ({_HAS_SIGNAL})""",  # lens validated above
        {"a": start, "b": end},
    )


def cap_cohorts() -> pd.DataFrame:
    """instrument_id -> cap cohort, from the single rule in v_stock_cap.

    HAS NO DATE DIMENSION. The view holds today's 1,199-name universe and today's cap
    band, so using it to split a historical cross-section does two things a caller must
    decide about consciously:

      * it drops every name not in the universe today — 60.4% of the 2019-06-28 scored
        cross-section carries a cap, 59.4% of 2022-06-30, 100% from 2024 on. The 40%
        that vanish are the ones that left the universe, which is survivorship bias in
        the cohort dimension, not a random sample.
      * it labels a 2019 row with a 2026 cap band, so a name that grew from micro to
        large is scored as large throughout.

    Both are fine for a recent-era cohort split and wrong for a 2019 one. A point-in-time
    cap needs equity_marketcap as of the date instead.
    """
    return _db.read_df(f"SELECT instrument_id::text AS instrument_id, cap FROM {M}.v_stock_cap")
