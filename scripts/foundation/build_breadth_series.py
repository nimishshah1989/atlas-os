#!/usr/bin/env python3
"""Page-1 (Markets Today) data layer: the Nifty-500 BREADTH SERIES, computed natively from
atlas_foundation.technical_daily (no atlas.* dependency). One row per trading day with the
absolute COUNTS of Nifty-500 constituents above the 21/50/200-EMA (the markets-today-redesign
spec wants counts, not %), plus net-new-highs and median momentum for the SignalScorecard.

Universe: CURRENT Nifty 500 membership applied across all history (spec D: accept current
membership for all dates). Materialised tiny (~one row/day) so the frontend reads it directly.
Re-runnable (nightly): DROP + rebuild.

BROAD-TRADING DAYS ONLY (fixes the "breadth dips to 0" chart bug): two kinds of non-normal
sessions produced junk breadth rows that rendered as dips toward zero —
  • NSE HOLIDAYS that carry a few spurious OHLCV rows (~10 instruments). No NIFTY 500 index
    close (market shut); dropped by the INNER JOIN on the index.
  • DIWALI MUHURAT special sessions (e.g. 2016-10-30, 2017-10-19, 2018-11-07): a real ~1-hour
    session WITH an index close but only ~15-40 stocks recorded, so breadth over 4-13 members
    is meaningless. Dropped by the broad-trading gate below.
We therefore emit breadth ONLY for days where (a) the NIFTY 500 index actually closed AND
(b) the broad market traded — at least MIN_TRADED stocks have an OHLCV row. Verified over the
last 12y: real sessions have ≥ 498 stocks while every artifact has ≤ 38, so the gate is a clean
cut that drops nothing real. (Holidays/Muhurat have no full bhavcopy to backfill — the broad
market wasn't open.)

    python build_breadth_series.py
"""

from __future__ import annotations

import _db

TGT = "atlas_foundation.breadth_nifty500_daily"
MIN_TRADED = 100  # min stocks with an OHLCV row for the day to count as a broad-trading session
                  # (artifacts ≤ 38, real sessions ≥ 498 — see module docstring)

SQL = f"""
DROP TABLE IF EXISTS {TGT} CASCADE;
CREATE TABLE {TGT} AS
WITH traded AS (
  -- broad-trading days only: drops NSE-holiday artifacts and Diwali Muhurat micro-sessions
  SELECT date FROM atlas_foundation.ohlcv_stock GROUP BY date HAVING count(*) >= {MIN_TRADED}
),
idx AS (
  -- Nifty 500 INDEX price momentum (robust; avg-constituent ret_3m is outlier-skewed,
  -- max ~2000% from microcaps). 63 trading sessions ~= 3 months.
  SELECT date,
         close AS idx_close,
         close / NULLIF(lag(close, 63) OVER (ORDER BY date), 0) - 1 AS idx_ret_3m
  FROM atlas_foundation.index_prices
  WHERE index_code = 'NIFTY 500'
),
breadth AS (
  SELECT t.date,
         count(*)                              AS n_members,
         sum((t.above_ema_21)::int)            AS above_21,
         sum((t.above_ema_50)::int)            AS above_50,
         sum((t.above_ema_200)::int)           AS above_200,
         sum((t.pos_52w >= 95)::int)           AS at_52w_high,   -- pos_52w is 0-100
         sum((t.pos_52w <= 5)::int)            AS at_52w_low,
         sum((t.pos_52w >= 95)::int)
           - sum((t.pos_52w <= 5)::int)        AS net_new_highs,
         sum((t.ema_50 > t.ema_200)::int)      AS gc_50_200,     -- golden cross: 50-EMA > 200-EMA
         round(avg(t.rsi_14)::numeric, 2)      AS avg_rsi_14
  FROM atlas_foundation.technical_daily t
  JOIN atlas_foundation.de_index_constituents c
    ON c.instrument_id = t.instrument_id
   AND c.index_code = 'NIFTY 500'
   AND c.effective_to IS NULL
  WHERE t.asset_class = 'stock'
  GROUP BY t.date
)
SELECT b.*,
       round(i.idx_close::numeric, 2)  AS idx_close,
       round(i.idx_ret_3m::numeric, 4) AS idx_ret_3m
FROM breadth b
JOIN idx i ON i.date = b.date          -- INNER: index closed that day (drops holiday artifacts)
JOIN traded tr ON tr.date = b.date;    -- INNER: broad market traded (drops Muhurat micro-sessions)
ALTER TABLE {TGT} ADD PRIMARY KEY (date);
"""


def run() -> None:
    _db.exec_script(SQL)
    n = _db.scalar(f"SELECT count(*) FROM {TGT}")
    rng = _db.read_df(f"SELECT min(date) mn, max(date) mx FROM {TGT}")
    print(f"built {TGT}: {n} trading days, {rng.iloc[0]['mn']} .. {rng.iloc[0]['mx']}")
    head = _db.read_df(
        f"SELECT date, n_members, above_21, above_50, above_200, gc_50_200, net_new_highs, avg_rsi_14, idx_ret_3m "
        f"FROM {TGT} ORDER BY date DESC LIMIT 5"
    )
    print(head.to_string(index=False))


if __name__ == "__main__":
    run()
