# Atlas State Engine — Design Spec

**Status:** DRAFT
**Date:** 2026-05-18
**Branch:** feat/atlas-strategy-lab
**Supersedes:** none (this is a fundamental redesign of the engine layer)

## Problem statement

Today's Atlas state indicators are empirically broken. The state validator (Chunk 9, shipped 2026-05-18) ran IC on 8 currently-displayed state badges over 2023-2024 at 63d horizon and produced:

| State | Status | Mean IC | IC IR | Interpretation |
|---|---|---|---|---|
| rs_state | decorative | -0.001 | -0.02 | NOT predictive |
| momentum_state | weak | +0.021 | +0.30 | borderline |
| risk_state | weak | -0.038 | -0.33 | borderline sign-aligned |
| volume_state | weak | +0.028 | +0.32 | borderline |
| history_gate_pass | **validated_inverse** | -0.042 | **-0.89** | gate-passers UNDERPERFORM |
| liquidity_gate_pass | **validated_inverse** | -0.075 | **-1.11** | gate-passers UNDERPERFORM |
| weinstein_gate_pass | decorative | +0.014 | +0.18 | NOT predictive |
| stage1_base_qualifies | weak | -0.022 | -0.34 | weakly sign-inverted |

The gates Atlas has been treating as quality filters (history, liquidity) are anti-predictive: stocks that pass them underperform stocks that fail them. The states fund managers see on every page are decorative or wrong.

Meanwhile, the V5 continuous-signal strategy (BASELINE-V5-RP-TREND, deployed today) sits at rank 1 of the leaderboard with +20.18% alpha OOS, 6/10 years DD-compliant, 9/10 alpha-positive years. The math works when the engine ignores the broken states.

This spec converts Atlas into a **state-defined engine of relative strength based instrument identification**, with pure price + volume data, stock as atomic element, and sector/MF/ETF/country views emerging bottom-up. The engine's primitives become trustworthy via IC-validated rule thresholds and an empirical burn-in before any swap.

## Goal

Redesign the engine such that:

1. Every state shown to a fund manager has an IC-validated rule definition that predicts forward returns at its action horizon.
2. The atomic decision unit is the stock; sector/MF/ETF/country views emerge from constituent state aggregation plus direct classification of the wrapper.
3. The engine uses pure price + volume data — no fundamentals, no news, no flow data.
4. Every recommendation carries a quantitative urgency signal (dwell-time vs cohort baseline), not just a composite-score percentile.
5. V5 stays rank 1 until the new state engine empirically wins on the live leaderboard.

Goal-post operational check (`atlas-lab goal-post --rank 1` returns `met:true`) stays green throughout the build.

## Constraints

- **Pure P+V**: Rung 2 — OHLCV at stock + index level plus everything derivable from it (SMA, EMA, RS rank, ATR, OBV, ADX, distribution days, % off 52w high/low, breadth, base depth/length). No EPS, news, ratings, sentiment, flows.
- **No fundamentals**: hard rule confirmed by user across multiple sessions.
- **Bottom-up**: stock states are atomic; sector/MF/ETF/country derive from constituent states + same classifier applied to wrapper OHLCV.
- **Coexistence**: V5 stays live; new engine builds alongside. `atlas_stock_states_daily` (old) coexists with `atlas_stock_state_daily` (new) until downstream migrates.
- **Atlas modulith**: new code lives in `atlas/intelligence/states/`. Hook-enforced file-size limits (600 LOC source, 800 LOC tests) apply.
- **All thresholds in DB**: every learned θ lands in `atlas_state_thresholds` with history. Never hardcoded in Python.

## Premises (agreed during brainstorm)

