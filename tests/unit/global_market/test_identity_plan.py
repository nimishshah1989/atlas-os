"""identity_plan: the diff rules, proven on REAL directory rows and the ids they mint.

Every desired row is a real 2026-09-04 record as ``identity_frame`` assembles it from the
snapshot (``conftest.py``); a scenario's "second value" is another real value from the same
files — the ticker's other CIK on file (ISRL, AEMC, IA, SPCX carry two), the ticker's other
Tiingo listing period (LEND 2019-05-09 → 2021-06-25 before 2026-05-18 →; AMAA 2026-06-26 →
06-30 before 06-30 →), a registrant's real historical spelling (ANTM → ELV 2022-06-28 and
FB → META 2022-06-09 per fja05680's ``sp500_ticker_start_end.csv``; QQQQ → QQQ 2011-03-23;
AGM$C, Farmer Mac's Series C preferred, Tiingo ``AGM-P-C`` 2014-06-19 → 2024-07-17), another
real row's name, or the FM's Stooq archive's own first/last bars. The "existing" tables are
what a previous run of the same planner produced, so every scenario starts from rows the
rules themselves minted. Pure: no DB, no network.

Dropped (cannot be built from real records): the two-instruments-one-alias clash — no real
member of the archive or row of the directory renders another row's alias.
"""

from __future__ import annotations

from dataclasses import astuple
from datetime import date

import pandas as pd
import pytest

from atlas.global_market import identity as ident
from atlas.global_market import identity_frame as frame_mod
from atlas.global_market import identity_plan as plan_mod
from atlas.global_market.identity_plan import Plan

pytestmark = pytest.mark.unit

DAY1 = date(2026, 9, 4)  # the snapshot's date; DAY2 / DAY3 the next weekly runs
DAY2 = date(2026, 9, 11)
DAY3 = date(2026, 9, 18)
SYMBOLS = (
    "SPY",
    "BRK.B",
    "AGM$D",
    "AGM$E",
    "AAPL",
    "BZZ",  # no SEC row, no Tiingo row → run-date fallback key
    "OWN",  # likewise (its real name is the "other name" below)
    "QQQ",
    "META",
    "ELV",
    "ISRL",
    "AEMC",
    "IA",
    "SPCX",
    "LEND",
    "AMAA",
)
Respell = str | tuple[str, str, str, str]  # plain, or (ACT, CQS, NASDAQ, SEC) spellings


@pytest.fixture(scope="module")
def files(nasdaq, other, company_tickers, company_tickers_mf, listings) -> dict:
    return {
        "nasdaq": nasdaq,
        "other": other,
        "ct": company_tickers,
        "mf": company_tickers_mf,
        "listings": listings,
    }


def _assemble(
    files: dict,
    run_date: date = DAY1,
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    respell: dict[str, Respell] | None = None,
    flip: tuple[str, ...] = (),
    drop_mf: tuple[str, ...] = (),
) -> list[dict]:
    """The desired rows for ``symbols`` through the real frame functions. ``respell`` writes
    a registrant's other real spelling into every file that names it; ``flip`` inverts the
    Nasdaq ETF flag; ``drop_mf`` removes a fund class from the MF file."""
    nq = files["nasdaq"].loc[files["nasdaq"]["symbol"].isin(symbols)].copy()
    ot = files["other"].loc[files["other"]["act_symbol"].isin(symbols)].copy()
    ct = files["ct"].copy()
    mf = files["mf"].loc[~files["mf"]["symbol"].isin(drop_mf)].copy()
    for old, new in (respell or {}).items():
        act, cqs, nas, sec = (new,) * 4 if isinstance(new, str) else new
        old_cqs = ot.loc[ot["act_symbol"] == old, "cqs_symbol"]
        old_sec = ident.sec_spelling(old_cqs.item()) if len(old_cqs) else old
        row = ot["act_symbol"] == old
        ot.loc[row, ["act_symbol", "cqs_symbol", "nasdaq_symbol"]] = [act, cqs, nas]
        nq.loc[nq["symbol"] == old, "symbol"] = act
        ct.loc[ct["ticker"] == old_sec, "ticker"] = sec
        mf.loc[mf["symbol"] == old, "symbol"] = act
    for s in flip:
        nq.loc[nq["symbol"] == s, "etf"] = ~nq.loc[nq["symbol"] == s, "etf"]
        ot.loc[ot["act_symbol"] == s, "etf"] = ~ot.loc[ot["act_symbol"] == s, "etf"]
    frame = frame_mod.directory_frame(nq, ot)
    frame = frame_mod.attach_sec(frame, ct, mf)
    frame = frame_mod.attach_listing_dates(frame, files["listings"], run_date)
    return frame.to_dict("records")


