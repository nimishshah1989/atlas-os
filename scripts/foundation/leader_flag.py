#!/usr/bin/env python3
"""atlas_foundation.v_stock_leader — the SINGLE leader rule.

A LEADER is a stock in the top decile (D10) of composite within its cap cohort. That
one sentence was written five times in SQL and the copies disagreed. The funds/ETF/
stocks/sectors pages used lead = (d_composite >= 10) filtered on >= 1;
build_fund_rank_history.py and verify_fund_rank.py used the retired 2-lens rule,
lead = (d_tech >= 9) + (d_flow >= 9) filtered on >= 2. Measured 2026-08-18: 73 leaders
vs 25, only 17 in common — so fund_rank_daily.breadth was a different number from the
breadth the fund page displayed. The DoD gate could not see it, because the verifier
had copied the builder's rule rather than production's; a verifier that copies the
thing it verifies verifies nothing.

Same fix as v_stock_cap: put the rule in one view and have every consumer select from
it. Nothing here is new methodology — this is production's rule, unchanged.

KEYED BY DATE, not just instrument. The frontend wants max(date);
build_fund_rank_history.py re-scores each historical day against THAT day's lens
scores, so a latest-only view could not serve it. Deciles partition by (date, cap), and
Postgres pushes a `WHERE date = ...` qual through the window function because `date` is
a partitioning column — so a single day costs an index scan of that day (743 rows,
~14ms), not a sort of the 3.1M-row journal. **Every consumer must filter on date**; an
unfiltered join fans out across ~1900 days.

Cap comes from v_stock_cap and defaults to 'micro' exactly as the page CTEs do, so an
uncovered name lands in the same cohort it lands in today rather than vanishing.

    python leader_flag.py            # create or replace the view
    python leader_flag.py --report   # create, then print today's leaders per cohort
"""

from __future__ import annotations

import argparse

import _db  # pyright: ignore[reportMissingImports]

M = "atlas_foundation"

# Top DECILE of composite. Not tunable methodology in the atlas_thresholds sense — it is
# the definition of the word "leader" (FM 2026-06-30: one simple rule), and the decile
# count is fixed by ntile(10). It stays here rather than in a threshold row for the same
# reason SEBI's cap ranks stay in cap_cohort.py.
LEAD_DECILE = 10

DDL = f"""
CREATE OR REPLACE VIEW {M}.v_stock_leader AS
SELECT date, instrument_id,
       COALESCE((d_composite >= {LEAD_DECILE})::int, 0) AS lead
FROM (
    SELECT date, instrument_id,
           CASE WHEN comp IS NULL THEN NULL
                ELSE ntile(10) OVER (PARTITION BY date, cap, (comp IS NULL) ORDER BY comp)
           END AS d_composite
    FROM (
        SELECT l.date, l.instrument_id, COALESCE(c.cap, 'micro') AS cap, l.composite::float AS comp
        FROM {M}.atlas_lens_scores_daily l
        JOIN {M}.instrument_master im ON im.instrument_id = l.instrument_id
        LEFT JOIN {M}.v_stock_cap c ON c.instrument_id = l.instrument_id
        WHERE l.asset_class = 'stock'
    ) j
) d
"""


def build(report: bool = False) -> dict:
    """Create/replace the view, then fail loudly if it misses a scored stock.

    A stock scored on the latest lens date but absent from the view is the failure mode
    that produces no error of its own: every roll-up joins `scored` INNER, so the name
    is dropped from the holdings base and each fund's breadth is quietly computed over a
    smaller portfolio. The only way that can happen is the instrument_master join — the
    same join the page CTEs make — so a gap means the journal has scored an instrument
    the master does not carry.
    """
    _db.exec_sql(DDL)
    missing = _db.read_df(
        f"""SELECT l.instrument_id::text AS instrument_id
            FROM {M}.atlas_lens_scores_daily l
            LEFT JOIN {M}.v_stock_leader v
              ON v.instrument_id = l.instrument_id AND v.date = l.date
            WHERE l.asset_class = 'stock'
              AND l.date = (SELECT max(date) FROM {M}.atlas_lens_scores_daily WHERE asset_class='stock')
              AND v.lead IS NULL
            ORDER BY 1"""
    )["instrument_id"].tolist()
    if missing:
        raise SystemExit(
            f"leader_flag: {len(missing)} stocks scored on the latest lens date are absent "
            f"from v_stock_leader — every roll-up INNER-joins the leader flag, so these "
            f"names would silently drop out of the fund/ETF breadth base: {missing[:20]}. "
            f"They are in atlas_lens_scores_daily but not instrument_master; fix the master."
        )
    sizes = _db.read_df(
        f"""SELECT COALESCE(c.cap,'micro') AS cap, count(*) n, sum(v.lead) n_lead
            FROM {M}.v_stock_leader v
            LEFT JOIN {M}.v_stock_cap c ON c.instrument_id = v.instrument_id
            WHERE v.date = (SELECT max(date) FROM {M}.atlas_lens_scores_daily WHERE asset_class='stock')
            GROUP BY 1"""
    )
    out = {
        cap: (int(n_lead), int(n))
        for cap, n_lead, n in zip(sizes["cap"], sizes["n_lead"], sizes["n"], strict=True)
    }
    if report:
        for cap, (n_lead, n) in out.items():
            print(f"  {cap:6s} {n_lead}/{n} leaders")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print leaders per cap cohort")
    build(report=ap.parse_args().report)
