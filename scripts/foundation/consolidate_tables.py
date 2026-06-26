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
    ("atlas.policy_registry", "policy_registry", []),                              # Policy alert layer (D3)
    ("atlas.atlas_signal_weights", "atlas_signal_weights", []),
    ("atlas.atlas_signal_ic", "atlas_signal_ic", []),
    ("atlas.atlas_market_regime_daily", "atlas_market_regime_daily", [["date"]]),  # Page-1 regime state
    ("atlas.atlas_macro_daily", "atlas_macro_daily", [["date"]]),                  # Page-A macro context
    ("atlas.mv_sector_cards", "mv_sector_cards", [["sector_name"]]),               # Page-B sector list
    ("atlas.mv_sector_rrg", "mv_sector_rrg", [["sector_name"]]),                   # Page-B RRG
    ("atlas.mv_sector_breadth", "mv_sector_breadth", [["sector_name"]]),           # Page-B breadth
    ("atlas.mv_sector_deepdive", "mv_sector_deepdive", [["sector_name"]]),         # Page-C deep-dive
    ("atlas.atlas_index_metrics_daily", "atlas_index_metrics_daily", [["date"]]),  # Page-B sector index RS
    ("atlas.mv_markets_rs_grid", "mv_markets_rs_grid", []),                        # Page-B global RS grid
    # ETF + Fund scorecards — single-schema: the /etfs + /funds pages + landing
    # conviction tabs read these directly; mirror so the whole platform reads ONE
    # schema (foundation_staging). (mv_*_v6 do not exist — pages read scorecards.)
    ("atlas.atlas_etf_scorecard", "atlas_etf_scorecard", [["snapshot_date"], ["instrument_id"], ["ticker"]]),
    ("atlas.atlas_fund_scorecard", "atlas_fund_scorecard", [["snapshot_date"], ["scheme_code"]]),
    ("atlas.atlas_fund_states_daily", "atlas_fund_states_daily", [["date"], ["mstar_id"]]),
    ("atlas.atlas_fund_metrics_daily", "atlas_fund_metrics_daily", [["date"], ["mstar_id"]]),
    ("atlas.atlas_etf_signal_calls", "atlas_etf_signal_calls", [["call_date"]]),
    # Universe master tables — single-schema enrichment for the board surfaces:
    # fund AUM + scheme_name (held-by panel, /funds), ETF ticker/name (/etfs).
    # aum_cr is stored in ₹ LAKH (see funds_holding_stock.ts). Mirror so the board
    # never reaches back into atlas.* for names/AUM.
    ("atlas.atlas_universe_funds", "atlas_universe_funds", [["mstar_id"]]),
    ("atlas.atlas_universe_etfs", "atlas_universe_etfs", [["ticker"]]),
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


def _sync_journal_latest(tgt: str) -> None:
    """Single-schema publish: copy the freshly-scored latest date from the atlas
    compute layer into the served foundation_staging journal, so the platform's one
    read schema stays current every run without rebuilding the whole 3.9M-row table.
    Idempotent (delete-then-insert that date)."""
    latest = _db.scalar(f"SELECT max(date) FROM {JOURNAL_SRC}")
    if latest is None:
        return
    _db.exec_sql(f"DELETE FROM {tgt} WHERE date = :d", {"d": latest})
    _db.exec_sql(f"INSERT INTO {tgt} SELECT * FROM {JOURNAL_SRC} WHERE date = :d", {"d": latest})
    n = int(_db.scalar(f"SELECT count(*) FROM {tgt} WHERE date = :d", {"d": latest}) or 0)
    print(f"  {JOURNAL_FS:24s} synced latest date {latest} ({n} rows) from {JOURNAL_SRC}")


def _copy_journal(force: bool) -> None:
    tgt = f"{FS}.{JOURNAL_FS}"
    if _exists(JOURNAL_FS) and not force:
        _sync_journal_latest(tgt)
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
