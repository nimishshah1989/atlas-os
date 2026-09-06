# ruff: noqa: S608 -- SQL here is assembled from the schema constant _gdb.M; every value is bound.
"""index_membership + sector_gics + benchmark_master round trip on a REAL database (rule #0).

Needs ``ATLAS_DB_URL`` pointing at a Postgres with the atlas_global DDL applied
(``scripts/global_market/apply_ddl.py`` on a scratch database) — a database without the
schema FAILS the module, it does not skip. Everything runs on ONE connection whose transaction
is rolled back at the end — nothing is committed, so the test is safe on any database with
the schema, including one that already holds a real membership run: the module starts by
clearing the index and the scaffold's sectors INSIDE that transaction.

Rows: the seven instrument rows ``scaffold_identity`` builds from the real 2026-09-04
directories (test scaffolding — ``build_identity.py`` is the only script that mints), the LIVE
SSGA SPY and Select Sector SPDR workbooks (fetched through the provider, so ``provider_calls``
records real requests; SSGA's notice keeps them out of the repo) and the committed fja05680
``start_end`` spells.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pandas as pd
import psycopg2
import pytest
import requests

from atlas.global_market import index_membership as imx
from atlas.global_market.providers.sp500_history import START_END_ENDPOINT, parse_start_end
from atlas.global_market.providers.ssga import (
    SECTOR_ETFS,
    SPY,
    SsgaProvider,
    parse_holdings,
    parse_sector_holdings,
    sector_by_membership,
)
from tests.unit.global_market.live_files import FIXTURES
from tests.unit.global_market.scaffold_identity import scaffold_rows
from tests.unit.global_market.script_loader import load_global_script

_gdb = load_global_script("_gdb")
im = load_global_script("ingest_index_membership")
sb = load_global_script("seed_benchmarks")

pytestmark = pytest.mark.integration

START_END = FIXTURES / "index" / START_END_ENDPOINT
M = _gdb.M

if not os.environ.get("ATLAS_DB_URL", "").strip():
    pytest.skip("ATLAS_DB_URL not set — the round trip needs a database", allow_module_level=True)


@pytest.fixture(scope="module")
def conn():
    c = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with c.cursor() as cur:
            cur.execute(
                "select count(*) from information_schema.tables where table_schema = %s "
                "and table_name in ('instrument_master', 'index_membership', 'benchmark_master')",
                (M,),
            )
            row = cur.fetchone()
            assert row and row[0] == 3, f"{M} schema not applied on this database"
            cur.execute(
                f"delete from {M}.index_membership where index_code = %s", (imx.INDEX_CODE,)
            )
        yield c
    finally:
        c.rollback()  # the whole module ran in one transaction; nothing persists
        c.close()


@pytest.fixture(scope="module")
def ids(conn) -> dict[str, str]:
    """Insert the scaffold rows (no-op where build_identity already minted them) and clear
    their sectors so the round trip proves the write."""
    rows = scaffold_rows()
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                f"insert into {M}.instrument_master (instrument_id, asset_class, symbol, name, "
                "exchange, cik, is_active, source) "
                "values (%s, %s, %s, %s, %s, %s, true, 'nasdaq_trader') "
                "on conflict (instrument_id) do nothing",
                (r.instrument_id, r.asset_class, r.symbol, r.name, r.exchange, r.cik),
            )
        cur.execute(
            f"update {M}.instrument_master set sector_gics = null "
            "where instrument_id::text = any(%s)",
            ([r.instrument_id for r in rows],),
        )
    return {r.symbol: r.instrument_id for r in rows}


@pytest.fixture(scope="module")
def ident(ids: dict[str, str]) -> Any:
    return imx.build_identity([imx.Instrument(i, s, True, None, None) for s, i in ids.items()], {})


@pytest.fixture(scope="module")
def live() -> tuple[SsgaProvider, date, pd.DataFrame, pd.DataFrame]:
    """``(provider, as_of, holdings, sector map)`` from live fetches — real provider_calls."""
    provider = SsgaProvider()
    try:
        as_of, df = parse_holdings(provider.fetch_holdings(SPY), SPY)
        sectors = {
            etf: parse_sector_holdings(provider.fetch_holdings(etf), etf)[1] for etf in SECTOR_ETFS
        }
    except requests.RequestException as e:
        pytest.skip(reason=f"SSGA unreachable: {e}")
    return provider, as_of, df, sector_by_membership(df, sectors)


def _intervals(conn) -> list[Any]:
    with conn.cursor() as cur:
        cur.execute(
            f"select instrument_id::text, effective_from, effective_to, weight_frac, source "
            f"from {M}.index_membership where index_code = %s "
            "order by instrument_id, effective_from",
            (imx.INDEX_CODE,),
        )
        return [imx.Interval(i, f, t, w, s) for i, f, t, w, s in cur.fetchall()]


def test_history_then_current_pass_round_trip(conn, ids: dict[str, str], ident, live) -> None:
    provider, as_of, df, mapping = live
    spells = imx.window_spells(parse_start_end(START_END.read_text()), imx.HISTORY_START, as_of)
    resolved = im.resolve_history(spells, ident, im.new_report())
    assert {i for i, _, _ in resolved} >= {ids[s] for s in ("AAPL", "NVDA", "MSFT")}
    history = imx.plan_history(resolved, [])
    assert history.notes == [] and history.deletes == []
    weights, by_ticker = im.resolve_holdings(df, ident, im.new_report())
    members = {s for s in ids if s in by_ticker}
    assert {"AAPL", "NVDA", "MSFT"} <= members and "SPY" not in members
    sectors = im.sectors_for(mapping, by_ticker, im.new_report())
    plan = imx.plan_current(weights, history.rows, as_of)
    assert plan.closes == [] and len(plan.confirms) == len(history.rows)
    assert len(plan.opens) == len(weights) - len(history.rows)

    with conn.cursor() as cur:
        im.write_history(cur, history)
        im.write_current(cur, plan, as_of)
        im.write_sectors(cur, sectors)
        im.assert_invariants(cur)
        n_calls = _gdb.record_provider_calls(cur, as_of, provider.name, provider.calls)
        _gdb.record_state(cur, imx.SOURCE_CURRENT, im.STATE_KEY, {"as_of": as_of.isoformat()})

    rows = {iv.instrument_id: iv for iv in _intervals(conn)}
    assert len(rows) == len(weights) == len(sectors)
    for sym in ("AAPL", "NVDA", "MSFT"):  # history-open, confirmed by SSGA today
        iv = rows[ids[sym]]
        assert (iv.effective_from, iv.effective_to, iv.source) == (imx.HISTORY_START, None, "ssga")
        assert iv.weight_frac == weights[ids[sym]]
    for iv in plan.opens:  # first seen in SSGA's file (RDDT, FERG, VMRK on 2026-09-03)
        assert (rows[iv.instrument_id].effective_from, rows[iv.instrument_id].source) == (
            as_of,
            "ssga",
        )
    with conn.cursor() as cur:
        cur.execute(
            f"select symbol, sector_gics, updated_at < now() - interval '1 second' as untouched "
            f"from {M}.instrument_master where instrument_id::text = any(%s) order by symbol",
            (list(ids.values()),),
        )
        got = {s: (g, u) for s, g, u in cur.fetchall()}
        assert got["SPY"][0] is None  # not an index member: nothing written
        assert got["AAPL"][0] == got["NVDA"][0] == got["MSFT"][0] == "Information Technology"
        assert all(got[s][0] is not None for s in members)
        assert all(got[s][1] for s in members)  # sector write never bumps updated_at
        cur.execute(
            f"select coalesce(sum(calls), 0) from {M}.provider_calls where provider = %s "
            "and run_date = %s",
            (provider.name, as_of),
        )
        total = int((cur.fetchone() or (0,))[0])
        assert n_calls == 12 and total >= sum(provider.calls.values()) == 12  # SPY + 11 sectors
        cur.execute(
            f"select value->>'as_of' from {M}.ingest_state where source = %s and key = %s",
            (imx.SOURCE_CURRENT, im.STATE_KEY),
        )
        assert cur.fetchone() == (as_of.isoformat(),)


def test_a_rerun_changes_nothing_and_history_never_touches_an_ssga_row(
    conn, ids: dict[str, str], ident, live
) -> None:
    _, as_of, df, _ = live
    before = _intervals(conn)
    weights, _ = im.resolve_holdings(df, ident, im.new_report())
    plan = imx.plan_current(weights, before, as_of)
    assert plan.opens == [] and plan.closes == [] and len(plan.confirms) == len(weights)
    spells = imx.window_spells(parse_start_end(START_END.read_text()), imx.HISTORY_START, as_of)
    resolved = im.resolve_history(spells, ident, im.new_report())
    history = imx.plan_history(resolved, before)
    # Every spell starts inside an ssga row now: nothing to write, nothing stale to delete.
    assert history.rows == [] and history.deletes == [] and len(history.notes) == len(resolved)
    with conn.cursor() as cur:
        im.write_history(cur, history)
        im.write_current(cur, plan, as_of)
        # The upsert guard itself: a history row for a key an ssga row holds must not change it,
        # and the delete statement never removes an ssga row.
        cur.execute(
            im.HISTORY_UPSERT.replace("%s", im._ROW),
            (imx.INDEX_CODE, ids["AAPL"], imx.HISTORY_START, as_of, None, imx.SOURCE_HISTORY),
        )
        cur.execute(im.HISTORY_DELETE, (imx.INDEX_CODE, ids["AAPL"], imx.HISTORY_START))
        im.assert_invariants(cur)
    after = _intervals(conn)
    assert [(iv.instrument_id, iv.effective_from, iv.effective_to, iv.source) for iv in after] == [
        (iv.instrument_id, iv.effective_from, iv.effective_to, iv.source) for iv in before
    ]


def test_the_invariants_catch_a_second_open_interval(conn, ids: dict[str, str]) -> None:
    """A second open row for AAPL (a real instrument, a real prior date) is what the stale-row
    bug produced; the assertion must name it. Undone by the module's rollback."""
    with conn.cursor() as cur:
        cur.execute("savepoint bad")
        cur.execute(
            f"insert into {M}.index_membership (index_code, instrument_id, effective_from, "
            "effective_to, weight_frac, source) values (%s, %s, %s, null, null, %s)",
            (imx.INDEX_CODE, ids["AAPL"], date(2026, 9, 1), imx.SOURCE_HISTORY),
        )
        with pytest.raises(RuntimeError, match="two open intervals"):
            im.assert_invariants(cur)
        cur.execute("rollback to savepoint bad")
        im.assert_invariants(cur)


def test_benchmarks_resolve_against_the_active_rows(conn, ids: dict[str, str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"select symbol, instrument_id::text, name from {M}.instrument_master "
            "where is_active and symbol = any(%s)",
            ([c for c, _ in sb.BENCHMARKS],),
        )
        active = {s: (i, n) for s, i, n in cur.fetchall()}
        rows, missing = sb.resolve(active)
        codes = [c for c, _ in sb.BENCHMARKS]
        assert [r[0] for r in rows] + missing == codes  # the plan's order, every code once
        assert ("SPY", ids["SPY"], "market", active["SPY"][1]) in rows
        print(f"resolved {[r[0] for r in rows]}; missing {missing} (7/7 after build_identity)")
        cur.execute(sb.UPSERT_SQL.replace("%s", "(%s, %s, %s, %s, true)"), rows[0])
        cur.execute(
            f"select code, instrument_id::text, role from {M}.benchmark_master where code = 'SPY'"
        )
        assert cur.fetchall() == [("SPY", ids["SPY"], "market")]
