# v6 Sectors MVs — design spec

**Date:** 2026-05-26
**Owner:** nimish
**Status:** draft (post /grill-with-docs, pre /plan-eng-review)
**Branch:** `feat/v6-mv-sector-cards` (from `feat/v6-deep-search-all-cells` HEAD per user direction)
**Scope:** **five** PostgreSQL materialized views backing the v6 Sectors page (04) +
deep-dive (04a). PR-per-MV. Each MV is a thin SQL aggregation over existing
`atlas_sector_metrics_daily` / `atlas_signal_calls` (+ small extensions for
breadth + RS-window columns). No new compute primitive engines.

## 0 · Locked decisions (post /plan-eng-review)

| ID | Decision |
|---|---|
| D1 | **RS windows persisted.** `atlas_sector_metrics_daily` gains `rs_1w`, `rs_1m`, `rs_6m`, `rs_12m` (alongside existing `bottomup_rs_3m_nifty500`). Backfilled via existing pipeline. Column-add migration is PR4's prerequisite. |
| D2 | **Verdict chip = deterministic map from `sector_state`.** Leading → OVERWEIGHT, Improving → NEUTRAL, Weakening → NEUTRAL, Lagging → UNDERWEIGHT. No new threshold config. Lives on `mv_sector_cards.verdict`. |
| D3 | **5th MV `mv_sector_rotation`** (~50 LOC). Pre-computes 6-week quadrant transitions per sector for the Rotation Pattern story block on /v6/sectors. Depends on PR3 (`mv_sector_rrg`). |
| D4 | **SQL bodies in `atlas/db/views/mv_sector_*.sql`.** Migrations read + execute. Easier git diffs. |
| D5 | **pg_cron chains pipeline + MV refresh** in a single sequence: `run_daily_sector_metrics()` → `REFRESH MV breadth` → `REFRESH MV cards` → `REFRESH MV deepdive` → `REFRESH MV rrg` → `REFRESH MV rotation`. No stale-data race. |
| D6 | **Tests at `tests/integration/test_mv_sector_*.py`** (existing layout). Per-PR: MV-exists, unique-index, row-count invariant, sample-row shape, null-handling. PR2 adds backfill-correctness test (`pct_above_ema20` ∈ [0, 100]). |
| D7 | **Open items R1-R4 verified in PR1/PR4 first commits** (see §7). |

## 1 · Inputs already in place (don't rebuild)

| Source | Provides |
|---|---|
| `atlas_sector_metrics_daily` | `bottomup_rs_3m_nifty500`, `bottomup_ret_{1w,1m,3m,6m}`, `rs_velocity`, `participation_50`, `participation_rs`, `leadership_concentration`, `topdown_*`, `constituent_count` |
| `atlas_sector_states_daily` | `sector_state`, `bottomup_state`, `topdown_state`, `divergence_flag` |
| `atlas_sector_master` | 22 actionable sectors (post-rollup) — `is_active=TRUE` |
| `atlas_signal_calls` | `cell_id`, `action` ∈ POSITIVE/NEUTRAL/NEGATIVE, `confidence_unconditional`, `cap_tier_at_trigger`, `tenure`, `exit_date`, `instrument_id` |
| `atlas_cell_definitions` | `display_name`, `tier`, `tenure`, `direction` |
| `atlas_instruments` | `instrument_id`, `symbol`, `sector`, `mcap` |
| `atlas_thresholds` | `confidence_band_cutoffs` (H≥X, M≥Y) — to be seeded |

## 2 · Extensions required (PR2 only)

ALTER `atlas_sector_metrics_daily` to add nullable columns:
- `pct_above_ema20  NUMERIC(5,2)` — % constituents with close > EMA20
- `pct_above_ema200 NUMERIC(5,2)` — % constituents with close > EMA200
- `pct_52wh        NUMERIC(5,2)` — % with fresh 52-week-high in last 5 trading days
- `hhi             NUMERIC(8,2)` — Herfindahl-Hirschman index (sum mcap-share² × 10000)

Extend `atlas.compute.sectors.compute_sector_breadth` to populate them.
5-year backfill via `backfill_sector_metrics(start_date=date(2021,5,26))`.

## 3 · Five MVs