1. **P1 — State role**: state acts as binary filter; within-state rank is a continuous composite. Both IC-validated. State transitions trigger actions; within-state rank drives position size.
2. **P2 — State catalog**: 7 states — Uninvestable, Stage 1 Base, Stage 2A Fresh Breakout, Stage 2B Confirmed, Stage 2C Mature, Stage 3 Top, Stage 4 Decline. Maps to Weinstein 4-stage with Stage 2 sub-states for buy-zone differentiation.
3. **P3 — Input universe**: Rung 2 (OHLCV + canonical technicals). No fundamentals.
4. **P4 — Aggregation**: dual view per non-stock instrument — direct classification of wrapper + constituent breadth. Breadth-primary for sectors/countries (fresh data); direct-primary for ETFs/MFs (holdings stale).
5. **P5 — Dwell + urgency**: dwell_days, dwell_percentile (vs cohort), urgency_score (urgent/normal/late) are first-class engine outputs. Cohort baselines refreshed weekly.
6. **P6 — Coexistence + burn-in**: 30-day burn-in before any rank-1 swap. State engine must beat V5 on alpha + DD compliance + IC of recommendations on the live leaderboard, not in backtest alone.

## Architecture

```
                  RAW DATA (Rung 2)
                  ─────────────────
   per-stock OHLCV daily              index/sector OHLCV daily
            │                                  │
            ▼                                  ▼
   ┌─────────────────────────────────────────────────────┐
   │  Feature layer (pure derivatives of OHLCV)          │
   │  SMA-50/150/200 | EMA-21 | ATR-14 | OBV | ADX-14    │
   │  RS rank (12m return, X-sectional)                  │
   │  Up/Down volume ratio (50d)  |  Distribution days   │
   │  % off 52w high  |  % off 52w low  |  Base depth    │
   │  Breadth: % universe above 50/200 MA                │
   └─────────────────────────────────────────────────────┘
            │
            ▼
   ┌─────────────────────────────────────────────────────┐
   │  STATE CLASSIFIER (atlas/intelligence/states/)      │
   │  rule skeleton + learned θ from IC validation       │
   │                                                      │
   │  Per (stock, day) →  state ∈ 7 states               │
   │  Per (stock, day) →  within_state_rank ∈ [0,1]      │
   │  Per (stock, day) →  dwell_days, dwell_percentile,  │
   │                       urgency_score                  │
   │                                                      │
   │  Output: atlas_stock_state_daily (NEW)              │
   └─────────────────────────────────────────────────────┘
            │
   ┌────────┴────────┐
   ▼                 ▼
STOCK            AGGREGATION                      ACTION ENGINE
VIEW             ─────────────                    ─────────────
│                Sector: direct + breadth          State transitions →
│                Country: direct + breadth          BUY / HOLD / TRIM / EXIT
│                ETF: direct + (breadth fresh)
│                MF:  direct + (breadth fresh)     Position size =
│                                                    base_size × within_state_rank
▼
RECOMMENDATIONS:
  atlas_strategy_recommendations_daily
  (existing table — same schema, new strategy_id 'STATE-ENGINE-V1-WEINSTEIN')
```

## State definitions (the classifier)

Every `θ` is a learned threshold persisted to `atlas_state_thresholds`. Initial values are hand-set defensible defaults; Phase 2 sweeps and tunes via IC validation.

```
Uninvestable ≡  liquidity_score < θ_liq
              OR data_gaps_252d > θ_gap
              OR close < θ_min_price
   [filter; not tradeable — excludes from all other classifications]

Stage 1 (Base) ≡  NOT in Stage 2/2A/2B/2C/3/4
              AND |close − SMA_150| / SMA_150 < θ_base_tightness
              AND ATR_14 / close < θ_low_vol
              AND 252d_low_age >= θ_min_recovery_days

Stage 2A (Fresh Breakout) ≡  prior_state was 1 OR 4
              AND close > SMA_50 > SMA_150 > SMA_200
              AND SMA_200 slope > 0 over θ_slope_days
              AND close >= θ_base_breakout × max(close_60d)
              AND volume_today > θ_vol_mult × volume_50d_avg
              AND rs_rank_12m >= θ_rs
              AND days_in_stage_2 <= θ_fresh_days

Stage 2B (Confirmed) ≡  in Stage 2 (price stack still holds)
              AND days_in_stage_2 between θ_fresh_days and θ_confirmed_days
              AND no distribution_day_signal_5d
              AND close > SMA_50

Stage 2C (Mature) ≡  in Stage 2 (price stack still holds)
              AND days_in_stage_2 > θ_confirmed_days
              AND (close / SMA_50 > θ_extension OR ATR_14_expansion > θ_atr_expansion)

Stage 3 (Top) ≡  prior_state was 2A/2B/2C
              AND (close < SMA_50 OR SMA_50 slope < 0)
              AND distribution_days_25d >= θ_distribution

Stage 4 (Decline) ≡  close < SMA_150 < SMA_200
              AND SMA_150 slope < 0
              AND close < θ_decline_floor × SMA_200
```

