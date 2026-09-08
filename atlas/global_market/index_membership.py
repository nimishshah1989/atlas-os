"""S&P 500 membership logic — pure functions over rows the script hands over (no I/O).

Two sources feed ``atlas_global.index_membership``: SSGA's SPY holdings for the CURRENT
constituents (weights) and ``fja05680/sp500`` for the history (spells). This module holds
what is decidable without a database — identity resolution over rows the script loaded,
the windowing of spells, and the open / close / confirm planning — so it can be tested on
real fixture rows; ``scripts/global_market/ingest_index_membership.py`` does the reads,
writes and reporting.

Semantics: ``effective_from`` is inclusive, ``effective_to`` EXCLUSIVE (``None`` = current
member; a date = the first date the instrument was observed NOT a member) — verified against
the fja05680 files (``providers/sp500_history.py``). Sources never mix on one row:
``fja05680`` rows are clipped so they never overlap an ``ssga`` row (the script's upsert
refuses to update an ``ssga`` row as well).

Two consequences of the weekly cadence, stated so nobody reads more precision into the dates
than they carry: a departure recorded by the current pass is the weekly OBSERVATION date —
the first holdings file without the name, up to seven sessions after the true change — and
once an ``ssga`` row exists for an instrument it is frozen: the history pass never rewrites
or deletes it, and a spell that starts inside it is dropped in its favour. Non-``ssga`` rows,
by contrast, are re-derived from the file on every history run (:func:`plan_history`) — so a
departure the current pass records on a ``fja05680`` row (the file had not caught up yet) is
provisional: the next history run replaces that observation date with the file's own end date,
or reopens the row until the file catches up and the current pass closes it again.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from atlas.global_market.config import CONFIG

INDEX_CODE = "SP500"
SOURCE_CURRENT = "ssga"
SOURCE_HISTORY = "fja05680"
# The platform's first session (atlas.config.MARKETS["us"]); earlier spells are clipped here.
HISTORY_START = date.fromisoformat(CONFIG.history_start)
REASON_NO_ACTIVE = "no ACTIVE instrument_master row by symbol or symbol_alias"
REASON_NO_INSTRUMENT = "no instrument_master row whose listing window overlaps the spell"
REASON_AMBIGUOUS = "several instrument_master rows overlap the spell"
REASON_DUPLICATE = "a second ticker resolved to the same instrument"


# ── identity (over rows the DB handed over) ──


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: str
    symbol: str
    is_active: bool
    listing_date: date | None
    delisted_at: date | None


@dataclass(frozen=True, slots=True)
class Identity:
    by_symbol: Mapping[str, Sequence[Instrument]]
    by_alias: Mapping[str, str]  # UPPER(source_symbol) → instrument_id, valid_to IS NULL
    rows: Mapping[str, Instrument]  # instrument_id → row


def build_identity(instruments: Iterable[Instrument], aliases: Mapping[str, str]) -> Identity:
    by_symbol: dict[str, list[Instrument]] = {}
    rows: dict[str, Instrument] = {}
    for r in instruments:
        by_symbol.setdefault(r.symbol, []).append(r)
        rows[r.instrument_id] = r
    return Identity(by_symbol, {k.upper(): v for k, v in aliases.items()}, rows)


def resolve_current(ticker: str, ident: Identity) -> tuple[str | None, str]:
    """``(instrument_id, 'symbol' | 'alias')`` or ``(None, reason)`` — ACTIVE rows only."""
    active = [r for r in ident.by_symbol.get(ticker, ()) if r.is_active]
    if len(active) == 1:
        return active[0].instrument_id, "symbol"
    iid = ident.by_alias.get(ticker.upper())
    if iid is not None and ident.rows[iid].is_active:
        return iid, "alias"
    return None, REASON_NO_ACTIVE


def _overlaps(r: Instrument, start: date, end: date | None) -> bool:
    """Listing window ``[listing_date, delisted_at]`` (NULL = unbounded) meets ``[start, end)``."""
    if r.listing_date is not None and end is not None and r.listing_date >= end:
        return False
    return r.delisted_at is None or r.delisted_at >= start


def resolve_spell(
    ticker: str, start: date, end: date | None, ident: Identity
) -> tuple[str | None, str]:
    """The instrument that held ``ticker`` over the spell: the active holder if its listing
    window overlaps, else the one delisted holder that does; none / several → unresolved."""
    candidates = list(ident.by_symbol.get(ticker, ()))
    alias = ident.by_alias.get(ticker.upper())
    if alias is not None and all(c.instrument_id != alias for c in candidates):
        candidates.append(ident.rows[alias])
    hits = [c for c in candidates if _overlaps(c, start, end)]
    active = [c for c in hits if c.is_active]
    if len(active) == 1:
        return active[0].instrument_id, "symbol" if active[0].symbol == ticker else "alias"
    if len(hits) == 1:
        return hits[0].instrument_id, "delisted holder"
    if not hits:
        return None, REASON_NO_INSTRUMENT
    return None, REASON_AMBIGUOUS + ": " + ", ".join(sorted(c.instrument_id for c in hits))


# ── intervals ──


@dataclass(frozen=True, slots=True)
class Interval:
    instrument_id: str
    effective_from: date
    effective_to: date | None
    weight_frac: Decimal | None
    source: str


@dataclass(frozen=True, slots=True)
class HistoryPlan:
    rows: list[Interval]  # fja05680 rows to upsert
    deletes: list[tuple[str, date]]  # (instrument_id, effective_from) of stale non-ssga rows
    notes: list[tuple[str, str]]  # (instrument_id, why a spell was clipped or dropped)


@dataclass(frozen=True, slots=True)
class CurrentPlan:
    opens: list[Interval]  # new rows at as_of
    closes: list[tuple[str, date]]  # (instrument_id, effective_from) → effective_to = as_of
    confirms: list[tuple[str, date, Decimal]]  # (instrument_id, effective_from, weight)


def window_spells(
    spells: pd.DataFrame, start: date, end: date
) -> list[tuple[str, date, date | None]]:
    """Spells that touch ``[start, end)``, their starts clipped to ``start``; a spell that ended
    on/before ``start`` is out, one still open stays open (the current pass settles it)."""
    out: list[tuple[str, date, date | None]] = []
    for t, s, e in spells[["ticker", "start_date", "end_date"]].itertuples(index=False):
        s_d, e_d = s, (None if pd.isna(e) else e)
        if (e_d is not None and e_d <= start) or s_d >= end:
            continue
        out.append((str(t), max(s_d, start), e_d))
    return out


def plan_history(
    spells: Iterable[tuple[str, date, date | None]], existing: Iterable[Interval]
) -> HistoryPlan:
    """The fja05680 rows for this run, clipped so none overlaps an existing ``ssga`` interval
    of the same instrument, and the stale rows to delete first.

    ``existing`` must be EVERY interval of the index (both sources): the non-``ssga`` rows are
    re-derived from the file on every run, so an existing non-``ssga`` row whose
    ``(instrument_id, effective_from)`` is not in the new spell set is deleted — the history
    is reproducible from the file, nothing is lost, and a spell whose start date moved
    upstream can no longer leave its old row behind as a second open interval. ``ssga`` rows
    are never deleted or shortened here (a spell that starts inside one is dropped with a
    note; one that runs into one is clipped to end where it starts).
    """
    ssga: dict[str, list[Interval]] = {}
    for iv in existing:
        if iv.source == SOURCE_CURRENT:
            ssga.setdefault(iv.instrument_id, []).append(iv)
    rows: list[Interval] = []
    notes: list[tuple[str, str]] = []
    for iid, s, e in spells:
        end = e
        dropped = False
        for iv in sorted(ssga.get(iid, ()), key=lambda x: x.effective_from):
            iv_end = iv.effective_to
            inside = iv.effective_from <= s and (iv_end is None or s < iv_end)
            if inside:
                dropped = True
                notes.append(
                    (iid, f"spell {s}→{e} starts inside ssga {iv.effective_from}→{iv_end}")
                )
                break
            if iv.effective_from > s and (end is None or iv.effective_from < end):
                end = iv.effective_from
                notes.append((iid, f"spell {s}→{e} clipped to end at ssga start {end}"))
        if not dropped:
            rows.append(Interval(iid, s, end, None, SOURCE_HISTORY))
    keep = {(r.instrument_id, r.effective_from) for r in rows}
    deletes = [
        (iv.instrument_id, iv.effective_from)
        for iv in existing
        if iv.source != SOURCE_CURRENT and (iv.instrument_id, iv.effective_from) not in keep
    ]
    return HistoryPlan(rows, deletes, notes)


def plan_current(
    current: Mapping[str, Decimal], existing: Iterable[Interval], as_of: date
) -> CurrentPlan:
    """Open / close / confirm against the open intervals: an open interval whose instrument
    is absent today closes at ``as_of`` (unless it opened today — no zero-length rows); a
    current instrument without an open interval opens one at ``as_of``; a current instrument
    with one keeps its ``effective_from`` and takes today's weight."""
    open_by_id = {iv.instrument_id: iv for iv in existing if iv.effective_to is None}
    opens = [
        Interval(iid, as_of, None, w, SOURCE_CURRENT)
        for iid, w in current.items()
        if iid not in open_by_id
    ]
    closes = [
        (iid, iv.effective_from)
        for iid, iv in open_by_id.items()
        if iid not in current and iv.effective_from < as_of
    ]
    confirms = [
        (iid, open_by_id[iid].effective_from, w) for iid, w in current.items() if iid in open_by_id
    ]
    return CurrentPlan(opens, closes, confirms)