### 3.1 mv_sector_cards (PR1, ~80 LOC SQL)
**Grain:** one row per sector. 22 rows.
**Use:** drives the 22-sector listing on `/v6/sectors`.

Columns:
- `sector_name` PK
- `constituent_count`, `mcap_total_inr`
- `bottomup_rs_3m_nifty500`, `bottomup_ret_1m`, `bottomup_ret_3m`
- `rs_velocity` (latest)
- `sector_state` ENUM (Leading / Improving / Weakening / Lagging from `atlas_sector_states_daily`)
- `verdict` ENUM (OVERWEIGHT / NEUTRAL / UNDERWEIGHT) — derived in SQL from `sector_state` per D2
- `open_buy_count`, `open_avoid_count`
- `conf_h_count`, `conf_m_count`, `conf_l_count` — derived via `atlas_thresholds` H/M floor keys (D7-R2)
- `as_of_date`

Index: `CREATE UNIQUE INDEX ON mv_sector_cards (sector_name)`.

### 3.2 mv_sector_breadth (PR2, ~70 LOC SQL · NEW)
**Grain:** one row per sector per trading date (5 years × 22 = ~27k rows).
**Use:** sector deep-dive breadth strip, sectors-page heatmap tooltip,
historical breadth divergence.

Columns:
- `(sector_name, date)` PK
- `pct_above_ema20`, `pct_above_ema200`, `pct_52wh`
- `hhi`
- `constituent_count`

Index: `CREATE UNIQUE INDEX ON mv_sector_breadth (sector_name, date)`,
plus secondary `(date)` for date-range scans.

### 3.3 mv_sector_rrg (PR3, ~60 LOC SQL)
**Grain:** 6 rows per sector (one per weekly sample × 22 sectors = 132 rows).
**Use:** RRG quadrant chart on `/v6/sectors` — X = RS-ratio rebased 100, Y = RS-momentum rebased 100.

Sampling rule: each Friday close in the trailing 6-week window. If the
latest date in `atlas_sector_metrics_daily` is not a Friday, the most-recent
trading date stands in for week 0.

Columns:
- `(sector_name, week_offset)` PK — `week_offset` 0..5 (0 = most recent)
- `sample_date`
- `rs_ratio` = `bottomup_rs_3m_nifty500 + 100` (centered at 100 = parity)
- `rs_momentum` = `rs_velocity × 100 + 100` (centered at 100, ±10 clip already applied upstream)
- `quadrant` ∈ {LEADING, WEAKENING, LAGGING, IMPROVING}
- `constituent_count` (for bubble sizing)

Index: `CREATE UNIQUE INDEX ON mv_sector_rrg (sector_name, week_offset)`.

### 3.4 mv_sector_deepdive (PR4, ~120 LOC SQL)
**Grain:** one row per sector (22 rows). Heavy-join view feeding `/v6/sectors/[name]`.
**Use:** the 6-tile hero strip + RS grid + sub-industry breakdown on the deep-dive page.

Columns:
- `sector_name` PK
- All `mv_sector_cards` columns
- 5-window RS grid: `rs_1w`, `rs_1m`, `rs_3m`, `rs_6m`, `rs_12m` — computed from `bottomup_ret_*` minus matching Nifty 500 returns (Nifty 500 returns sourced from `atlas_index_metrics_daily`)
- Latest `pct_above_ema20`, `pct_above_ema200`, `pct_52wh`, `hhi` (joined from `mv_sector_breadth` for latest date)
- Active cell list: `active_cells JSONB` — `[{cell_id, display_name, tier, tenure}, …]` distinct cells where any open BUY in this sector is firing
- `regime_fit` ∈ {High, Mid, Low} — derived from `confidence_regime_conditional` of the sector's open BUYs, bucketed
- `top_subindustry_name`, `top_subindustry_mcap_share` (NULL if sub-industry taxonomy not in scope this PR)

Index: `CREATE UNIQUE INDEX ON mv_sector_deepdive (sector_name)`.

### 3.5 mv_sector_rotation (PR5, ~50 LOC SQL · NEW per D3)
**Grain:** one row per sector. 22 rows.
**Use:** Rotation Pattern story-block card on `/v6/sectors` (Out-of / Into / Improving / Weakening lists).

