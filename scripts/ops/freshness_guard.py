#!/usr/bin/env python3
"""Freshness guard — fail LOUD if any KEY production table hasn't reached the EOD.

The 26-June staleness went unnoticed because nothing asserted freshness. This gate
runs at the end of the daily orchestrator (and inside the Sunday QA): every table the
board renders must have data at the last complete EOD. Exit 1 (+ a one-line reason per
stale table) if not, so the orchestrator alerts. Reads the single schema only.

    python scripts/ops/freshness_guard.py --eod 2026-07-01
    python scripts/ops/freshness_guard.py            # defaults to _db.eod_cutoff()
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "foundation"))
import _db

M = "atlas_foundation"

# (table, date_col, max_lag_trading_days) — most must be exactly at the EOD; a few
# feeds legitimately lag (delivery T+1, holdings weekly) so carry a tolerance.
#
# EVERY table the board renders belongs here. The 2026-07-03 finding: the guard only
# watched the core scoring tables (which stayed fresh), so the DERIVED presentation
# tables (sector cards/breadth/deepdive/metrics, macro, scorecards, holdings) went stale
# for a week+ without a peep when their builders were removed in the consolidation. If
# the board reads it, it is guarded here — no silent staleness ever again.
KEY_TABLES = [
    # ── core scoring (must be exactly at EOD) ──
    ("ohlcv_stock", "date", 0),
    ("ohlcv_etf", "date", 0),
    ("index_prices", "date", 0),
    ("technical_daily", "date", 0),
    ("atlas_lens_scores_daily", "date", 0),
    ("sector_lens_daily", "date", 0),
    ("fund_rank_daily", "date", 0),
    ("atlas_index_metrics_daily", "date", 0),
    ("atlas_market_regime_daily", "date", 0),
    ("breadth_nifty500_daily", "date", 2),
    # ── slower core feeds (legitimate lag) ──
    ("de_mf_nav_daily", "nav_date", 1),
    ("delivery_daily", "date", 2),
]

# Derived board tables. A stale sector card must NOT freeze the whole board deploy the
# way a stale price feed should — so these are WARN-tier: reported loudly + written to
# the health snapshot (so they show RED on /admin/data-status), but they don't fail the
# gate. Their fix is to restore the builders the consolidation removed, not to block.
BOARD_TABLES = [
    # NOTE: atlas_sector_metrics_daily is intentionally NOT here — it's a legacy
    # intermediate that no live board page renders (its only reader, getSectorsForDate,
    # survives solely in a unit test). The lean sector rebuild (build_sector_cards.py)
    # derives mv_sector_cards returns straight from the fresh atlas_index_metrics_daily,
    # bypassing this table. Guarding a table the board doesn't render contradicts the
    # guard's charter, so it's dropped rather than fed a dead row.
    ("mv_sector_cards", "as_of_date", 1),
    ("mv_sector_breadth", "as_of_date", 1),
    ("mv_sector_deepdive", "data_as_of", 1),
    ("atlas_macro_daily", "date", 3),
    # atlas_etf_scorecard + atlas_fund_scorecard RETIRED (FM 2026-07-03): /funds + /etfs
    # moved to the native lens composite; the scorecard pipeline was purged. Their FE reads
    # are repointed to native holdings and the tables are dropped, so they're gone from here.
    ("de_mf_holdings", "as_of_date", 8),  # Morningstar, weekly
    ("de_etf_holdings", "as_of_date", 8),  # Morningstar, weekly
    # Portfolio layer (WARN-tier: a stale paper-track pages the FM, it doesn't
    # freeze the board deploy; validate_portfolios.py is the correctness gate).
    ("portfolio_nav_daily", "date", 1),
    ("technical_fund_daily", "date", 1),
]

# ── PRODUCER REGISTRY — the invariant that makes the 2026-07 incident unrepeatable ──
# Root cause of that incident: the consolidation deleted the builders while the board
# still read their tables, and NOTHING tied a guarded table to a producer — so the
# orphaning went unnoticed for a week+ until the tables visibly went stale. This registry
# makes the link explicit and CI-enforced: every guarded table maps to a producer TOKEN
# (script filename or function) that MUST appear in an orchestrator. Delete a builder, or
# drop its cron step, and tests/unit/test_producer_registry.py goes RED before it can
# merge — the staleness guard below is the runtime half; this is the build-time half.
ORCHESTRATORS = ["scripts/ops/atlas_daily.sh", "scripts/ops/atlas_weekly.sh"]
PRODUCERS = {
    "ohlcv_stock": "ingest_kite.py",
    "ohlcv_etf": "ingest_kite.py",
    "index_prices": "ingest_bhavcopy.py",
    "technical_daily": "compute_all.py",
    "atlas_lens_scores_daily": "lens_daily.py",
    "sector_lens_daily": "rollup_sectors.py",
    "fund_rank_daily": "build_fund_rank_history.py",
    "atlas_index_metrics_daily": "build_index_metrics",
    "atlas_market_regime_daily": "run_daily_regime",
    "breadth_nifty500_daily": "build_breadth_series.py",
    "de_mf_nav_daily": "ingest_nav.py",
    "delivery_daily": "fetch_delivery.py",
    "mv_sector_cards": "build_sector_cards.py",
    "mv_sector_breadth": "build_sector_cards.py",
    "mv_sector_deepdive": "build_sector_cards.py",
    "atlas_macro_daily": "ingest_macro.py",
    "de_mf_holdings": "ingest_mf_holdings.py",
    "de_etf_holdings": "ingest_etf_holdings.py",
    "portfolio_nav_daily": "portfolio_run.py",
    "technical_fund_daily": "compute_fund_technicals.py",
}


def check_producers() -> list[str]:
    """Every guarded table must have a producer wired into an orchestrator. Pure
    filesystem — the build-time half of the freshness contract. Returns violations
    (empty = healthy). Enforced by tests/unit/test_producer_registry.py."""
    repo = Path(__file__).resolve().parents[2]
    orch = "\n".join((repo / o).read_text() for o in ORCHESTRATORS if (repo / o).exists())
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


# Per-instrument tables whose EOD row-count should stay ~stable vs the prior session.
# A sharp drop = an INCOMPLETE ingest even though max(date) looks fresh — the exact
# failure that blanked the 2026-07-01 board (10/2287 stocks ingested, yet max(date)
# was still 07-01 so the max-date-only guard passed). Completeness closes that hole.
COMPLETENESS_TABLES = {
    "ohlcv_stock",
    "ohlcv_etf",
    "index_prices",
    "technical_daily",
    "atlas_lens_scores_daily",
}
COMPLETENESS_MIN_FRAC = 0.5  # EOD count must be >= 50% of the prior session's count


def check_board(eod: dt.date) -> list[str]:
    """Derived board tables — reported loudly but NON-blocking (WARN tier). Same
    max(date)-vs-tolerance logic as check(); kept separate so these never fail the gate."""
    warn = []
    for table, col, lag in BOARD_TABLES:
        mx = _db.scalar(f"select max({col}) from {M}.{table}")
        if mx is None:
            warn.append(f"{table}: EMPTY")
            continue
        behind = (eod - mx).days
        status = "OK" if behind <= lag else "STALE"
        print(f"  [{status}] {table:<28} max={mx} (eod={eod}, behind={behind}d, tol={lag})")
        if behind > lag:
            warn.append(f"{table}: {behind}d behind (max={mx})")
    return warn


def check(eod: dt.date) -> list[str]:
    stale = []
    for table, col, lag in KEY_TABLES:
        mx = _db.scalar(f"select max({col}) from {M}.{table}")
        if mx is None:
            stale.append(f"{table}: EMPTY")
            continue
        behind = (eod - mx).days
        status = "OK" if behind <= lag else "STALE"
        print(f"  [{status}] {table:<28} max={mx} (eod={eod}, behind={behind}d, tol={lag})")
        if behind > lag:
            stale.append(f"{table} stale: max={mx}, {behind}d behind EOD {eod}")
            continue
        # Completeness: a fresh max(date) with a collapsed row-count is an INCOMPLETE
        # ingest (07-01 blank-board failure). Compare latest vs prior session's count.
        if table in COMPLETENESS_TABLES:
            cur_n = _db.scalar(f"select count(*) from {M}.{table} where {col} = :d", {"d": mx}) or 0
            prev_d = _db.scalar(f"select max({col}) from {M}.{table} where {col} < :d", {"d": mx})
            prev_n = (
                _db.scalar(f"select count(*) from {M}.{table} where {col} = :d", {"d": prev_d})
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


# The NSE announcements feed (lens_filings) can't use the row-count completeness check:
# filings are event-driven and genuinely sparse on some days, so a low daily count is not
# proof of breakage. The reliable health signal is whether the INGESTER is still running —
# i.e. lens_filings_state.updated_at is recent for most symbols. A collapse here means the
# daily re-fetch stopped, which is exactly what froze the feed in Jul 2026 (the terminal
# 'done' bug: 24 filings that month vs 6,267 the prior one) with NO alert. WARN-tier: a
# stale news feed should page the FM, not block the whole board deploy.
FILINGS_REFETCH_MIN_FRAC = 0.5


def check_filings_ingestion(eod: dt.date) -> list[str]:
    total = (
        _db.scalar(
            f"select count(*) from {M}.instrument_master "
            "where asset_class='stock' and kite_token is not null"
        )
        or 0
    )
    cutoff = dt.datetime.combine(eod, dt.time()) - dt.timedelta(days=2)
    fresh = (
        _db.scalar(
            f"select count(*) from {M}.lens_filings_state where updated_at > :cut",
            {"cut": cutoff},
        )
        or 0
    )
    frac = fresh / total if total else 0.0
    status = "OK" if frac >= FILINGS_REFETCH_MIN_FRAC else "STALLED"
    print(f"  [{status}] lens_filings ingestion    {fresh}/{total} symbols re-fetched <2d ({frac:.0%})")
    if total and frac < FILINGS_REFETCH_MIN_FRAC:
        return [
            f"lens_filings ingestion STALLED: only {fresh}/{total} symbols re-fetched in 2d "
            f"(<{int(FILINGS_REFETCH_MIN_FRAC * 100)}%) — the announcements feed is not updating"
        ]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert all KEY tables are fresh to the EOD")
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    args = ap.parse_args()
    eod = args.eod or _db.eod_cutoff()
    print(f"[freshness_guard] EOD={eod}")
    # Build-time contract (also hard-enforced in CI): every guarded table has a live
    # producer. Print here for operator visibility if the cron is edited on the box.
    prod_problems = check_producers()
    if prod_problems:
        print(f"[freshness_guard] ⚠️  PRODUCER CONTRACT — {len(prod_problems)} orphaned table(s):")
        for p in prod_problems:
            print(f"    - {p}")
    stale = check(eod)
    print("  ── derived board tables (warn-only) ──")
    warn = check_board(eod)
    warn += check_filings_ingestion(eod)
    if warn:
        print(
            f"[freshness_guard] ⚠️  WARN — {len(warn)} derived board table(s) stale (NOT blocking):"
        )
        for w in warn:
            print(f"    - {w}")
    if stale:
        print(f"[freshness_guard] FAIL — {len(stale)} CORE table(s) stale:")
        for s in stale:
            print(f"    - {s}")
        return 1
    print(
        "[freshness_guard] PASS — all CORE tables fresh to EOD"
        + (f" ({len(warn)} derived table(s) flagged, see WARN above)" if warn else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
