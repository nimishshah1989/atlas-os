#!/usr/bin/env python3
"""atlas_foundation.v_stock_cap — the SINGLE cap-cohort rule.

Cap was derived from index membership, in frontend SQL, duplicated across
stock_lens.ts and sector_lens.ts (and a third time in decile_core.cap_bucket). That
worked only while the universe WAS the indices. Under the liquidity floor every new
name is in no index and would collapse into 'micro', taking that cohort from 250 to
~700 — and since deciles are cut within cohort, every micro decile and every Leader
badge would silently change meaning.

Market-cap rank is what the index rule was approximating all along (NIFTY 100 = top
100, MIDCAP 150 = 101-250, SMLCAP 250 = 251-500). The two do not agree exactly and
are not meant to: NSE selects on a 6-month average cap and reconstitutes twice a
year, so names near a boundary sit on the other side of it between reconstitutions.
What the switch buys is one definition instead of three, on a basis that keeps
meaning when the universe stops being the indices.

Ranked over ACTIVE stocks only: cap is a statement about position within Atlas's
coverage, exactly as the index rule was.

    python cap_cohort.py            # create or replace the view
    python cap_cohort.py --report   # create, then print cohort sizes
"""

from __future__ import annotations

import argparse

import _db  # pyright: ignore[reportMissingImports]

M = "atlas_foundation"

# SEBI's statutory cap classes by market-cap rank — not tunable methodology, so they
# stay here rather than in atlas_thresholds. Matches decile_core.cap_bucket().
LARGE_MAX, MID_MAX, SMALL_MAX = 100, 250, 500

DDL = f"""
CREATE OR REPLACE VIEW {M}.v_stock_cap AS
WITH r AS (
    SELECT im.instrument_id,
           row_number() OVER (ORDER BY m.market_cap_cr DESC, im.symbol) AS mcap_rank
    FROM {M}.instrument_master im
    JOIN {M}.equity_marketcap m ON m.instrument_id = im.instrument_id
    WHERE im.asset_class = 'stock' AND im.is_active
      AND m.market_cap_cr IS NOT NULL AND m.market_cap_cr > 0
)
SELECT instrument_id,
       mcap_rank,
       CASE WHEN mcap_rank <= {LARGE_MAX} THEN 'large'
            WHEN mcap_rank <= {MID_MAX}   THEN 'mid'
            WHEN mcap_rank <= {SMALL_MAX} THEN 'small'
            ELSE 'micro' END AS cap
FROM r
"""


def build(report: bool = False) -> dict:
    """Create/replace the view, then fail loudly if it does not cover every active stock.

    Partial coverage is the one failure mode that produces no error on its own and
    changes what every cohort MEANS. An uncovered name gets no row at all, so a
    consumer's LEFT JOIN defaults it to 'micro' — and worse, the names that remain get
    re-ranked, so the 100/250/500 cuts land somewhere else entirely. At 300 covered
    stocks instead of 747 nothing is micro and a genuine small-cap is labelled 'large'.
    Silence there would defeat the point of centralising the rule.
    """
    _db.exec_sql(DDL)
    uncovered = _db.read_df(
        f"""SELECT im.symbol FROM {M}.instrument_master im
            LEFT JOIN {M}.v_stock_cap v ON v.instrument_id = im.instrument_id
            WHERE im.asset_class = 'stock' AND im.is_active AND v.cap IS NULL
            ORDER BY im.symbol"""
    )["symbol"].tolist()
    if uncovered:
        raise SystemExit(
            f"cap_cohort: {len(uncovered)} active stocks have no market cap, so they are "
            f"absent from v_stock_cap — they would fall through to 'micro' AND shift the "
            f"rank cuts for every other name: {uncovered[:20]}. Re-run fetch_marketcap.py."
        )
    sizes = _db.read_df(
        f"""SELECT cap, count(*) n FROM {M}.v_stock_cap
            GROUP BY 1 ORDER BY min(mcap_rank)"""
    )
    out = dict(zip(sizes["cap"], sizes["n"], strict=True))
    if report:
        for cap, n in out.items():
            print(f"  {cap:6s} {n}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print cohort sizes")
    build(report=ap.parse_args().report)
