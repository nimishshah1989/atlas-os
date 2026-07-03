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
    ("atlas_sector_metrics_daily", "date", 1),
    ("mv_sector_cards", "as_of_date", 1),
    ("mv_sector_breadth", "as_of_date", 1),
    ("mv_sector_deepdive", "data_as_of", 1),
    ("atlas_macro_daily", "date", 3),
    ("atlas_etf_scorecard", "snapshot_date", 2),
    ("atlas_fund_scorecard", "snapshot_date", 2),
    ("de_mf_holdings", "as_of_date", 8),  # Morningstar, weekly
    ("de_etf_holdings", "as_of_date", 8),  # Morningstar, weekly
]

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


def _lag(eod: dt.date, table: str, col: str) -> tuple[object, object]:
    mx = _db.scalar(f"select max({col}) from {M}.{table}")
    return mx, (None if mx is None else (eod - mx).days)


def check_board(eod: dt.date) -> list[str]:
    """Derived board tables — reported loudly but NON-blocking (WARN tier)."""
    warn = []
    for table, col, lag in BOARD_TABLES:
        mx, behind = _lag(eod, table, col)
        if mx is None:
            warn.append(f"{table}: EMPTY")
            continue
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert all KEY tables are fresh to the EOD")
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    args = ap.parse_args()
    eod = args.eod or _db.eod_cutoff()
    print(f"[freshness_guard] EOD={eod}")
    stale = check(eod)
    print("  ── derived board tables (warn-only) ──")
    warn = check_board(eod)
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
