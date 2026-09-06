"""Diff the DESIRED identity frame against what ``instrument_master`` holds — pure.

The planner decides, row by row, what the script writes; it never touches the database.
The rules (docs/global/phase1.md P1-A, revised 2026-09-04 after review):

* An existing ACTIVE row is matched by ``symbol`` alone (one active row per symbol is the
  table's invariant) and UPDATED in place — identity columns only, ``asset_class`` included
  (an ETF-flag flip on the same registrant is an update, never a second instrument); its
  uuid is kept even when its ``listing_date`` estimate changes (the key is for minting,
  never re-derived).
* The registrant is the identity. A symbol whose CIK CHANGES between runs — to another
  registrant, from none to one, or from one to none — is a RECYCLED ticker: the old row is
  deactivated, a NEW instrument minted. One exception: across an ETF-flag flip, a stored
  CIK the SEC files still carry under the ticker beside the one the other class's
  precedence picks (the frame's ``sec_conflict``) is the same registrant — the stored SEC
  columns are kept and the conflict noted.
* With no CIK on either side, Tiingo's listing start is the evidence: a start that moves
  FORWARD by more than :data:`LISTING_DATE_JUMP_DAYS` is a recycle; a name that no longer
  agrees (``identity.names_agree``) while the start moved forward at all is a recycle; a
  backward move (Tiingo extending history — a new listing period never starts earlier than
  the one it replaces) or a name change alone is an update with a note.
* A symbol that disappears from the directory becomes ``is_active = false`` with
  ``delisted_at`` = run date; its history and its aliases stay. ``source = 'manual'`` rows
  are never deactivated by the directory — they are reported.
* A symbol that appears is first tried as a RENAME: a departing row with the same CIK
  (funds: the same CIK, series and class) whose identity has exactly one active listing
  before and after keeps its uuid under the new symbol; the old spellings' aliases are
  closed and the new ones opened. A CIK with several listings (share classes, a trust's
  funds) is never paired — the new row is inserted with a ``possible rename`` note.
* Otherwise the appearing symbol mints its key; when the minted uuid is already on file
  (the same registrant relisted under the same ticker, or the same fallback key) that row is
  REACTIVATED — as is a deactivated no-CIK row with the same symbol and an agreeing name,
  whatever the run-date component of its key (a listing that flickers out of one weekly
  file is one instrument, not two).
* Stooq archive members absent from the directory become INACTIVE rows under the fallback
  key ``us:{kind}:{symbol}:{first bar}`` (``source='stooq'``, ``delisted_at`` = the last bar)
  unless a row already carries the symbol — then the archive is aliased to it.
* Aliases: one OPEN ``(source, source_symbol)`` at a time — left alone when open on the same
  instrument, CLOSED (``valid_to`` = run date) and re-opened when open on another (how a
  recycled ticker's Stooq file moves to the new holder), inserted when new.
* Circuit breaker: deactivating more than :data:`MASS_DEACTIVATION_FRAC` of the active rows
  or :data:`MASS_DEACTIVATION_ROWS` rows (whichever is smaller) is refused
  (:class:`MassDeactivationError`) unless the caller allows it — a truncated directory must
  never delist the market.

Rows are plain dicts (``instrument_id`` as ``str``, missing values ``None``) so the script
can hand them to ``execute_values`` unchanged.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any

from atlas.global_market import identity as ident
from atlas.global_market.identity_frame import LISTING_SOURCE_TIINGO

IDENTITY_COLUMNS = (
    "asset_class",
    "name",
    "exchange",
    "cik",
    "series_id",
    "class_id",
    "listing_date",
)
ROW_COLUMNS = ("instrument_id", "symbol", *IDENTITY_COLUMNS, "delisted_at", "is_active", "source")
SOURCE_NASDAQ_TRADER = "nasdaq_trader"
SOURCE_MANUAL = "manual"

# Data-quality guards, not methodology (nothing here scores or classifies): the largest
# weekly delisting wave a directory may carry before the run is refused as a bad download,
# and the forward move of a Tiingo listing start that reads as a new listing period rather
# than a data correction.
MASS_DEACTIVATION_FRAC = 0.02
MASS_DEACTIVATION_ROWS = 200
LISTING_DATE_JUMP_DAYS = 30

ACTION_INSERT = "insert"
ACTION_RENAME = "rename"
ACTION_REACTIVATE = "reactivate"
ACTION_UPDATE = "update"
ACTION_DEACTIVATE = "deactivate"
ACTION_UNCHANGED = "unchanged"

Row = dict[str, Any]
_CIK_IN_NOTE = re.compile(r"\b\d{10}\b")


@dataclass(frozen=True, slots=True)
class ReportRow:
    symbol: str
    asset_class: str
    exchange: str | None
    cik: str | None
    series_id: str | None
    key_kind: str = field(init=False)  # cik | fallback, from ``cik``
    action: str
    aliases: str = ""  # "stooq:BRK-B.US;tiingo:BRK-B;…"
    note: str = ""
    sec_conflict: str | None = (
        None  # every CIK the SEC files carry for the ticker, when they disagree
    )
    name_agrees: bool | None = None  # directory name vs the SEC title; None = no title on file

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_kind", ident.key_kind(self.cik))


REPORT_COLUMNS = tuple(f.name for f in fields(ReportRow))


@dataclass(slots=True)
class Plan:
    inserts: list[Row] = field(default_factory=list)  # full rows, new instrument_ids
    renames: list[Row] = field(default_factory=list)  # full rows, ids on file, new symbol
    reactivations: list[Row] = field(default_factory=list)  # full rows, ids already on file
    updates: list[Row] = field(default_factory=list)  # instrument_id + IDENTITY_COLUMNS
    touches: list[str] = field(default_factory=list)  # unchanged ids (updated_at = now())
    deactivations: list[Row] = field(default_factory=list)  # instrument_id, delisted_at
    alias_inserts: list[tuple[str, str, str, str]] = field(
        default_factory=list
    )  # src, sym, id, note
    alias_closes: list[tuple[str, str, str]] = field(default_factory=list)  # src, sym, old id
    report: list[ReportRow] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "insert": len(self.inserts),
            "rename": len(self.renames),
            "reactivate": len(self.reactivations),
            "update": len(self.updates),
            "unchanged": len(self.touches),
            "deactivate": len(self.deactivations),
            "alias_insert": len(self.alias_inserts),
            "alias_close": len(self.alias_closes),
        }


class MassDeactivationError(RuntimeError):
    """The plan would delist more of the market than one weekly directory plausibly can."""

    def __init__(self, count: int, cap: int, active: int) -> None:
        self.count, self.cap, self.active = count, cap, active
        super().__init__(
            f"refusing to deactivate {count:,d} of {active:,d} active rows (cap {cap:,d} = "
            f"min({MASS_DEACTIVATION_FRAC:.0%} of active, {MASS_DEACTIVATION_ROWS})) — a "
            "truncated directory? pass --allow-mass-deactivation only after checking the files"
        )


def _ciks_seen(d: Mapping[str, Any]) -> set[str]:
    """Every CIK the SEC files carry for the row's ticker: the chosen one plus the
    conflicting ones the frame recorded."""
    seen = set(_CIK_IN_NOTE.findall(d.get("sec_conflict") or ""))
    if d.get("cik"):
        seen.add(d["cik"])
    return seen


def _merge(existing: Row, desired: Row) -> tuple[Row, list[str]]:
    """The identity columns an in-place update (or a reactivation / rename) carries, and
    the notes explaining every departure from the desired row: the directory's
    asset_class / name / exchange; the SEC columns when the run knows them, else the stored
    ones — the stored ones outright when the run's CIK conflicts with a stored CIK the files
    still carry; a Tiingo listing date over any stored one, but never a run-date fallback
    over a stored date."""
    out = {c: desired.get(c) for c in IDENTITY_COLUMNS}
    notes: list[str] = []
    if existing.get("cik") and out["cik"] != existing["cik"]:
        for c in ("cik", "series_id", "class_id"):
            out[c] = existing.get(c)
        notes.append(
            f"stored cik {existing['cik']} kept: the sec files carry it under this ticker "
            f"beside {desired.get('cik')}"
        )
    else:
        for c in ("series_id", "class_id"):
            if out[c] is None:
                out[c] = existing.get(c)
    if desired.get("listing_source") != LISTING_SOURCE_TIINGO and existing.get("listing_date"):
        out["listing_date"] = existing["listing_date"]
        notes.append("listing_date kept (no tiingo date)")
    if out["asset_class"] != existing.get("asset_class"):
        notes.append(f"asset_class {existing.get('asset_class')} -> {out['asset_class']}")
    return out, notes


def _full_row(
    instrument_id: str, desired: Row, source: str, *, active: bool, delisted_at: date | None
) -> Row:
    return {
        "instrument_id": instrument_id,
        "symbol": desired["symbol"],
        **{c: desired.get(c) for c in IDENTITY_COLUMNS},
        "delisted_at": delisted_at,
        "is_active": active,
        "source": source,
    }


def _alias_text(pairs: Iterable[tuple[str, str]]) -> str:
    return ";".join(f"{s}:{v}" for s, v in pairs)


def _class_key(r: Mapping[str, Any]) -> tuple[str, str, str] | None:
    if r.get("cik") and r.get("series_id") and r.get("class_id"):
        return (r["cik"], r["series_id"], r["class_id"])
    return None


class _Planner:
    def __init__(
        self,
        existing: Iterable[Row],
        open_aliases: Mapping[tuple[str, str], str],
        tiingo_tickers: Collection[str],
        run_date: date,
    ) -> None:
        self.run_date = run_date
        self.tiingo = tiingo_tickers
        self.by_id: dict[str, Row] = {}
        self.active_by_symbol: dict[str, Row] = {}
        self.by_symbol: dict[str, list[Row]] = defaultdict(list)
        for raw in existing:
            row = {**raw, "instrument_id": str(raw["instrument_id"])}
            self.by_id[row["instrument_id"]] = row
            self.by_symbol[row["symbol"]].append(row)
            if row["is_active"]:
                if row["symbol"] in self.active_by_symbol:
                    raise ValueError(f"instrument_master: two ACTIVE rows for {row['symbol']}")
                self.active_by_symbol[row["symbol"]] = row
        self.open_aliases = dict(open_aliases)
        self.wanted_aliases: dict[tuple[str, str], tuple[str, str]] = {}  # pair → (id, note)
        self.handled: set[str] = set()  # existing ids accounted for this run
        self.deactivated: set[str] = set()  # ids deactivated this run: never reactivated in it
        self.renamed: set[str] = set()
        self.desired: list[Row] = []
        self.arrivals: list[Row] = []  # desired rows with no active holder
        self.plan = Plan()

    # ── directory rows ──

    def directory_row(self, d: Row) -> None:
        self.desired.append(d)
        cur = self.active_by_symbol.get(d["symbol"])
        if cur is None:
            self.arrivals.append(d)  # resolved once the departures are known (renames)
            return
        self.handled.add(cur["instrument_id"])
        same, notes = self._same_registrant(cur, d)
        if not same:
            self._deactivate(cur, notes[0])
            self._mint_or_reactivate(
                d, [f"new instrument; previous holder {cur['instrument_id']} deactivated"]
            )
            return
        merged, merge_notes = _merge(cur, d)
        notes += merge_notes
        changed = [c for c in IDENTITY_COLUMNS if merged[c] != cur.get(c)]
        if changed:
            self.plan.updates.append({"instrument_id": cur["instrument_id"], **merged})
            action = ACTION_UPDATE
            notes.append("changed: " + ",".join(changed))
        else:
            self.plan.touches.append(cur["instrument_id"])
            action = ACTION_UNCHANGED
        self._report(d, merged, action, cur["instrument_id"], notes)

    def _same_registrant(self, cur: Row, d: Row) -> tuple[bool, list[str]]:
        """Is the active row the same instrument as the directory row? ``(True, notes)``
        or ``(False, [why it is a recycled ticker])``."""
        if cur.get("cik"):
            if cur["cik"] == d.get("cik"):
                return True, []
            # Across an ETF-flag flip the other class's precedence picks the other CIK on
            # file for the ticker (IA, SPCX): still this registrant. Flag unchanged, the
            # CIK the precedence picks IS the registrant.
            if cur.get("asset_class") != d.get("asset_class") and cur["cik"] in _ciks_seen(d):
                return True, []
            return False, [f"cik changed {cur['cik']} -> {d.get('cik')}: recycled ticker"]
        if d.get("cik"):
            return False, [f"cik {d['cik']} appeared on a row minted without one: recycled ticker"]
        # No CIK on either side: Tiingo's listing start and the name are the evidence.
        stored = cur.get("listing_date")
        moved = (
            d.get("listing_source") == LISTING_SOURCE_TIINGO
            and stored is not None
            and d["listing_date"] != stored
        )
        forward = (d["listing_date"] - stored).days if moved and d["listing_date"] > stored else 0
        agree = ident.names_agree(cur.get("name"), d.get("name"))
        if forward > LISTING_DATE_JUMP_DAYS:
            return False, [
                f"listing start moved forward {forward} days ({stored} -> "
                f"{d['listing_date']}): recycled ticker"
            ]
        if forward and not agree:
            return False, [
                f"name changed ({cur.get('name')!r} -> {d.get('name')!r}) and listing start "
                f"moved forward {forward} days: recycled ticker"
            ]
        notes = []
        if cur.get("name") != d.get("name"):
            notes.append(
                f"name changed, no cik on either side ({'agrees' if agree else 'DISAGREES'}): "
                f"{cur.get('name')!r} -> {d.get('name')!r}"
            )
        if forward:
            notes.append(
                f"listing start moved forward {forward} days ({stored} -> {d['listing_date']})"
            )
        elif moved:
            notes.append(
                f"listing start moved back {stored} -> {d['listing_date']} "
                "(tiingo extended history)"
            )
        return True, notes

    # ── arrivals and departures ──

    def resolve_arrivals(self) -> None:
        """Pair each arriving symbol with a departing row of the same identity (a RENAME)
        where the identity is unambiguous, else mint / reactivate; then deactivate what is
        left — except manual rows, which are only reported."""
        departing = [
            r for r in self.active_by_symbol.values() if r["instrument_id"] not in self.handled
        ]
        before_cik = Counter(r["cik"] for r in self.active_by_symbol.values() if r.get("cik"))
        after_cik = Counter(d["cik"] for d in self.desired if d.get("cik"))
        before_class = Counter(k for r in self.active_by_symbol.values() if (k := _class_key(r)))
        after_class = Counter(k for d in self.desired if (k := _class_key(d)))
        by_class = {
            k: r for r in departing if (k := _class_key(r)) and r["source"] != SOURCE_MANUAL
        }
        by_cik = {r["cik"]: r for r in departing if r.get("cik") and r["source"] != SOURCE_MANUAL}
        for d in self.arrivals:
            old: Row | None = None
            note = ""
            if (
                (ck := _class_key(d))
                and ck in by_class
                and before_class[ck] == 1 == after_class[ck]
            ):
                old = by_class[ck]
            elif d.get("cik") and d["cik"] in by_cik:
                cand = by_cik[d["cik"]]
                if before_cik[d["cik"]] == 1 == after_cik[d["cik"]]:
                    old = cand
                else:
                    note = (
                        f"possible rename of {cand['symbol']}, not paired (cik {d['cik']} has "
                        f"{before_cik[d['cik']]} active row(s) and {after_cik[d['cik']]} "
                        "directory listing(s))"
                    )
            if old is not None and old["instrument_id"] not in self.renamed:
                self._rename(old, d)
            else:
                self._mint_or_reactivate(d, [note] if note else [])
        for r in departing:
            if r["instrument_id"] in self.handled:
                continue
            if r["source"] == SOURCE_MANUAL:
                self.handled.add(r["instrument_id"])
                self._report_plain(
                    r,
                    ACTION_UNCHANGED,
                    "manual row absent from the directory: left active (never auto-deactivated)",
                )
            else:
                self._deactivate(r, "left the directory")

    def _rename(self, old: Row, d: Row) -> None:
        merged, notes = _merge(old, d)
        row = _full_row(
            old["instrument_id"],
            {**d, **merged},
            SOURCE_NASDAQ_TRADER,
            active=True,
            delisted_at=None,
        )
        self.plan.renames.append(row)
        self.handled.add(old["instrument_id"])
        self.renamed.add(old["instrument_id"])
        self._report(
            d,
            merged,
            ACTION_RENAME,
            old["instrument_id"],
            [f"rename {old['symbol']} -> {d['symbol']} (same registrant, uuid kept)", *notes],
        )

    def _mint_or_reactivate(self, d: Row, notes: list[str]) -> None:
        key = ident.instrument_key(d["asset_class"], d.get("cik"), d["symbol"], d["listing_date"])
        iid = str(ident.mint(key))
        prev = self.by_id.get(iid)
        why = "reactivated: same identity key as an inactive row"
        if prev is None and not d.get("cik"):
            prev = self._flickered(d)
            if prev is not None:
                why = (
                    f"reactivated: inactive no-cik row {prev['instrument_id']} carries this "
                    f"symbol and an agreeing name ({prev.get('name')!r})"
                )
        if prev is None:
            row = _full_row(iid, d, SOURCE_NASDAQ_TRADER, active=True, delisted_at=None)
            self.plan.inserts.append(row)
            self._report(d, d, ACTION_INSERT, iid, notes)
            return
        if prev["is_active"]:
            raise ValueError(
                f"{d['symbol']}: minted uuid {iid} is the ACTIVE row {prev['symbol']} — "
                "planner bookkeeping error"
            )
        merged, merge_notes = _merge(prev, d)
        row = _full_row(
            prev["instrument_id"],
            {**d, **merged},
            SOURCE_NASDAQ_TRADER,
            active=True,
            delisted_at=None,
        )
        self.plan.reactivations.append(row)
        self.handled.add(prev["instrument_id"])
        self._report(
            d, merged, ACTION_REACTIVATE, prev["instrument_id"], [why, *notes, *merge_notes]
        )

    def _flickered(self, d: Row) -> Row | None:
        """The latest-delisted inactive no-CIK row under this symbol whose name agrees —
        the same listing seen again after a gap, whatever run date its key carries."""
        cands = [
            r
            for r in self.by_symbol.get(d["symbol"], [])
            if not r["is_active"]
            and r["instrument_id"] not in self.deactivated
            and not r.get("cik")
            and ident.names_agree(r.get("name"), d.get("name"))
        ]
        return max(cands, key=lambda r: r.get("delisted_at") or date.min) if cands else None

    def _report(
        self, d: Row, merged: Mapping[str, Any], action: str, iid: str, notes: list[str]
    ) -> None:
        aliases = ident.aliases_for(d, self.tiingo)
        for source, spelling in aliases:
            self._want((source, spelling), iid, "")
        self.plan.report.append(
            ReportRow(
                symbol=d["symbol"],
                asset_class=merged["asset_class"],
                exchange=merged.get("exchange"),
                cik=merged.get("cik"),
                series_id=merged.get("series_id"),
                action=action,
                aliases=_alias_text(aliases),
                note="; ".join(n for n in notes if n),
                sec_conflict=d.get("sec_conflict"),
                name_agrees=d.get("name_agrees"),
            )
        )

    def _deactivate(self, cur: Row, note: str) -> None:
        self.plan.deactivations.append(
            {"instrument_id": cur["instrument_id"], "delisted_at": self.run_date}
        )
        self.handled.add(cur["instrument_id"])
        self.deactivated.add(cur["instrument_id"])
        self._report_plain(cur, ACTION_DEACTIVATE, note)

    def _report_plain(self, r: Row, action: str, note: str, aliases: str = "") -> None:
        """A report line from a row's own columns (nothing merged)."""
        self.plan.report.append(
            ReportRow(
                symbol=r["symbol"],
                asset_class=r["asset_class"],
                exchange=r.get("exchange"),
                cik=r.get("cik"),
                series_id=r.get("series_id"),
                action=action,
                aliases=aliases,
                note=note,
            )
        )

    # ── archive-only members ──

    def stooq_member(self, m: Row) -> None:
        """``m``: symbol (canonical), stooq_ticker, asset_class, exchange, first_bar, last_bar."""
        holders = self.by_symbol.get(m["symbol"], [])
        if holders:
            active = [h for h in holders if h["is_active"]]
            target = (
                active[0]
                if active
                else max(holders, key=lambda h: h.get("delisted_at") or date.min)
            )
            self._want(
                (ident.SOURCE_STOOQ, m["stooq_ticker"]), target["instrument_id"], "archive member"
            )
            self._report_plain(
                {**target, "symbol": m["symbol"]},
                ACTION_UNCHANGED,
                f"archive-only member aliased to existing row {target['instrument_id']}",
                _alias_text([(ident.SOURCE_STOOQ, m["stooq_ticker"])]),
            )
            return
        if m.get("first_bar") is None:
            self._report_plain(
                m,
                ACTION_UNCHANGED,
                "archive-only member with an empty file: no bars, no listing date, no row",
            )
            return
        desired = {
            "asset_class": m["asset_class"],
            "symbol": m["symbol"],
            "exchange": m.get("exchange"),
            "listing_date": m["first_bar"],
        }
        key = ident.instrument_key(m["asset_class"], None, m["symbol"], m["first_bar"])
        iid = str(ident.mint(key))
        self._want((ident.SOURCE_STOOQ, m["stooq_ticker"]), iid, "archive-only (delisted) member")
        row = _full_row(iid, desired, ident.SOURCE_STOOQ, active=False, delisted_at=m["last_bar"])
        self.plan.inserts.append(row)
        self._report_plain(
            desired,
            ACTION_INSERT,
            f"archive-only (delisted) member: bars {m['first_bar']} -> {m['last_bar']}, "
            "source=stooq, inactive",
            _alias_text([(ident.SOURCE_STOOQ, m["stooq_ticker"])]),
        )

    # ── aliases ──

    def _want(self, pair: tuple[str, str], iid: str, note: str) -> None:
        prev = self.wanted_aliases.get(pair)
        if prev is not None and prev[0] != iid:
            raise ValueError(
                f"alias {pair} claimed by two instruments this run: {prev[0]} and {iid}"
            )
        self.wanted_aliases[pair] = (iid, note)

    def finish_aliases(self) -> Plan:
        for (source, spelling), (iid, note) in sorted(self.wanted_aliases.items()):
            open_id = self.open_aliases.get((source, spelling))
            if open_id == iid:
                continue
            if open_id is not None:
                self.plan.alias_closes.append((source, spelling, open_id))
                note = (note + "; " if note else "") + f"moved from {open_id}"
            self.plan.alias_inserts.append((source, spelling, iid, note))
        # A renamed instrument's old spellings: closed (valid_to = run date) unless this run
        # wants the pair again (then it is either kept, or moved by the loop above).
        for (source, spelling), open_id in sorted(self.open_aliases.items()):
            if open_id in self.renamed and (source, spelling) not in self.wanted_aliases:
                self.plan.alias_closes.append((source, spelling, open_id))
        return self.plan


