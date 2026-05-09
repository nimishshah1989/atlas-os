# M12 — Backend Data Health Observability

**Date:** 2026-05-09
**Audience:** 3 internal users (Nimish, fund manager, Jeet)
**Hosting:** `atlas.jswealth.in/health` (Next.js page in atlas-frontend, same auth as the rest of the app)

---

## Goal

Live monitor the freshness, quality, and pipeline health of atlas-os backend
data. Catch anomalies before they reach client-facing screens. Passive
dashboard — no push alerts.

Two layers:

1. **Pipeline health** — every backfill / daily script logs start, end, status,
   rows written. Dashboard shows last 24 h of runs and 14-day adherence.
2. **Data quality** — every night, snapshot ~30 metrics across atlas.* tables
   and compare today vs yesterday vs 14-day rolling avg. Flag anomalies.

---

## Schema (Migration 013)

Three append-only operational tables. No FKs (operational data shouldn't
break if a referenced run is purged).

### `atlas.atlas_pipeline_runs`
One row per script invocation.
```
run_id          UUID PK
script_name     VARCHAR(64) NOT NULL
milestone       VARCHAR(8)
phase           VARCHAR(32)
started_at      TIMESTAMPTZ NOT NULL
ended_at        TIMESTAMPTZ
status          VARCHAR(16) NOT NULL  -- running | success | failed
rows_written    BIGINT
error_message   TEXT                  -- first 4KB of traceback
host            VARCHAR(64)
git_sha         VARCHAR(40)
```

Indexes: `(script_name, started_at DESC)`.

### `atlas.atlas_validator_results`
One row per validator run.
```
run_id            UUID PK
validator         VARCHAR(16) NOT NULL  -- M3 | M4 | M5
ran_at            TIMESTAMPTZ NOT NULL
total_checks      INTEGER NOT NULL
failures          INTEGER NOT NULL
status            VARCHAR(8) NOT NULL  -- PASS | FAIL
failure_summary   JSONB                 -- first 100 failure labels
host              VARCHAR(64)
git_sha           VARCHAR(40)
```

Indexes: `(validator, ran_at DESC)`.

### `atlas.atlas_health_daily`
Long-format metric snapshots.
```
data_date         DATE        NOT NULL
table_name        VARCHAR(64) NOT NULL
metric_name       VARCHAR(64) NOT NULL
value_today       NUMERIC
value_prior_day   NUMERIC
rolling_14d_avg   NUMERIC
rolling_14d_std   NUMERIC
pct_change_dod    NUMERIC
z_score           NUMERIC
is_anomaly        BOOLEAN     NOT NULL DEFAULT FALSE
severity          VARCHAR(8)            -- info | warn | critical
notes             TEXT
computed_at       TIMESTAMPTZ NOT NULL

PRIMARY KEY (data_date, table_name, metric_name)
```

Indexes: `(data_date DESC, is_anomaly)`.

---

## Metric Catalog

~30 metrics across atlas.* tables. Computed nightly by `health_check_daily.py`.

| Table | Metrics |
|---|---|
| `atlas_market_regime_daily` | `regime_state_today` (categorical), `pct_above_ema_50`, `india_vix`, `breadth_pct`, `dislocation_active` |
| `atlas_sector_states_daily` | `count_overweight`, `count_neutral`, `count_avoid`, `count_state_changes_dod` |
| `atlas_stock_decisions_daily` | `row_count`, `pct_investable`, `pct_market_gate`, `pct_sector_gate`, `pct_strength_gate`, `pct_direction_gate`, `pct_risk_gate`, `pct_volume_gate`, `count_breakout_triggers`, `mean_position_size_pct` |
| `atlas_etf_decisions_daily` | `row_count`, `pct_investable`, `count_breakout_triggers` |
| `atlas_fund_decisions_daily` | `count_recommended`, `count_hold`, `count_reduce`, `count_exit`, `pct_with_entry_trigger` |
| `atlas_fund_metrics_daily` | `row_count`, `pct_null_nav_state`, `mean_rs_pctile_3m` |
| `atlas_stock_metrics_daily` | `row_count`, `pct_null_rs_state` |
| `atlas_etf_metrics_daily` | `row_count`, `pct_null_rs_state` |
| `atlas_fund_lens_monthly` | `row_count` (snapshot, monthly cadence — DoD compares to last disclosure) |

---

## Anomaly Thresholds

For each numeric metric:
- **`info`**: `|z_score| > 1.5` OR `|pct_change_dod| > 0.10`
- **`warn`**: `|z_score| > 2.5` OR `|pct_change_dod| > 0.20`
- **`critical`**: `|z_score| > 4.0` OR `|pct_change_dod| > 0.50`

For categorical metrics (regime_state, sector_state changes), `is_anomaly = true`
whenever value differs from prior day. Severity by domain context:
- Regime flip → critical
- Sector state flip → warn
- DISLOCATION_SUSPENDED → critical

Categorical comparison is exact-match. NULL prior_value = first observation,
no anomaly flag.

---

## Architecture

```
RECORDING LAYER (atlas/health/runs.py)
  Every script wrapped:
    run_id = record_run(script, milestone)
    try: ...do work...
    finally: finish_run(run_id, status, rows, error)
  Writes → atlas_pipeline_runs

ORCHESTRATOR (scripts/health_check_daily.py)
  Runs nightly after m5_daily:
    1. Snapshot row counts + latest dates
    2. Compute ~30 metrics per atlas.* table
    3. Compare today vs yesterday vs 14-day window
    4. Flag anomalies, write atlas_health_daily
    5. Run validate_m3/m4/m5, write atlas_validator_results
  Records itself in atlas_pipeline_runs.

DASHBOARD (atlas-frontend at /health)
  Server Components query atlas.* directly:
    - HealthHeader: aggregate traffic-light
    - PipelineRunsTable: last 24 h
    - FreshnessTable: latest_date + lag per atlas table
    - AnomaliesPanel: today's flagged metrics
    - ValidatorScorecard: M3/M4/M5 history (sparklines)
```

---

## Build Phases

| Phase | Time | Output |
|---|---|---|
| A | ~3 hr | Migration 013, recording layer, daily-script patches |
| B | ~3 hr | Health orchestrator (freshness + metrics + anomaly + validator) |
| C | ~3 hr | Dashboard UI (5 server components) |
| D | ~1 hr | Smoke test on EC2, cron entry, commit/push |

**Total: ~10 hr focused work.**

---

## Success Criteria

1. Migration 013 applies cleanly on EC2.
2. `record_run()` / `finish_run()` callable from any script; rows in `atlas_pipeline_runs` after invocation.
3. `health_check_daily.py` runs end-to-end, writes ~30 rows to `atlas_health_daily`.
4. Anomaly logic unit-tested with boundary inputs (z=2.49 vs z=2.50, pct=0.199 vs pct=0.200).
5. `/health` page renders all 5 sections with live data.
6. Anomaly highlighting uses Atlas DS signal-warn / signal-neg colors.
7. Cron entry on EC2: `health_check_daily.py` runs after `m5_daily`.

---

## Skills Used

- `karpathy-guidelines` — surgical edits, no scope creep
- `frontend-design` — production-grade UI for the dashboard components
- `vercel-react-best-practices` — Server Component query patterns
- `nextjs-app-router-patterns` — `/health` route structure
- `superpowers:test-driven-development` — for `anomaly.py` (math correctness critical)
- `verification-before-completion` — before declaring done
- `design-review` — visual QA after first render
