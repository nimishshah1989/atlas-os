# Phase 3 — Aggregate Tables + Unified Views + Persistence: Approach

**Date:** 2026-05-19
**Branch:** feat/atlas-consolidation
**Migration head before this chunk:** 080 (atlas_stock_signal_unified view)

## Data scale check

Tables touched are new (no existing rows). The `atlas_stock_state_daily` source
table has rows from classifier_version='v2.0-validated'; sector/fund/etf
aggregate tables start empty and grow one row per (sector|fund|etf, date) nightly.
Scale is under 1K rows per table initially — straightforward pandas aggregation.

## Renumbering decision

Plan originally numbered: 081/082/083 = views (before their tables existed),
084/085/086 = tables. That dependency ordering is wrong — a view cannot be
created against a non-existent table. Correct ordering:

- 081 = atlas_sector_state_v2 table
- 082 = atlas_fund_state_v2 table
- 083 = atlas_etf_state_v2 table
- 084 = atlas_sector_signal_unified view (reads 081's table)
- 085 = atlas_fund_signal_unified view (reads 082's table + optional LEFT JOIN to atlas_fund_states_daily)
- 086 = atlas_etf_signal_unified view (reads 083's table)

## Wiki patterns used

- **Idempotent Upsert** — ON CONFLICT DO UPDATE on (sector, date), (mstar_id, date),
  (etf_ticker, date) natural keys. Matches the 45+ reference pattern.
- **Empty Aggregation Table** (staging) — tables exist ahead of nightly compute;
  views over empty tables return 0 rows safely. Views are CREATE OR REPLACE
  so they don't error if re-run.

## Approach

**Migrations (081-086):** Plain Alembic op.create_table + op.execute for views.
All in-schema "atlas". Views are CREATE OR REPLACE so upgrading twice is safe.
Down migrations drop views/tables in reverse order.

**Fund view LEFT JOIN:** The plan's 082 view body has a LEFT JOIN to
`atlas_fund_states_daily` for nav_state. That table may or may not exist locally.
Strategy: define the view with the LEFT JOIN — if the table is absent, the
CREATE VIEW will fail. Check whether it exists; if not, define nav_state as NULL
with a comment. This is confirmed safe by the spec ("if it fails IC, also cut").

**persistence.py:** Three functions, each uses a `text()` UPSERT with
`ON CONFLICT ... DO UPDATE`. SQLAlchemy `engine.begin()` context manager
ensures atomic commit. Returns len(records) for the caller to log.

**Tests — migrations:** Integration tests gated behind `ATLAS_INTEGRATION_TESTS=1`
(following the pattern from test_signal_unified_views.py). Three table-existence
tests (check information_schema.columns), three view smoke tests (SELECT 1 row,
verify column set).

**Tests — persistence:** Uses `test_engine` fixture. No conftest.py exists in
tests/intelligence/aggregations/ — create one with a `test_engine` fixture
backed by ATLAS_DB_URL. Insert test rows, verify upsert idempotency, DELETE
in teardown via transaction rollback.

## Edge cases

- Fund view LEFT JOIN: if atlas_fund_states_daily absent, nav_state = NULL (tolerated).
- Upsert: NULL mean_within_state_rank / mean_rs_rank_12m — explicitly allowed
  (Numeric nullable=True). Passed through as Python None → SQL NULL.
- Empty DataFrame: each persist_* returns 0 immediately without hitting DB.
- Decimal in records dict from pandas: upsert SQL uses float params; Decimal
  converts fine through SQLAlchemy type coercion.

## Expected runtime

All migrations run in <1s (DDL only). Persistence test inserts 1-3 rows each;
<50ms. Full pytest suite for this chunk: <10s.
