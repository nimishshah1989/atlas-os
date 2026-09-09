"""What the stock EVENT lenses need out of ``atlas_global``: 8-K filings and short interest.

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
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import _gdb

from atlas.global_market.providers.finra import ShortInterest
from atlas.global_market.scoring.stock_catalyst import Filing
from atlas.global_market.scoring.stock_catalyst import missing_keys as missing_catalyst_keys
from atlas.global_market.scoring.stock_flow import missing_keys as missing_flow_keys

__all__ = [
    "FILINGS_SQL",
    "SHORT_INTEREST_SQL",
    "LensInputs",
    "filings_by_instrument",
    "lens_inputs",
    "short_interest_by_instrument",
]

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


# ── the flow lens's feed ────────────────────────────────────────────────────
#
# The WHOLE history, not just the newest settlement: the scorer picks the newest reading at or
# before the anchor itself, which is what makes a backfilled score honest. Bounded by the lens's
# own staleness limit plus a settlement, so a name whose feed stopped is refused rather than
# scored on a figure from last year.
SHORT_INTEREST_SQL = f"""
SELECT s.instrument_id::text AS instrument_id, im.symbol, s.settlement_date,
       s.short_interest, s.previous_short_interest, s.avg_daily_volume,
       s.days_to_cover, s.change_percent, s.split_flag, s.revision_flag
FROM {M}.short_interest s
JOIN {M}.instrument_master im ON im.instrument_id = s.instrument_id
JOIN {M}.universe_snapshot u
  ON u.instrument_id = s.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
WHERE s.settlement_date <= :anchor AND s.settlement_date >= :since
ORDER BY s.instrument_id, s.settlement_date
"""


def short_interest_by_instrument(
    anchor: dt.date, max_age_days: int
) -> dict[str, list[ShortInterest]]:
    """``instrument_id -> [ShortInterest]`` over the readings the lens could still use.

    The window is the staleness limit plus one settlement fortnight, so the newest usable reading
    is always inside it and nothing older is carried for no reason.
    """
    since = anchor - dt.timedelta(days=max_age_days + 20)
    frame = _gdb.read_df(SHORT_INTEREST_SQL, {"anchor": anchor, "since": since})
    out: dict[str, list[ShortInterest]] = {}
    for r in frame.to_dict("records"):
        out.setdefault(str(r["instrument_id"]), []).append(
            ShortInterest(
                symbol=str(r["symbol"]),
                settlement_date=r["settlement_date"],
                issue_name="",
                short_shares=_decimal(r["short_interest"]),
                previous_short_shares=_decimal(r["previous_short_interest"]),
                average_daily_volume=_decimal(r["avg_daily_volume"]),
                days_to_cover=_decimal(r["days_to_cover"]),
                change_percent=_decimal(r["change_percent"]),
                is_revision=bool(r["revision_flag"]),
                split_flag=bool(r["split_flag"]),
            )
        )
    return out


def _decimal(value: object) -> Decimal | None:
    """A database NUMERIC or NULL as a Decimal. pandas turns a NULL into None or NaN depending on
    the column's dtype, and NaN would sail through every comparison the scorer makes."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    return Decimal(str(value))


# ── what the event lenses need, and what to say when it is not there ────────


@dataclass(frozen=True, slots=True)
class LensInputs:
    """The event lenses' inputs at one anchor, with the reason each is empty when it is."""

    filings: dict[str, list[Filing]]
    short: dict[str, list[ShortInterest]]
    missing_catalyst: list[str]
    missing_flow: list[str]

    def lines(self, schema: str, names: int) -> list[str]:
        """What the run prints. A lens that cannot score says which keys are missing and what to
        run; one that can says how much of the universe it actually reached, because "scored" and
        "had something to score" are different facts."""
        out = []
        out.append(
            f"the catalyst lens is NOT scored: {len(self.missing_catalyst)} key(s) missing from "
            f"{schema}.atlas_thresholds, first {self.missing_catalyst[0]!r} — run seed_thresholds.py"
            if self.missing_catalyst
            else f"catalyst: {len(self.filings):,d} of {names:,d} name(s) filed an 8-K in the window"
        )
        out.append(
            f"the flow lens is NOT scored: {len(self.missing_flow)} key(s) missing, first "
            f"{self.missing_flow[0]!r} — run seed_thresholds.py"
            if self.missing_flow
            else f"flow: {len(self.short):,d} name(s) carry a short-interest reading"
        )
        return out


def lens_inputs(anchor: dt.date, th: Mapping[str, Decimal]) -> LensInputs:
    """Load both event feeds, or neither where the lens's own keys are not seeded.

    A lens with missing thresholds does not fetch: reading a feed for a lens that cannot score is
    a query nobody uses, and the printed reason is what an operator needs instead.
    """
    missing_catalyst = missing_catalyst_keys(th)
    missing_flow = missing_flow_keys(th)
    return LensInputs(
        filings={}
        if missing_catalyst
        else filings_by_instrument(anchor, int(th["catalyst_recency_t3"])),
        short={}
        if missing_flow
        else short_interest_by_instrument(anchor, int(th["flow_si_max_age_days"])),
        missing_catalyst=missing_catalyst,
        missing_flow=missing_flow,
    )
