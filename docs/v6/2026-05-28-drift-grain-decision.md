# Drift Detection — Grain Decision (cell vs signal-call)

**Status:** decision proposed by me; awaiting user lock when they return.

**Date:** 2026-05-28
**Context:** Stream B agent discovered the live `atlas.atlas_drift_event_log` schema is **cell-centric** (FK = `cell_id`), not signal-call-centric as the spec implied. Migration 114 was not needed because the table already exists, but its grain differs from what the trader-view chip on `/stocks/[symbol]` expects.

## Live state of the data

| Metric | Value |
|---|---|
| Rows in `atlas_drift_event_log` | **0** (table exists, never populated) |
| Open signal_calls (`exit_date IS NULL`) | 587 |
| Distinct cells across those 587 open calls | **18** |
| Avg calls per cell | ~33 |

## The grain question, sharpened

- **Cell-grain drift** (current schema): one drift event per cell per day. The `/stocks/RELIANCE` chip would show the cell-average drift across all 33 stocks in its cell. **Lies by aggregation.** RELIANCE might be tracking perfectly while LT is dragging the cell-average sigma high.
- **Signal-call-grain drift** (what the trader-view chip needs): one drift event per `signal_call_id` per day. Per-stock accuracy.
- **Both** is also possible — engine self-audit consumes cell-grain; trader UI consumes signal-grain.

## Compute cost

- Cell-grain: 18 rows/day (one per cell)
- Signal-grain: 587 rows/day
- **Trivial either way.** Compute is not the bottleneck.

## Recommendation

**Add `signal_call_id` as a nullable column to `atlas_drift_event_log` and write at signal-call grain.** Keep `cell_id` (already there) as metadata. Engine self-audit aggregates via `cell_id`; trader UI joins on `signal_call_id`.

### Why this over a parallel table

1. Single drift compute pass, single source of truth.
2. Schema migration is additive (nullable column), zero downtime.
3. `atlas_drift_event_log` history is empty (0 rows), so there's nothing to backfill.
4. Cell-aggregation is a simple `GROUP BY cell_id` over the signal-grain rows — no separate compute.

### Migration sketch

```python
# migrations/versions/114_drift_event_log_add_signal_call_id.py
op.execute("""
    ALTER TABLE atlas.atlas_drift_event_log
        ADD COLUMN IF NOT EXISTS signal_call_id uuid
            REFERENCES atlas.atlas_signal_calls(signal_call_id);

    CREATE INDEX IF NOT EXISTS ix_drift_event_log_signal_call
        ON atlas.atlas_drift_event_log (signal_call_id);
""")
```

`compute_drift.py` already exists (Stream B commit `1a2f0b99`); only the INSERT body needs to be updated to include `signal_call_id`. Two-line change.

## Why I didn't ship this autonomously

It's a schema change to a production table. The user has been explicit that data-affecting changes need their review. Marker-gate enforcement on the MCP side blocks me from ALTER TABLE without explicit approval anyway. Documenting and queuing for their return.

## What to do when user returns

1. Lock the grain decision (signal-call recommended).
2. Write migration 114 (alembic).
3. Update `compute_drift.py` INSERT body to include `signal_call_id`.
4. Write migration 115 (`mv_stock_landscape_drift` MV — joins on `signal_call_id`).
5. Write migration 116 (pg_cron drift schedule + EC2 listener systemd).
6. Wire `DriftChip` into the stock-detail page (Stream D).
