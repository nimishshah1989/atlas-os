# Stream B — Drift Detection Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire daily realized-vs-predicted drift detection on top of the existing `atlas_signal_calls` schema. Output: drift event log writes per signal_call, MV column for current drift state, and a UI chip on every stock/ETF page.

**Architecture:** New Python module `atlas/drift/compute_drift.py` runs nightly via pg_cron (post-MV refresh). Writes to existing `atlas_drift_event_log` table (schema per CONTEXT.md lines 115-130). Adds `drift_z` + `drift_status` columns to `mv_stock_landscape` and `mv_etf_scorecard`. Frontend renders a chip from those columns.

**Tech Stack:** PostgreSQL (Supabase), Python 3.11, SQLAlchemy 2.0 async. React/Next.js for UI chip. Decimal for all financial math.

**Source spec:** `docs/superpowers/specs/2026-05-28-trader-view-redesign.html` §6.

---

### Task 1: Verify `atlas_drift_event_log` schema exists

**Files:**
- Read-only check on Supabase

- [ ] **Step 1: Check schema**

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'atlas' AND table_name = 'atlas_drift_event_log'
ORDER BY ordinal_position;
```

Expected columns per CONTEXT.md: `event_id`, `signal_call_id`, `observed_at`, `realized_excess`, `predicted_excess`, `sigma_predicted`, `z_score`, `actor`, `realized_window`, `status_before`, `status_after`, `action`.

- [ ] **Step 2: If missing, write migration 114**

```python
# migrations/versions/114_atlas_drift_event_log.py
"""Create atlas_drift_event_log table per CONTEXT.md."""

from alembic import op
import sqlalchemy as sa

revision = "114_atlas_drift_event_log"
down_revision = "113_weinstein_thresholds"

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_drift_event_log (
          event_id          bigserial PRIMARY KEY,
          signal_call_id    uuid NOT NULL REFERENCES atlas.atlas_signal_calls(signal_call_id),
          observed_at       timestamptz NOT NULL DEFAULT NOW(),
          realized_window   interval NOT NULL,        -- e.g. '30 days'
          realized_excess   numeric(12,6) NOT NULL,   -- decimal fraction
          predicted_excess  numeric(12,6) NOT NULL,   -- prorated for elapsed time
          sigma_predicted   numeric(12,6) NOT NULL,
          z_score           numeric(8,4) NOT NULL,
          status_before     text,
          status_after      text,
          action            text,
          actor             text NOT NULL DEFAULT 'cron:drift'
        );

        CREATE INDEX IF NOT EXISTS ix_drift_event_log_signal_call
          ON atlas.atlas_drift_event_log (signal_call_id);
        CREATE INDEX IF NOT EXISTS ix_drift_event_log_observed
          ON atlas.atlas_drift_event_log (observed_at DESC);
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_drift_event_log;")
```

- [ ] **Step 3: Commit + apply**

```bash
git add migrations/versions/114_atlas_drift_event_log.py
git commit -m "feat(drift): atlas_drift_event_log table (migration 114)"
ssh atlas "cd /home/ubuntu/atlas-os && source venv/bin/activate && alembic upgrade head"
```

---

### Task 2: Daily drift computer

**Files:**
- Create: `atlas/drift/__init__.py`
- Create: `atlas/drift/compute_drift.py`

- [ ] **Step 1: Write the compute module**

```python
# atlas/drift/compute_drift.py
"""Daily drift detection.

For each OPEN signal_call (exit_date IS NULL), compute:
  realized_excess  = price_today / price_at_entry - bench_today / bench_at_entry
  elapsed_frac     = days_since_entry / tenure_days   (clamped to [0, 1])
  predicted_today  = predicted_excess * elapsed_frac
  sigma_today      = sigma_predicted * sqrt(elapsed_frac)
  Z                = (realized_excess - predicted_today) / sigma_today

Write a row to atlas_drift_event_log when |Z| > 2 (drift event).
Write the current Z + status to mv_stock_landscape.drift_z /
mv_etf_scorecard.drift_z via a simple UPDATE join.

Run as the LAST step of nightly cron at 21:50 UTC (after MV refresh).
"""

from __future__ import annotations
import math
import os
from decimal import Decimal
from sqlalchemy import create_engine, text
import structlog

