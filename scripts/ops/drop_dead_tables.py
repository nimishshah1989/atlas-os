#!/usr/bin/env python3
"""Drop the 25 dead atlas_foundation tables left behind by the consolidation purge.

Context: the "235 retired backend modules" cleanup (73fc760e) deleted the M2–M5
builders but left their OUTPUT tables in the schema — stale, unproduced, and unread.
A full audit (every table cross-referenced against all live frontend + backend code,
excluding comments/tests/dead-DDL) found 25 with ZERO live non-comment references and
NO inbound FK or view dependency. This drops them.

Idempotent (DROP TABLE IF EXISTS ... CASCADE) and self-documenting: the manifest below
groups each table by the retired subsystem it belonged to. The schema of any table here
is recoverable from the pre-drop baseline in git history if a subsystem is ever revived.

Run once (needs prod DB write access):
    set -a; source .env; set +a
    PYTHONPATH=.:scripts/foundation .venv/bin/python scripts/ops/drop_dead_tables.py

AFTER running, regenerate the schema baseline so a fresh DB matches prod (needs a
pg_dump whose major version matches the server, i.e. 17):
    pg_dump "$ATLAS_DB_URL" --schema=atlas_foundation --schema-only \
        --no-owner --no-privileges --no-tablespaces \
      | sed -n '/CREATE SCHEMA/,$p' > migrations/baseline/atlas_foundation_schema.sql
    # then make the CREATE SCHEMA line IF NOT EXISTS (see the baseline .py docstring)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "foundation"))
import _db  # pyright: ignore[reportMissingImports]

M = "atlas_foundation"

# (table, subsystem it belonged to). Every one verified: 0 live non-comment refs,
# no inbound FK, no dependent view. See the freshness-remediation memory for the audit.
DEAD_TABLES: list[tuple[str, str]] = [
    # ── retired scorecards (FM 2026-07-03: /funds+/etfs use the native lens composite) ──
    ("atlas_etf_scorecard", "scorecard"),
    ("atlas_fund_scorecard", "scorecard"),
    ("atlas_scorecard_daily", "scorecard"),
    # ── M5 conviction / signal-call methodology (retired) ──
    ("atlas_signal_calls", "M5 signals"),
    ("atlas_signal_ic", "M5 signals"),
    ("atlas_signal_weights", "M5 signals"),
    ("atlas_etf_signal_calls", "M5 signals"),
    # ── M4 fund/ETF metrics + states (superseded by the native etf_lens/fund_lens roll-ups) ──
    ("atlas_etf_metrics_daily", "M4 fund/etf"),
    ("atlas_fund_metrics_daily", "M4 fund/etf"),
    ("atlas_fund_states_daily", "M4 fund/etf"),
    ("atlas_universe_etfs", "M4 fund/etf"),
    # ── M3 sector metrics + states (superseded by build_sector_cards + sector_lens_daily) ──
    ("atlas_sector_metrics_daily", "M3 sector"),
    ("atlas_sector_states_daily", "M3 sector"),
    # ── M2/M3 stock metrics + conviction (superseded by technical_daily + the lens journal) ──
    ("atlas_stock_metrics_daily", "M2/M3 stock"),
    ("atlas_stock_conviction_daily", "M2/M3 stock"),
    ("technical_stock", "M2/M3 stock"),
    # ── dead v6 materialised views (superseded by native queries / getSectorIndexRs) ──
    ("mv_etf_deepdive", "dead v6 MV"),
    ("mv_etf_list_v6", "dead v6 MV"),
    ("mv_markets_rs_grid", "dead v6 MV"),
    ("mv_stock_landscape_trader", "dead v6 MV"),
    # ── dead ingest state / staging bootstrap (staging_ddl.sql is not croned) ──
    ("backfill_state", "dead state"),
    ("corp_action", "dead state"),
    ("corp_action_event", "dead state"),
    ("de_trading_calendar", "dead state"),
    ("ingest_run", "dead state"),
]


def main() -> int:
    print(f"Dropping {len(DEAD_TABLES)} dead tables from {M} ...")
    total = 0
    for table, subsystem in DEAD_TABLES:
        exists = _db.scalar(f"select to_regclass('{M}.{table}')")
        if exists is None:
            print(f"  skip  {table:<30} (already gone)")
            continue
        n = _db.scalar(f"select count(*) from {M}.{table}") or 0
        total += n
        _db.exec_sql(f"drop table if exists {M}.{table} cascade")
        gone = _db.scalar(f"select to_regclass('{M}.{table}')") is None
        print(f"  {'DROP ' if gone else 'FAIL '}{table:<30} {n:>10,} rows  [{subsystem}]")
        if not gone:
            print(f"    !! {table} still exists after DROP — investigate", file=sys.stderr)
            return 1
    remaining = _db.scalar(
        f"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        f"where n.nspname='{M}' and c.relkind in ('r','m','v')"
    )
    print(f"\nDone — {total:,} rows of dead M-era data reclaimed. {remaining} relations remain.")
    print("NEXT: regenerate migrations/baseline/atlas_foundation_schema.sql (see docstring).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