### Within-state rank

```
within_state_rank = w1·freshness_norm + w2·rs_rank_norm + w3·volume_score_norm
  freshness_norm   = 1 - (dwell_days / cohort_p75_dwell_days)   ; 1=fresh, 0=overdue
  rs_rank_norm     = cross-sectional rank of rs_rank_12m         ; 1=strongest
  volume_score_norm= cross-sectional rank of (up_vol/down_vol)   ; 1=most-confirmed
```

Weights w1..w3 are also IC-validated against forward returns within each state.

### IC validation loop

For each θ in each state:
1. Generate state-membership boolean series under candidate θ values (grid of ~10 values per threshold).
2. Compute IC of state-membership vs forward returns at the state's natural horizon:
   - Stage 2A → 21d and 63d forward
   - Stage 2B → 63d forward
   - Stage 2C → 21d forward (looking for reversion)
   - Stage 3 → 21d forward (looking for further decline)
   - Stage 1, Stage 4 → not optimized (Stage 1 is "watch", Stage 4 is "avoid"; IC is informational only)
3. Pick θ that maximizes Q5–Q1 spread AND has IR_of_IC > 0.4.
4. Persist optimal θ + IC report to `atlas_state_thresholds`.
5. If no θ in the grid passes the gate, flag the state definition as "broken" — needs design revisit, not just retuning.

## Dwell-time + urgency

```
PER (stock, day):
  dwell_days       = current_date - state_since_date
  dwell_percentile = percentile rank of dwell_days within cohort's historical distribution
  urgency_score    = derived (urgent | normal | late) per state-specific table

PER (cohort, state):  atlas_state_dwell_statistics
  cohort       ∈ {'large_cap', 'mid_cap', 'small_cap'} ∪ per-sector keys
  state        ∈ 7 state values
  mean, median, p25, p75, p95, p99 dwell_days
  n_observations
  as_of_date   (refresh: weekly via cron)
```

Urgency mapping per state:

| State | Short dwell vs cohort | Long dwell vs cohort |
|---|---|---|
| Stage 2A Fresh | URGENT (act now, alpha window open) | LATE (window almost expired, consider passing) |
| Stage 2B Confirmed | NORMAL (early in confirmed trend) | LATE (consider 2C transition imminent) |
| Stage 2C Mature | LATE (reversion risk rising) | URGENT to trim (beyond cohort norms) |
| Stage 3 Top | NORMAL (confirm before exit) | URGENT to exit (distribution prolonged) |
| Stage 1, Stage 4 | not actionable | not actionable |

## Aggregation (sector / ETF / MF / country)

Two state values per non-stock instrument:

**Direct** — apply same classifier to the wrapper's own OHLCV.

**Breadth** — count constituent states.

```
For sector NIFTY-IT, on 2026-05-18:
  direct_state    = (run classifier on NIFTY-IT index OHLCV) → e.g., "Stage 2B Confirmed"
  breadth_pct_stage_1 = 23%
  breadth_pct_stage_2 = 65%   (across 2A+2B+2C)
  breadth_pct_stage_3 = 12%
  breadth_pct_stage_4 = 0%
  breadth_summary = "healthy" | "fragile" | "deteriorating" (derived rule)
```

| Level | Direct primary | Breadth primary | Notes |
|---|---|---|---|
| Sector | yes | **yes** | symmetric; breadth tells WHY |
| Country | yes | **yes** | breadth is the macro tell |
| ETF | **yes** | when holdings <30d fresh | holdings often stale |
| MF | **yes** | informational only | NAV-direct is the practical truth |

