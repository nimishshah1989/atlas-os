"""Reading 8-K filings out of ``atlas_global`` for the catalyst lens.

POINT-IN-TIME, ENFORCED TWICE. This query filters ``filed <= :anchor`` and the scorer filters
again on the same field. That is deliberate belt-and-braces: the query keeps the result set
small, and the scorer's own filter is what makes ``score_catalyst`` safe to call from a test, a
notebook or a future backfill that forgot to bound its window. A score that can see next month's
8-K makes every backtest built on it optimistic, and nothing downstream can detect it.

THE WINDOW IS THE LENS'S OWN. ``catalyst_recency_t3`` is how far back an event still carries any
weight, so anything older changes no score and is not fetched. The window comes from
``atlas_thresholds`` (rule #1) — the reader must not invent the horizon the lens scores over.
"""

from __future__ import annotations

import datetime as dt

import _gdb

from atlas.global_market.scoring.stock_catalyst import Filing

__all__ = ["FILINGS_SQL", "filings_by_instrument"]

M = _gdb.M

FILINGS_SQL = f"""
SELECT f.instrument_id::text AS instrument_id, f.filed, f.items, f.accession_no
FROM {M}.filings_8k f
JOIN {M}.universe_snapshot u
  ON u.instrument_id = f.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
WHERE f.filed <= :anchor AND f.filed >= :since
ORDER BY f.instrument_id, f.filed
"""


def filings_by_instrument(anchor: dt.date, lookback_days: int) -> dict[str, list[Filing]]:
    """``instrument_id -> [Filing]`` over the lens's window, oldest first.

    A stock absent from the result filed nothing in the window. The scorer answers that with
    ``None`` — no news is not bad news — rather than with a 50 that would claim the news netted
    out to neutral.
    """
    since = anchor - dt.timedelta(days=lookback_days)
    frame = _gdb.read_df(FILINGS_SQL, {"anchor": anchor, "since": since})
    out: dict[str, list[Filing]] = {}
    for r in frame.to_dict("records"):
        out.setdefault(str(r["instrument_id"]), []).append(
            Filing(
                filed=r["filed"],
                # A postgres text[] arrives as a list; an empty one is a filing that named no
                # item, which is a real state and not a reason to drop the filing.
                items=tuple(r["items"] or ()),
                accession_no=str(r["accession_no"]),
            )
        )
    return out
