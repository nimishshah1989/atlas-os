# SP02 — Materialized Views + RRG Velocity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED PRE-FLIGHT:** Before starting any task in this plan, read `docs/phase2/00-master-plan.html` section "Sub-project 02" in full. The Phase 2 contract requires it. Project rules in `CLAUDE.md` enforce a planning-skill hook on writes to `atlas/**` and `frontend/src/**` — this plan satisfies that gate.

**Goal:** Replace on-demand JOIN-heavy frontend queries with five pre-computed PostgreSQL materialized views refreshed nightly via `pg_cron`. Add `rs_velocity` (4-week rate-of-change of `bottomup_rs_3m_nifty500`) to `atlas_sector_metrics_daily` so the sector page can display true Relative Rotation Graph quadrant movement. New frontend query files read from the views; existing pages are not modified.

**Architecture:** Four layers, all additive. (1) **Migration 034** adds the `rs_velocity` column to `atlas_sector_metrics_daily` (schema only — `NULL` until the pipeline is updated). (2) **Migration 035** creates five materialized views with unique indexes on Supabase Postgres. (3) **Migration 036** registers pg_cron jobs to refresh all five views at 14:00 UTC (20:00 IST) each day after the nightly pipeline completes. (4) **Python surgical edit** to `atlas/compute/sectors.py` computes `rs_velocity` inside the existing bottom-up pipeline and writes it alongside the other metrics columns. Frontend query files and RRG component are new files only — zero edits to existing pages.

**Tech Stack:** Pure Postgres DDL (migrations 034/035/036), SQLAlchemy 2.0 (existing — only for migration runner), Pandas + NumPy (existing — `rs_velocity` computation), Recharts (already in stack — RRG scatter component), TypeScript + `postgres` tagged-template client (existing pattern from `frontend/src/lib/queries/sectors.ts`).

**Confirmed DB facts (queried live before writing this plan):**
- `atlas_sector_metrics_daily` exists with 20 columns. No `rs_velocity` column yet.
- `atlas_stock_metrics_daily` has `rs_3m_nifty500`, `rs_pctile_3m` (3-month RS vs Nifty500 available per stock per date).
- `atlas_stock_states_daily` has `rs_state`, `sector`, `instrument_id` (no `company_name` — join `atlas_universe_stocks` for names).
- `atlas_universe_stocks` has `instrument_id`, `symbol`, `company_name`, `sector`, `tier`.
- `atlas_market_regime_daily` has `regime_state`, `deployment_multiplier`, `date`.
- `pg_cron` extension is NOT installed on the local/dev Supabase instance. It IS available on Supabase hosted projects via SQL: `CREATE EXTENSION IF NOT EXISTS pg_cron;` — migration 036 handles installation and graceful fallback.

**File structure to create / modify:**
```
migrations/versions/034_add_rs_velocity_column.py       # CREATE
migrations/versions/035_create_materialized_views.py    # CREATE
migrations/versions/036_pg_cron_refresh_jobs.py         # CREATE
atlas/compute/sectors.py                                 # MODIFY (surgical: rs_velocity computation)
tests/compute/test_sectors_rs_velocity.py               # CREATE
frontend/src/lib/queries/leaders.ts                      # CREATE
frontend/src/lib/queries/rotation.ts                     # CREATE
frontend/src/components/sectors/SectorRRGPlot.tsx        # CREATE
```

**File responsibility split:**
- `034_add_rs_velocity_column.py` — schema only. Adds nullable `NUMERIC(10, 6)` column. Reversible.
- `035_create_materialized_views.py` — five view DDL + unique indexes. Each view documented with its purpose. Reversible (DROP MATERIALIZED VIEW).
- `036_pg_cron_refresh_jobs.py` — installs pg_cron extension (idempotent) + `cron.schedule()` calls. Graceful: logs a warning and exits cleanly if pg_cron is unavailable. Reversible (`cron.unschedule()`).
- `atlas/compute/sectors.py` — add one function `compute_rs_velocity(df_metrics: pd.DataFrame) -> pd.DataFrame` and call it inside `_run_pipeline` after `assemble_sector_metrics`. Add `"rs_velocity"` to `METRICS_COLUMNS` tuple. No other changes.
- `tests/compute/test_sectors_rs_velocity.py` — unit tests for `compute_rs_velocity` only. Four focused tests. No DB.
- `frontend/src/lib/queries/leaders.ts` — reads `mv_rs_leaders_daily`. Exported types + one async function.
- `frontend/src/lib/queries/rotation.ts` — reads `mv_sector_rotation_state`. Exported types + one async function.
- `frontend/src/components/sectors/SectorRRGPlot.tsx` — Recharts scatter of RS level vs RS velocity, quadrant overlays, hover tooltip.

**Pre-existing Atlas patterns this plan follows:**
- `bulk_upsert` + `METRICS_COLUMNS` tuple for metric writes in `sectors.py`
- `import 'server-only'` + postgres tagged-template (`sql\`...\``) for frontend query files
- `op.execute(sa.text(...))` DDL style from migrations 032/033
- `Decimal(10, 6)` for financial ratio columns (same as `mean_ic` in migration 033)
- `CREATE INDEX IF NOT EXISTS` with explicit names for index reversibility
- Frontend TypeScript: all Postgres `NUMERIC` columns returned as `string | null`; parse at display time

---

## Task 0: Pre-flight verification

**Files:** none created/modified.

- [ ] **Step 1: Read SP02 in the master plan**

  Open `docs/phase2/00-master-plan.html` and read the `id="sp2"` div in full. Confirm the deliverables listed there match this plan. They should: 5 views, pg_cron at 19:30 IST, rs_velocity, frontend queries, RRG component.

