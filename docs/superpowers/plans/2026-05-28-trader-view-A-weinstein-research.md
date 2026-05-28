# Stream A — Weinstein Per Cap-Tier Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the optimal Weinstein MA lookback per cap_tier (Large/Mid/Small) using walk-forward IC validation, and lock the chosen values into `atlas_thresholds` for use by the verdict composer (stream C).

**Architecture:** Pure backend research. SQL-driven stage classification + IC computation against historical price data. Output is data (thresholds + report), not code paths. Runs on EC2 against Supabase.

**Tech Stack:** PostgreSQL (Supabase), Python 3.11, pandas, numpy, SQLAlchemy. EC2 via SSH (Mac psycopg2 broken per memory). No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-28-trader-view-redesign.html` §7.

---

### Task 1: Create candidate-grid view

**Files:**
- Create: `scripts/research/weinstein_lookback_grid.sql`
- Test: run on Supabase via MCP read-only

- [ ] **Step 1: Write the candidate-grid SQL**

```sql
-- scripts/research/weinstein_lookback_grid.sql
-- For each (instrument_id, date, lookback_weeks) compute:
--   - MA value
--   - price vs MA (above / below / near ±2%)
--   - MA slope sign over last 4 weeks
-- Produces a denormalized table for downstream IC compute.