@pytest.fixture(scope="module")
def desired(files: dict) -> list[dict]:
    rows = _assemble(files)
    assert len(rows) == len(SYMBOLS)
    return rows


def _by_symbol(rows: list[dict]) -> dict[str, dict]:
    return {r["symbol"]: r for r in rows}


def _existing_from(p: Plan) -> list[dict]:
    """What instrument_master holds after a plan is applied to an empty table."""
    return [dict(r) for r in p.inserts + p.reactivations + p.renames]


def _apply(existing: list[dict], p: Plan) -> list[dict]:
    """The table after ``p`` is applied to ``existing`` (what the script's apply() does)."""
    by_id = {r["instrument_id"]: dict(r) for r in existing}
    for d in p.deactivations:
        by_id[d["instrument_id"]].update(is_active=False, delisted_at=d["delisted_at"])
    for r in p.renames + p.reactivations + p.inserts:
        by_id[r["instrument_id"]] = dict(r)
    for u in p.updates:
        by_id[u["instrument_id"]].update(u)
    return list(by_id.values())


def _open_aliases_from(p: Plan, before: dict | None = None) -> dict[tuple[str, str], str]:
    out = dict(before or {})
    for s, v, _old in p.alias_closes:
        out.pop((s, v), None)
    for s, v, iid, _n in p.alias_inserts:
        out[(s, v)] = iid
    return out


def _with(rows: list[dict], symbol: str, **changes) -> list[dict]:
    return [{**d, **changes} if d["symbol"] == symbol else d for d in rows]


def _without(rows: list[dict], *symbols: str) -> list[dict]:
    return [d for d in rows if d["symbol"] not in symbols]


def _report(p: Plan, symbol: str, action: str | None = None) -> plan_mod.ReportRow:
    return next(
        r for r in p.report if r.symbol == symbol and (action is None or r.action == action)
    )


def _plan(
    desired,
    existing=(),
    aliases=None,
    tiingo=frozenset(),
    run_date=DAY2,
    *,
    allow_mass_deactivation: bool = True,
) -> Plan:
    """On a 16-row table two percent is zero rows, so the circuit breaker is off here: every
    scenario asserts its EXACT deactivations instead, and the breaker has its own test on
    the full 13,154-row build."""
    return plan_mod.plan(
        desired,
        [],
        list(existing),
        aliases or {},
        tiingo,
        run_date,
        allow_mass_deactivation=allow_mass_deactivation,
    )


# ── first run on an empty table ──