## Action engine

```
state transition → action mapping:
  Stage 1 → 2A           BUY  (open new position; fresh-breakout entry)
  Stage 2A → 2B          HOLD (confirmed; tighten trailing stop)
  Stage 2B → 2C          HOLD (mature; tighten stop further)
  Stage 2x → 3           TRIM (50% off; raise stop)
  Stage 3 → 4            EXIT (full close)
  Stage 4 → 1            WATCH (base forming; not actionable)
  any → Uninvestable     FORCE EXIT (data/liquidity violation)

Position size at entry  = base_position_pct × within_state_rank
```

Risk gates (apply BEFORE state-transition action fires):
- Portfolio drawdown > θ_dd_halt → block all new BUYs
- Market regime = RISK-OFF → block all new BUYs (regime classified by same engine on broad-market index)
- Trend filter: NIFTY-500 50d-MA < 200d-MA → reduce gross exposure to 50% (carries through from V5-RP-TREND)
- Sector concentration cap: max θ_sector_cap stocks per sector in portfolio

All risk-gate thresholds live in `atlas_state_thresholds` alongside classifier thresholds. IC-validated periodically.

## Data model

```sql
-- New table: per-stock daily state classification
CREATE TABLE atlas.atlas_stock_state_daily (
    instrument_id     UUID NOT NULL,
    date              DATE NOT NULL,
    state             VARCHAR(24) NOT NULL,
    prior_state       VARCHAR(24),
    state_since_date  DATE NOT NULL,
    dwell_days        INTEGER NOT NULL,
    dwell_percentile  NUMERIC(5,4),
    urgency_score     VARCHAR(12) NOT NULL,
    within_state_rank NUMERIC(5,4),
    -- explanation columns
    rs_rank_12m       NUMERIC(5,4),
    close_vs_sma_50   NUMERIC(8,4),
    close_vs_sma_150  NUMERIC(8,4),
    close_vs_sma_200  NUMERIC(8,4),
    sma_200_slope     NUMERIC(8,6),
    volume_ratio_50d  NUMERIC(6,3),
    distribution_days INTEGER,
    classifier_version VARCHAR(16) NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (instrument_id, date),
    CHECK (state IN ('uninvestable','stage_1','stage_2a','stage_2b','stage_2c','stage_3','stage_4')),
    CHECK (urgency_score IN ('urgent','normal','late','n/a'))
);
CREATE INDEX ix_atlas_stock_state_daily_date ON atlas.atlas_stock_state_daily (date);
CREATE INDEX ix_atlas_stock_state_daily_state ON atlas.atlas_stock_state_daily (date, state);

-- New table: per-cohort dwell baselines, refreshed weekly
CREATE TABLE atlas.atlas_state_dwell_statistics (
    cohort_key   VARCHAR(64) NOT NULL,
    state        VARCHAR(24) NOT NULL,
    mean_dwell_days   NUMERIC(8,2),
    median_dwell_days INTEGER,
    p25_dwell_days    INTEGER,
    p75_dwell_days    INTEGER,
    p95_dwell_days    INTEGER,
    n_observations    INTEGER,
    as_of_date        DATE NOT NULL,
    refreshed_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cohort_key, state, as_of_date)
);

-- New table: learned thresholds with history
CREATE TABLE atlas.atlas_state_thresholds (
    threshold_name  VARCHAR(64) NOT NULL,
    state_or_gate   VARCHAR(24) NOT NULL,
    threshold_value NUMERIC(12,6) NOT NULL,
    ic_at_threshold NUMERIC(8,4),
    ic_ir_at_threshold NUMERIC(8,4),
    q5_q1_spread    NUMERIC(8,4),
    as_of_date      DATE NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT FALSE,
    tuned_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (threshold_name, state_or_gate, as_of_date)
);

-- New table: state transition audit log
CREATE TABLE atlas.atlas_state_action_log (
    instrument_id  UUID NOT NULL,
    date           DATE NOT NULL,
    transition     VARCHAR(48) NOT NULL,  -- e.g., 'stage_1->stage_2a'
    action         VARCHAR(16) NOT NULL,  -- BUY/HOLD/TRIM/EXIT/WATCH/FORCE_EXIT
    suppressed_by  VARCHAR(32),           -- risk gate that blocked, NULL if action fired
    position_size  NUMERIC(8,4),
    within_state_rank NUMERIC(5,4),
    urgency_score  VARCHAR(12),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (instrument_id, date, transition)
);

-- Extend atlas_sector_states_daily with breadth columns (or new atlas_sector_state_daily table)
-- Extend atlas_etf_states_daily, add atlas_mf_state_daily, atlas_country_state_daily
```