log = structlog.get_logger()
TENURE_DAYS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


def _engine():
    return create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def compute_open_drift() -> int:
    """Returns number of drift events logged."""
    sql_select = text("""
        SELECT
          sc.signal_call_id,
          sc.instrument_id,
          sc.entry_date,
          sc.tenure,
          sc.predicted_excess,
          sc.sigma_predicted,
          (SELECT close_adj FROM atlas.atlas_prices_daily
             WHERE instrument_id = sc.instrument_id
               AND date = sc.entry_date) AS price_at_entry,
          (SELECT close_adj FROM atlas.atlas_prices_daily
             WHERE instrument_id = sc.instrument_id
             ORDER BY date DESC LIMIT 1) AS price_today,
          (SELECT close_adj FROM atlas.atlas_index_prices_daily
             WHERE index_code = 'NIFTY 500' AND date = sc.entry_date) AS bench_at_entry,
          (SELECT close_adj FROM atlas.atlas_index_prices_daily
             WHERE index_code = 'NIFTY 500'
             ORDER BY date DESC LIMIT 1) AS bench_today,
          (CURRENT_DATE - sc.entry_date) AS days_elapsed
        FROM atlas.atlas_signal_calls sc
        WHERE sc.exit_date IS NULL
          AND sc.action IN ('POSITIVE', 'NEGATIVE')
          AND sc.predicted_excess IS NOT NULL
          AND sc.sigma_predicted IS NOT NULL
    """)

    sql_insert = text("""
        INSERT INTO atlas.atlas_drift_event_log
          (signal_call_id, observed_at, realized_window, realized_excess,
           predicted_excess, sigma_predicted, z_score, actor)
        VALUES
          (:scid, NOW(), :window, :realized, :predicted, :sigma, :z, 'cron:drift')
    """)

    n_events = 0
    eng = _engine()
    with eng.begin() as conn:
        rows = list(conn.execute(sql_select))
        for r in rows:
            tenure_days = TENURE_DAYS.get(r.tenure)
            if tenure_days is None or r.price_at_entry is None or r.price_today is None:
                continue
            if r.bench_at_entry is None or r.bench_today is None:
                continue

            realized = Decimal(r.price_today) / Decimal(r.price_at_entry) - Decimal("1") \
                     - (Decimal(r.bench_today) / Decimal(r.bench_at_entry) - Decimal("1"))
            elapsed_frac = min(max(float(r.days_elapsed) / tenure_days, 0.001), 1.0)
            predicted_today = Decimal(str(float(r.predicted_excess) * elapsed_frac))
            sigma_today = Decimal(str(float(r.sigma_predicted) * math.sqrt(elapsed_frac)))
            z = (realized - predicted_today) / sigma_today if sigma_today != 0 else Decimal("0")

            if abs(z) > Decimal("2"):
                conn.execute(sql_insert, {
                    "scid": r.signal_call_id,
                    "window": f"{r.days_elapsed} days",
                    "realized": realized,
                    "predicted": predicted_today,
                    "sigma": sigma_today,
                    "z": z,
                })
                n_events += 1
                log.warning("drift_event", signal_call_id=str(r.signal_call_id), z=str(z))

    log.info("drift_compute_complete", n_events=n_events, n_open=len(rows))
    return n_events


if __name__ == "__main__":
    n = compute_open_drift()
    print(f"drift events logged: {n}")
```

- [ ] **Step 2: Add `__init__.py`**

```python
# atlas/drift/__init__.py
"""Drift detection module — daily realized-vs-predicted Z-score per open signal."""
```

- [ ] **Step 3: Commit**

```bash
git add atlas/drift/
git commit -m "feat(drift): compute_drift.py — daily realized-vs-predicted Z + event log writes"
```

---

### Task 3: Drift columns on MVs

**Files:**
- Create: `migrations/versions/115_drift_columns_on_mvs.py`

- [ ] **Step 1: Write migration**

```python
# migrations/versions/115_drift_columns_on_mvs.py
"""Add drift_z + drift_status to mv_stock_landscape + mv_etf_scorecard."""

from alembic import op

revision = "115_drift_columns_on_mvs"
down_revision = "114_atlas_drift_event_log"

