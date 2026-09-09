#!/usr/bin/env python3
"""Freshness guard for the US platform — fail LOUD if a KEY atlas_global table is stale.

Structure copied from scripts/ops/freshness_guard.py (India). The one deliberate
difference: staleness is counted in SPY SESSIONS — the anchor's own bars
(atlas.global_market.calendar.sessions_behind) — never np.busday_count. A weekday
exchange holiday is not a session and must not read as lag.

    python scripts/global_market/freshness_guard.py --eod 2026-09-03
    python scripts/global_market/freshness_guard.py            # defaults to _gdb.eod_cutoff()

The registries fill as Phase 1 producers land (P1-A identity, P1-C macro + index
membership, …); tests/unit/global_market/test_producer_registry.py enforces the registry
contract, so a producer that lands without its cron step goes red in CI.

``--eod`` on a non-session date (a weekend, a holiday) anchors to the latest SPY session on
or before it. With no SPY bar at all there is no calendar and the guard FAILS; a missing bar
on a session day is gate A's check (``SPY has a bar at EOD``), not this guard's — by
membership-by-presence a day without a bar is not a session.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb (sibling module)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # atlas package, run as a script
import _gdb

from atlas.global_market import calendar as gcal

M = _gdb.M

# (table, date_col, max_lag_SESSIONS). Empty in Phase 0. Phase 1 registers, per the plan:
#   ("ohlcv_daily", "date", 0), ("technical_daily", "date", 0),
#   ("lens_scores_daily", "date", 0), ("etf_scores_daily", "date", 0),
#   ("country_daily", "date", 0), ("macro_daily", "date", 3)
KEY_TABLES: list[tuple[str, str, int]] = [
    ("ohlcv_daily", "date", 0),  # the spine: every board number descends from it (P1-B)
    ("macro_daily", "date", 3),  # FRED posts DGS10/DTB3 the next business day (P1-C)
    ("technical_daily", "date", 0),  # nightly from ohlcv_daily, same session (P1-D)
    ("country_daily", "date", 0),  # nightly read over technical_daily, same session
    ("etf_scores_daily", "date", 0),  # nightly blend over technical_daily, same session (P2-C)
    ("lens_scores_daily", "date", 0),  # nightly blend over technical_daily, same session (P2-D)
]

# Derived board tables — WARN tier (reported + written to the health snapshot, never a
# blocked publish). Phase 1/2 register (date column per the DDL):
#   etf_holdings 8, etf_exposure_daily 8, etf_meta 8, etf_classification 8,
#   stock_financials_pit 95
# etf_holdings/etf_meta landed on N-PORT, whose cadence the plan's 8 did not anticipate; the
# lags below are that feed's own and the reason is written beside each.
BOARD_TABLES: list[tuple[str, str, int]] = [
    ("instrument_master", "updated_at", 8),  # weekly build_identity touches every listed row (P1-A)
    ("index_membership", "updated_at", 8),  # weekly SSGA pass touches every current row (P1-C)
    ("universe_snapshot", "date", 8),  # nightly once the FM sets the floor (P1-E)
    # Nightly, but WARN not KEY: a stale classification degrades peer groups, it does not make
    # a price wrong, and withholding the whole board's publish over a name-reading rule that
    # changes monthly would be the wrong trade.
    ("etf_classification", "valid_from", 8),  # nightly regex pass over fund names (P2-B)
    # M2: every active basket is re-marked nightly; EMPTY (warn) until the first basket exists,
    # and a basket built during the day is booked by the 5-minute worker, not this table's max.
    ("basket_nav_daily", "date", 8),
    # Filing-driven, not nightly: a 10-Q lands ~40 days after the quarter it covers, so a
    # long quiet stretch is the normal state of this table rather than a stalled producer.
    ("stock_financials_pit", "filed", 95),  # SEC EDGAR company facts (P3-A)
    # N-PORT is public for the third month of each filer's FISCAL quarter and appears ~60 days
    # later, so the newest snapshot in the table is two months old on the day it lands and this
    # date can never be recent. 95 sessions ≈ four and a half months: past the natural lag and
    # inside one quarter, so a producer that stopped is caught before the next filings would
    # have refreshed it anyway.
    ("etf_holdings", "as_of_date", 95),  # SEC N-PORT-P holdings snapshots
    # updated_at, not a period: this row is TOUCHED whenever its fund files, and with several
    # thousand funds on staggered fiscal years something files most weeks — but not every week,
    # which is why this is 30 sessions and not the weekly tier's 8.
    ("etf_meta", "updated_at", 30),  # SEC N-PORT-P fund facts
    # Keyed by the SNAPSHOT's date, not the session it was computed on: exposures change only
    # when holdings do, so this date is the holdings' date and carries their lag exactly.
    ("etf_exposure_daily", "as_of_date", 95),  # build_exposures.py over those holdings
    # 8-Ks are event-driven, so quiet weeks are normal for ONE company — but not across five
    # hundred of them: an S&P 500 member files results four times a year, so the newest 8-K in
    # this table is days old whenever the producer is running. 8 sessions catches a stopped
    # feed without failing on a genuinely quiet fortnight.
    ("filings_8k", "filed", 8),  # SEC submissions → the catalyst lens (P3-B)
]

# ── PRODUCER REGISTRY (the build-time half of the freshness contract) ──
# Every guarded table maps to a producer TOKEN (script filename or function) that MUST
# appear in an orchestrator. Delete a builder, or drop its cron step, and
# tests/unit/global_market/test_producer_registry.py goes RED before it can merge.
ORCHESTRATORS = ["scripts/ops/atlas_global_daily.sh", "scripts/ops/atlas_global_weekly.sh"]
PRODUCERS: dict[str, str] = {
    "instrument_master": "build_identity.py",
    "ohlcv_daily": "ingest_prices.py",
    "macro_daily": "ingest_macro.py",
    "index_membership": "ingest_index_membership.py",
    "universe_snapshot": "build_universe_snapshot.py",
    "technical_daily": "compute_technicals.py",
    "country_daily": "build_country_views.py",
    "etf_classification": "classify_etfs.py",
    "etf_scores_daily": "score_etfs.py",
    "basket_nav_daily": "mark_baskets.py",
    "lens_scores_daily": "score_stocks.py",
    "stock_financials_pit": "ingest_financials.py",
    "etf_holdings": "ingest_nport.py",
    "etf_meta": "ingest_nport.py",
    "etf_exposure_daily": "build_exposures.py",
    "filings_8k": "ingest_filings_8k.py",
}


def _live_lines(text: str) -> str:
    """Orchestrator text minus comment lines. The Phase 0 orchestrators carry the whole
    Phase 1 step list COMMENTED OUT; a substring match over raw text would let a
    commented step satisfy the registry, which is exactly the orphaning it exists to catch."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def check_producers() -> list[str]:
    """Every guarded table must have a producer wired into an orchestrator. Pure
    filesystem — the build-time half of the freshness contract. Returns violations
    (empty = healthy). Enforced by tests/unit/global_market/test_producer_registry.py."""
    repo = Path(__file__).resolve().parents[2]
    orch = "\n".join(
        _live_lines((repo / o).read_text()) for o in ORCHESTRATORS if (repo / o).exists()
    )
    problems = []
    for table, _col, _lag in KEY_TABLES + BOARD_TABLES:
        token = PRODUCERS.get(table)
        if token is None:
            problems.append(f"{table}: guarded but absent from PRODUCERS registry")
        elif token not in orch:
            problems.append(
                f"{table}: producer '{token}' not wired into any orchestrator (orphaned)"
            )
    return problems