## Sequencing — 6 phases over ~6 weeks (human cadence) / ~12-18 days (CC cadence)

### Phase 0 — Pre-build (1 week)
- State catalog audit: list every state-badge currently in frontend, map deprecation path
- Migrations: 4 new tables (atlas_stock_state_daily, atlas_state_dwell_statistics, atlas_state_thresholds, atlas_state_action_log)
- Coexistence plan locked: keep atlas_stock_states_daily live; no deprecation in Phase 0

### Phase 1 — Classifier MVP (2 weeks)
- `atlas/intelligence/states/classifier.py` (~400 LOC) — 7 state definitions with hand-set defensible θ
- `atlas/intelligence/states/dwell.py` (~150 LOC) — dwell computation + cohort baselines
- Backfill `atlas_stock_state_daily` for 2014-2026
- Smoke test: known Stage 2 stocks at known dates land in Stage 2

### Phase 2 — IC validation closes the loop (1 week)
- Sweep grid of θ per state; pick IC-maximizing values
- Persist to `atlas_state_thresholds`; re-backfill `atlas_stock_state_daily`
- IC report per state with mean_ic, Q5-Q1, IR_of_IC

### Phase 2.5 — Component IC validation (1 week)

The composite state (Stage 2A et al.) is a conjunction of component checks. A
composite that passes IC validation does NOT prove each component earns its
place — a strong conjunct can mask a useless one.

For fund managers to trust a recommendation page that says
"BUY because: RS Leader + Volume Accumulation + Stage 2A," every claim on that
page must be independently statistically valid. This phase IC-validates each
component indicator at its own action horizon, independently of how the
composite state uses it.

Components + their horizons:

| Component | Metric | Tier-defining threshold | Implied horizon |
|---|---|---|---|
| Relative strength | rs_rank_12m | Leader ≥0.90 / Strong 0.70-0.90 / Average 0.30-0.70 / Weak 0.10-0.30 / Laggard <0.10 | 63d |
| Momentum | normalized slope(close, 21) | Accelerating / Stable / Decelerating | 21d |
| Volatility | atr_14 / close (NATR) | Low / Normal / Elevated / High | 63d (warns, sign-inverted IC) |
| Volume | up_down_volume_ratio_50d | Accumulation / Neutral / Distribution | 21d |

For each (component, tier) pair, the validator computes IC of "in this tier"
vs forward returns at the implied horizon. Classification per tier:

- `validated` IR > 0.4 AND sign matches implied direction
- `validated_inverse` IR > 0.4 AND sign opposite to implied direction
- `weak` IR in (0.2, 0.4)
- `decorative` IR ≤ 0.2

New table:

```sql
CREATE TABLE atlas.atlas_component_validation (
    component_name VARCHAR(48) NOT NULL,
    badge          VARCHAR(32) NOT NULL,
    threshold_range VARCHAR(64) NOT NULL,
    implied_action VARCHAR(48) NOT NULL,
    horizon_days   INTEGER NOT NULL,
    as_of_date     DATE NOT NULL,
    mean_ic        NUMERIC(10,6),
    ic_std         NUMERIC(10,6),
    ic_t_stat      NUMERIC(10,4),
    ic_ir          NUMERIC(10,4),
    q5_q1_spread   NUMERIC(10,6),
    n_observations INTEGER,
    status         VARCHAR(24) NOT NULL,
    validated_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (component_name, badge, horizon_days, as_of_date),
    CHECK (status IN ('validated', 'validated_inverse', 'weak', 'decorative'))
);
```

