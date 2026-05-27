# MV Sector Cards — Final Audit

**Date:** 2026-05-27  
**Migration:** 102_mv_sector_cards.py  
**MV:** `atlas.mv_sector_cards`  
**Status:** READY FOR PARENT SESSION TO APPLY VIA SUPABASE MCP

---

## Definition of Done check

| Item | Status | Notes |
|------|--------|-------|
| Migration 102 file with full CREATE MV SQL | DONE | 102_mv_sector_cards.py |
| pg_cron schedule at 20:40 IST (14:40 UTC) | DONE | `40 14 * * *` |
| Tests: 35 unit pass | DONE | 0 failures |
| Tests: 7 integration (EC2-only) | SKIPPED (expected) | Require ATLAS_INTEGRATION_TESTS=1 |
| ruff check --select E,F,W | DONE | All checks passed |
| Design doc | DONE | docs/v6/mvs/2026-05-27-mv-sector-cards-design.md |
| Memory entry | DONE | ~/.forge/knowledge/raw/atlas-os/chunk-mv-sector-cards-learnings.md |
| Committed + pushed | DONE (see commit SHA in parent report) |

---

## Schema self-check

| Rule | Verified |
|------|----------|
| WITH NO DATA on CREATE | YES — line in _CREATE_MV |
| CREATE UNIQUE INDEX before REFRESH | YES — step order enforced |
| REFRESH before CRON schedule | YES |
| upgrade() order: MV → INDEX → REFRESH → CRON | YES |
| downgrade() order: UNSCHEDULE → DROP INDEX → DROP MV | YES |
| No hardcoded credentials | YES |
| No bare except clauses | YES (no Python logic, just op.execute) |
| All money columns NUMERIC (no float) | YES — all round() casts ::numeric |

---

## Column coverage vs mockup spec

| Mockup column | MV column | Source |
|--------------|-----------|--------|
| sector_name | sector_name | atlas_sector_metrics_daily |
| # stocks | constituent_count | atlas_universe_stocks count |
| 1W return | ret_1w | rs_1w + n500_ret_1w |
| 1M return | ret_1m | bottomup_ret_1m |
| 3M return | ret_3m | bottomup_ret_3m |
| 6M return | ret_6m | bottomup_ret_6m |
| 12M return | ret_12m | rs_12m + n500_ret_12m |
| RS 1M | rs_1m | atlas_sector_metrics_daily.rs_1m (migration 097) |
| RS 3M | rs_3m | bottomup_rs_3m_nifty500 |
| RS 6M | rs_6m | atlas_sector_metrics_daily.rs_6m (migration 097) |
| Vol 60d ann. | vol_60d_ann | AVG(realized_vol_63) from stock_metrics_daily |
| % > EMA20 | pct_above_ema20 | atlas_sector_metrics_daily.pct_above_ema20 |
| % > EMA200 | pct_above_ema200 | atlas_sector_metrics_daily.pct_above_ema200 |
| % @ 52WH | pct_at_52wh | atlas_sector_metrics_daily.pct_52wh |
| HHI conc. | hhi_concentration | atlas_sector_metrics_daily.hhi |
| BUY firing count | buy_signal_count | atlas_signal_calls (action=POSITIVE, exit_date IS NULL) |
| Confidence H·M·L | confidence_distribution | JSONB {"H":n,"M":n,"L":n} |
| Verdict (OW/NW/UW) | verdict + verdict_abbr | atlas_sector_states_daily.sector_state |

**All 15+ mockup columns covered.**

---

## Data gaps (explicit NULL, not zero)

| Column | NULL when | Reason |
|--------|----------|--------|
| ret_1w | rs_1w IS NULL OR n500_ret_1w IS NULL | Pre-097 backfill dates |
| ret_12m | rs_12m IS NULL OR n500_ret_12m IS NULL | Pre-097 backfill dates |
| rs_1m, rs_6m | pre-097 dates | Migration 097 backfill required |
| pct_above_ema20, pct_above_ema200, pct_at_52wh | pre-097 dates | Migration 097 backfill |
| hhi_concentration | pre-097 dates | Migration 097 backfill |
| vol_60d_ann | No stock_metrics_daily rows for sector+date | NULL propagated, not 0 |

---

## Apply instructions (for parent session)

Execute these in order via Supabase MCP execute_sql on project `nanvgbhootvvthjujkvs`:

1. **`_CREATE_MV`** — the full CREATE MATERIALIZED VIEW ... WITH NO DATA block
2. **`_CREATE_UNIQUE_INDEX`** — unique index on (as_of_date, sector_name)
3. **`_REFRESH_MV`** — initial full REFRESH (expect 30-60 seconds)
4. **`_CRON_SCHEDULE`** — register pg_cron job at 14:40 UTC

All SQL bodies are in `migrations/versions/102_mv_sector_cards.py`.