CREATE OR REPLACE VIEW atlas.v_weinstein_grid_candidates AS
WITH params AS (
  SELECT unnest(ARRAY[5, 10, 20, 30]) AS lookback_weeks
),
weekly_close AS (
  SELECT
    instrument_id,
    date_trunc('week', date) AS week_start,
    LAST_VALUE(close_adj) OVER (
      PARTITION BY instrument_id, date_trunc('week', date)
      ORDER BY date
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS close_w
  FROM atlas.atlas_prices_daily
  WHERE date >= '2018-01-01'
)
SELECT
  w.instrument_id,
  w.week_start AS as_of_week,
  p.lookback_weeks,
  AVG(w.close_w) OVER (
    PARTITION BY w.instrument_id, p.lookback_weeks
    ORDER BY w.week_start
    ROWS BETWEEN p.lookback_weeks - 1 PRECEDING AND CURRENT ROW
  ) AS ma_value,
  w.close_w,
  w.close_w / AVG(w.close_w) OVER (...) - 1 AS price_vs_ma_pct
FROM weekly_close w
CROSS JOIN params p;
```

- [ ] **Step 2: Run on Supabase via MCP**

Use `mcp__plugin_supabase_supabase__execute_sql` with the view body. Verify row count = (n_instruments × n_weeks × 4 lookbacks). Expect ~20M rows over 8 years × 500 stocks × 4 lookbacks × 52 weeks.

Expected: query plan uses a hash aggregate not a sort. If timing > 60s, materialize as a table instead.

- [ ] **Step 3: Commit**

```bash
git add scripts/research/weinstein_lookback_grid.sql
git commit -m "research(weinstein): candidate-grid SQL for 5W/10W/20W/30W × all stocks"
```

---

### Task 2: Stage classifier per candidate

**Files:**
- Create: `scripts/research/weinstein_stage_classify.sql`

- [ ] **Step 1: Write the stage classifier**

```sql
-- scripts/research/weinstein_stage_classify.sql
-- For each (instrument_id, week, lookback) compute stage 1/2/3/4
-- using price-vs-MA + MA slope over previous 4 weeks.
-- Slope thresholds match canonical Weinstein:
--   slope_pct = (ma_now - ma_4w_ago) / ma_4w_ago
--   STAGE 1: price above MA, slope flat (|slope| < 0.01)
--   STAGE 2: price above MA, slope > +0.01
--   STAGE 3: price below MA, slope flat (|slope| < 0.01)
--   STAGE 4: price below MA, slope < -0.01

CREATE OR REPLACE VIEW atlas.v_weinstein_stage_classify AS
WITH base AS (
  SELECT
    instrument_id,
    as_of_week,
    lookback_weeks,
    close_w,
    ma_value,
    price_vs_ma_pct,
    LAG(ma_value, 4) OVER (PARTITION BY instrument_id, lookback_weeks ORDER BY as_of_week) AS ma_4w_ago
  FROM atlas.v_weinstein_grid_candidates
),
classified AS (
  SELECT
    *,
    CASE WHEN ma_4w_ago IS NULL THEN NULL
         ELSE (ma_value - ma_4w_ago) / NULLIF(ma_4w_ago, 0)
    END AS ma_slope_pct
  FROM base
)
SELECT
  *,
  CASE
    WHEN ma_slope_pct IS NULL OR ma_value IS NULL THEN NULL
    WHEN close_w >= ma_value AND ma_slope_pct >  0.01 THEN 2
    WHEN close_w >= ma_value AND ABS(ma_slope_pct) <= 0.01 THEN 1
    WHEN close_w <  ma_value AND ABS(ma_slope_pct) <= 0.01 THEN 3
    WHEN close_w <  ma_value AND ma_slope_pct < -0.01 THEN 4
    ELSE NULL
  END AS stage
FROM classified;
```

- [ ] **Step 2: Smoke-test against TATAMOTORS / RELIANCE / YESBANK**

```sql
SELECT as_of_week, lookback_weeks, stage, ma_slope_pct, price_vs_ma_pct
FROM atlas.v_weinstein_stage_classify
WHERE instrument_id IN (
  SELECT instrument_id FROM atlas.atlas_universe_stocks
  WHERE symbol IN ('RELIANCE', 'TMPV', 'YESBANK')
)
AND as_of_week >= '2025-01-01'
ORDER BY instrument_id, as_of_week DESC, lookback_weeks
LIMIT 60;
```

Spot-check: RELIANCE was Stage 2 throughout 2025 H2 in real life. Confirm stage=2 dominates in the 30W column for RELIANCE in that window.

- [ ] **Step 3: Commit**

```bash
git add scripts/research/weinstein_stage_classify.sql
git commit -m "research(weinstein): stage classifier per (instrument × week × lookback)"
```

---

### Task 3: Forward-IC compute

**Files:**
- Create: `scripts/research/weinstein_forward_ic.sql`

- [ ] **Step 1: Write forward-return + IC compute**

```sql
-- scripts/research/weinstein_forward_ic.sql
-- For each (cap_tier × lookback × stage) at each as_of_week,
-- compute forward 6m excess return (vs NIFTY 500) per stock,
-- then Spearman IC across stocks within the (cap_tier, lookback, stage, week) bucket.
-- Note: 6m horizon = 130 trading days. Use trading-day calendar, not calendar weeks.

CREATE TABLE IF NOT EXISTS atlas.weinstein_research_ic AS
WITH stage_with_caps AS (
  SELECT
    s.instrument_id,
    s.as_of_week,
    s.lookback_weeks,
    s.stage,
    u.cap_tier
  FROM atlas.v_weinstein_stage_classify s
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = s.instrument_id
   AND u.effective_to IS NULL
  WHERE u.cap_tier IN ('Large', 'Mid', 'Small')  -- Q5: exclude Micro
    AND s.stage IS NOT NULL
),
forward_returns AS (
  SELECT
    stage_with_caps.*,
    p_now.close_adj  AS price_now,
    p_fwd.close_adj  AS price_6m,
    n_now.close_adj  AS nifty_now,
    n_fwd.close_adj  AS nifty_6m,
    (p_fwd.close_adj / NULLIF(p_now.close_adj, 0) - 1)
      - (n_fwd.close_adj / NULLIF(n_now.close_adj, 0) - 1) AS excess_6m
  FROM stage_with_caps
  LEFT JOIN atlas.atlas_prices_daily p_now
    ON p_now.instrument_id = stage_with_caps.instrument_id
   AND p_now.date = stage_with_caps.as_of_week::date
  LEFT JOIN atlas.atlas_prices_daily p_fwd
    ON p_fwd.instrument_id = stage_with_caps.instrument_id
   AND p_fwd.date = stage_with_caps.as_of_week::date + INTERVAL '130 days'
  LEFT JOIN atlas.atlas_index_prices_daily n_now
    ON n_now.index_code = 'NIFTY 500'
   AND n_now.date = stage_with_caps.as_of_week::date
  LEFT JOIN atlas.atlas_index_prices_daily n_fwd
    ON n_fwd.index_code = 'NIFTY 500'
   AND n_fwd.date = stage_with_caps.as_of_week::date + INTERVAL '130 days'
)
SELECT
  cap_tier,
  lookback_weeks,
  stage,
  COUNT(*) AS n_obs,
  CORR(excess_6m, stage::numeric) AS ic_spearman,  -- ranked by stage; lower = better
  AVG(excess_6m) AS avg_excess,
  STDDEV(excess_6m) AS sd_excess
FROM forward_returns
WHERE excess_6m IS NOT NULL
GROUP BY cap_tier, lookback_weeks, stage
ORDER BY cap_tier, lookback_weeks, stage;
```

- [ ] **Step 2: Execute via Supabase MCP and capture results**

Save results to `docs/v6/2026-05-28-weinstein-ic-raw.csv`.

- [ ] **Step 3: Commit**

```bash
git add scripts/research/weinstein_forward_ic.sql docs/v6/2026-05-28-weinstein-ic-raw.csv
git commit -m "research(weinstein): forward 6m IC per (cap × lookback × stage)"
```

---

### Task 4: Walk-forward validation

**Files:**
- Create: `scripts/research/weinstein_walk_forward.py`

- [ ] **Step 1: Write the walk-forward harness**

```python
# scripts/research/weinstein_walk_forward.py
"""Walk-forward Weinstein lookback validation.

For each (cap_tier, lookback) compute out-of-sample IC across rolling
3-year train / 1-year test windows from 2018 to 2026. A lookback wins
if its mean OOS IC at the chosen tenure beats the IC floor in CONTEXT.md
(>= 0.04 for 6m) AND is stable across windows (SD across windows < 0.02).

Connects to Supabase via DATABASE_URL env var. Run on EC2 (Mac psycopg2
broken). Output is a markdown report at
docs/v6/2026-05-28-weinstein-research-results.md.
"""

from __future__ import annotations
import os
import sys
import datetime as dt
import pandas as pd
from sqlalchemy import create_engine, text

IC_FLOOR_6M = 0.04  # per CONTEXT.md line 568-576
STABILITY_SD_CAP = 0.02
WALK_TRAIN_YEARS = 3
WALK_TEST_YEARS = 1
START_DATE = dt.date(2018, 1, 1)
END_DATE = dt.date(2026, 1, 1)


def engine():
    url = os.environ["DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def ic_window(eng, cap_tier: str, lookback: int, train_start: dt.date, train_end: dt.date) -> float:
    sql = text("""
        SELECT CORR(excess_6m, stage::numeric) AS ic
        FROM atlas.weinstein_research_ic_raw_obs
        WHERE cap_tier = :cap_tier
          AND lookback_weeks = :lookback
          AND as_of_week BETWEEN :start AND :end
    """)
    df = pd.read_sql(sql, eng, params={
        "cap_tier": cap_tier, "lookback": lookback,
        "start": train_start, "end": train_end
    })
    return float(df["ic"].iloc[0]) if not df.empty else float("nan")


def run() -> pd.DataFrame:
    eng = engine()
    rows = []
    for cap_tier in ("Large", "Mid", "Small"):
        for lookback in (5, 10, 20, 30):
            window_start = START_DATE
            window_ics = []
            while window_start + dt.timedelta(days=365 * (WALK_TRAIN_YEARS + WALK_TEST_YEARS)) <= END_DATE:
                train_end = window_start + dt.timedelta(days=365 * WALK_TRAIN_YEARS)
                test_end = train_end + dt.timedelta(days=365 * WALK_TEST_YEARS)
                ic = ic_window(eng, cap_tier, lookback, train_end, test_end)
                window_ics.append((train_end, ic))
                window_start += dt.timedelta(days=365)  # advance 1 year
            mean_ic = sum(ic for _, ic in window_ics) / max(len(window_ics), 1)
            sd_ic = pd.Series([ic for _, ic in window_ics]).std()
            rows.append({
                "cap_tier": cap_tier, "lookback": lookback,
                "mean_oos_ic": mean_ic, "sd_oos_ic": sd_ic,
                "passes_floor": mean_ic >= IC_FLOOR_6M,
                "passes_stability": sd_ic <= STABILITY_SD_CAP,
                "n_windows": len(window_ics),
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run()
    print(df.to_string(index=False))
    df.to_csv("docs/v6/2026-05-28-weinstein-walk-forward.csv", index=False)
```

- [ ] **Step 2: Run on EC2 and capture output**

```bash
ssh atlas "cd /home/ubuntu/atlas-os && source venv/bin/activate && python scripts/research/weinstein_walk_forward.py"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/research/weinstein_walk_forward.py docs/v6/2026-05-28-weinstein-walk-forward.csv
git commit -m "research(weinstein): walk-forward validation harness + raw OOS IC results"
```

---

### Task 5: Whipsaw rate compute

**Files:**
- Create: `scripts/research/weinstein_whipsaw.sql`

- [ ] **Step 1: Write whipsaw query**

```sql
-- scripts/research/weinstein_whipsaw.sql
-- For each (cap_tier × lookback) compute the rate at which stocks
-- flip stage between consecutive weeks. Lower is better (stable).

CREATE TABLE IF NOT EXISTS atlas.weinstein_research_whipsaw AS
WITH transitions AS (
  SELECT
    instrument_id,
    lookback_weeks,
    cap_tier,
    stage,
    LAG(stage) OVER (PARTITION BY instrument_id, lookback_weeks ORDER BY as_of_week) AS prev_stage,
    LAG(stage, 2) OVER (PARTITION BY instrument_id, lookback_weeks ORDER BY as_of_week) AS prev_prev_stage
  FROM atlas.v_weinstein_stage_classify s
  JOIN atlas.atlas_universe_stocks u USING (instrument_id)
  WHERE u.effective_to IS NULL AND u.cap_tier IN ('Large', 'Mid', 'Small')
)
SELECT
  cap_tier,
  lookback_weeks,
  COUNT(*) AS n_obs,
  AVG(CASE WHEN prev_stage IS NOT NULL AND stage != prev_stage THEN 1 ELSE 0 END) AS flip_rate_1w,
  AVG(CASE
        WHEN prev_prev_stage IS NOT NULL
         AND stage = prev_prev_stage
         AND stage != prev_stage
        THEN 1 ELSE 0
      END) AS whipsaw_rate
FROM transitions
GROUP BY cap_tier, lookback_weeks
ORDER BY cap_tier, lookback_weeks;
```

- [ ] **Step 2: Run + commit results**

```bash
git add scripts/research/weinstein_whipsaw.sql
git commit -m "research(weinstein): whipsaw rate per (cap × lookback)"
```

---

### Task 6: Pick winners + write thresholds

**Files:**
- Create: `migrations/versions/113_atlas_weinstein_thresholds.py`

- [ ] **Step 1: Synthesize results**

Read `docs/v6/2026-05-28-weinstein-walk-forward.csv` and `atlas.weinstein_research_whipsaw`. For each cap_tier pick the lookback that:
1. Passes IC floor (mean_oos_ic >= 0.04)
2. Passes stability (sd_oos_ic <= 0.02)
3. Among passers, has the lowest whipsaw_rate

Tiebreaker: prefer the longer lookback (less data churn downstream).

Write the chosen values to `docs/v6/2026-05-28-weinstein-research-results.md` with the rationale.

- [ ] **Step 2: Write migration**

```python
# migrations/versions/113_atlas_weinstein_thresholds.py
"""Add Weinstein per-cap-tier lookback thresholds.

Revision ID: 113_weinstein_thresholds
Revises: 112_<previous>
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa

revision = "113_weinstein_thresholds"
down_revision = "112_<previous>"  # FILL IN actual previous revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add weinstein_ma_weeks_large/mid/small + slope/proximity thresholds
    # to atlas.atlas_thresholds. Winners come from
    # docs/v6/2026-05-28-weinstein-research-results.md.
    op.execute("""
        INSERT INTO atlas.atlas_thresholds (key, value, value_type, description, updated_at)
        VALUES
          ('weinstein.ma_weeks.Large', '30', 'integer',
           'Weinstein moving-average lookback (weeks) for Large-cap stocks',
           NOW()),
          ('weinstein.ma_weeks.Mid',   '20', 'integer',
           'Weinstein moving-average lookback (weeks) for Mid-cap stocks',
           NOW()),
          ('weinstein.ma_weeks.Small', '10', 'integer',
           'Weinstein moving-average lookback (weeks) for Small-cap stocks',
           NOW()),
          ('weinstein.slope_flat_band', '0.01', 'numeric',
           'MA-slope band considered flat (|slope_pct| <= this → Stage 1 or 3)',
           NOW()),
          ('weinstein.price_proximity_band', '0.02', 'numeric',
           'Price-vs-MA proximity band (within ±this → Stage 1 or 3 candidate)',
           NOW())
        ON CONFLICT (key) DO UPDATE
          SET value = EXCLUDED.value,
              updated_at = NOW();
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM atlas.atlas_thresholds
        WHERE key IN (
          'weinstein.ma_weeks.Large',
          'weinstein.ma_weeks.Mid',
          'weinstein.ma_weeks.Small',
          'weinstein.slope_flat_band',
          'weinstein.price_proximity_band'
        );
    """)
```

NOTE: replace placeholder values with the actual winners from the research output.

- [ ] **Step 3: Apply migration and verify**

```bash
ssh atlas "cd /home/ubuntu/atlas-os && source venv/bin/activate && alembic upgrade head"
```

```sql
SELECT key, value FROM atlas.atlas_thresholds WHERE key LIKE 'weinstein.%';
```

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/113_atlas_weinstein_thresholds.py docs/v6/2026-05-28-weinstein-research-results.md
git commit -m "research(weinstein): lock per-tier lookbacks → atlas_thresholds (migration 113)"
```

---

### Task 7: Fast-confirm A/B harness

**Files:**
- Create: `scripts/research/weinstein_fast_confirm_ab.sql`

- [ ] **Step 1: Define fast-confirm rule**

```sql
-- scripts/research/weinstein_fast_confirm_ab.sql
-- Fast-confirm Stage 1→2 promotion: classify as Stage 2 when
--   price >= chosen_MA AND chosen_MA_slope >= 0 for >= 3 consecutive weeks
-- even if strict slope >= 0.01 hasn't been hit.
-- Logs both classifiers in parallel for A/B comparison over 60 days.

CREATE TABLE IF NOT EXISTS atlas.weinstein_ab_log (
  observed_at      timestamptz NOT NULL DEFAULT NOW(),
  instrument_id    uuid        NOT NULL,
  cap_tier         text        NOT NULL,
  ma_weeks         int         NOT NULL,
  stage_strict     int,
  stage_fast       int,
  diverged         boolean     NOT NULL,
  PRIMARY KEY (observed_at, instrument_id, ma_weeks)
);

CREATE INDEX IF NOT EXISTS ix_weinstein_ab_log_observed
  ON atlas.weinstein_ab_log (observed_at);
```

- [ ] **Step 2: Wire daily log writer**

Add a 21:50 UTC pg_cron job (after MV refresh at 21:45 UTC) that writes
one row per (instrument × cap_tier_chosen_lookback) per day. Will produce
~500 rows/day × 60 days = 30K rows for the A/B comparison.

- [ ] **Step 3: Commit + schedule eval at T+60d**

```bash
git add scripts/research/weinstein_fast_confirm_ab.sql
git commit -m "research(weinstein): fast-confirm vs strict A/B logger + 60d schedule"
```

Add to `docs/v6/2026-05-28-weinstein-research-results.md`: "A/B eval scheduled 2026-07-27."

---

### Definition of Done

- [ ] `atlas.atlas_thresholds` contains the 5 weinstein.* keys with research-validated values
- [ ] `docs/v6/2026-05-28-weinstein-research-results.md` documents the winning lookback per cap_tier with mean OOS IC + whipsaw rate + the alternatives considered
- [ ] Migration 113 is applied and reversible
- [ ] A/B logger is writing rows nightly for the 60-day fast-confirm eval
- [ ] Micro-cap is explicitly excluded with a 1-line note ("Q5 spec lock — Micro defaults to no Weinstein veto")
- [ ] No code in `atlas/` references hardcoded lookback values — all reads come from `load_thresholds()` per the architectural rule

### Self-review checklist

- [ ] Every step has actual SQL/Python code, not placeholders
- [ ] Migration revision ID is unique and chains correctly
- [ ] Walk-forward windows are non-overlapping for OOS purity
- [ ] Whipsaw + IC computations exclude Micro
- [ ] IC floor cited from CONTEXT.md, not invented
