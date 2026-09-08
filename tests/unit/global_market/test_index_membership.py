"""The membership logic over REAL rows: the pure module and the script's file-level pieces.

Identity rows come from the real 2026-09-04 directories (``scaffold_identity``), the holdings
and the sector files are the LIVE SSGA workbooks (``conftest`` — nothing of SSGA's is
committed; those tests are ``live``), the spells are the committed MIT-licensed ``start_end``
copy (``unit``). Counts that depend on the live file are computed from it and printed beside
what the 2026-09-03 file held. Where a code path needs "a member that left" or "a stale
row", the test hands the planner a SUBSET of the real rows — never an invented row, weight
or date: RDDT, FERG and VMRK have no history spell because they joined after the file's last
row, and that is exactly the state the tests use them in.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from atlas.global_market import identity
from atlas.global_market import index_membership as imx
from atlas.global_market.providers.sp500_history import START_END_ENDPOINT, parse_start_end
from atlas.global_market.providers.ssga import sector_by_membership
from tests.unit.global_market.live_files import FIXTURES
from tests.unit.global_market.scaffold_identity import scaffold_rows
from tests.unit.global_market.script_loader import load_global_script

im = load_global_script("ingest_index_membership")

START_END = FIXTURES / "index" / START_END_ENDPOINT
HISTORY = ("AAPL", "NVDA", "MSFT")  # the scaffold members fja05680 knows
_alias = identity.stooq_spelling("AAPL")  # AAPL.US — P1-A's own rendering, not typed here
assert _alias is not None
AAPL_ALIAS: str = _alias

unit, live = pytest.mark.unit, pytest.mark.live


@pytest.fixture(scope="module")
def as_of(spy_holdings: tuple[date, pd.DataFrame]) -> date:
    return spy_holdings[0]


@pytest.fixture(scope="module")
def holdings(spy_holdings: tuple[date, pd.DataFrame]) -> pd.DataFrame:
    return spy_holdings[1]


@pytest.fixture(scope="module")
def sector_map(holdings: pd.DataFrame, sector_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return sector_by_membership(holdings, sector_frames)


@pytest.fixture(scope="module")
def spells() -> pd.DataFrame:
    return parse_start_end(START_END.read_text())


@pytest.fixture(scope="module")
def ids() -> dict[str, str]:
    return {r.symbol: r.instrument_id for r in scaffold_rows()}


@pytest.fixture(scope="module")
def ident(ids: dict[str, str]) -> Any:
    rows = [imx.Instrument(iid, sym, True, None, None) for sym, iid in ids.items()]
    return imx.build_identity(rows, {AAPL_ALIAS: ids["AAPL"]})


@pytest.fixture(scope="module")
def expected_members(holdings: pd.DataFrame, ids: dict[str, str]) -> dict[str, str]:
    """The scaffold symbols that are in today's file (all six on 2026-09-03; SPY never)."""
    tickers = set(holdings["ticker"].dropna())
    return {s: i for s, i in ids.items() if s in tickers}


@pytest.fixture(scope="module")
def weights(holdings: pd.DataFrame, ident: Any) -> dict[str, Decimal]:
    return im.resolve_holdings(holdings, ident, im.new_report())[0]


@pytest.fixture(scope="module")
def history_rows(spells: pd.DataFrame, ident: Any, ids: dict[str, str]) -> list[imx.Interval]:
    """What a history pass writes from the committed file for the scaffold: AAPL, NVDA and
    MSFT open since HISTORY_START (their spells start in 1996/2001/1994, clipped)."""
    w = imx.window_spells(spells, imx.HISTORY_START, date(2026, 9, 3))
    plan = imx.plan_history(im.resolve_history(w, ident, im.new_report()), [])
    assert plan.deletes == [] and plan.notes == []
    assert {r.instrument_id for r in plan.rows} == {ids[s] for s in HISTORY}
    return plan.rows


# ── gates ──