def plan(
    desired: Iterable[Row],
    stooq_members: Iterable[Row],
    existing: Iterable[Row],
    open_aliases: Mapping[tuple[str, str], str],
    tiingo_tickers: Collection[str],
    run_date: date,
    *,
    allow_mass_deactivation: bool = False,
) -> Plan:
    """Everything the script writes, in the order it must write it: deactivations first
    (they free the active-symbol slot), then renames, reactivations and inserts, then
    in-place updates and touches, then alias closes and inserts.

    ``desired``: the assembled directory frame's rows (``identity_frame.DESIRED_COLUMNS``);
    ``stooq_members``: archive members absent from the directory (symbol, stooq_ticker,
    asset_class, exchange, first_bar, last_bar); ``existing``: every ``instrument_master``
    row; ``open_aliases``: ``(source, source_symbol) → instrument_id`` for rows with
    ``valid_to IS NULL``; ``tiingo_tickers``: the tickers proven present in Tiingo's list.
    Raises :class:`MassDeactivationError` when the circuit breaker trips (nothing is planned
    past it).
    """
    p = _Planner(existing, open_aliases, tiingo_tickers, run_date)
    for d in desired:
        p.directory_row(d)
    p.resolve_arrivals()
    active = len(p.active_by_symbol)
    cap = min(int(MASS_DEACTIVATION_FRAC * active), MASS_DEACTIVATION_ROWS)
    if len(p.plan.deactivations) > cap and not allow_mass_deactivation:
        raise MassDeactivationError(len(p.plan.deactivations), cap, active)
    for m in stooq_members:
        p.stooq_member(m)
    return p.finish_aliases()