def test_first_run_inserts_every_row_with_the_documented_key(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    p = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    assert p.counts() == {
        "insert": len(SYMBOLS),
        "rename": 0,
        "reactivate": 0,
        "update": 0,
        "unchanged": 0,
        "deactivate": 0,
        "alias_insert": sum(len(r.aliases.split(";")) for r in p.report),
        "alias_close": 0,
    }
    rows = _by_symbol(p.inserts)
    assert rows["SPY"]["instrument_id"] == str(ident.mint("us:etf:0000884394:SPY"))
    assert rows["BRK.B"]["instrument_id"] == str(ident.mint("us:stock:0001067983:BRK.B"))
    assert rows["AGM$D"]["instrument_id"] == str(ident.mint("us:stock:0000845877:AGM$D"))
    assert rows["AAPL"]["instrument_id"] == str(ident.mint("us:stock:0000320193:AAPL"))
    assert rows["QQQ"]["instrument_id"] == str(ident.mint("us:etf:0001067839:QQQ"))
    assert rows["ISRL"]["instrument_id"] == str(ident.mint("us:etf:0002081107:ISRL"))  # MF file
    assert rows["IA"]["instrument_id"] == str(
        ident.mint("us:stock:0000836690:IA")
    )  # not the MF CIK
    assert rows["BZZ"]["instrument_id"] == str(ident.mint("us:etf:BZZ:2026-09-04"))
    assert rows["LEND"]["instrument_id"] == str(ident.mint("us:etf:LEND:2026-05-18"))
    assert all(r["is_active"] and r["delisted_at"] is None for r in p.inserts)
    assert all(r["source"] == "nasdaq_trader" for r in p.inserts)
    assert rows["SPY"]["listing_date"] == date(1993, 1, 29)
    report = {r.symbol: r for r in p.report}
    assert report["SPY"].action == "insert" and report["SPY"].key_kind == "cik"
    assert report["BZZ"].key_kind == "fallback"
    assert (
        report["BRK.B"].aliases
        == "stooq:BRK-B.US;tiingo:BRK-B;sec:BRK-B;nasdaq_symbol:BRK.B;cqs:BRK.B"
    )
    assert report["AGM$D"].aliases == (
        "stooq:AGM_D.US;tiingo:AGM-P-D;sec:AGM-PD;nasdaq_symbol:AGM-D;cqs:AGMpD"
    )
    assert ("stooq", "AGM_D.US", rows["AGM$D"]["instrument_id"], "") in p.alias_inserts
    # The frame's conflict and name columns travel into the report.
    assert report["IA"].sec_conflict == "company_tickers 0000836690; company_tickers_mf 0001592900"
    assert report["AEMC"].name_agrees is False and report["AAPL"].name_agrees is True
    assert plan_mod.REPORT_COLUMNS == (
        "symbol",
        "asset_class",
        "exchange",
        "cik",
        "series_id",
        "key_kind",
        "action",
        "aliases",
        "note",
        "sec_conflict",
        "name_agrees",
    )
    assert astuple(report["IA"])[:6] == ("IA", "stock", "NASDAQ", "0000836690", None, "cik")


# ── re-run: idempotent ──


def test_rerun_on_the_same_files_plans_nothing_and_keeps_every_uuid(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    second = _plan(desired, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.counts() == {
        "insert": 0,
        "rename": 0,
        "reactivate": 0,
        "update": 0,
        "unchanged": len(SYMBOLS),
        "deactivate": 0,
        "alias_insert": 0,
        "alias_close": 0,
    }
    assert sorted(second.touches) == sorted(r["instrument_id"] for r in first.inserts)
    assert {r.action for r in second.report} == {"unchanged"}


def test_a_listing_start_moving_back_updates_in_place_without_reminting(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """LEND was minted with Tiingo's current period (2026-05-18); when Tiingo extends its
    history to the earlier real period's start (2019-05-09) the row's listing_date moves
    back but the uuid — hashed from 2026-05-18 — stays."""
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    lend_id = _by_symbol(first.inserts)["LEND"]["instrument_id"]
    earlier = files["listings"]  # the real earlier period's start is in the raw Tiingo rows
    assert date(2019, 5, 9) < earlier.set_index("ticker").loc["LEND", "start_date"]
    later = _with(desired, "LEND", listing_date=date(2019, 5, 9))
    second = _plan(later, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.counts()["insert"] == 0 and second.counts()["update"] == 1
    (upd,) = second.updates
    assert upd["instrument_id"] == lend_id and upd["listing_date"] == date(2019, 5, 9)
    assert "moved back" in _report(second, "LEND").note


def test_a_run_date_fallback_never_overwrites_a_stored_listing_date(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    no_tiingo = [
        {**d, "listing_date": DAY2, "listing_source": "run_date", "tiingo_ticker": None}
        for d in desired
    ]
    second = _plan(no_tiingo, _existing_from(first), _open_aliases_from(first))
    assert second.counts()["update"] == 0 and second.counts()["unchanged"] == len(SYMBOLS)


# ── the registrant is the identity ──


def test_a_cik_that_appears_on_a_no_cik_row_is_a_recycled_ticker(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """ISRL listed 2026-09-01; had the SEC files not caught up with it on the first run it
    would carry the fallback key — the run that brings its real CIK (0002081107, the MF
    file) mints a new instrument and retires the fallback row."""
    launch = _with(
        desired,
        "ISRL",
        cik=None,
        series_id=None,
        class_id=None,
        sec_ticker=None,
        sec_source=None,
        sec_conflict=None,
        name_agrees=None,
    )
    first = _plan(launch, tiingo=tiingo_tickers, run_date=DAY1)
    old_id = _by_symbol(first.inserts)["ISRL"]["instrument_id"]
    assert old_id == str(ident.mint("us:etf:ISRL:2026-09-01"))
    second = _plan(desired, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.deactivations == [{"instrument_id": old_id, "delisted_at": DAY2}]
    (new,) = second.inserts
    assert new["instrument_id"] == str(ident.mint("us:etf:0002081107:ISRL"))
    assert "recycled ticker" in _report(second, "ISRL", "deactivate").note
    assert ("stooq", "ISRL.US", old_id) in second.alias_closes  # the archive file moves
    assert (
        "stooq",
        "ISRL.US",
        new["instrument_id"],
        "moved from " + old_id,
    ) in second.alias_inserts


def test_a_cik_the_sec_files_drop_is_a_recycled_ticker_and_its_return_reactivates(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    spy_id = _by_symbol(first.inserts)["SPY"]["instrument_id"]
    dropped = _with(
        desired,
        "SPY",
        cik=None,
        series_id=None,
        class_id=None,
        sec_ticker=None,
        sec_source=None,
        name_agrees=None,
    )
    second = _plan(dropped, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.deactivations == [{"instrument_id": spy_id, "delisted_at": DAY2}]
    (fallback,) = second.inserts
    assert fallback["instrument_id"] == str(ident.mint("us:etf:SPY:1993-01-29"))
    assert "cik changed 0000884394 -> None" in _report(second, "SPY", "deactivate").note
    # The files carry the CIK again: the original row's key mints its own uuid → reactivated;
    # the fallback holder is retired. Nothing is minted twice.
    table = _apply(_existing_from(first), second)
    third = _plan(
        desired,
        table,
        _open_aliases_from(second, _open_aliases_from(first)),
        tiingo_tickers,
        run_date=DAY3,
    )
    assert third.counts()["insert"] == 0 and third.counts()["reactivate"] == 1
    assert third.reactivations[0]["instrument_id"] == spy_id
    assert third.deactivations == [
        {"instrument_id": fallback["instrument_id"], "delisted_at": DAY3}
    ]
    assert sum(1 for r in _apply(table, third) if r["symbol"] == "SPY" and r["is_active"]) == 1


def test_a_different_registrant_under_the_same_symbol_is_a_recycled_ticker(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """ISRL and AEMC carry two real CIKs across the SEC files. Once the MF file no longer
    lists the fund class, the ticker resolves to the OTHER registrant (Israel Acquisitions
    Corp 0001915328; C2 Blockchain 0001882781): a different instrument."""
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    ids = {s: r["instrument_id"] for s, r in _by_symbol(first.inserts).items()}
    changed = _assemble(files, drop_mf=("ISRL", "AEMC"))
    by = _by_symbol(changed)
    assert (by["ISRL"]["cik"], by["ISRL"]["sec_conflict"]) == ("0001915328", None)
    assert (by["AEMC"]["cik"], by["AEMC"]["name_agrees"]) == ("0001882781", False)
    second = _plan(changed, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert sorted(d["instrument_id"] for d in second.deactivations) == sorted(
        [ids["ISRL"], ids["AEMC"]]
    )
    new = _by_symbol(second.inserts)
    assert new["ISRL"]["instrument_id"] == str(ident.mint("us:etf:0001915328:ISRL"))
    assert new["AEMC"]["instrument_id"] == str(ident.mint("us:etf:0001882781:AEMC"))
    assert "cik changed 0002081107 -> 0001915328" in _report(second, "ISRL", "deactivate").note


def test_an_etf_flag_flip_on_the_same_registrant_is_an_update_in_place(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """IA and SPCX are stock-flagged by Nasdaq while the MF file carries a fund class under
    each ticker (another CIK). Flipping the flag makes the MF file the first lookup, but the
    stored CIK is still on file under the ticker (sec_conflict): same registrant, updated in
    place, uuid and CIK kept. QQQ flipped to stock resolves to the same CIK either way."""
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    ids = {s: r["instrument_id"] for s, r in _by_symbol(first.inserts).items()}
    flipped = _assemble(files, flip=("IA", "SPCX", "QQQ"))
    by = _by_symbol(flipped)
    assert (by["IA"]["asset_class"], by["IA"]["cik"]) == ("etf", "0001592900")  # MF-first
    assert (by["QQQ"]["asset_class"], by["QQQ"]["cik"], by["QQQ"]["series_id"]) == (
        "stock",
        "0001067839",
        None,
    )
    second = _plan(flipped, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.counts()["insert"] == 0 and second.counts()["deactivate"] == 0
    assert second.counts()["update"] == 3
    upd = {u["instrument_id"]: u for u in second.updates}
    assert upd[ids["IA"]]["asset_class"] == "etf" and upd[ids["IA"]]["cik"] == "0000836690"
    assert upd[ids["IA"]]["series_id"] is None  # the other registrant's class is not ours
    assert upd[ids["SPCX"]]["cik"] == "0001181412"
    note = _report(second, "IA").note
    assert "asset_class stock -> etf" in note and "stored cik 0000836690 kept" in note
    # QQQ: same CIK, series/class kept from the stored row, class flipped with a note.
    assert upd[ids["QQQ"]]["asset_class"] == "stock"
    assert upd[ids["QQQ"]]["series_id"] == "S000101292"
    assert "asset_class etf -> stock" in _report(second, "QQQ").note


# ── delisting, recycling after a gap, reactivation ──


def test_a_symbol_that_leaves_the_directory_is_deactivated_with_the_run_date(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    second = _plan(
        _without(desired, "BZZ"), _existing_from(first), _open_aliases_from(first), tiingo_tickers
    )
    bzz_id = _by_symbol(first.inserts)["BZZ"]["instrument_id"]
    assert second.deactivations == [{"instrument_id": bzz_id, "delisted_at": DAY2}]
    assert second.counts()["alias_close"] == 0  # its aliases stay open: history keeps mapping
    gone = _report(second, "BZZ")
    assert gone.action == "deactivate" and gone.note == "left the directory"


def test_a_manual_row_absent_from_the_directory_is_reported_never_deactivated(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    existing = [
        {**r, "source": "manual"} if r["symbol"] == "BZZ" else r for r in _existing_from(first)
    ]
    second = _plan(_without(desired, "BZZ"), existing, _open_aliases_from(first), tiingo_tickers)
    assert second.counts()["deactivate"] == 0
    row = _report(second, "BZZ")
    assert row.action == "unchanged" and "manual row" in row.note


def test_a_recycled_ticker_after_a_gap_is_a_new_instrument_and_the_old_one_stays_inactive(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """The real ISRL history in three weekly runs: the SPAC (Israel Acquisitions Corp,
    0001915328 — company_tickers.json still lists it) holds the ticker, delists, then the
    ETF (0002081107) lists under it."""
    spac_rows = _assemble(files, drop_mf=("ISRL",))
    first = _plan(spac_rows, tiingo=tiingo_tickers, run_date=DAY1)
    old_id = _by_symbol(first.inserts)["ISRL"]["instrument_id"]
    assert old_id == str(ident.mint("us:etf:0001915328:ISRL"))
    second = _plan(
        _without(spac_rows, "ISRL"),
        _existing_from(first),
        _open_aliases_from(first),
        tiingo_tickers,
    )
    assert second.counts()["deactivate"] == 1
    table = _apply(_existing_from(first), second)
    third = _plan(desired, table, _open_aliases_from(first), tiingo_tickers, run_date=DAY3)
    (new,) = third.inserts
    assert new["symbol"] == "ISRL" and new["instrument_id"] != old_id
    assert new["instrument_id"] == str(ident.mint("us:etf:0002081107:ISRL"))
    assert third.counts()["deactivate"] == 0  # the old holder is already inactive
    # The old holder's aliases move to the new instrument: closed, then re-opened.
    assert ("stooq", "ISRL.US", old_id) in third.alias_closes
    assert any(
        s == "stooq" and v == "ISRL.US" and iid == new["instrument_id"]
        for s, v, iid, _ in third.alias_inserts
    )
    isrl = [r for r in _apply(table, third) if r["symbol"] == "ISRL"]
    assert len(isrl) == 2 and sum(1 for r in isrl if r["is_active"]) == 1


def test_the_same_registrant_relisting_reactivates_its_old_row(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    spy_id = _by_symbol(first.inserts)["SPY"]["instrument_id"]
    existing = _existing_from(first)
    for row in existing:
        if row["instrument_id"] == spy_id:
            row.update(is_active=False, delisted_at=DAY2)
    third = _plan(desired, existing, _open_aliases_from(first), tiingo_tickers, run_date=DAY3)
    assert third.counts()["insert"] == 0 and third.counts()["reactivate"] == 1
    (row,) = third.reactivations
    assert row["instrument_id"] == spy_id and row["is_active"] and row["delisted_at"] is None
    spy = _report(third, "SPY")
    assert spy.action == "reactivate" and "same identity key" in spy.note


def test_a_flickered_no_cik_row_is_reactivated_whatever_its_run_date_key(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """BZZ (no SEC row, no Tiingo row) is keyed on the run date it was first seen. Out of
    one weekly file and back in the next, it would mint a NEW key — but it is the same
    listing under the same name, so the old row is reactivated instead."""
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    bzz_id = _by_symbol(first.inserts)["BZZ"]["instrument_id"]
    second = _plan(
        _without(desired, "BZZ"), _existing_from(first), _open_aliases_from(first), tiingo_tickers
    )
    table = _apply(_existing_from(first), second)
    back = _with(desired, "BZZ", listing_date=DAY3)  # a run-date key would now be 2026-09-18
    third = _plan(back, table, _open_aliases_from(first), tiingo_tickers, run_date=DAY3)
    assert third.counts() == {**third.counts(), "insert": 0, "reactivate": 1, "deactivate": 0}
    (row,) = third.reactivations
    assert row["instrument_id"] == bzz_id and row["is_active"] and row["delisted_at"] is None
    assert row["listing_date"] == DAY1  # the first sighting stays the listing date
    assert "agreeing name" in _report(third, "BZZ").note
    # Under a DIFFERENT name (OWN's real name, no token in common) it is a new instrument.
    other_name = _by_symbol(desired)["OWN"]["name"]
    renamed = _with(back, "BZZ", name=other_name)
    fourth = _plan(renamed, table, _open_aliases_from(first), tiingo_tickers, run_date=DAY3)
    (new,) = fourth.inserts
    assert new["symbol"] == "BZZ" and new["instrument_id"] == str(
        ident.mint("us:etf:BZZ:2026-09-18")
    )
    assert fourth.counts()["reactivate"] == 0


def test_a_listing_start_jumping_forward_is_a_recycle_and_a_small_move_an_update(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """No CIK on either side: LEND's earlier real period (2019-05-09 → 2021-06-25, the
    Amplify lending ETF) then its current one (2026-05-18 →, SEI's) — a forward jump of
    years, a recycled ticker. AMAA's two periods start four days apart (2026-06-26, 06-30):
    an update with a note. AMAA under another real name over that small move: a recycle."""
    earlier = _with(
        _with(desired, "LEND", listing_date=date(2019, 5, 9)),
        "AMAA",
        listing_date=date(2026, 6, 26),
    )
    first = _plan(earlier, tiingo=tiingo_tickers, run_date=DAY1)
    ids = {s: r["instrument_id"] for s, r in _by_symbol(first.inserts).items()}
    second = _plan(desired, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.deactivations == [{"instrument_id": ids["LEND"], "delisted_at": DAY2}]
    assert _by_symbol(second.inserts)["LEND"]["instrument_id"] == str(
        ident.mint("us:etf:LEND:2026-05-18")
    )
    assert "moved forward 2566 days" in _report(second, "LEND", "deactivate").note
    (upd,) = second.updates
    assert upd["instrument_id"] == ids["AMAA"] and upd["listing_date"] == date(2026, 6, 30)
    assert "moved forward 4 days" in _report(second, "AMAA").note
    other_name = _by_symbol(desired)["OWN"]["name"]
    third = _plan(
        _with(desired, "AMAA", name=other_name),
        _existing_from(first),
        _open_aliases_from(first),
        tiingo_tickers,
    )
    assert {d["instrument_id"] for d in third.deactivations} == {ids["LEND"], ids["AMAA"]}
    assert "name changed" in _report(third, "AMAA", "deactivate").note


def test_a_name_change_alone_on_a_no_cik_row_is_an_update_with_a_note(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    other_name = _by_symbol(desired)["OWN"]["name"]
    second = _plan(
        _with(desired, "BZZ", name=other_name),
        _existing_from(first),
        _open_aliases_from(first),
        tiingo_tickers,
    )
    assert second.counts()["deactivate"] == 0 and second.counts()["update"] == 1
    row = _report(second, "BZZ")
    assert row.action == "update" and "DISAGREES" in row.note


# ── renames ──


def test_a_registrant_that_changes_ticker_keeps_its_uuid(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """Anthem → Elevance Health (ANTM → ELV, 2022-06-28; CIK 0001156039) and Facebook →
    Meta (FB → META, 2022-06-09; CIK 0001326801): each registrant's old spelling in the
    directory and in company_tickers.json, then the real files."""
    before = _assemble(files, respell={"ELV": "ANTM", "META": "FB"})
    first = _plan(before, tiingo=tiingo_tickers, run_date=DAY1)
    ids = {s: r["instrument_id"] for s, r in _by_symbol(first.inserts).items()}
    assert ids["ANTM"] == str(ident.mint("us:stock:0001156039:ANTM"))
    assert ids["FB"] == str(ident.mint("us:stock:0001326801:FB"))
    second = _plan(desired, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.counts()["rename"] == 2
    assert second.counts()["insert"] == 0 and second.counts()["deactivate"] == 0
    renamed = _by_symbol(second.renames)
    assert renamed["ELV"]["instrument_id"] == ids["ANTM"] and renamed["ELV"]["is_active"]
    assert renamed["META"]["instrument_id"] == ids["FB"]
    row = _report(second, "ELV")
    assert row.action == "rename" and "rename ANTM -> ELV" in row.note
    # The old spellings are closed on the same instrument; the new ones opened.
    closed = {(s, v) for s, v, i in second.alias_closes if i == ids["ANTM"]}
    assert closed == {
        ("stooq", "ANTM.US"),
        ("sec", "ANTM"),
        ("nasdaq_symbol", "ANTM"),
        ("cqs", "ANTM"),
    }
    opened = {(s, v) for s, v, i, _n in second.alias_inserts if i == ids["ANTM"]}
    assert opened == {
        ("stooq", "ELV.US"),
        ("tiingo", "ELV"),
        ("sec", "ELV"),
        ("nasdaq_symbol", "ELV"),
        ("cqs", "ELV"),
    }
    # And the run after is a plain re-run.
    table = _apply(_existing_from(first), second)
    third = _plan(
        desired,
        table,
        _open_aliases_from(second, _open_aliases_from(first)),
        tiingo_tickers,
        run_date=DAY3,
    )
    assert third.counts()["unchanged"] == len(SYMBOLS) and third.counts()["alias_insert"] == 0


def test_a_fund_that_changes_ticker_is_paired_by_its_class_id(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """QQQQ → QQQ (2011-03-23): the same CIK, series and class under the old spelling in
    every file that names it — paired even though a trust's CIK may carry many funds."""
    before = _assemble(files, respell={"QQQ": "QQQQ"})
    first = _plan(before, tiingo=tiingo_tickers, run_date=DAY1)
    old = _by_symbol(first.inserts)["QQQQ"]
    assert (old["cik"], old["series_id"], old["class_id"]) == (
        "0001067839",
        "S000101292",
        "C000271435",
    )
    second = _plan(desired, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.counts()["rename"] == 1 and second.counts()["insert"] == 0
    assert second.renames[0]["instrument_id"] == old["instrument_id"]
    assert second.renames[0]["symbol"] == "QQQ"


def test_an_ambiguous_rename_under_a_multi_listing_cik_is_not_paired(
    files: dict, desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    """Farmer Mac (CIK 0000845877) lists several preferreds. Its redeemed Series C (AGM$C;
    Tiingo AGM-P-C 2014-06-19 → 2024-07-17) leaving while Series E appears is NOT a rename:
    two securities of one registrant. The new row is inserted with a note."""
    before = _assemble(files, respell={"AGM$E": ("AGM$C", "AGMpC", "AGM-C", "AGM-PC")})
    first = _plan(before, tiingo=tiingo_tickers, run_date=DAY1)
    ids = {s: r["instrument_id"] for s, r in _by_symbol(first.inserts).items()}
    assert ids["AGM$C"] == str(ident.mint("us:stock:0000845877:AGM$C"))
    second = _plan(desired, _existing_from(first), _open_aliases_from(first), tiingo_tickers)
    assert second.counts()["rename"] == 0
    assert second.deactivations == [{"instrument_id": ids["AGM$C"], "delisted_at": DAY2}]
    (new,) = second.inserts
    assert new["instrument_id"] == str(ident.mint("us:stock:0000845877:AGM$E"))
    assert _report(second, "AGM$E").note == (
        "possible rename of AGM$C, not paired (cik 0000845877 has 2 active row(s) and 2 "
        "directory listing(s))"
    )


# ── the circuit breaker ──


def test_more_deactivations_than_a_weekly_file_can_carry_are_refused(
    desired: list[dict], tiingo_tickers: frozenset[str], request: pytest.FixtureRequest
) -> None:
    """Against the full 2026-09-04 build (13,154 active rows; cap = min(2 percent, 200) =
    200): a directory missing 300 rows is refused, 150 pass, --allow overrides."""
    full = request.getfixturevalue("desired_frame")
    rows = full.to_dict("records")
    first = _plan(rows, tiingo=tiingo_tickers, run_date=DAY1)
    existing = _existing_from(first)
    assert len(existing) == 13154
    aliases = _open_aliases_from(first)
    with pytest.raises(plan_mod.MassDeactivationError, match="300 of 13,154") as e:
        _plan(rows[300:], existing, aliases, tiingo_tickers, allow_mass_deactivation=False)
    assert (e.value.count, e.value.cap) == (300, 200)
    allowed = _plan(rows[300:], existing, aliases, tiingo_tickers)
    assert allowed.counts()["deactivate"] == 300
    fine = _plan(rows[150:], existing, aliases, tiingo_tickers, allow_mass_deactivation=False)
    assert fine.counts()["deactivate"] == 150


@pytest.fixture(scope="module")
def desired_frame(with_sec: pd.DataFrame, listings: pd.DataFrame) -> pd.DataFrame:
    return frame_mod.attach_listing_dates(with_sec, listings, DAY1)


# ── archive-only members (real spans from the FM's 2026-09-04 d_us_txt.zip) ──


def _member(symbol: str, ticker: str, kind: str, exchange: str, first, last) -> dict:
    return {
        "symbol": symbol,
        "stooq_ticker": ticker,
        "asset_class": kind,
        "exchange": exchange,
        "first_bar": first,
        "last_bar": last,
    }


# alot.us.txt: AstroNova, 5,142 bars 2005-02-25 → 2026-08-26, absent from the directory.
ALOT = _member("ALOT", "ALOT.US", "stock", "NASDAQ", date(2005, 2, 25), date(2026, 8, 26))
# bzz.us.txt: 58 bars 2026-06-08 → 2026-09-03 (the archive files it under "nyse stocks").
BZZ = _member("BZZ", "BZZ.US", "stock", "NYSE", date(2026, 6, 8), date(2026, 9, 3))
# albt.us.txt: an empty file (0 bytes) of a name absent from the directory.
ALBT = _member("ALBT", "ALBT.US", "stock", "NASDAQ", None, None)


def test_an_archive_only_member_becomes_an_inactive_row_under_the_fallback_key(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    p = plan_mod.plan(desired, [ALOT], [], {}, tiingo_tickers, DAY1)
    row = _by_symbol(p.inserts)["ALOT"]
    assert row["instrument_id"] == str(ident.mint("us:stock:ALOT:2005-02-25"))
    assert row["is_active"] is False and row["delisted_at"] == date(2026, 8, 26)
    assert row["source"] == "stooq" and row["listing_date"] == date(2005, 2, 25)
    assert (
        "stooq",
        "ALOT.US",
        row["instrument_id"],
        "archive-only (delisted) member",
    ) in p.alias_inserts
    again = plan_mod.plan(
        desired, [ALOT], _existing_from(p), _open_aliases_from(p), tiingo_tickers, DAY2
    )
    # The row now carries the symbol, so the member is aliased to it — no second row.
    assert again.counts()["insert"] == 0 and again.counts()["alias_insert"] == 0
    note = _report(again, "ALOT")
    assert note.action == "unchanged" and row["instrument_id"] in note.note


def test_an_archive_member_of_a_delisted_directory_symbol_is_aliased_not_duplicated(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    first = _plan(desired, tiingo=tiingo_tickers, run_date=DAY1)
    bzz_id = _by_symbol(first.inserts)["BZZ"]["instrument_id"]
    second = plan_mod.plan(
        _without(desired, "BZZ"),
        [BZZ],
        _existing_from(first),
        _open_aliases_from(first),
        tiingo_tickers,
        DAY2,
        allow_mass_deactivation=True,  # a 16-row table: see _plan
    )
    assert second.counts()["insert"] == 0 and second.counts()["deactivate"] == 1
    note = next(r for r in second.report if r.symbol == "BZZ" and "archive-only" in r.note)
    assert bzz_id in note.note  # aliased to the (now inactive) directory row


def test_an_empty_archive_file_makes_no_row(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    p = plan_mod.plan(desired, [ALBT], [], {}, tiingo_tickers, DAY1)
    assert "ALBT" not in _by_symbol(p.inserts)
    assert "empty file" in _report(p, "ALBT").note


# ── bookkeeping guards ──


def test_the_plan_rejects_two_active_rows_for_one_symbol(
    desired: list[dict], tiingo_tickers: frozenset[str]
) -> None:
    existing = _existing_from(_plan(desired, tiingo=tiingo_tickers, run_date=DAY1))
    with pytest.raises(ValueError, match="two ACTIVE rows"):
        _plan(desired, [*existing, dict(existing[0])], {}, tiingo_tickers)


def test_pandas_missing_values_are_read_as_none(
    tiingo_tickers: frozenset[str], desired: list[dict]
) -> None:
    frame = pd.DataFrame(desired)
    p = _plan(frame.to_dict("records"), tiingo=tiingo_tickers, run_date=DAY1)
    assert _by_symbol(p.inserts)["BZZ"]["cik"] is None
