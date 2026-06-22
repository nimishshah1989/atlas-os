#!/usr/bin/env python3
"""D22 consolidation: bring every table v4 uses into foundation_staging (additive, no
drops of the originals — D23). Reads from the live source schemas (atlas.*, public.de_*),
writes copies into foundation_staging. Idempotent.

Two classes:
  - MIRRORS  — borrowed feeds + atlas config that have an external source of truth. Safe to
    re-sync every run: DROP + CREATE AS SELECT + add the indexes the v4 queries need.
  - JOURNAL  — atlas.atlas_lens_scores_daily becomes CANONICAL in foundation_staging. Copied
    ONCE with its PK (instrument_id, date) so the lens pipeline can upsert here going forward.
    Never auto-dropped (would destroy fresh v4 writes); use --force-journal to rebuild.

Run:  python consolidate_tables.py            # copy everything (skips journal if present)
      python consolidate_tables.py --force-journal
"""
from __future__ import annotations

import sys
import time

import _db

FS = "foundation_staging"

# (source_fqn, fs_name, [index column-lists])
MIRRORS = [
    ("public.de_mf_holdings", "de_mf_holdings", [["as_of_date"], ["mstar_id"], ["instrument_id"]]),
    ("public.de_mf_master", "de_mf_master", [["mstar_id"]]),
    ("public.de_mf_nav_daily", "de_mf_nav_daily", [["mstar_id", "nav_date"]]),
    ("public.de_etf_holdings", "de_etf_holdings", [["ticker"], ["instrument_id"]]),
    ("public.de_etf_master", "de_etf_master", [["ticker"]]),
    ("public.de_index_constituents", "de_index_constituents", []),
    ("public.de_trading_calendar", "de_trading_calendar", []),
    ("atlas.atlas_thresholds", "atlas_thresholds", []),
    ("atlas.atlas_sector_master", "atlas_sector_master", []),
    ("atlas.atlas_signal_weights", "atlas_signal_weights", []),
    ("atlas.atlas_signal_ic", "atlas_signal_ic", []),
    ("atlas.atlas_market_regime_daily", "atlas_market_regime_daily", [["date"]]),  # Page-1 regime state
]
JOURNAL_SRC = "atlas.atlas_lens_scores_daily"
JOURNAL_FS = "atlas_lens_scores_daily"


def _exists(name: str) -> bool:
    return bool(_db.scalar(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:s AND c.relname=:t", {"s": FS, "t": name}))


def _rows(fqn: str) -> int:
    return int(_db.scalar(f"SELECT count(*) FROM {fqn}") or 0)


def _copy_mirror(src: str, fs_name: str, indexes: list[list[str]]) -> None:
    tgt = f"{FS}.{fs_name}"
    t0 = time.time()
    _db.exec_sql(f"DROP TABLE IF EXISTS {tgt} CASCADE")
    _db.exec_sql(f"CREATE TABLE {tgt} AS SELECT * FROM {src}")
    for cols in indexes:
        idx = f"ix_{fs_name}_{'_'.join(cols)}"
        try:
            _db.exec_sql(f"CREATE INDEX {idx} ON {tgt} ({', '.join(cols)})")
        except Exception as e:  # noqa: BLE001  (best-effort: bad col shouldn't abort the copy)
            print(f"    ! index {idx} skipped: {str(e).splitlines()[0][:80]}")
    print(f"  {fs_name:24s} {_rows(tgt):>9d} rows  (src {_rows(src):>9d})  {time.time()-t0:5.1f}s")


def _copy_journal(force: bool) -> None:
    tgt = f"{FS}.{JOURNAL_FS}"
    if _exists(JOURNAL_FS) and not force:
        print(f"  {JOURNAL_FS:24s} EXISTS ({_rows(tgt)} rows) — skipped (canonical; --force-journal to rebuild)")
        return
    t0 = time.time()
    _db.exec_sql(f"DROP TABLE IF EXISTS {tgt} CASCADE")
    _db.exec_sql(f"CREATE TABLE {tgt} AS SELECT * FROM {JOURNAL_SRC}")
    print(f"    data copied in {time.time()-t0:.0f}s, adding PK…")
    _db.exec_sql(f"ALTER TABLE {tgt} ADD PRIMARY KEY (instrument_id, date)")
    print(f"  {JOURNAL_FS:24s} {_rows(tgt):>9d} rows  (src {_rows(JOURNAL_SRC):>9d})  {time.time()-t0:5.1f}s  [CANONICAL]")


def run(force_journal: bool) -> None:
    print(f"=== D22 consolidation -> {FS} (additive; sources untouched) ===")
    print("MIRRORS (re-synced from source):")
    for src, fs_name, idx in MIRRORS:
        _copy_mirror(src, fs_name, idx)
    print("JOURNAL (canonical in foundation_staging):")
    _copy_journal(force_journal)
    print("done.")


if __name__ == "__main__":
    run("--force-journal" in sys.argv)