# Per-instrument tables whose EOD row-count should stay ~stable vs the prior session
# (a fresh max(date) with a collapsed count is an INCOMPLETE ingest — India's 07-01
# blank board). Phase 1: {ohlcv_daily, technical_daily, lens_scores_daily, etf_scores_daily}.
COMPLETENESS_TABLES: set[str] = {"technical_daily"}
COMPLETENESS_MIN_FRAC = 0.5  # EOD count must be >= 50% of the prior session's count


def spy_sessions() -> list[dt.date]:
    """The anchor calendar: every date SPY has a bar. Membership-by-presence."""
    df = _gdb.read_df(
        f"select distinct date from {M}.ohlcv_daily "
        f"where instrument_id = (select instrument_id from {M}.instrument_master "
        "where symbol = 'SPY') order by date"
    )
    return gcal.sessions(df["date"])


def _as_date(mx: dt.date) -> dt.date:
    """``max(col)`` as a New York calendar date. A ``date`` column comes back as-is; a
    ``timestamptz`` column (instrument_master.updated_at) comes back as an aware datetime,
    which ``sessions_behind`` cannot compare with the EOD date — take the market-local day."""
    if isinstance(mx, dt.datetime):
        return mx.astimezone(ZoneInfo(gcal.NEW_YORK)).date()
    return mx