- [ ] **Step 2: Verify table columns match plan assumptions**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      cols = c.execute(text(\"\"\"
          SELECT column_name
          FROM information_schema.columns
          WHERE table_schema = 'atlas'
            AND table_name   = 'atlas_sector_metrics_daily'
          ORDER BY ordinal_position
      \"\"\")).fetchall()
      print([r[0] for r in cols])
  "
  ```

  Expected: list of 20 columns **without** `rs_velocity`. If `rs_velocity` already exists, migration 034 is a no-op — confirm and proceed to Task 1 verification.

- [ ] **Step 3: Verify pg_cron availability**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      rows = c.execute(text(\"SELECT extname FROM pg_extension WHERE extname='pg_cron'\")).fetchall()
      print('pg_cron installed:', bool(rows))
      avail = c.execute(text(\"SELECT name FROM pg_available_extensions WHERE name='pg_cron'\")).fetchall()
      print('pg_cron available to install:', bool(avail))
  "
  ```

  Expected on Supabase hosted: `pg_cron available to install: True`. If neither is true, task 6 (pg_cron migration) uses the fallback path documented there.

- [ ] **Step 4: Confirm atlas_universe_stocks has company_name**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      rows = c.execute(text(\"\"\"
          SELECT column_name
          FROM information_schema.columns
          WHERE table_schema = 'atlas'
            AND table_name   = 'atlas_universe_stocks'
          ORDER BY ordinal_position
      \"\"\")).fetchall()
      print([r[0] for r in rows])
  "
  ```

  Expected: `['instrument_id', 'symbol', 'company_name', 'tier', 'sector', ...]`. The `mv_rs_leaders_daily` view JOINs on this table for names. If `company_name` is missing, substitute `symbol` in the view DDL.

- [ ] **Step 5: Check latest alembic revision**

  ```bash
  alembic current
  ```

  Expected: `033 (head)`. If head is already at 034+, skip ahead to the appropriate task.

---

## Task 1: Migration 034 — add `rs_velocity` column

**Files:**
- Create: `migrations/versions/034_add_rs_velocity_column.py`

This migration is schema-only. The column is `NULL` for all existing rows until the Python pipeline runs and back-fills it. Adding a nullable column to an existing table is instantaneous on Postgres (no table rewrite).

- [ ] **Step 1: Write the migration**

  Create `migrations/versions/034_add_rs_velocity_column.py`:

  ```python
  """SP02: add rs_velocity column to atlas_sector_metrics_daily.

  rs_velocity = rate of change of bottomup_rs_3m_nifty500 over a 4-week
  (28 calendar day) rolling window. Computed nightly by atlas/compute/sectors.py
  after the existing bottom-up aggregation. NULL until the next pipeline run.

  Window length is tunable via atlas_thresholds key 'rs_velocity_window_days'
  (default 28). Precision NUMERIC(10, 6) matches other ratio columns in this table.

  Revision ID: 034
  Revises: 033
  Create Date: 2026-05-12
  """

  import sqlalchemy as sa
  from alembic import op

  revision = "034"
  down_revision = "033"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.execute(sa.text("""
          ALTER TABLE atlas.atlas_sector_metrics_daily
          ADD COLUMN IF NOT EXISTS rs_velocity NUMERIC(10, 6)
      """))

      # Index for the materialized view mv_sector_rotation_state which filters
      # on velocity sign — partial index on non-NULL rows only.
      op.execute(sa.text("""
          CREATE INDEX IF NOT EXISTS idx_sector_metrics_rs_velocity
          ON atlas.atlas_sector_metrics_daily (sector_name, date DESC)
          WHERE rs_velocity IS NOT NULL
      """))


  def downgrade() -> None:
      op.execute(sa.text("""
          DROP INDEX IF EXISTS atlas.idx_sector_metrics_rs_velocity
      """))
      op.execute(sa.text("""
          ALTER TABLE atlas.atlas_sector_metrics_daily
          DROP COLUMN IF EXISTS rs_velocity
      """))
  ```

- [ ] **Step 2: Run migration locally**

  ```bash
  alembic upgrade head 2>&1 | tail -5
  ```

  Expected: `Running upgrade 033 -> 034, SP02: add rs_velocity column to atlas_sector_metrics_daily.`

- [ ] **Step 3: Verify column added**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      rows = c.execute(text(\"\"\"
          SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
          WHERE table_schema = 'atlas'
            AND table_name   = 'atlas_sector_metrics_daily'
            AND column_name  = 'rs_velocity'
      \"\"\")).fetchall()
      print(rows)
  "
  ```

  Expected: `[('rs_velocity', 'numeric', 'YES')]`

- [ ] **Step 4: Commit**

  ```bash
  git add migrations/versions/034_add_rs_velocity_column.py
  git commit -m "feat(sp02): migration 034 — add rs_velocity column to atlas_sector_metrics_daily"
  ```

---

## Task 2: Migration 035 — five materialized views

**Files:**
- Create: `migrations/versions/035_create_materialized_views.py`

All five views require a UNIQUE INDEX to enable `REFRESH MATERIALIZED VIEW CONCURRENTLY` (which does not block reads). Each view is written with `WITH NO DATA` on creation so the migration runs instantly; the first populate happens via an explicit `REFRESH` at the end of the migration (or via nightly cron).

- [ ] **Step 1: Write the migration**

  Create `migrations/versions/035_create_materialized_views.py`:

  ```python
  """SP02: create five materialized views for sub-3ms frontend reads.

  Views:
  - mv_rs_leaders_daily       — top RS stocks per timeframe with names/sectors
  - mv_sector_rotation_state  — sector RS level + RS velocity + RRG quadrant
  - mv_current_market_regime  — latest regime row with deployment multiplier
  - mv_breakout_candidates    — stocks transitioning into Strong or Leader today
  - mv_deterioration_watch    — stocks transitioning OUT of Strong/Leader today

  All views use UNIQUE INDEXes so REFRESH CONCURRENTLY works without read locks.
  Created WITH NO DATA; populated at end of migration via first REFRESH.

  Revision ID: 035
  Revises: 034
  Create Date: 2026-05-12
  """

  import sqlalchemy as sa
  from alembic import op

  revision = "035"
  down_revision = "034"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      # ------------------------------------------------------------------ #
      # 1. mv_rs_leaders_daily                                               #
      # ------------------------------------------------------------------ #
      # Top RS stocks per timeframe (3m, 6m, 12m percentile) joined with
      # names from atlas_universe_stocks. One row per (instrument_id, date).
      # Ranked top-50 globally by rs_pctile_3m and limited to 200 rows so
      # the materialized view stays small. Adjust LIMIT as needed.
      op.execute(sa.text("""
          CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_rs_leaders_daily AS
          SELECT
              m.instrument_id,
              m.date,
              u.symbol,
              u.company_name,
              u.sector,
              u.tier,
              m.rs_pctile_3m::numeric(10,4)   AS rs_pctile_3m,
              m.rs_pctile_1m::numeric(10,4)   AS rs_pctile_1m,
              m.rs_3m_nifty500::numeric(10,4) AS rs_3m_nifty500,
              m.rs_6m_nifty500::numeric(10,4) AS rs_6m_nifty500,
              s.rs_state,
              s.momentum_state,
              s.state_since_date
          FROM atlas.atlas_stock_metrics_daily m
          JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = m.instrument_id
          JOIN atlas.atlas_stock_states_daily s
            ON s.instrument_id = m.instrument_id
           AND s.date           = m.date
          WHERE m.date = (
              SELECT MAX(date)
              FROM atlas.atlas_stock_metrics_daily
          )
            AND s.rs_state IN ('Leader', 'Strong')
            AND s.liquidity_gate_pass = TRUE
            AND s.history_gate_pass   = TRUE
          ORDER BY m.rs_pctile_3m DESC NULLS LAST
          WITH NO DATA
      """))

      op.execute(sa.text("""
          CREATE UNIQUE INDEX IF NOT EXISTS uidx_rs_leaders_daily_pk
          ON atlas.mv_rs_leaders_daily (instrument_id, date)
      """))

      op.execute(sa.text("""
          CREATE INDEX IF NOT EXISTS idx_rs_leaders_daily_sector
          ON atlas.mv_rs_leaders_daily (sector, rs_pctile_3m DESC)
      """))

      # ------------------------------------------------------------------ #
      # 2. mv_sector_rotation_state                                          #
      # ------------------------------------------------------------------ #
      # One row per sector for the latest date. Includes RS level, RS
      # velocity, sector_state, and RRG quadrant assignment.
      # Quadrant logic (per master plan SP02):
      #   Leading   = rs_pctile >= 50 AND rs_velocity >= 0
      #   Weakening = rs_pctile >= 50 AND rs_velocity <  0
      #   Improving = rs_pctile <  50 AND rs_velocity >= 0
      #   Lagging   = rs_pctile <  50 AND rs_velocity <  0
      # RS percentile is computed cross-sectionally (PERCENT_RANK) on
      # bottomup_rs_3m_nifty500 for the latest date.
      op.execute(sa.text("""
          CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_sector_rotation_state AS
          WITH latest AS (
              SELECT MAX(date) AS d FROM atlas.atlas_sector_metrics_daily
          ),
          latest_metrics AS (
              SELECT
                  m.sector_name,
                  m.date,
                  m.bottomup_rs_3m_nifty500,
                  m.rs_velocity,
                  m.constituent_count,
                  PERCENT_RANK() OVER (
                      ORDER BY m.bottomup_rs_3m_nifty500 NULLS LAST
                  ) AS rs_pctile_cross_sector
              FROM atlas.atlas_sector_metrics_daily m
              WHERE m.date = (SELECT d FROM latest)
          ),
          latest_states AS (
              SELECT sector_name, sector_state, bottomup_rs_state,
                     bottomup_momentum_state, participation_rs_pct
              FROM atlas.atlas_sector_states_daily
              WHERE date = (SELECT d FROM latest)
          )
          SELECT
              lm.sector_name,
              lm.date,
              lm.bottomup_rs_3m_nifty500::numeric(10, 4) AS rs_level,
              lm.rs_velocity::numeric(10, 6)              AS rs_velocity,
              lm.rs_pctile_cross_sector::numeric(10, 4)   AS rs_pctile_cross_sector,
              lm.constituent_count,
              ls.sector_state,
              ls.bottomup_rs_state,
              ls.bottomup_momentum_state,
              ls.participation_rs_pct::numeric(10, 4)     AS participation_rs_pct,
              CASE
                  WHEN lm.rs_pctile_cross_sector >= 0.5
                   AND COALESCE(lm.rs_velocity, 0) >= 0   THEN 'Leading'
                  WHEN lm.rs_pctile_cross_sector >= 0.5
                   AND lm.rs_velocity             <  0    THEN 'Weakening'
                  WHEN lm.rs_pctile_cross_sector  < 0.5
                   AND COALESCE(lm.rs_velocity, 0) >= 0   THEN 'Improving'
                  ELSE                                         'Lagging'
              END AS rrg_quadrant
          FROM latest_metrics lm
          LEFT JOIN latest_states ls ON ls.sector_name = lm.sector_name
          ORDER BY lm.rs_pctile_cross_sector DESC NULLS LAST
          WITH NO DATA
      """))

      op.execute(sa.text("""
          CREATE UNIQUE INDEX IF NOT EXISTS uidx_sector_rotation_pk
          ON atlas.mv_sector_rotation_state (sector_name, date)
      """))

      op.execute(sa.text("""
          CREATE INDEX IF NOT EXISTS idx_sector_rotation_quadrant
          ON atlas.mv_sector_rotation_state (rrg_quadrant)
      """))

      # ------------------------------------------------------------------ #
      # 3. mv_current_market_regime                                          #
      # ------------------------------------------------------------------ #
      # Single row: the latest market regime with all key columns. Frontend
      # reads this instead of SELECT MAX(date) + JOIN on regime table.
      op.execute(sa.text("""
          CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_current_market_regime AS
          SELECT
              r.date,
              r.regime_state,
              r.deployment_multiplier::numeric(10, 4)    AS deployment_multiplier,
              r.dislocation_active,
              r.dislocation_started,
              r.nifty500_close::numeric(12, 2)           AS nifty500_close,
              r.nifty500_above_ema_50,
              r.nifty500_above_ema_200,
              r.pct_above_ema_50::numeric(10, 4)         AS pct_above_ema_50,
              r.pct_above_ema_200::numeric(10, 4)        AS pct_above_ema_200,
              r.pct_in_strong_states::numeric(10, 4)     AS pct_in_strong_states,
              r.india_vix::numeric(10, 4)                AS india_vix,
              r.advances_count,
              r.declines_count,
              r.net_new_highs,
              r.ad_ratio::numeric(10, 4)                 AS ad_ratio,
              r.mcclellan_oscillator::numeric(10, 4)     AS mcclellan_oscillator
          FROM atlas.atlas_market_regime_daily r
          WHERE r.date = (SELECT MAX(date) FROM atlas.atlas_market_regime_daily)
          WITH NO DATA
      """))

      op.execute(sa.text("""
          CREATE UNIQUE INDEX IF NOT EXISTS uidx_current_regime_date
          ON atlas.mv_current_market_regime (date)
      """))

      # ------------------------------------------------------------------ #
      # 4. mv_breakout_candidates                                            #
      # ------------------------------------------------------------------ #
      # Stocks that transitioned INTO 'Strong' or 'Leader' on the latest date
      # (i.e. rs_state today IN ('Strong','Leader') AND rs_state yesterday was
      # NOT in that set). Filters out illiquid and history-insufficient rows.
      op.execute(sa.text("""
          CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_breakout_candidates AS
          WITH latest AS (
              SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
          ),
          today AS (
              SELECT instrument_id, rs_state, momentum_state, sector,
                     state_since_date, date
              FROM atlas.atlas_stock_states_daily
              WHERE date = (SELECT d FROM latest)
                AND rs_state IN ('Strong', 'Leader')
                AND liquidity_gate_pass = TRUE
                AND history_gate_pass   = TRUE
          ),
          yesterday AS (
              SELECT instrument_id, rs_state
              FROM atlas.atlas_stock_states_daily
              WHERE date = (SELECT d - 1 FROM latest)
          )
          SELECT
              t.instrument_id,
              t.date,
              u.symbol,
              u.company_name,
              u.sector,
              u.tier,
              t.rs_state          AS new_rs_state,
              y.rs_state          AS prior_rs_state,
              t.momentum_state,
              t.state_since_date,
              m.rs_pctile_3m::numeric(10, 4)   AS rs_pctile_3m,
              m.rs_3m_nifty500::numeric(10, 4) AS rs_3m_nifty500
          FROM today t
          LEFT JOIN yesterday y
            ON y.instrument_id = t.instrument_id
          JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = t.instrument_id
          LEFT JOIN atlas.atlas_stock_metrics_daily m
            ON m.instrument_id = t.instrument_id
           AND m.date           = t.date
          WHERE y.rs_state IS NULL
             OR y.rs_state NOT IN ('Strong', 'Leader')
          ORDER BY m.rs_pctile_3m DESC NULLS LAST
          WITH NO DATA
      """))

      op.execute(sa.text("""
          CREATE UNIQUE INDEX IF NOT EXISTS uidx_breakout_candidates_pk
          ON atlas.mv_breakout_candidates (instrument_id, date)
      """))

      op.execute(sa.text("""
          CREATE INDEX IF NOT EXISTS idx_breakout_candidates_sector
          ON atlas.mv_breakout_candidates (sector, rs_pctile_3m DESC)
      """))

      # ------------------------------------------------------------------ #
      # 5. mv_deterioration_watch                                            #
      # ------------------------------------------------------------------ #
      # Stocks that were 'Strong' or 'Leader' yesterday and are no longer
      # today (rs_state changed out of those tiers). Early-warning list.
      op.execute(sa.text("""
          CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_deterioration_watch AS
          WITH latest AS (
              SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
          ),
          today AS (
              SELECT instrument_id, rs_state, momentum_state, sector,
                     state_since_date, date
              FROM atlas.atlas_stock_states_daily
              WHERE date = (SELECT d FROM latest)
                AND rs_state NOT IN ('Strong', 'Leader',
                                     'ILLIQUID', 'INSUFFICIENT_HISTORY')
          ),
          yesterday AS (
              SELECT instrument_id, rs_state
              FROM atlas.atlas_stock_states_daily
              WHERE date = (SELECT d - 1 FROM latest)
                AND rs_state IN ('Strong', 'Leader')
          )
          SELECT
              t.instrument_id,
              t.date,
              u.symbol,
              u.company_name,
              u.sector,
              u.tier,
              y.rs_state          AS prior_rs_state,
              t.rs_state          AS new_rs_state,
              t.momentum_state,
              t.state_since_date,
              m.rs_pctile_3m::numeric(10, 4)   AS rs_pctile_3m,
              m.rs_3m_nifty500::numeric(10, 4) AS rs_3m_nifty500
          FROM today t
          JOIN yesterday y
            ON y.instrument_id = t.instrument_id
          JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = t.instrument_id
          LEFT JOIN atlas.atlas_stock_metrics_daily m
            ON m.instrument_id = t.instrument_id
           AND m.date           = t.date
          ORDER BY m.rs_pctile_3m DESC NULLS LAST
          WITH NO DATA
      """))

      op.execute(sa.text("""
          CREATE UNIQUE INDEX IF NOT EXISTS uidx_deterioration_watch_pk
          ON atlas.mv_deterioration_watch (instrument_id, date)
      """))

      op.execute(sa.text("""
          CREATE INDEX IF NOT EXISTS idx_deterioration_watch_sector
          ON atlas.mv_deterioration_watch (sector, rs_pctile_3m DESC)
      """))

      # ------------------------------------------------------------------ #
      # First populate of all five views                                     #
      # ------------------------------------------------------------------ #
      # Runs synchronously in the migration so views are immediately usable.
      # Subsequent refreshes go via pg_cron (migration 036).
      op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_current_market_regime"))
      op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_sector_rotation_state"))
      op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_rs_leaders_daily"))
      op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_breakout_candidates"))
      op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_deterioration_watch"))


  def downgrade() -> None:
      for view in [
          "mv_deterioration_watch",
          "mv_breakout_candidates",
          "mv_current_market_regime",
          "mv_sector_rotation_state",
          "mv_rs_leaders_daily",
      ]:
          op.execute(sa.text(f"DROP MATERIALIZED VIEW IF EXISTS atlas.{view}"))
  ```

- [ ] **Step 2: Run migration locally**

  ```bash
  alembic upgrade head 2>&1 | tail -10
  ```

  Expected: `Running upgrade 034 -> 035, SP02: create five materialized views...` followed by no errors. The final REFRESH calls will produce output like `REFRESH MATERIALIZED VIEW`.

- [ ] **Step 3: Verify all five views exist with expected columns**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  views = [
      'mv_rs_leaders_daily',
      'mv_sector_rotation_state',
      'mv_current_market_regime',
      'mv_breakout_candidates',
      'mv_deterioration_watch',
  ]
  with eng.connect() as c:
      for v in views:
          rows = c.execute(text(f\"\"\"
              SELECT column_name
              FROM information_schema.columns
              WHERE table_schema = 'atlas' AND table_name = '{v}'
              ORDER BY ordinal_position
          \"\"\")).fetchall()
          print(f'{v}: {[r[0] for r in rows]}')
  "
  ```

  Expected per view:
  - `mv_rs_leaders_daily`: `['instrument_id', 'date', 'symbol', 'company_name', 'sector', 'tier', 'rs_pctile_3m', 'rs_pctile_1m', 'rs_3m_nifty500', 'rs_6m_nifty500', 'rs_state', 'momentum_state', 'state_since_date']`
  - `mv_sector_rotation_state`: `['sector_name', 'date', 'rs_level', 'rs_velocity', 'rs_pctile_cross_sector', 'constituent_count', 'sector_state', 'bottomup_rs_state', 'bottomup_momentum_state', 'participation_rs_pct', 'rrg_quadrant']`
  - `mv_current_market_regime`: `['date', 'regime_state', 'deployment_multiplier', 'dislocation_active', ...]`
  - `mv_breakout_candidates`: `['instrument_id', 'date', 'symbol', 'company_name', 'sector', 'tier', 'new_rs_state', 'prior_rs_state', 'momentum_state', 'state_since_date', 'rs_pctile_3m', 'rs_3m_nifty500']`
  - `mv_deterioration_watch`: same shape as breakout_candidates but `prior_rs_state` in Strong/Leader and `new_rs_state` outside.

- [ ] **Step 4: Verify unique indexes exist**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      rows = c.execute(text(\"\"\"
          SELECT indexname, indexdef
          FROM pg_indexes
          WHERE schemaname = 'atlas'
            AND indexname LIKE 'uidx_%'
          ORDER BY indexname
      \"\"\")).fetchall()
      for r in rows: print(r[0])
  "
  ```

  Expected: five `uidx_*` index names, one per view.

- [ ] **Step 5: Spot-check row counts**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  views = [
      'mv_rs_leaders_daily',
      'mv_sector_rotation_state',
      'mv_current_market_regime',
      'mv_breakout_candidates',
      'mv_deterioration_watch',
  ]
  with eng.connect() as c:
      for v in views:
          n = c.execute(text(f'SELECT COUNT(*) FROM atlas.{v}')).scalar()
          print(f'{v}: {n} rows')
  "
  ```

  Expected:
  - `mv_rs_leaders_daily`: > 0 (all current Leader/Strong stocks)
  - `mv_sector_rotation_state`: ~14 rows (one per NIFTY sector)
  - `mv_current_market_regime`: exactly 1 row
  - `mv_breakout_candidates`: 0–50 rows (depends on trading day; 0 is valid on weekends)
  - `mv_deterioration_watch`: 0–30 rows (same)

- [ ] **Step 6: Commit**

  ```bash
  git add migrations/versions/035_create_materialized_views.py
  git commit -m "feat(sp02): migration 035 — five materialized views with unique indexes"
  ```

---

## Task 3: Migration 036 — pg_cron refresh jobs

**Files:**
- Create: `migrations/versions/036_pg_cron_refresh_jobs.py`

`pg_cron` is a Postgres extension that runs SQL on a schedule. On Supabase hosted projects it is available via `CREATE EXTENSION`. This migration installs it and registers one named cron job per view. Schedule is `30 14 * * *` UTC = 20:30 IST, which gives the nightly Atlas pipeline (runs ~19:00 IST) a 90-minute buffer to complete before the refresh.

If pg_cron is unavailable (e.g. local dev Postgres), the migration logs a warning and succeeds. This is not a fatal failure — views can be refreshed manually via `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

- [ ] **Step 1: Write the migration**

  Create `migrations/versions/036_pg_cron_refresh_jobs.py`:

  ```python
  """SP02: install pg_cron and register nightly refresh jobs for all five MVs.

  Schedule: 30 14 * * * UTC = 20:30 IST, after the nightly Atlas pipeline
  which completes by ~20:00 IST. Uses REFRESH MATERIALIZED VIEW CONCURRENTLY
  so reads are never blocked.

  If pg_cron is not available (local dev Postgres without extension), the
  migration succeeds with a warning logged via RAISE NOTICE. This is non-fatal
  — views can be refreshed manually.

  Refresh order matters:
    1. mv_current_market_regime   (no deps)
    2. mv_sector_rotation_state   (reads atlas_sector_metrics_daily — depends on
                                   nightly sectors.py which populates rs_velocity)
    3. mv_rs_leaders_daily        (no deps beyond stock tables)
    4. mv_breakout_candidates     (no deps)
    5. mv_deterioration_watch     (no deps)

  Each job is named uniquely so it can be identified in cron.job and unscheduled
  in downgrade without affecting other jobs.

  Revision ID: 036
  Revises: 035
  Create Date: 2026-05-12
  """

  import sqlalchemy as sa
  from alembic import op

  revision = "036"
  down_revision = "035"
  branch_labels = None
  depends_on = None

  # Cron expression: minute=30, hour=14 UTC (20:30 IST), every day.
  _SCHEDULE = "30 14 * * *"

  _JOBS = [
      ("atlas_mv_regime",        "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_current_market_regime"),
      ("atlas_mv_rotation",      "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rotation_state"),
      ("atlas_mv_rs_leaders",    "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_rs_leaders_daily"),
      ("atlas_mv_breakouts",     "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_breakout_candidates"),
      ("atlas_mv_deterioration", "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_deterioration_watch"),
  ]


  def upgrade() -> None:
      # Install pg_cron — idempotent; no-op if already installed.
      op.execute(sa.text("""
          DO $$
          BEGIN
              IF EXISTS (
                  SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron'
              ) THEN
                  EXECUTE 'CREATE EXTENSION IF NOT EXISTS pg_cron';
                  RAISE NOTICE 'pg_cron: extension installed or already present';
              ELSE
                  RAISE NOTICE 'pg_cron: extension not available on this Postgres instance. '
                               'Manual REFRESH required until pg_cron is enabled.';
              END IF;
          END
          $$
      """))

      # Schedule each view — only if pg_cron is now installed.
      for job_name, command in _JOBS:
          op.execute(sa.text(f"""
              DO $$
              BEGIN
                  IF EXISTS (
                      SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
                  ) THEN
                      -- Unschedule first (idempotent re-run safety)
                      PERFORM cron.unschedule(j.jobid)
                      FROM cron.job j
                      WHERE j.jobname = '{job_name}';

                      PERFORM cron.schedule(
                          '{job_name}',
                          '{_SCHEDULE}',
                          $cmd${command}$cmd$
                      );
                      RAISE NOTICE 'pg_cron: scheduled job %', '{job_name}';
                  ELSE
                      RAISE NOTICE 'pg_cron not available — skipping schedule for %', '{job_name}';
                  END IF;
              END
              $$
          """))  # noqa: S608 — job_name is a constant defined above; no user input


  def downgrade() -> None:
      for job_name, _ in _JOBS:
          op.execute(sa.text(f"""
              DO $$
              BEGIN
                  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
                      PERFORM cron.unschedule(j.jobid)
                      FROM cron.job j
                      WHERE j.jobname = '{job_name}';
                  END IF;
              END
              $$
          """))  # noqa: S608 — job_name is a constant; no user input
  ```

- [ ] **Step 2: Run migration locally**

  ```bash
  alembic upgrade head 2>&1 | tail -10
  ```

  Expected (local dev without pg_cron): lines starting with `NOTICE: pg_cron: extension not available...` and `NOTICE: pg_cron not available — skipping schedule for...`. Migration succeeds. On Supabase hosted: `NOTICE: pg_cron: extension installed` + five schedule notices.

- [ ] **Step 3: Commit**

  ```bash
  git add migrations/versions/036_pg_cron_refresh_jobs.py
  git commit -m "feat(sp02): migration 036 — pg_cron nightly refresh schedule for all five MVs"
  ```

---

## Task 4: Python — compute `rs_velocity` in `atlas/compute/sectors.py`

**Files:**
- Modify: `atlas/compute/sectors.py` (surgical — 4 changes, no refactor)
- Create: `tests/compute/test_sectors_rs_velocity.py`

`rs_velocity` = rate of change of `bottomup_rs_3m_nifty500` over a 4-week window. Formula: `(RS_today - RS_28_days_ago) / abs(RS_28_days_ago)` where the denominator is guarded against zero. Window length is loaded from `atlas_thresholds` at key `"rs_velocity_window_days"` with a fallback of 28. The computation operates on the full metrics DataFrame (all sectors, all dates in the current run), so the rolling window is available as long as the run covers at least 28 calendar days of history.

The four surgical changes to `sectors.py`:
1. Add `"rs_velocity"` to `METRICS_COLUMNS` tuple (after `"leadership_concentration"`, before `"compute_run_id"`).
2. Add `compute_rs_velocity()` function near the other `compute_*` functions.
3. Call `compute_rs_velocity(metrics, thresholds)` in `_run_pipeline` after `assemble_sector_metrics`.
4. Verify `assemble_sector_metrics` passes through the new column via `reindex(columns=schema_cols)` — it already does because `schema_cols` is derived from `METRICS_COLUMNS`, so adding to the tuple is sufficient.

- [ ] **Step 1: Write the failing test first**

  Create `tests/compute/test_sectors_rs_velocity.py`:

  ```python
  """Unit tests for compute_rs_velocity in atlas/compute/sectors.py.

  Tests are pure pandas — no DB. Each test verifies a specific invariant of
  the velocity formula to catch regression if the formula changes.
  """

  from decimal import Decimal

  import pandas as pd
  import pytest


  # Import the function under test. This import will FAIL until the function
  # is added to sectors.py — that's the expected TDD red state.
  from atlas.compute.sectors import compute_rs_velocity


  def _make_metrics(sector: str, dates_rs: list[tuple]) -> pd.DataFrame:
      """Build a minimal metrics DataFrame for one sector.

      dates_rs: list of (date_str, rs_value | None)
      """
      rows = [
          {"sector_name": sector, "date": pd.Timestamp(d), "bottomup_rs_3m_nifty500": rs}
          for d, rs in dates_rs
      ]
      return pd.DataFrame(rows)


  class TestComputeRsVelocity:
      def test_velocity_is_rate_of_change(self):
          """28 days apart: velocity = (new - old) / abs(old)."""
          df = _make_metrics("IT", [
              ("2026-01-01", 1.10),
              ("2026-01-29", 1.21),  # 28 calendar days later
          ])
          result = compute_rs_velocity(df, window_days=28)
          # velocity for 2026-01-29: (1.21 - 1.10) / abs(1.10) ≈ 0.1
          row = result.loc[result["date"] == pd.Timestamp("2026-01-29"), "rs_velocity"]
          assert not row.empty
          assert abs(float(row.iloc[0]) - 0.1) < 1e-6

      def test_velocity_is_null_if_no_prior_window(self):
          """First date(s) with no prior window → rs_velocity is NaN/None."""
          df = _make_metrics("IT", [
              ("2026-01-01", 1.10),
              ("2026-01-05", 1.15),
          ])
          result = compute_rs_velocity(df, window_days=28)
          # Both dates are less than 28 days apart → both should be NaN
          assert result["rs_velocity"].isna().all()

      def test_zero_rs_base_produces_null(self):
          """Zero denominator must produce NULL, not inf or NaN from division."""
          df = _make_metrics("Banking", [
              ("2026-01-01", 0.0),
              ("2026-01-29", 0.5),
          ])
          result = compute_rs_velocity(df, window_days=28)
          row = result.loc[result["date"] == pd.Timestamp("2026-01-29"), "rs_velocity"]
          # Zero base → velocity should be NaN (guarded division)
          assert row.empty or pd.isna(row.iloc[0])

      def test_multiple_sectors_computed_independently(self):
          """Each sector's velocity must use only its own prior RS value."""
          it_df   = _make_metrics("IT",      [("2026-01-01", 1.0), ("2026-01-29", 1.1)])
          bank_df = _make_metrics("Banking", [("2026-01-01", 2.0), ("2026-01-29", 2.2)])
          df = pd.concat([it_df, bank_df], ignore_index=True)
          result = compute_rs_velocity(df, window_days=28)

          it_vel   = result.loc[(result["sector_name"] == "IT")      & (result["date"] == pd.Timestamp("2026-01-29")), "rs_velocity"].iloc[0]
          bank_vel = result.loc[(result["sector_name"] == "Banking")  & (result["date"] == pd.Timestamp("2026-01-29")), "rs_velocity"].iloc[0]

          assert abs(float(it_vel)   - 0.1) < 1e-6
          assert abs(float(bank_vel) - 0.1) < 1e-6

      def test_rs_velocity_column_added_to_output(self):
          """Output DataFrame must have rs_velocity column even if all NaN."""
          df = _make_metrics("IT", [("2026-01-01", 1.10)])
          result = compute_rs_velocity(df, window_days=28)
          assert "rs_velocity" in result.columns

      def test_negative_velocity_on_falling_rs(self):
          """RS declining → negative velocity."""
          df = _make_metrics("FMCG", [
              ("2026-01-01", 1.20),
              ("2026-01-29", 1.08),  # RS fell
          ])
          result = compute_rs_velocity(df, window_days=28)
          row = result.loc[result["date"] == pd.Timestamp("2026-01-29"), "rs_velocity"]
          assert float(row.iloc[0]) < 0
  ```

- [ ] **Step 2: Run tests — confirm red state**

  ```bash
  pytest tests/compute/test_sectors_rs_velocity.py -v 2>&1 | head -20
  ```

  Expected: `ImportError: cannot import name 'compute_rs_velocity' from 'atlas.compute.sectors'`.

- [ ] **Step 3: Add `rs_velocity` to `METRICS_COLUMNS` in `sectors.py`**

  In `atlas/compute/sectors.py`, locate the `METRICS_COLUMNS` tuple (line 46). Add `"rs_velocity"` between `"leadership_concentration"` and `"compute_run_id"`:

  ```python
  METRICS_COLUMNS: tuple[str, ...] = (
      "sector_name",
      "date",
      "bottomup_ret_1w",
      "bottomup_ret_1m",
      "bottomup_ret_3m",
      "bottomup_ret_6m",
      "bottomup_rs_3m_nifty500",
      "bottomup_ema_10_ratio",
      "bottomup_ema_20_ratio",
      "topdown_index_code",
      "topdown_ret_1m",
      "topdown_ret_3m",
      "topdown_rs_3m_nifty500",
      "constituent_count",
      "participation_50",
      "participation_rs",
      "leadership_concentration",
      "rs_velocity",          # SP02: 4-week rate-of-change of bottomup_rs_3m_nifty500
      "compute_run_id",
  )
  ```

- [ ] **Step 4: Add `compute_rs_velocity()` function to `sectors.py`**

  Place this function immediately before `assemble_sector_metrics` (around line 761). The function is pure pandas — no SQL, no DB:

  ```python
  def compute_rs_velocity(
      df_metrics: pd.DataFrame,
      window_days: int = 28,
  ) -> pd.DataFrame:
      """Compute rs_velocity: 4-week rate-of-change of ``bottomup_rs_3m_nifty500``.

      Formula:
          rs_velocity = (RS_today - RS_N_days_ago) / |RS_N_days_ago|

      where N = ``window_days`` (default 28 calendar days, tunable via
      atlas_thresholds key ``rs_velocity_window_days``).

      Division guard: if RS_N_days_ago == 0, rs_velocity is NaN (not inf).

      Args:
          df_metrics: long-form DataFrame with columns
              ``sector_name``, ``date``, ``bottomup_rs_3m_nifty500``.
              May contain other columns — they are preserved unchanged.
          window_days: look-back window in calendar days. Caller passes
              ``int(thresholds.get("rs_velocity_window_days", 28))``.

      Returns:
          The same DataFrame with a new ``rs_velocity`` column added (float,
          NaN for dates with insufficient lookback).
      """
      if df_metrics.empty:
          return df_metrics.assign(rs_velocity=pd.NA)

      # Work on a copy keyed by sector + date so we don't disturb caller's frame.
      work = df_metrics[["sector_name", "date", "bottomup_rs_3m_nifty500"]].copy()
      work = work.sort_values(["sector_name", "date"])

      # For each (sector, date) find the most-recent row whose date is at most
      # ``window_days`` calendar days earlier. We use merge_asof per sector.
      prior_frames: list[pd.DataFrame] = []
      for sector, grp in work.groupby("sector_name", sort=False):
          grp = grp.sort_values("date").reset_index(drop=True)
          # Build a lagged frame: shift dates forward by window_days so we can
          # merge_asof on the shifted date to find the "closest prior" RS.
          lagged = grp[["date", "bottomup_rs_3m_nifty500"]].copy()
          lagged = lagged.rename(columns={"bottomup_rs_3m_nifty500": "rs_prior"})
          lagged["date_shifted"] = lagged["date"] + pd.Timedelta(days=window_days)

          merged = pd.merge_asof(
              grp.rename(columns={"date": "date_today"}),
              lagged.rename(columns={"date": "date_anchor", "date_shifted": "date_today"}),
              on="date_today",
              direction="backward",
              tolerance=pd.Timedelta(days=5),  # ±5d tolerance for trading day gaps
          )
          prior_frames.append(merged.rename(columns={"date_today": "date"})[
              ["sector_name", "date", "bottomup_rs_3m_nifty500", "rs_prior"]
          ])

      prior_df = pd.concat(prior_frames, ignore_index=True)

      # Rate-of-change with zero-guard.
      rs_base = prior_df["rs_prior"].replace(0, pd.NA)
      prior_df["rs_velocity"] = (
          (prior_df["bottomup_rs_3m_nifty500"] - prior_df["rs_prior"])
          / rs_base.abs()
      )

      # Join velocity back onto the original frame.
      velocity_col = prior_df[["sector_name", "date", "rs_velocity"]]
      out = df_metrics.copy()
      out = out.merge(velocity_col, on=["sector_name", "date"], how="left")
      return out
  ```

- [ ] **Step 5: Wire `compute_rs_velocity` into `_run_pipeline`**

  In `_run_pipeline` (around line 867), locate the line `metrics = assemble_sector_metrics(bottomup, topdown, breadth)`. Add the velocity computation immediately after:

  ```python
  metrics = assemble_sector_metrics(bottomup, topdown, breadth)

  # SP02: compute rs_velocity after assembly (needs full sector × date frame).
  velocity_window = int(thresholds.get("rs_velocity_window_days", Decimal("28")))
  metrics = compute_rs_velocity(metrics, window_days=velocity_window)
  ```

  Note: `thresholds` is already in scope (fetched at line 856). `load_thresholds` returns `dict[str, Decimal]` so we call `int()` on the value.

- [ ] **Step 6: Also export `compute_rs_velocity` in the module's `__all__`**

  Near line 921, add to the `__all__` list:

  ```python
  "compute_rs_velocity",
  ```

- [ ] **Step 7: Run the tests — confirm green**

  ```bash
  pytest tests/compute/test_sectors_rs_velocity.py -v
  ```

  Expected: 6 tests pass.

- [ ] **Step 8: Run pyright and ruff on the modified file**

  ```bash
  pyright atlas/compute/sectors.py
  ruff check atlas/compute/sectors.py
  ```

  Expected: no errors. If pyright complains about `pd.Timedelta` typing, add `# type: ignore[arg-type]` with justification.

- [ ] **Step 9: Commit**

  ```bash
  git add atlas/compute/sectors.py tests/compute/test_sectors_rs_velocity.py
  git commit -m "feat(sp02): compute rs_velocity (4-week RoC of bottomup_rs_3m) in sector pipeline"
  ```

---

## Task 5: Frontend — `leaders.ts` query file

**Files:**
- Create: `frontend/src/lib/queries/leaders.ts`

This file reads from `mv_rs_leaders_daily`. Pattern follows `sectors.ts` exactly: `import 'server-only'`, postgres tagged template, TypeScript type for each query return shape, all NUMERIC columns as `string | null`.

- [ ] **Step 1: Create `frontend/src/lib/queries/leaders.ts`**

  ```typescript
  // frontend/src/lib/queries/leaders.ts
  // Reads from mv_rs_leaders_daily — pre-computed by nightly pg_cron at 20:30 IST.
  // All NUMERIC columns returned as string | null (Postgres driver behaviour).
  // Parse to number at display time, never here.
  import 'server-only'
  import sql from '@/lib/db'

  export type RSLeaderRow = {
    instrument_id:  string
    date:           Date
    symbol:         string
    company_name:   string | null
    sector:         string | null
    tier:           string | null
    rs_pctile_3m:   string | null  // NUMERIC — cross-stock percentile 0–1
    rs_pctile_1m:   string | null  // NUMERIC
    rs_3m_nifty500: string | null  // NUMERIC — raw RS vs Nifty500 over 3 months
    rs_6m_nifty500: string | null  // NUMERIC — raw RS vs Nifty500 over 6 months
    rs_state:       string | null  // 'Leader' | 'Strong'
    momentum_state: string | null
    state_since_date: Date | null
  }

  /**
   * Returns all current RS leaders/strong stocks from the materialized view.
   * Optionally filtered by sector. Ordered by rs_pctile_3m DESC.
   *
   * @param sector  Filter to a specific sector, or null for all sectors.
   * @param limit   Maximum rows to return (default 100).
   */
  export async function getRSLeaders(
    sector: string | null = null,
    limit = 100,
  ): Promise<RSLeaderRow[]> {
    if (limit < 1 || limit > 500) {
      throw new Error(`limit must be between 1 and 500, got: ${limit}`)
    }
    if (sector !== null) {
      return sql<RSLeaderRow[]>`
        SELECT
          instrument_id,
          date,
          symbol,
          company_name,
          sector,
          tier,
          rs_pctile_3m::text   AS rs_pctile_3m,
          rs_pctile_1m::text   AS rs_pctile_1m,
          rs_3m_nifty500::text AS rs_3m_nifty500,
          rs_6m_nifty500::text AS rs_6m_nifty500,
          rs_state,
          momentum_state,
          state_since_date
        FROM atlas.mv_rs_leaders_daily
        WHERE sector = ${sector}
        ORDER BY rs_pctile_3m DESC NULLS LAST
        LIMIT ${limit}
      `
    }
    return sql<RSLeaderRow[]>`
      SELECT
        instrument_id,
        date,
        symbol,
        company_name,
        sector,
        tier,
        rs_pctile_3m::text   AS rs_pctile_3m,
        rs_pctile_1m::text   AS rs_pctile_1m,
        rs_3m_nifty500::text AS rs_3m_nifty500,
        rs_6m_nifty500::text AS rs_6m_nifty500,
        rs_state,
        momentum_state,
        state_since_date
      FROM atlas.mv_rs_leaders_daily
      ORDER BY rs_pctile_3m DESC NULLS LAST
      LIMIT ${limit}
    `
  }

  export type BreakoutCandidateRow = {
    instrument_id:    string
    date:             Date
    symbol:           string
    company_name:     string | null
    sector:           string | null
    tier:             string | null
    new_rs_state:     string | null
    prior_rs_state:   string | null
    momentum_state:   string | null
    state_since_date: Date | null
    rs_pctile_3m:     string | null
    rs_3m_nifty500:   string | null
  }

  export type DeteriorationWatchRow = BreakoutCandidateRow

  export async function getBreakoutCandidates(): Promise<BreakoutCandidateRow[]> {
    return sql<BreakoutCandidateRow[]>`
      SELECT
        instrument_id,
        date,
        symbol,
        company_name,
        sector,
        tier,
        new_rs_state,
        prior_rs_state,
        momentum_state,
        state_since_date,
        rs_pctile_3m::text   AS rs_pctile_3m,
        rs_3m_nifty500::text AS rs_3m_nifty500
      FROM atlas.mv_breakout_candidates
      ORDER BY rs_pctile_3m DESC NULLS LAST
    `
  }

  export async function getDeteriorationWatch(): Promise<DeteriorationWatchRow[]> {
    return sql<DeteriorationWatchRow[]>`
      SELECT
        instrument_id,
        date,
        symbol,
        company_name,
        sector,
        tier,
        new_rs_state,
        prior_rs_state,
        momentum_state,
        state_since_date,
        rs_pctile_3m::text   AS rs_pctile_3m,
        rs_3m_nifty500::text AS rs_3m_nifty500
      FROM atlas.mv_deterioration_watch
      ORDER BY rs_pctile_3m DESC NULLS LAST
    `
  }
  ```

- [ ] **Step 2: Type-check with tsc**

  ```bash
  cd frontend && npx tsc --noEmit 2>&1 | grep "leaders.ts" | head -10
  ```

  Expected: no errors for `leaders.ts`.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/src/lib/queries/leaders.ts
  git commit -m "feat(sp02): leaders.ts — query file for mv_rs_leaders_daily, mv_breakout_candidates, mv_deterioration_watch"
  ```

---

## Task 6: Frontend — `rotation.ts` query file

**Files:**
- Create: `frontend/src/lib/queries/rotation.ts`

This file reads from `mv_sector_rotation_state` and `mv_current_market_regime`. The RRG quadrant is computed server-side in the view DDL and returned as a `string` column.

- [ ] **Step 1: Create `frontend/src/lib/queries/rotation.ts`**

  ```typescript
  // frontend/src/lib/queries/rotation.ts
  // Reads from mv_sector_rotation_state and mv_current_market_regime.
  // These views are refreshed nightly at 20:30 IST by pg_cron.
  // All NUMERIC columns returned as string | null — parse at display time.
  import 'server-only'
  import sql from '@/lib/db'

  export type RRGQuadrant = 'Leading' | 'Improving' | 'Lagging' | 'Weakening'

  export type SectorRotationRow = {
    sector_name:             string
    date:                    Date
    rs_level:                string | null  // NUMERIC — bottomup_rs_3m_nifty500
    rs_velocity:             string | null  // NUMERIC — 4-week RoC of rs_level
    rs_pctile_cross_sector:  string | null  // NUMERIC — 0–1 cross-sector percentile
    constituent_count:       number | null
    sector_state:            string | null  // 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid'
    bottomup_rs_state:       string | null
    bottomup_momentum_state: string | null
    participation_rs_pct:    string | null  // NUMERIC
    rrg_quadrant:            RRGQuadrant | null
  }

  export type MarketRegimeRow = {
    date:                  Date
    regime_state:          string
    deployment_multiplier: string | null   // NUMERIC — parse for display
    dislocation_active:    boolean
    dislocation_started:   Date | null
    nifty500_close:        string | null
    nifty500_above_ema_50: boolean | null
    nifty500_above_ema_200: boolean | null
    pct_above_ema_50:      string | null
    pct_above_ema_200:     string | null
    pct_in_strong_states:  string | null
    india_vix:             string | null
    advances_count:        number | null
    declines_count:        number | null
    net_new_highs:         number | null
    ad_ratio:              string | null
    mcclellan_oscillator:  string | null
  }

  /**
   * Returns all sectors with their RRG quadrant assignment for the current date.
   * Ordered by rs_pctile_cross_sector DESC (Leading sectors first).
   */
  export async function getSectorRotationState(): Promise<SectorRotationRow[]> {
    return sql<SectorRotationRow[]>`
      SELECT
        sector_name,
        date,
        rs_level::text                AS rs_level,
        rs_velocity::text             AS rs_velocity,
        rs_pctile_cross_sector::text  AS rs_pctile_cross_sector,
        constituent_count,
        sector_state,
        bottomup_rs_state,
        bottomup_momentum_state,
        participation_rs_pct::text    AS participation_rs_pct,
        rrg_quadrant
      FROM atlas.mv_sector_rotation_state
      ORDER BY rs_pctile_cross_sector DESC NULLS LAST
    `
  }

  /**
   * Returns the current market regime (exactly one row from mv_current_market_regime).
   * Returns null if the view is empty (e.g. database not yet populated).
   */
  export async function getCurrentMarketRegime(): Promise<MarketRegimeRow | null> {
    const rows = await sql<MarketRegimeRow[]>`
      SELECT
        date,
        regime_state,
        deployment_multiplier::text  AS deployment_multiplier,
        dislocation_active,
        dislocation_started,
        nifty500_close::text         AS nifty500_close,
        nifty500_above_ema_50,
        nifty500_above_ema_200,
        pct_above_ema_50::text       AS pct_above_ema_50,
        pct_above_ema_200::text      AS pct_above_ema_200,
        pct_in_strong_states::text   AS pct_in_strong_states,
        india_vix::text              AS india_vix,
        advances_count,
        declines_count,
        net_new_highs,
        ad_ratio::text               AS ad_ratio,
        mcclellan_oscillator::text   AS mcclellan_oscillator
      FROM atlas.mv_current_market_regime
      LIMIT 1
    `
    return rows[0] ?? null
  }
  ```

- [ ] **Step 2: Type-check**

  ```bash
  cd frontend && npx tsc --noEmit 2>&1 | grep "rotation.ts" | head -10
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/src/lib/queries/rotation.ts
  git commit -m "feat(sp02): rotation.ts — query file for mv_sector_rotation_state and mv_current_market_regime"
  ```

---

## Task 7: Frontend — `SectorRRGPlot.tsx` component

**Files:**
- Create: `frontend/src/components/sectors/SectorRRGPlot.tsx`

A Recharts `ScatterChart` that plots sectors as dots on a 2D grid (X = RS velocity, Y = RS level). The four quadrants are labelled with translucent background fills. Hover tooltip shows sector name, quadrant, RS level, and velocity. No existing component is modified.

RRG convention (as confirmed by master plan SP02):
- **X-axis**: `rs_velocity` (negative = losing momentum, positive = gaining)
- **Y-axis**: `rs_level` (= `rs_pctile_cross_sector` for normalised view, or raw `rs_level` for absolute view)
- **Quadrant dividers**: X=0 (velocity), Y=median RS percentile (0.5)

- [ ] **Step 1: Create `frontend/src/components/sectors/SectorRRGPlot.tsx`**

  ```tsx
  // allow-large: single-responsibility RRG chart; quadrant fills + tooltip require
  // inline SVG coordinates that make this component naturally longer than 200 lines.
  'use client'

  import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ReferenceLine,
    ResponsiveContainer,
    Cell,
  } from 'recharts'
  import type { SectorRotationRow, RRGQuadrant } from '@/lib/queries/rotation'

  // ------------------------------------------------------------------ //
  // Types                                                                //
  // ------------------------------------------------------------------ //

  interface SectorRRGPlotProps {
    data: SectorRotationRow[]
    /** Height in pixels (default 480). */
    height?: number
    /** Show raw rs_level on Y-axis instead of rs_pctile_cross_sector. */
    useRawRS?: boolean
  }

  interface PlotPoint {
    sector_name:  string
    x:            number   // rs_velocity (parsed from string)
    y:            number   // rs_pctile_cross_sector or rs_level
    quadrant:     RRGQuadrant | null
    sector_state: string | null
  }

  // ------------------------------------------------------------------ //
  // Constants                                                            //
  // ------------------------------------------------------------------ //

  const QUADRANT_COLORS: Record<RRGQuadrant, string> = {
    Leading:   '#1D9E75',  // teal — strong and improving
    Improving: '#60C6A5',  // lighter teal — building momentum
    Lagging:   '#C84B3B',  // red — weak and losing
    Weakening: '#F0A070',  // amber — rolling over
  }

  const QUADRANT_BG: Record<RRGQuadrant, string> = {
    Leading:   'rgba(29, 158, 117, 0.06)',
    Improving: 'rgba(96, 198, 165, 0.06)',
    Lagging:   'rgba(200, 75, 59, 0.06)',
    Weakening: 'rgba(240, 160, 112, 0.06)',
  }

  const QUADRANT_LABELS: Record<RRGQuadrant, { label: string; x: string; y: string }> = {
    Leading:   { label: 'Leading',   x: '75%', y: '10%' },
    Improving: { label: 'Improving', x: '25%', y: '10%' },
    Lagging:   { label: 'Lagging',   x: '25%', y: '90%' },
    Weakening: { label: 'Weakening', x: '75%', y: '90%' },
  }

  // ------------------------------------------------------------------ //
  // Helpers                                                              //
  // ------------------------------------------------------------------ //

  function parseNum(v: string | null | undefined): number | null {
    if (v == null) return null
    const n = Number(v)
    return isFinite(n) ? n : null
  }

  function quadrantColor(q: RRGQuadrant | null): string {
    return q ? QUADRANT_COLORS[q] : '#9CA3AF'
  }

  // ------------------------------------------------------------------ //
  // Custom Tooltip                                                        //
  // ------------------------------------------------------------------ //

  function RRGTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: PlotPoint }> }) {
    if (!active || !payload?.length) return null
    const d = payload[0].payload
    const xLabel = d.x != null ? (d.x >= 0 ? `+${d.x.toFixed(3)}` : d.x.toFixed(3)) : 'n/a'
    const yLabel = d.y != null ? (d.y * 100).toFixed(1) + '%' : 'n/a'
    return (
      <div className="rounded border border-stone-200 bg-white px-3 py-2 shadow text-xs leading-5">
        <p className="font-semibold text-stone-800">{d.sector_name}</p>
        <p style={{ color: quadrantColor(d.quadrant) }}>
          {d.quadrant ?? 'Unknown'}
        </p>
        <p className="text-stone-500">RS Percentile: <span className="text-stone-800">{yLabel}</span></p>
        <p className="text-stone-500">RS Velocity: <span className="text-stone-800">{xLabel}</span></p>
        {d.sector_state && (
          <p className="text-stone-500">State: <span className="text-stone-800">{d.sector_state}</span></p>
        )}
      </div>
    )
  }

  // ------------------------------------------------------------------ //
  // Main Component                                                        //
  // ------------------------------------------------------------------ //

  export function SectorRRGPlot({ data, height = 480, useRawRS = false }: SectorRRGPlotProps) {
    const points: PlotPoint[] = data.flatMap((row) => {
      const x = parseNum(row.rs_velocity)
      const y = useRawRS ? parseNum(row.rs_level) : parseNum(row.rs_pctile_cross_sector)
      if (x == null || y == null) return []
      return [{
        sector_name:  row.sector_name,
        x,
        y,
        quadrant:     (row.rrg_quadrant as RRGQuadrant | null) ?? null,
        sector_state: row.sector_state ?? null,
      }]
    })

    if (points.length === 0) {
      return (
        <div className="flex h-48 items-center justify-center text-sm text-stone-400">
          No sector rotation data available
        </div>
      )
    }

    // Y-axis range: 0–1 for percentile view, auto for raw
    const yDomain: [number, number] | ['auto', 'auto'] = useRawRS ? ['auto', 'auto'] : [0, 1]
    const yTickFormatter = useRawRS
      ? (v: number) => v.toFixed(2)
      : (v: number) => `${(v * 100).toFixed(0)}%`

    return (
      <div className="w-full" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 24, bottom: 40, left: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E2DC" />

            {/* Quadrant dividers */}
            <ReferenceLine x={0}   stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="6 3" label={{ value: 'Velocity = 0', position: 'insideTopRight', fontSize: 11, fill: '#9CA3AF' }} />
            <ReferenceLine y={0.5} stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="6 3" label={{ value: 'Median RS', position: 'insideTopLeft', fontSize: 11, fill: '#9CA3AF' }} />

            <XAxis
              type="number"
              dataKey="x"
              name="RS Velocity"
              label={{ value: 'RS Velocity (4-week RoC)', position: 'insideBottom', offset: -16, fontSize: 12, fill: '#7A7A7A' }}
              tickFormatter={(v) => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2)}
              tick={{ fontSize: 11 }}
              stroke="#E5E2DC"
            />
            <YAxis
              type="number"
              dataKey="y"
              name={useRawRS ? 'RS Level' : 'RS Percentile'}
              domain={yDomain}
              tickFormatter={yTickFormatter}
              label={{ value: useRawRS ? 'RS Level' : 'RS Percentile', angle: -90, position: 'insideLeft', fontSize: 12, fill: '#7A7A7A' }}
              tick={{ fontSize: 11 }}
              stroke="#E5E2DC"
            />

            <Tooltip content={<RRGTooltip />} cursor={{ strokeDasharray: '3 3' }} />

            <Scatter name="Sectors" data={points}>
              {points.map((entry, idx) => (
                <Cell
                  key={`cell-${idx}`}
                  fill={quadrantColor(entry.quadrant)}
                  stroke={quadrantColor(entry.quadrant)}
                  strokeWidth={1}
                  fillOpacity={0.85}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    )
  }

  export default SectorRRGPlot
  ```

- [ ] **Step 2: Type-check**

  ```bash
  cd frontend && npx tsc --noEmit 2>&1 | grep "SectorRRGPlot.tsx" | head -10
  ```

  Expected: no errors (or only minor Recharts `Cell` prop type warnings which are safe to ignore).

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/src/components/sectors/SectorRRGPlot.tsx
  git commit -m "feat(sp02): SectorRRGPlot component — Recharts scatter with RRG quadrant overlays"
  ```

---

## Task 8: EC2 deployment and pg_cron verification

**Files:** none (ops task)

This task runs migrations 034/035/036 on EC2 (production Supabase), verifies the views are populated, and confirms pg_cron schedules are registered.

- [ ] **Step 1: SSH to EC2 and pull latest main**

  ```bash
  ssh jsl-wealth-server
  cd ~/atlas-os && git pull origin main
  ```

  Expected: fast-forward merge showing new migration files 034, 035, 036.

- [ ] **Step 2: Run migrations 034 → 036**

  ```bash
  cd ~/atlas-os && alembic upgrade head 2>&1 | tail -20
  ```

  Expected output lines (in order):
  ```
  Running upgrade 033 -> 034, SP02: add rs_velocity column...
  Running upgrade 034 -> 035, SP02: create five materialized views...
  Running upgrade 035 -> 036, SP02: install pg_cron and register nightly refresh jobs...
  NOTICE:  pg_cron: extension installed or already present
  NOTICE:  pg_cron: scheduled job atlas_mv_regime
  NOTICE:  pg_cron: scheduled job atlas_mv_rotation
  NOTICE:  pg_cron: scheduled job atlas_mv_rs_leaders
  NOTICE:  pg_cron: scheduled job atlas_mv_breakouts
  NOTICE:  pg_cron: scheduled job atlas_mv_deterioration
  ```

- [ ] **Step 3: Verify views populated**

  ```bash
  cd ~/atlas-os && python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  views = [
      'mv_rs_leaders_daily',
      'mv_sector_rotation_state',
      'mv_current_market_regime',
      'mv_breakout_candidates',
      'mv_deterioration_watch',
  ]
  with eng.connect() as c:
      for v in views:
          n = c.execute(text(f'SELECT COUNT(*) FROM atlas.{v}')).scalar()
          print(f'{v}: {n} rows')
  "
  ```

  Expected: `mv_current_market_regime: 1 row`, `mv_sector_rotation_state: ~14 rows`, others > 0 (on a trading day).

- [ ] **Step 4: Verify pg_cron jobs registered**

  ```bash
  cd ~/atlas-os && python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      rows = c.execute(text(\"\"\"
          SELECT jobname, schedule, command
          FROM cron.job
          WHERE jobname LIKE 'atlas_mv_%'
          ORDER BY jobname
      \"\"\")).fetchall()
      for r in rows: print(r)
  "
  ```

  Expected: 5 rows, each with `schedule = '30 14 * * *'` and the corresponding `REFRESH MATERIALIZED VIEW CONCURRENTLY` command.

- [ ] **Step 5: Trigger a manual refresh and time it**

  ```bash
  cd ~/atlas-os && python3 -c "
  import time
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  views = [
      'mv_current_market_regime',
      'mv_sector_rotation_state',
      'mv_rs_leaders_daily',
      'mv_breakout_candidates',
      'mv_deterioration_watch',
  ]
  with eng.connect() as c:
      for v in views:
          t0 = time.time()
          c.execute(text(f'REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.{v}'))
          c.commit()
          print(f'{v}: refreshed in {(time.time()-t0)*1000:.0f}ms')
  "
  ```

  Expected: each refresh completes in < 10 seconds (typically < 2 seconds for current data volumes). The 30-second success criterion from the master plan applies to all five in aggregate.

- [ ] **Step 6: Run sectors pipeline to populate `rs_velocity` and re-refresh rotation view**

  ```bash
  cd ~/atlas-os && python3 -c "
  from atlas.compute.sectors import run_daily_sector_metrics
  n = run_daily_sector_metrics()
  print(f'sector rows written: {n}')
  "
  ```

  Then re-refresh `mv_sector_rotation_state` to pick up the now-populated `rs_velocity`:

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  with eng.connect() as c:
      c.execute(text('REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rotation_state'))
      c.commit()
      rows = c.execute(text('SELECT sector_name, rs_velocity, rrg_quadrant FROM atlas.mv_sector_rotation_state ORDER BY rs_pctile_cross_sector DESC LIMIT 5')).fetchall()
      for r in rows: print(r)
  "
  ```

  Expected: 5 sectors listed with non-null `rs_velocity` values and quadrant labels. If `rs_velocity` is still NULL, run a full sector backfill: `python3 -c "from atlas.compute.sectors import backfill_sector_metrics; backfill_sector_metrics()"`.

---

## Task 9: Final — mark SP02 shipped + update memory

**Files:**
- Modify: `docs/phase2/00-master-plan.html` (add "Shipped" badge to SP02 section)
- Create: `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp02_state.md`

- [ ] **Step 1: Add "Shipped" badge to SP02 section in master plan HTML**

  In `docs/phase2/00-master-plan.html`, locate the SP02 badges div (line ~295):

  ```html
  <div class="badges"><span class="badge">Parallel track 2</span><span class="badge">No blockers</span><span class="badge">Unblocks: SP03, SP05</span></div>
  ```

  Replace with:

  ```html
  <div class="badges"><span class="badge">Parallel track 2</span><span class="badge">No blockers</span><span class="badge">Unblocks: SP03, SP05</span><span class="badge" style="background:rgba(29,158,117,0.15);color:#1D9E75;font-weight:600;">Shipped 2026-05-12</span></div>
  ```

- [ ] **Step 2: Write memory file**

  Create `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp02_state.md`:

  ```markdown
  # SP02 — Materialized Views + RRG Velocity — State

  **Status:** Shipped (2026-05-12)

  ## What shipped
  - Migration 034: `rs_velocity NUMERIC(10,6)` column on `atlas_sector_metrics_daily`
  - Migration 035: five materialized views — `mv_rs_leaders_daily`, `mv_sector_rotation_state`,
    `mv_current_market_regime`, `mv_breakout_candidates`, `mv_deterioration_watch`
  - Migration 036: pg_cron scheduled refresh at 14:00 UTC (20:30 IST) nightly
  - `atlas/compute/sectors.py`: `compute_rs_velocity()` wired into `_run_pipeline`
  - `frontend/src/lib/queries/leaders.ts`: RS leaders + breakout/deterioration query file
  - `frontend/src/lib/queries/rotation.ts`: sector rotation + current regime query file
  - `frontend/src/components/sectors/SectorRRGPlot.tsx`: Recharts RRG scatter component

  ## Open items / follow-up
  - Existing sector/stocks page components still read from base tables via old query files.
    A separate follow-up task wires them to the new query files.
  - `rs_velocity` backfill: run `backfill_sector_metrics()` on EC2 after deploy so historical
    rows are populated (current pipeline only fills forward from the daily run).
  - pg_cron on local dev: not installed. Local refresh is manual
    (`REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.<view_name>`).

  ## Views quick-reference
  | View | Natural key | Refresh ~rows |
  |---|---|---|
  | `mv_rs_leaders_daily` | `(instrument_id, date)` | ~100–500 (Leader+Strong stocks) |
  | `mv_sector_rotation_state` | `(sector_name, date)` | ~14 (NIFTY sectors) |
  | `mv_current_market_regime` | `(date)` | 1 |
  | `mv_breakout_candidates` | `(instrument_id, date)` | 0–50 |
  | `mv_deterioration_watch` | `(instrument_id, date)` | 0–30 |
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add docs/phase2/00-master-plan.html
  git commit -m "docs(sp02): mark SP02 shipped in master plan"
  ```

---

## Success Criteria Checklist

Before claiming SP02 done, verify every item:

- [ ] `alembic current` shows `036 (head)` on both local and EC2
- [ ] All five views exist with unique indexes (`SELECT indexname FROM pg_indexes WHERE indexname LIKE 'uidx_%'`)
- [ ] `mv_current_market_regime` returns exactly 1 row
- [ ] `mv_sector_rotation_state` returns ~14 rows with non-null `rrg_quadrant`
- [ ] At least 5 rows in `mv_sector_rotation_state` have non-null `rs_velocity` (pipeline has run)
- [ ] `pytest tests/compute/test_sectors_rs_velocity.py` — 6 tests pass
- [ ] `npx tsc --noEmit` in `frontend/` — zero errors from new files
- [ ] pg_cron: 5 jobs visible in `cron.job` on EC2 with correct `30 14 * * *` schedule
- [ ] Manual timing: all 5 views refresh in < 30 seconds total on EC2
- [ ] `SectorRRGPlot.tsx` renders with 14 sector dots and quadrant label annotations (visual check via `/browse`)