def upgrade() -> None:
    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_landscape_drift CASCADE;
        CREATE MATERIALIZED VIEW atlas.mv_stock_landscape_drift AS
        SELECT
          sc.instrument_id,
          sc.signal_call_id,
          de.z_score                              AS drift_z,
          CASE
            WHEN de.z_score IS NULL              THEN 'no_data'
            WHEN ABS(de.z_score) <= 1.5          THEN 'within_band'
            WHEN ABS(de.z_score) <= 2.0          THEN 'mild_drift'
            ELSE                                      'significant_drift'
          END                                     AS drift_status,
          de.observed_at                          AS drift_observed_at
        FROM atlas.atlas_signal_calls sc
        LEFT JOIN LATERAL (
          SELECT z_score, observed_at
          FROM atlas.atlas_drift_event_log
          WHERE signal_call_id = sc.signal_call_id
          ORDER BY observed_at DESC LIMIT 1
        ) de ON true
        WHERE sc.exit_date IS NULL;

        CREATE UNIQUE INDEX uix_mv_stock_landscape_drift_iid
          ON atlas.mv_stock_landscape_drift (instrument_id);
    """)

def downgrade() -> None:
    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_landscape_drift CASCADE;
    """)
```

- [ ] **Step 2: Apply + verify**

```bash
ssh atlas "alembic upgrade head"
```

```sql
SELECT drift_status, COUNT(*) FROM atlas.mv_stock_landscape_drift GROUP BY 1;
```

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/115_drift_columns_on_mvs.py
git commit -m "feat(drift): mv_stock_landscape_drift — drift_z + drift_status per open signal"
```

---

### Task 4: Schedule pg_cron drift job

**Files:**
- Create: `migrations/versions/116_pg_cron_drift_nightly.py`

- [ ] **Step 1: Wire to pg_cron at 21:50 UTC**

```python
# migrations/versions/116_pg_cron_drift_nightly.py
"""Schedule drift compute nightly at 21:50 UTC (after MV refresh 21:45)."""

from alembic import op

revision = "116_pg_cron_drift_nightly"
down_revision = "115_drift_columns_on_mvs"

def upgrade() -> None:
    op.execute("""
        SELECT cron.schedule(
          'drift_compute_nightly',
          '50 21 * * *',
          $$
            -- pg_cron cannot call Python directly. Use a NOTIFY pattern:
            -- a background worker on EC2 listens for this channel and
            -- triggers atlas.drift.compute_drift.compute_open_drift().
            SELECT pg_notify('drift_compute', 'run');

            -- Also refresh the drift MV synchronously
            REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_landscape_drift;
          $$
        );
    """)

def downgrade() -> None:
    op.execute("SELECT cron.unschedule('drift_compute_nightly');")
```

- [ ] **Step 2: Add EC2 systemd unit for the LISTEN worker**

```ini
# scripts/systemd/atlas-drift-listener.service (commit as a config file)
[Unit]
Description=Atlas drift compute listener
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/atlas-os
Environment="DATABASE_URL=postgresql://..."
ExecStart=/home/ubuntu/atlas-os/venv/bin/python -m atlas.drift.listener
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```python
# atlas/drift/listener.py
"""LISTEN on drift_compute channel; trigger compute when notified."""
import os
import select
import psycopg2
import structlog
from atlas.drift.compute_drift import compute_open_drift

log = structlog.get_logger()


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.set_isolation_level(0)  # AUTOCOMMIT
    cur = conn.cursor()
    cur.execute("LISTEN drift_compute;")
    log.info("listener_started")
    while True:
        if select.select([conn], [], [], 60) == ([], [], []):
            continue
        conn.poll()
        while conn.notifies:
            _ = conn.notifies.pop(0)
            log.info("drift_compute_triggered")
            try:
                compute_open_drift()
            except Exception as e:
                log.exception("drift_compute_failed", error=str(e))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit + deploy**

```bash
git add migrations/versions/116_pg_cron_drift_nightly.py atlas/drift/listener.py scripts/systemd/atlas-drift-listener.service
git commit -m "feat(drift): pg_cron schedule + LISTEN worker for nightly drift compute"
```

```bash
ssh atlas "sudo cp /home/ubuntu/atlas-os/scripts/systemd/atlas-drift-listener.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now atlas-drift-listener"
```

