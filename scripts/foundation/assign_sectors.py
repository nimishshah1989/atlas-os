#!/usr/bin/env python3
"""Guard the sector mapping of the active scored universe (A2).

Durable, idempotent, chain-runnable. Runs AFTER build_universe.py (which writes/refreshes
instrument rows but never touches `sector`) and is safe to re-run.

SOURCE OF TRUTH: `atlas_foundation.instrument_master.sector` IS the sector classification
now. The former raw fallback (`public.de_instrument.sector`) was dropped in the single-schema
consolidation, and no other per-stock sector source survived — every remaining sector-bearing
table (mv_stock_landscape, sector_lens_daily) is DERIVED from instrument_master, so filling
from it would be circular. There is therefore nothing to COALESCE from.

What this script does instead (RULE #0 — never fabricate a sector):
  • REPORT the count + symbols of any active stock with no sector (loud, so an NSE
    reconstitution that adds an un-sectored name is caught rather than silently scored blank).
  • GUARD that the distinct actionable-sector count stays ≤ 21 (the FM-locked canonical fold).
A non-zero unmapped count is surfaced but is NON-FATAL (the weekly cron continues); adding the
curated sector for a new name is an FM step (the 31→≤21 fold map is FM-held — see
memory v4-d13-taxonomy-mismatch).
"""

from __future__ import annotations

import _db

_ACTIVE_STOCK = (
    "FROM atlas_foundation.instrument_master "
    "WHERE asset_class='stock' AND is_active"
)


def _unmapped_symbols() -> list[str]:
    df = _db.read_df(
        f"SELECT symbol {_ACTIVE_STOCK} AND (sector IS NULL OR sector='') ORDER BY symbol"
    )
    return list(df["symbol"])


def _distinct() -> int:
    return int(
        _db.scalar(
            f"SELECT count(DISTINCT sector) {_ACTIVE_STOCK} "
            "AND sector IS NOT NULL AND sector<>''"
        )
        or 0
    )


def run() -> dict:
    unmapped = _unmapped_symbols()
    distinct = _distinct()
    res = {"unmapped": len(unmapped), "distinct_sectors": distinct}
    print(res)
    if unmapped:
        print(
            f"  ⚠️  {len(unmapped)} active stock(s) have NO sector — curate in instrument_master "
            f"(FM fold map): {', '.join(unmapped)}"
        )
    if distinct > 21:
        raise SystemExit(f"GUARD TRIPPED: distinct sectors {distinct} > 21 — aborting")
    return res


if __name__ == "__main__":
    run()