@live
def test_the_holdings_gate_accepts_the_live_file_and_refuses_a_truncated_one(
    holdings: pd.DataFrame,
) -> None:
    n, total, problems = im.holdings_gate(holdings)
    print(f"live: {n} equity rows, Σ weight_frac {total} (503 / 0.99936168 on 2026-09-03)")
    assert im.MEMBERS_MIN <= n <= im.MEMBERS_MAX and problems == []
    assert im.WEIGHT_SUM_MIN <= total <= im.WEIGHT_SUM_MAX
    n_cut, total_cut, problems_cut = im.holdings_gate(holdings.iloc[:250])  # real rows, too few
    assert n_cut < im.MEMBERS_MIN and total_cut < total
    assert any("equity rows" in p for p in problems_cut)


@unit
def test_the_as_of_gate_refuses_the_future_and_a_stale_download() -> None:
    eod = recorded = date(2026, 9, 3)  # the run ingest_state recorded on the box
    assert im.as_of_gate(recorded, eod, recorded, False) is None  # same-day rerun: confirms
    assert im.as_of_gate(date(2026, 9, 4), date(2026, 9, 4), recorded, False) is None  # advances
    assert "after the EOD" in (im.as_of_gate(date(2026, 9, 4), eod, None, False) or "")
    assert "OLDER" in (im.as_of_gate(date(2026, 9, 2), eod, recorded, False) or "")
    assert im.as_of_gate(date(2026, 9, 2), eod, recorded, True) is None  # a documented rollback


# ── resolution ──


@live
def test_resolution_over_the_live_holdings_with_seven_identity_rows(
    holdings: pd.DataFrame, ident: Any, ids: dict[str, str], expected_members: dict[str, str]
) -> None:
    report = im.new_report()
    weights, by_ticker = im.resolve_holdings(holdings, ident, report)
    n_ticker_rows = int(holdings["ticker"].notna().sum())
    unresolved = n_ticker_rows - len(weights)
    print(f"live: {len(weights)} resolved of {n_ticker_rows} ticker rows (6 of 504 on 2026-09-03)")
    assert set(weights) == set(expected_members.values()) and "SPY" not in by_ticker
    assert by_ticker == expected_members
    assert report.counts["current:unresolved"] == unresolved
    assert weights[ids["NVDA"]] > Decimal("0.02")  # the largest weight in the index today
    assert unresolved / n_ticker_rows > im.MAX_UNRESOLVED_FRAC  # → the script refuses to write


@unit
def test_symbol_first_then_alias_then_unresolved(ident: Any, ids: dict[str, str]) -> None:
    assert imx.resolve_current("AAPL", ident) == (ids["AAPL"], "symbol")
    assert imx.resolve_current(AAPL_ALIAS, ident) == (ids["AAPL"], "alias")
    assert imx.resolve_current("2602335D", ident) == (None, imx.REASON_NO_ACTIVE)  # contra line


@live
def test_the_report_lists_every_unresolved_ticker_with_its_reason(
    holdings: pd.DataFrame, ident: Any, expected_members: dict[str, str], tmp_path: Path
) -> None:
    path = tmp_path / "idx.csv"
    report = im.new_report(path)
    im.resolve_holdings(holdings, ident, report)
    report.close()
    rows = list(csv.DictReader(path.open()))
    n_ticker_rows = int(holdings["ticker"].notna().sum())
    n = len(expected_members)
    assert [*rows[0]] == list(im.REPORT_COLUMNS)
    assert len(rows) == n_ticker_rows  # the cash line has no ticker and is not a row
    assert Counter(r["status"] for r in rows) == {"resolved": n, "unresolved": n_ticker_rows - n}
    assert report.counts == {"current:resolved": n, "current:unresolved": n_ticker_rows - n}
    unresolved = next(r for r in rows if r["status"] == "unresolved")
    assert unresolved["detail"] == imx.REASON_NO_ACTIVE and unresolved["instrument_id"] == ""


# ── sectors by membership ──


@live
def test_sectors_for_writes_only_members_and_reports_every_member_without_a_sector(
    sector_map: pd.DataFrame, expected_members: dict[str, str], ids: dict[str, str]
) -> None:
    report = im.new_report()
    sectors = im.sectors_for(sector_map, expected_members, report)
    unmapped = set(sector_map.loc[sector_map["sector_gics"].isna(), "ticker"])
    members_without = sorted(set(expected_members) & unmapped)
    print(
        f"live: {len(sectors)} sectors for the scaffold; {len(unmapped)} unmapped ticker rows "
        f"in the file, of which members {members_without} (none on 2026-09-03)"
    )
    assert set(sectors) == {i for s, i in expected_members.items() if s not in unmapped}
    assert (
        sectors[ids["AAPL"]]
        == sectors[ids["NVDA"]]
        == sectors[ids["MSFT"]]
        == ("Information Technology")
    )
    if "RDDT" in sectors:
        assert sectors[ids["RDDT"]] == "Communication Services"
    if "VMRK" in sectors:
        assert sectors[ids["VMRK"]] == "Real Estate"
    assert report.counts.get("sector:mapped", 0) == len(sectors)
    assert report.counts.get("sector:unmapped", 0) == len(members_without)
    assert "sector:unmapped" not in report.counts or members_without  # non-members: no row