---

### Task 5: Frontend drift chip

**Files:**
- Modify: `frontend/src/lib/queries/v6/stocks.ts` (add drift fields)
- Create: `frontend/src/components/v6/stocks/DriftChip.tsx`
- Modify: `frontend/src/app/stocks/[symbol]/page.tsx`

- [ ] **Step 1: Add drift fields to stock query**

```typescript
// frontend/src/lib/queries/v6/stocks.ts — extend getStockDetail()
// Add after existing JOINs:
//   LEFT JOIN atlas.mv_stock_landscape_drift d ON d.instrument_id = s.instrument_id
// Select:
//   d.drift_z::text, d.drift_status, d.drift_observed_at::text
// Add to StockDetailRow type:
//   drift_z: number | null
//   drift_status: 'within_band' | 'mild_drift' | 'significant_drift' | 'no_data' | null
//   drift_observed_at: string | null
```

- [ ] **Step 2: Create DriftChip component**

```tsx
// frontend/src/components/v6/stocks/DriftChip.tsx
'use client'

interface DriftChipProps {
  status: 'within_band' | 'mild_drift' | 'significant_drift' | 'no_data' | null
  z: number | null
}

export function DriftChip({ status, z }: DriftChipProps) {
  if (status == null || status === 'no_data') return null

  if (status === 'within_band') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] bg-signal-pos/10 text-signal-pos rounded-sm font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-pos" />
        Within band
      </span>
    )
  }

  const sign = z != null && z > 0 ? '+' : ''
  const label = status === 'mild_drift' ? 'Mild drift' : 'Drift — call is failing'
  const cls = status === 'mild_drift'
    ? 'bg-signal-warn/10 text-signal-warn'
    : 'bg-signal-neg/10 text-signal-neg'

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] ${cls} rounded-sm font-medium`}>
      <span className={`w-1.5 h-1.5 rounded-full ${status === 'mild_drift' ? 'bg-signal-warn' : 'bg-signal-neg'}`} />
      {label} {z != null && `${sign}${z.toFixed(1)}σ`}
    </span>
  )
}
```

- [ ] **Step 3: Wire into stock page header**

In `frontend/src/app/stocks/[symbol]/page.tsx`, add the chip next to the verdict block (final placement determined by stream D).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queries/v6/stocks.ts frontend/src/components/v6/stocks/DriftChip.tsx frontend/src/app/stocks/[symbol]/page.tsx
git commit -m "feat(drift): DriftChip component + wiring into stock detail page"
```

---

### Task 6: Smoke test end-to-end

- [ ] **Step 1: Force a drift event**

Pick an open signal_call with a known stale prediction. Manually compute Z by hand and confirm `compute_open_drift()` produces the same number.

- [ ] **Step 2: Verify chip renders on stock page**

```bash
curl -s https://atlas.jslwealth.in/stocks/RELIANCE | grep -i drift
```

- [ ] **Step 3: Confirm event log has rows**

```sql
SELECT COUNT(*) FROM atlas.atlas_drift_event_log WHERE observed_at >= CURRENT_DATE;
```

---

### Definition of Done

- [ ] `atlas_drift_event_log` table exists with the schema in Task 1
- [ ] `atlas/drift/compute_drift.py` correctly computes Z per open signal_call
- [ ] `mv_stock_landscape_drift` populated with latest Z + drift_status per instrument
- [ ] pg_cron drift_compute_nightly fires at 21:50 UTC daily
- [ ] EC2 systemd unit `atlas-drift-listener.service` is running and processes NOTIFY events
- [ ] `DriftChip` renders correct color + sigma on at least 3 sample stocks (1 within band, 1 mild drift, 1 significant drift if data permits)
- [ ] No hardcoded thresholds — drift Z bands (1.5, 2.0) live in `atlas_thresholds` table

### Self-review checklist

- [ ] All financial math uses `Decimal`, not `float` (per global rules)
- [ ] σ scales with √elapsed_frac, not linearly (correct stochastic-process math)
- [ ] CASE expressions handle NULL price/bench gracefully (return no_data, not crash)
- [ ] Drift events written only when |Z| > 2 (every-day spam is muted)
- [ ] Mv refresh uses CONCURRENTLY so reads aren't blocked
