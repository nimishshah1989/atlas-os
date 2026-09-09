"""Reading the assembled point-in-time fundamentals out of ``atlas_global``.

ONE DEFINITION, TWO READERS. ``score_stocks.py`` needs these metrics to score the fundamental
lens; ``seed_thresholds.py --fundamental-bands`` needs the SAME metrics to cut the ladder the
lens is scored against. Two copies of this query would eventually differ — a filter tightened on
one side, a column added on the other — and the bands would then describe a population the
scorer never sees, which is the quietest way to get a wrong score: every number real, every
number about something else.

THE POINT-IN-TIME FILTER IS THE WHOLE REASON ``stock_financials_pit`` IS KEYED BY ``filed``.
``WHERE f.filed <= :anchor`` is what makes a backfilled score honest: a restatement filed in
March must be invisible to a score dated February, or the journal quietly learns the future and
every backtest built on it is optimistic in a way no gate can see.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Container

import _gdb

from atlas.global_market.fundamentals import metrics as fundamentals
from atlas.global_market.fundamentals.metrics import Metrics

__all__ = ["FINANCIALS_SQL", "GICS_FINANCIALS", "financial_ids", "financial_metrics"]

M = _gdb.M

#: ``instrument_master.sector_gics`` as the Select Sector SPDRs spell it. A bank's debt/equity
#: and current ratio are not comparable with an industrial's, so ``ratios`` suppresses both at
#: the source and the balance-sheet sub-score is absent rather than wrong — India's own stance.
GICS_FINANCIALS = "Financials"

# Every point-in-time row a reader on the anchor could have seen, for the stocks being scored.
FINANCIALS_SQL = f"""
SELECT f.instrument_id::text AS instrument_id, f.period_end, f.form, f.filed, f.period_start,
       f.accession_no, f.fiscal_year, f.fiscal_period,
       {", ".join("f." + c for c in sorted(set(fundamentals.CONCEPT_COLUMNS.values())))}
FROM {M}.stock_financials_pit f
JOIN {M}.universe_snapshot u
  ON u.instrument_id = f.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
WHERE f.filed <= :anchor
ORDER BY f.instrument_id, f.period_end, f.filed
"""

# The universe's financial companies, by the sector the identity build recorded.
FINANCIAL_IDS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id
FROM {M}.instrument_master im
JOIN {M}.universe_snapshot u
  ON u.instrument_id = im.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
WHERE im.is_active AND im.asset_class = 'stock' AND im.sector_gics = :sector
"""


def financial_ids() -> set[str]:
    """The universe's ``Financials`` instrument ids."""
    frame = _gdb.read_df(FINANCIAL_IDS_SQL, {"sector": GICS_FINANCIALS})
    return {str(r["instrument_id"]) for r in frame.to_dict("records")}


def financial_metrics(anchor: dt.date, financials: Container[str]) -> dict[str, Metrics]:
    """``instrument_id -> Metrics`` as of the anchor, for every stock with a full TTM window.

    A name whose assembled series is short of the window is ABSENT from the result rather than
    present with nulls: the fundamental lens is not scored for it at all, which is the honest
    answer, and it keeps such a name out of the cross-section the bands are cut from.
    """
    frame = _gdb.read_df(FINANCIALS_SQL, {"anchor": anchor}, coerce_float=False)
    if frame.empty:
        return {}
    out: dict[str, Metrics] = {}
    for iid, block in frame.groupby("instrument_id", sort=False):
        rows = fundamentals.rows_from_records(block.to_dict("records"))
        found = fundamentals.metrics_as_of(rows, anchor, is_financial=str(iid) in financials)
        if found is not None:
            out[str(iid)] = found
    return out