# ── the current pass ──


@live
def test_an_empty_table_opens_every_resolved_member_at_as_of(
    weights: dict[str, Decimal], as_of: date
) -> None:
    plan = imx.plan_current(weights, [], as_of)
    assert not plan.closes and not plan.confirms
    assert {iv.instrument_id: iv.weight_frac for iv in plan.opens} == weights
    assert all(
        iv.effective_from == as_of and iv.effective_to is None and iv.source == "ssga"
        for iv in plan.opens
    )


@live
def test_a_rerun_on_the_same_file_only_confirms(weights: dict[str, Decimal], as_of: date) -> None:
    first = imx.plan_current(weights, [], as_of)
    again = imx.plan_current(weights, first.opens, as_of)
    assert not again.opens and not again.closes
    assert {(i, e): w for i, e, w in again.confirms} == {(i, as_of): w for i, w in weights.items()}


@live
def test_a_member_absent_today_closes_and_a_joiner_without_a_spell_opens(
    weights: dict[str, Decimal],
    history_rows: list[imx.Interval],
    ids: dict[str, str],
    as_of: date,
    expected_members: dict[str, str],
) -> None:
    """Existing open intervals as the history pass wrote them: AAPL, NVDA, MSFT since
    HISTORY_START. Today's file WITHOUT MSFT → MSFT closes at as_of (exclusive end). RDDT,
    FERG and VMRK are in today's file but have no interval (no spell: they joined after the
    file's last row) → they open at as_of. AAPL and NVDA are confirmed."""
    without_msft = {i: w for i, w in weights.items() if i != ids["MSFT"]}
    plan = imx.plan_current(without_msft, history_rows, as_of)
    assert plan.closes == [(ids["MSFT"], imx.HISTORY_START)]
    joiners = {s: i for s, i in expected_members.items() if s not in HISTORY}
    print(
        f"live: joiners without a fja05680 spell {sorted(joiners)} (FERG, RDDT, VMRK on 2026-09-03)"
    )
    assert {iv.instrument_id: (iv.effective_from, iv.weight_frac) for iv in plan.opens} == {
        i: (as_of, weights[i]) for i in joiners.values()
    }
    assert {i for i, _, _ in plan.confirms} == {ids["AAPL"], ids["NVDA"]}


@live
def test_a_row_opened_today_is_never_closed_today(weights: dict[str, Decimal], as_of: date) -> None:
    """Closing at as_of a row that opened at as_of would leave a zero-length interval."""
    opened_today = imx.plan_current(weights, [], as_of).opens
    assert imx.plan_current({}, opened_today, as_of).closes == []


# ── the history pass (the committed 2026-09-04 copy) ──


@unit
def test_window_clips_at_the_platform_start_and_keeps_open_spells_open(
    spells: pd.DataFrame,
) -> None:
    assert imx.HISTORY_START == date(2016, 1, 4)  # atlas.config.MARKETS["us"].history_start
    w = imx.window_spells(spells, imx.HISTORY_START, date(2026, 9, 3))
    by: dict[str, list[tuple[date, date | None]]] = {}
    for t, s, e in w:
        by.setdefault(t, []).append((s, e))
    assert len(w) == 750 and sum(1 for _, _, e in w if e is None) == 503
    assert by["AAPL"] == [(imx.HISTORY_START, None)]  # member since 1996: clipped, still open
    assert by["AABA"] == [(imx.HISTORY_START, date(2017, 6, 19))]  # left after the start
    assert by["SIVB"] == [(date(2018, 3, 19), date(2023, 3, 15))]  # inside the window
    assert by["DELL"] == [(date(2024, 9, 23), None)]  # its 1996→2013 spell is out
    assert by["SNDK"] == [(imx.HISTORY_START, date(2016, 5, 12)), (date(2025, 11, 28), None)]


