# Chunk: D1 PIT Nifty 500 Membership Ingester

**Date:** 2026-05-19
**Chunk:** v6-D1

## Data scale

No live DB available in this worktree (Mac psycopg2 path). Schema defined in
migration 080 — `atlas_index_membership` is new (0 rows). The table uses:
- `PRIMARY KEY (index_name, instrument_id, valid_from)` — natural key
- `ON CONFLICT DO NOTHING` is safe for idempotent adds
- DB-dependent tests will skip when `ATLAS_TEST_DB_URL` is unset

## Chosen approach

Pure Python dataclass + SQLAlchemy text() queries.

- `parse_reconstitution_snapshot` — parses NSE JSON payload into a typed
  `ReconstitutionSnapshot` dataclass (no DB, fully unit-testable)
- `diff_snapshots` — set arithmetic (curr - prior, prior - curr), pure function
- `MembershipIngester.apply_diff` — UPDATE valid_to for drops, INSERT for adds
- `MembershipIngester.ingest_snapshot` — queries current open membership, calls
  diff + apply

No pandas needed: the table is small (Nifty 500 = 500 rows max per snapshot).
SQL via text() is appropriate at this scale.

## Wiki patterns checked

- Idempotent Upsert — `ON CONFLICT DO NOTHING` on the PK for adds
- Sector from Index Constituents — NSE reconstitution pattern matches our design

## Existing code reused

- `atlas/data_prereqs/v6/base.py` — BaseScraper already handles NSE session
  warming; membership.py focuses purely on parse + diff + persist
- `tests/data_prereqs/v6/test_migration.py` — existing conftest pattern for
  `ATLAS_TEST_DB_URL` skip guard; we replicate it in conftest.py

## Edge cases

- Missing symbol in instrument master → raises `LookupError` explicitly
  (no silent skip)
- Empty adds/drops sets → apply_diff is a no-op, still logs with count=0
- Symbol in both adds and drops (impossible by set arithmetic, but documented)
- duplicate INSERT: `ON CONFLICT DO NOTHING` prevents duplicate rows

## Expected runtime

- 500 symbols, 2 DB round-trips per symbol max → <2s on t3.large even with
  per-symbol resolves. For production backfill, a batch resolve via
  `WHERE symbol = ANY(:arr)` would be the optimization, but not needed at 500 rows.