Module: `atlas/intelligence/states/component_validator.py` (~250 LOC). Reuses
the same `atlas/intelligence/validation/ic_engine.py` and
`forward_returns.py` as the state validator.

CLI: `atlas-lab states validate-components --start YYYY-MM-DD --end YYYY-MM-DD`.

Frontend impact: every component sub-badge on the recommendation page reads
its rendering treatment from `atlas_component_validation.status` for that
specific tier. Tiers with status='decorative' render as plain text without the
implied action. Tiers with status='validated_inverse' render with a clear
"counter-intuitive" indicator (e.g., the badge says "Accumulation" but the
hover shows "historically anti-predictive: stocks in this tier have
underperformed at 21d horizon"). This is the only way to avoid the
`history_gate_pass`-class trap surfaced 2026-05-18 morning.

### Phase 3 — Aggregation (1 week)
- Sector + country breadth computed from constituent states
- ETF + MF direct classification via wrapper OHLCV/NAV
- ETF breadth where holdings <30d fresh
- New per-level tables for sector / ETF / MF / country states

### Phase 4 — Action engine + recommendations (1 week)
- `atlas/intelligence/states/actions.py` (~200 LOC) — transition → action mapping
- Risk gate composition
- New strategy in `atlas_strategy_leaderboard`: `STATE-ENGINE-V1-WEINSTEIN` (profile=aggressive)
- Recommendations land in `atlas_strategy_recommendations_daily`

### Phase 5 — Frontend rewiring (1-2 weeks)
- Stock detail: state + dwell + urgency
- Sector / country: direct | breadth side-by-side
- ETF / MF: direct primary + holdings breadth (where fresh)
- Admin: `/admin/state-thresholds` with current θ, IC, last-tuned

### Phase 6 — Burn-in + V5 deprecation decision (30 days)
- STATE-ENGINE-V1 runs alongside V5-RP-TREND
- Goal-post automation tracks rank=1 strategy regardless of engine
- Promotion criteria: state engine wins on alpha + DD compliance + recommendation hit rate
- If state engine wins → swap; if V5 wins → state engine stays as informational view; if both have value → both stay live as separate profiles

## What's NOT in scope

- **Threshold optimizer service** (was Chunk 13). Phase 2's IC validation IS the threshold optimizer. No separate service.
- **MF holdings ingestion improvements**. We accept stale holdings; direct-NAV view is primary for MFs.
- **Intraday refinement** (Rung 3). Daily classifier is the V1; intraday is Phase 2.
- **Multi-region**: India only in V1. Rerun classifier on US / Global universes is a Phase 2 extension after V1 burn-in succeeds.
- **New states beyond the 7**: locked. Adding states post-hoc has higher overfit risk than tuning thresholds within the 7.

## Reconciliation with the Atlas Intelligence Engine mandate

The previous mandate (see `~/.gstack/projects/atlas-os/nimishshah-feat-atlas-strategy-lab-design-intelligence-engine-20260518-103703.md`) built the auto-discovery strategy engine — `atlas/trading/lab.py`, `atlas-lab` CLI, `goal_post.py`, migration 071 (profile column), ETF adapter, initial `state_validator.py`. Chunks 0–3, 6, 9, 12 are live on EC2. Chunks 4, 7, 10, 11, 13 are deferred.

This state-engine spec does NOT replace that work. It redesigns the *primitives* that engine consumes — the states themselves. The two mandates compose:

- Previous: orchestration that produces *best strategies* combinatorially across asset classes.
- This: redesign the *state primitives* so the engine has trustworthy inputs.

Mapping of previous deferred chunks to this spec:

| Previous chunk | Status | Resolution |
|---|---|---|
| Chunk 7 MF adapter | Deferred | Stays deferred. Independent of state engine. Picked up as parallel lane during state-engine Phase 5. |
| Chunks 10+11 frontend | Deferred | Stays deferred. Picked up as parallel lane during state-engine Phase 5. Frontend rewiring will surface BOTH V5-RP-TREND (continuous) and STATE-ENGINE-V1 (categorical) leaderboard entries. |
| Chunk 13 threshold optimizer | **Subsumed** | This spec's Phase 2 IS the threshold optimizer. Sweeps every θ across reasonable values, picks the IC-maximizing one, persists to `atlas_state_thresholds`. No separate build. |
| "Flip gate logic on validated_inverse" | **Subsumed** | The old `history_gate_pass` / `liquidity_gate_pass` go away. New gates are defined in this spec's classifier (Uninvestable state's `liquidity_score < θ_liq` plus per-state rules). No flip; replacement. |