@live
def test_history_covers_the_current_members_up_to_the_changes_after_its_last_row(
    spells: pd.DataFrame, holdings: pd.DataFrame, as_of: date
) -> None:
    open_now = {t for t, _, e in imx.window_spells(spells, imx.HISTORY_START, as_of) if e is None}
    ssga = set(holdings.loc[holdings["ticker"].notna() & holdings["sedol"].notna(), "ticker"])
    joined, gone = sorted(ssga - open_now), sorted(open_now - ssga)
    print(
        f"live: {len(ssga & open_now)} of {len(ssga)} SSGA equities have a fja05680 spell; "
        f"joined since the file's last row {joined}; gone {gone} "
        "(2026-09-03: 500 of 503; joined FERG, RDDT, VMRK; gone AVB, EA, EQR)"
    )
    assert len(open_now) == 503
    assert len(ssga & open_now) >= 0.98 * len(ssga)  # the index turns over ~5% a year
    assert set(HISTORY) <= ssga & open_now


@unit
def test_spells_resolve_by_symbol_or_alias_and_report_the_rest(
    spells: pd.DataFrame, ident: Any, ids: dict[str, str]
) -> None:
    w = [
        x
        for x in imx.window_spells(spells, imx.HISTORY_START, date(2026, 9, 3))
        if x[0] in ("AAPL", "SIVB")
    ]
    report = im.new_report()
    resolved = im.resolve_history(w, ident, report)
    assert resolved == [(ids["AAPL"], imx.HISTORY_START, None)]
    assert report.counts == {"history:resolved": 1, "history:unresolved": 1}
    assert imx.resolve_spell(AAPL_ALIAS, imx.HISTORY_START, None, ident) == (ids["AAPL"], "alias")
    assert imx.resolve_spell("SIVB", date(2018, 3, 19), date(2023, 3, 15), ident) == (
        None,
        imx.REASON_NO_INSTRUMENT,
    )


@unit
def test_history_is_rederived_and_a_stale_row_is_deleted(
    history_rows: list[imx.Interval], ids: dict[str, str]
) -> None:
    """The previous pass wrote AAPL, NVDA and MSFT; this run's spell set lacks MSFT (say its
    identity row is gone) — MSFT's old row is not in the new set, so it is deleted; the other
    two are re-upserted unchanged. Nothing is lost: the file re-derives the row next time."""
    spells = [(r.instrument_id, r.effective_from, r.effective_to) for r in history_rows]
    again = imx.plan_history([s for s in spells if s[0] != ids["MSFT"]], history_rows)
    assert again.deletes == [(ids["MSFT"], imx.HISTORY_START)] and again.notes == []
    assert {r.instrument_id for r in again.rows} == {ids["AAPL"], ids["NVDA"]}
    assert imx.plan_history(spells, history_rows).deletes == []  # the same set: nothing stale


@live
def test_history_never_overlaps_deletes_or_shortens_an_ssga_interval(
    weights: dict[str, Decimal],
    history_rows: list[imx.Interval],
    ids: dict[str, str],
    as_of: date,
) -> None:
    aapl, nvda, msft = (ids[s] for s in HISTORY)
    ssga_open = [imx.Interval(aapl, as_of, None, weights[aapl], "ssga")]
    stale_msft = [r for r in history_rows if r.instrument_id == msft]
    plan = imx.plan_history(
        [(aapl, imx.HISTORY_START, None), (nvda, imx.HISTORY_START, None)],
        ssga_open + stale_msft,
    )
    assert plan.rows == [
        imx.Interval(aapl, imx.HISTORY_START, as_of, None, "fja05680"),  # clipped at the ssga start
        imx.Interval(nvda, imx.HISTORY_START, None, None, "fja05680"),
    ]
    assert [iid for iid, _ in plan.notes] == [aapl]
    assert plan.deletes == [(msft, imx.HISTORY_START)]  # stale fja05680 row; never the ssga one
    inside = imx.plan_history([(aapl, as_of, None)], ssga_open)
    assert inside.rows == [] and len(inside.notes) == 1  # a spell starting inside ssga is ssga's
    assert inside.deletes == []