def check_board(eod: dt.date, cal: list[dt.date]) -> list[str]:
    """Derived board tables — reported loudly but NON-blocking (WARN tier)."""
    warn = []
    for table, col, lag in BOARD_TABLES:
        mx = _gdb.scalar(f"select max({col}) from {M}.{table}")
        if mx is None:
            print(f"  [EMPTY] {table:<28} no rows (eod={eod}, tol={lag})")
            warn.append(f"{table}: EMPTY")
            continue
        mx = _as_date(mx)
        behind = gcal.sessions_behind(cal, mx, eod)
        status = "OK" if behind <= lag else "STALE"
        print(f"  [{status}] {table:<28} max={mx} (eod={eod}, behind={behind}s, tol={lag})")
        if behind > lag:
            warn.append(f"{table}: {behind} session(s) behind (max={mx})")
    return warn


def check(eod: dt.date, cal: list[dt.date]) -> list[str]:
    stale = []
    for table, col, lag in KEY_TABLES:
        mx = _gdb.scalar(f"select max({col}) from {M}.{table}")
        if mx is None:
            print(f"  [EMPTY] {table:<28} no rows (eod={eod}, tol={lag})")
            stale.append(f"{table}: EMPTY")
            continue
        mx = _as_date(mx)
        behind = gcal.sessions_behind(cal, mx, eod)
        status = "OK" if behind <= lag else "STALE"
        print(f"  [{status}] {table:<28} max={mx} (eod={eod}, behind={behind}s, tol={lag})")
        if behind > lag:
            stale.append(f"{table} stale: max={mx}, {behind} session(s) behind EOD {eod}")
            continue
        if table in COMPLETENESS_TABLES:
            cur_n = (
                _gdb.scalar(f"select count(*) from {M}.{table} where {col} = :d", {"d": mx}) or 0
            )
            prev_d = _gdb.scalar(f"select max({col}) from {M}.{table} where {col} < :d", {"d": mx})
            prev_n = (
                _gdb.scalar(f"select count(*) from {M}.{table} where {col} = :d", {"d": prev_d})
                if prev_d
                else 0
            ) or 0
            if prev_n and cur_n < COMPLETENESS_MIN_FRAC * prev_n:
                print(f"  [INCOMPLETE] {table:<28} {cur_n} rows on {mx} vs {prev_n} on {prev_d}")
                stale.append(
                    f"{table} INCOMPLETE: {cur_n} rows on {mx} vs {prev_n} on {prev_d} "
                    f"(<{int(COMPLETENESS_MIN_FRAC * 100)}% of prior session)"
                )
    return stale


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assert all KEY atlas_global tables are fresh to the EOD"
    )
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    args = ap.parse_args()
    eod = args.eod or _gdb.eod_cutoff()
    print(f"[freshness_guard:global] EOD={eod}")
    prod_problems = check_producers()
    if prod_problems:
        print(
            f"[freshness_guard:global] ⚠️  PRODUCER CONTRACT — {len(prod_problems)} orphaned table(s):"
        )
        for p in prod_problems:
            print(f"    - {p}")
    # The anchor calendar is only loaded once a table is guarded: in Phase 0 nothing is
    # ingested yet, and the guard's job here is the registry contract alone.
    cal = spy_sessions() if (KEY_TABLES or BOARD_TABLES) else []
    if (KEY_TABLES or BOARD_TABLES) and not cal:
        print("[freshness_guard:global] FAIL — no SPY bars in ohlcv_daily: no anchor calendar")
        return 1
    anchor = gcal.latest_session_on_or_before(cal, eod) if cal else eod
    if anchor is None:
        print(
            f"[freshness_guard:global] FAIL — no SPY session on or before EOD {eod} "
            f"(first bar {cal[0]})"
        )
        return 1
    if anchor != eod:
        print(f"[freshness_guard:global] EOD {eod} is not a SPY session — anchoring to {anchor}")
    stale = check(anchor, cal)
    print("  ── derived board tables (warn-only) ──")
    warn = check_board(anchor, cal)
    if warn:
        print(
            f"[freshness_guard:global] ⚠️  WARN — {len(warn)} derived table(s) stale (NOT blocking):"
        )
        for w in warn:
            print(f"    - {w}")
    if stale:
        print(f"[freshness_guard:global] FAIL — {len(stale)} CORE table(s) stale:")
        for s in stale:
            print(f"    - {s}")
        return 1
    print(
        f"[freshness_guard:global] PASS — {len(KEY_TABLES)} CORE table(s) fresh to EOD"
        + (f" ({len(warn)} derived table(s) flagged, see WARN above)" if warn else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