Cross-mandate sequencing:

```
Week 1   State engine Phase 0 (migrations) + cohort definitions
Week 2-3 State engine Phase 1 (classifier MVP + dwell)
Week 4   State engine Phase 2 (IC tuning = previous Chunk 13)
Week 5   State engine Phase 3 (aggregation) || previous Chunk 7 (MF adapter, parallel)
Week 6   State engine Phase 4 (action engine + recommendations) ||
         previous Chunks 10+11 (frontend, parallel)
Week 7-10 Burn-in (30 days)
         IC monitoring of state engine output vs V5 closes the drift loop.
```

No prior work is abandoned. The state-engine build absorbs the threshold-optimization piece and supersedes the failed gate logic. MF and frontend deferred chunks run as parallel lanes when their dependencies are ready.

## What already exists (reuse map)

| Need | Reuse |
|---|---|
| IC computation | `atlas/intelligence/validation/ic_engine.py` |
| Forward returns | `atlas/intelligence/validation/forward_returns.py` |
| Threshold persistence pattern | model on `atlas_strategy_proposals` (composite proposals UI) |
| Backtest engine | `atlas/trading/lab.py` (run state-engine through the same loop) |
| CLI infrastructure | `atlas/trading/cli.py` (add `atlas-lab states` subcommand) |
| Goal-post automation | `atlas/trading/goal_post.py` (no changes — engine-agnostic) |
| Strategy leaderboard | `atlas_strategy_leaderboard` (schema unchanged; state engine inserts a new row) |
| Recommendations table | `atlas_strategy_recommendations_daily` (schema unchanged) |

## Open questions to resolve before Phase 1

1. **Cohort definitions**: how do we segment stocks into large-cap / mid-cap / small-cap? By market cap? By Nifty-100/Nifty-Next-50/etc. membership? **Pre-Phase 1 decision required.**
2. **Initial θ values for hand-set defaults**: need a one-day session to pick defensible defaults using existing Atlas thresholds + Minervini/Weinstein literature. Not blocking but should happen in Phase 0 to make Phase 1 a clean start.
3. **State naming for the UI**: do we render "Stage 2A Fresh Breakout" verbatim or use friendlier labels like "Just broke out — high urgency"? Phase 5 design decision; not blocking the engine build.

## Success criteria

Engine v1 ships when:

1. `atlas_stock_state_daily` is backfilled for 2014-2026 and being refreshed nightly.
2. All 7 states (where IC is expected) have IR_of_IC > 0.4 against forward returns at their natural horizon.
3. Dwell baselines populated for at least 3 cohorts (large/mid/small cap).
4. Sector breadth + country breadth views render on the frontend.
5. `atlas_strategy_recommendations_daily` has the daily output of STATE-ENGINE-V1.
6. After 30-day burn-in, the goal-post hook reports `met:true` for whichever strategy is at rank 1 — either V5-RP-TREND or STATE-ENGINE-V1.

## Distribution plan

Backend deploys via existing PM2 + nightly cron on EC2 .214. Frontend deploys via `pm2 restart atlas-frontend`. No new infrastructure. New nightly cron job: `atlas-lab classify-states` after the existing data refresh, before signal/strategy refresh.