Columns:
- `sector_name` PK
- `quadrant_today` ∈ {LEADING, WEAKENING, LAGGING, IMPROVING} — same logic as `mv_sector_rrg.quadrant` at `week_offset=0`
- `quadrant_6w_ago` — same at `week_offset=5`
- `rotation_class` ENUM (LEADING_TO_WEAKENING / IMPROVING_TO_LEADING / LAGGING_TO_IMPROVING / WEAKENING_TO_LAGGING / STABLE) — derived from the (6w_ago → today) transition
- `rs_ratio_today`, `rs_ratio_6w_ago` (for client-side sparkline)

Index: `CREATE UNIQUE INDEX ON mv_sector_rotation (sector_name)`.

## 4 · Refresh + ops

- All five MVs created with `CREATE MATERIALIZED VIEW … WITH NO DATA`, then
  populated by an explicit `REFRESH MATERIALIZED VIEW CONCURRENTLY` post-migration.
- pg_cron job `sectors_pipeline_and_mv_refresh_2000_ist` chains the daily sector
  pipeline + MV refresh in one sequence (D5).
- Refresh order: pipeline → `mv_sector_breadth` → `mv_sector_cards` → `mv_sector_deepdive` → `mv_sector_rrg` → `mv_sector_rotation`
  (deepdive joins breadth; rotation joins rrg).

## 5 · Tests (per-PR, TDD)

Each PR follows superpowers:test-driven-development:

1. **Red:** write `tests/db/test_<mv_name>.py` asserting (a) MV exists, (b)
   row-count invariant (22 / ~27k / 132 / 22), (c) sample-row shape, (d)
   unique-index present, (e) null-handling on missing sectors.
2. **Green:** apply migration + REFRESH on the small snapshot fixture
   (100 stocks × 7 years, 22 sectors guaranteed by stratified sampling).
3. **Refactor:** SQL formatting + comment density.

Integration test in `tests/integration/test_sector_mvs_e2e.py` covers all
four MVs after the last PR.

## 6 · Per-PR review gate

Each MV goes through, in order:
1. `superpowers:test-driven-development` (red→green→refactor)
2. `superpowers:verification-before-completion` (run tests, show output)
3. `/codex review`
4. `coderabbit:code-review`
5. `/review` (built-in pre-landing review)
6. squash-merge into main (user authorized per memory)

## 7 · Risks + open items

- **R1 — Sector master count:** if `atlas_sector_master` does not hold exactly
  22 active sectors, PR1 prerequisite is a config migration to align it with
  the locked 22-sector list (CONTEXT.md §Actionable sectors). Verify in PR1
  first commit.
- **R2 — `atlas_thresholds.confidence_band_cutoffs` seed:** if not present,
  PR1 must seed it in the same migration. Cutoffs: H≥0.70, M≥0.50, L<0.50
  (locked from CEO plan H/M/L distribution; revisit at Stage 4 calibration).
- **R3 — Nifty 500 return source for RS windows:** PR4 needs `atlas_index_metrics_daily`
  to carry `ret_1w/1m/3m/6m/12m` for the Nifty 500 row. Verify in PR4 first commit;
  if absent, sub-task adds them.
- **R4 — Sub-industry taxonomy:** PR4's `top_subindustry_*` columns require an
  `atlas_subindustry_master` table that does not yet exist. **Deferred:** these
  two columns ship as NULL in PR4; populated by a follow-on PR.

## 8 · Out of scope

- No new compute engines. All metrics either already exist or are added to
  the existing `compute_sector_breadth` function.
- No frontend wiring — these MVs are read by `/v1/sectors.*` endpoints in
  a separate PR train.
- No SP02-style cron orchestration changes beyond adding the four MVs to the
  existing pg_cron job catalog.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | (not run — scoped feature, no business pivot) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 3 architectural decisions locked (D1/D2/D3); 4 quality decisions locked (D4-D7); 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | (mockups already locked 2026-05-26) |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | (runs per-PR, not at plan stage) |

**UNRESOLVED:** 0 — all three plan-time questions answered.
**VERDICT:** ENG CLEARED — ready to implement. PR-per-MV. Codex + CodeRabbit + /review run per-PR.
