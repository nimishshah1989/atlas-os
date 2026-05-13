# SP09 — CTS Timing Engine

**Date:** 2026-05-12  
**Status:** Design approved, pending implementation  
**Depends on:** SP04 Stage 4a (calibration loop pattern), SP07 Hermes (brief agent pattern)

---

## What problem this solves

Atlas answers WHAT (RS, regime, sector state, conviction). The Champion Trader System (CTS) by Jhaveri Securities answers WHEN and HOW MUCH (timing entry, sizing the risk). Today these are two separate systems. SP09 makes Atlas the authoritative home for CTS signals — computed nightly, back-tested, self-calibrating.

The conjunction is the edge: Atlas Overweight + CTS Stage 2 + PPC fired today = high-probability setup with measured IC. Neither alone is as strong.

---

## CTS Signal Definitions (translated from Pine Script)

### TRP (True Range Percentage)
```
TRP = (High - Low) / Close × 100
avg_trp = SMA(TRP, 20)
trp_ratio = TRP / avg_trp
tradeable_threshold = 2.0%  ← from atlas_thresholds['cts_trp_tradeable_min']
```

### Stage (Weinstein)
- Compute 150-day SMA of adjusted close.
- Stage 2: price > SMA_150 AND SMA_150 slope > 0 over last 20 days
- Stage 1: price ≤ SMA_150 AND SMA_150 flat (slope near 0)
- Stage 1B: Stage 1 AND within 5% of SMA_150 breakout (price recently crossed up)
- Stage 3: price > SMA_150 AND SMA_150 slope turning negative
- Stage 4: price < SMA_150

### PPC (Positive Pivotal Candle) — ALL four required
1. `trp_ratio >= cts_ppc_range_multiplier`  (default 1.5)
2. `(close - low) / (high - low) >= cts_ppc_close_pct`  (default 0.60 → top 40%)
3. `volume / avg_volume_20 >= cts_ppc_volume_multiplier`  (default 1.5)
4. Green candle: `close > open`

**PPC Strength Score (composite, 0–1):**
```
ppc_strength = w_trp * min(trp_ratio / 3.0, 1.0)
             + w_vol * min(volume_ratio / 4.0, 1.0)
             + w_rs  * rs_pctile_cross_sector          ← from Atlas
             + w_stage * (stage == 2)
```
Initial weights: 0.35 / 0.35 / 0.20 / 0.10  
These weights go into `atlas_signal_weights` table (`tier='cts_ppc'`) — calibrated by the same IC loop as SP04.

### NPC (Negative Pivotal Candle) — mirror of PPC
1. `trp_ratio >= cts_npc_range_multiplier`
2. `(high - close) / (high - low) >= cts_npc_close_pct`  (close in bottom 40%)
3. `volume / avg_volume_20 >= cts_npc_volume_multiplier`
4. Red candle: `close < open`

### Contraction
1. ATR(14) slope negative over last N bars (linear regression, N = `cts_contraction_bars`)
2. Progressive range narrowing: `narrowing_count / (N-1) >= 0.6`
3. Price within `cts_contraction_resistance_pct` of highest-high (lookback 50 bars)

**Trigger bar** = current bar when all three conditions met.  
**Trigger level** = high of trigger bar.

---

## Calibratable Parameters (all in `atlas_thresholds` with `cts_` prefix)

| Key | Default | Bounds | What it controls |
|-----|---------|--------|------------------|
| `cts_trp_tradeable_min` | 2.0 | 1.0–4.0 | Minimum TRP% to consider a stock tradeable |
| `cts_ppc_range_multiplier` | 1.50 | 1.20–2.50 | TRP ratio threshold for PPC |
| `cts_ppc_close_pct` | 0.60 | 0.50–0.80 | Close-in-range % threshold for PPC |
| `cts_ppc_volume_multiplier` | 1.50 | 1.20–3.00 | Volume ratio threshold for PPC |
| `cts_npc_range_multiplier` | 1.50 | 1.20–2.50 | TRP ratio threshold for NPC |
| `cts_npc_close_pct` | 0.40 | 0.20–0.50 | Close-in-range % threshold for NPC (ceiling) |
| `cts_npc_volume_multiplier` | 1.50 | 1.20–3.00 | Volume ratio threshold for NPC |
| `cts_contraction_bars` | 5 | 3–10 | Narrowing lookback window |
| `cts_contraction_resistance_pct` | 3.0 | 1.0–8.0 | Max % from highest-high to qualify |
| `cts_stage2_sma_period` | 150 | 120–200 | SMA period for Weinstein stage |
| `cts_stage2_slope_min_days` | 20 | 10–40 | Lookback to compute SMA slope direction |

---

## Database Schema (migration 043)

```sql
-- Daily CTS signal snapshot per instrument
CREATE TABLE atlas.atlas_cts_signals_daily (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date        DATE NOT NULL,
    instrument_id UUID NOT NULL REFERENCES atlas.atlas_instruments(id),

    -- Stage
    stage           SMALLINT,         -- 1, 2, 3, 4
    is_stage1b      BOOLEAN,
    sma_150         NUMERIC(12, 4),
    sma_150_slope   NUMERIC(8, 6),    -- 20-day slope, positive = rising

    -- TRP
    trp             NUMERIC(6, 4),
    avg_trp         NUMERIC(6, 4),
    trp_ratio       NUMERIC(6, 4),
    is_tradeable    BOOLEAN,          -- trp >= cts_trp_tradeable_min

    -- PPC
    is_ppc          BOOLEAN,
    ppc_strength    NUMERIC(6, 4),    -- 0–1 composite

    -- NPC
    is_npc          BOOLEAN,
    npc_strength    NUMERIC(6, 4),

    -- Contraction
    is_contraction  BOOLEAN,
    is_trigger_bar  BOOLEAN,
    trigger_level   NUMERIC(12, 4),
    atr_14          NUMERIC(8, 4),
    atr_slope       NUMERIC(10, 6),   -- linear-reg slope (negative = compressing)

    -- Forward returns (backfilled by update_cts_fwd_returns.py)
    fwd_ret_5d      NUMERIC(8, 6),
    fwd_ret_10d     NUMERIC(8, 6),
    fwd_ret_20d     NUMERIC(8, 6),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT atlas_cts_signals_daily_uq UNIQUE (date, instrument_id)
);
CREATE INDEX cts_sig_date_idx   ON atlas.atlas_cts_signals_daily (date);
CREATE INDEX cts_sig_inst_idx   ON atlas.atlas_cts_signals_daily (instrument_id);
CREATE INDEX cts_sig_ppc_idx    ON atlas.atlas_cts_signals_daily (date) WHERE is_ppc;
CREATE INDEX cts_sig_stage2_idx ON atlas.atlas_cts_signals_daily (date) WHERE stage = 2;

-- Sector-level pivot balance (PPC vs NPC count)
CREATE TABLE atlas.atlas_cts_sector_pivot_daily (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    sector          VARCHAR(100) NOT NULL,
    ppc_count       INT NOT NULL DEFAULT 0,
    npc_count       INT NOT NULL DEFAULT 0,
    total_tradeable INT NOT NULL DEFAULT 0,
    pivot_balance   NUMERIC(6, 4),    -- (ppc - npc) / total_tradeable
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT atlas_cts_sector_pivot_uq UNIQUE (date, sector)
);

-- Rolling Timing IC measurements
CREATE TABLE atlas.atlas_cts_timing_ic (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    as_of_date          DATE NOT NULL,
    signal_name         VARCHAR(50) NOT NULL,   -- 'ppc_strength', 'npc_strength', 'atr_slope'
    lookback_window     INT NOT NULL,
    forward_horizon     INT NOT NULL,
    n_observations      INT NOT NULL,
    ic                  NUMERIC(8, 6),
    t_stat              NUMERIC(8, 4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT atlas_cts_timing_ic_uq UNIQUE (as_of_date, signal_name, lookback_window, forward_horizon)
);

-- Hit rate measurements (precision of binary signal)
CREATE TABLE atlas.atlas_cts_hit_rates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    as_of_date          DATE NOT NULL,
    signal_type         VARCHAR(20) NOT NULL,   -- 'ppc', 'npc', 'contraction'
    stage_filter        SMALLINT,               -- NULL = all stages, 2 = stage 2 only
    forward_horizon     INT NOT NULL,           -- 5, 10, 20 days
    return_threshold    NUMERIC(6, 4) NOT NULL, -- 0.05 = 5%
    hit_count           INT NOT NULL,
    total_signals       INT NOT NULL,
    hit_rate            NUMERIC(6, 4),          -- hit_count / total_signals
    base_rate           NUMERIC(6, 4),          -- same metric on non-signal stocks
    lift_ratio          NUMERIC(6, 4),          -- hit_rate / base_rate
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT atlas_cts_hit_rates_uq UNIQUE (as_of_date, signal_type, stage_filter, forward_horizon, return_threshold)
);

-- Parameter calibration proposals (same pattern as atlas_weight_proposals)
CREATE TABLE atlas.atlas_cts_param_proposals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    as_of_date      DATE NOT NULL,
    param_key       VARCHAR(100) NOT NULL,      -- matches atlas_thresholds key
    current_value   NUMERIC(12, 6) NOT NULL,
    proposed_value  NUMERIC(12, 6) NOT NULL,
    smoothed_value  NUMERIC(12, 6) NOT NULL,    -- Bayesian smoothed
    direction       VARCHAR(10) NOT NULL,        -- 'increase' | 'decrease'
    expected_lift_delta NUMERIC(8, 6),          -- expected delta in hit-rate lift
    rationale       TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|applied
    applied_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Module Structure

```
atlas/compute/cts/
├── __init__.py
├── primitives.py       # TRP, ATR, SMA slope, volume ratio — vectorised pandas
├── stage.py            # Weinstein stage classifier (150-SMA, slope)
├── signals.py          # PPC, NPC, Contraction detection + strength scoring
└── sector_pivot.py     # SPB = (PPC − NPC) / total_tradeable per sector

atlas/intelligence/cts/
├── __init__.py
├── timing_ic.py        # Spearman IC: signal_strength vs fwd_ret_20d
│                       #   Reuses validation.ic_engine directly
├── hit_rate.py         # Hit rate + lift ratio: is_ppc AND stage=2 → fwd>5%
├── auto_calibration/
│   ├── __init__.py
│   ├── ic_monitor.py   # Rolling timing IC (90-day lookback, 20-day horizon)
│   ├── param_candidates.py  # Delta-IC driven threshold proposals
│   ├── smoothing.py    # 15% Bayesian smoothing (reuse SP04 pattern exactly)
│   └── persistence.py  # atlas_cts_param_proposals CRUD
└── strength_calibration/
    ├── __init__.py
    └── weight_ic.py    # IC-based weight proposals for ppc_strength composite
                        #   Writes to atlas_signal_weights (tier='cts_ppc')
                        #   Reuses SP04 candidate_generator exactly
```

---

## Two Feedback Loops (not one)

This is the key insight from the Premise Challenge:

**Loop A — Strength Scoring (continuous signals, IC objective)**
- `ppc_strength` composite weights: `[w_trp, w_vol, w_rs, w_stage]`
- These are continuous. Calibrate via Spearman IC exactly like SP04.
- Stored in `atlas_signal_weights` table, tier = `'cts_ppc'`.
- Nightly: `recompute_signal_ic.py` already handles this if we add `cts_ppc` as a tier.

**Loop B — Detection Thresholds (binary classifiers, lift-ratio objective)**
- The `*_multiplier` and `*_pct` thresholds in `atlas_thresholds`.
- These control whether a signal fires at all — a precision/recall tradeoff.
- Calibrate via Hit Rate Lift (signal hit rate / base hit rate).
- Objective: maximize `lift_ratio` at 20-day, 5% threshold.
- Proposals generated by `param_candidates.py`, smoothed 15%, admin approved.

**Why separate?** Using IC on binary thresholds conflates two different questions. IC measures whether signal *strength* predicts *magnitude* of returns. Lift ratio measures whether signal *presence* predicts *direction*. Both matter; neither alone is sufficient.

---

## Calibration Loop B — Threshold Proposal Algorithm

```python
# For each threshold parameter (e.g., cts_ppc_volume_multiplier):
# 1. Compute hit rate at current threshold value (last 90 days)
# 2. Compute hit rate at current_value + 0.1 increment (simulate via filter)
# 3. Compute hit rate at current_value - 0.1 increment
# 4. If best_alternative_lift - current_lift > MATERIAL_LIFT_DELTA:
#    generate proposal
# 5. Apply Bayesian smoothing: smoothed = 0.85 * current + 0.15 * proposed
# 6. Insert into atlas_cts_param_proposals (status='pending')
# 7. Admin approves → apply to atlas_thresholds, log to atlas_threshold_history

MATERIAL_LIFT_DELTA = Decimal("0.05")   # 5% relative improvement in lift ratio
MIN_OBSERVATIONS_FOR_PROPOSAL = 30      # need 30+ signals to trust the measurement
```

This mirrors `candidate_generator.py`'s `MATERIAL_CHANGE_THRESHOLD` pattern exactly.

---

## Nightly Pipeline Additions

Add to `run_atlas_intelligence_nightly.sh` after `compute_conviction`:

```bash
# CTS Timing Engine (SP09) — runs AFTER M2-M5 pipeline writes daily prices
run_step "compute_cts_signals"          python scripts/compute_cts_signals.py --persist
run_step "update_cts_fwd_returns"       python scripts/update_cts_fwd_returns.py --persist
run_step "compute_cts_sector_pivot"     python scripts/compute_cts_sector_pivot.py --persist
run_step "compute_timing_ic"            python scripts/compute_timing_ic.py --persist
run_step "compute_cts_hit_rates"        python scripts/compute_cts_hit_rates.py --persist
run_step "generate_cts_param_candidates" python scripts/generate_cts_param_candidates.py --persist
```

`compute_cts_signals.py` requires the M2-M5 OHLCV pipeline to have completed (it reads from `atlas_stock_price_daily`). The nightly M2 cron runs at IST 03:30; the intelligence cron runs at IST 04:00 — ordering is already correct.

---

## Scripts Map

| Script | What it does |
|--------|-------------|
| `compute_cts_signals.py` | Vectorised PPC/NPC/Contraction/Stage for all ~750 stocks; writes `atlas_cts_signals_daily` |
| `update_cts_fwd_returns.py` | Back-fills `fwd_ret_5d/10d/20d` on past signal rows once the price data exists |
| `compute_cts_sector_pivot.py` | Aggregates PPC/NPC count by sector → `atlas_cts_sector_pivot_daily` |
| `compute_timing_ic.py` | Spearman IC for `ppc_strength`, `npc_strength`, `atr_slope` vs forward returns |
| `compute_cts_hit_rates.py` | Lift ratio for binary PPC/NPC/Contraction at 5/10/20-day horizons |
| `generate_cts_param_candidates.py` | Proposes threshold adjustments, Bayesian-smoothed, writes proposals |
| `backfill_cts_signals.py` (one-time) | Vectorised compute over 2Y of history to bootstrap IC measurements |

---

## On-demand Stock Decision Brief (Hermes Agent)

**Endpoint:** `POST /api/v1/stocks/{symbol}/cts_brief`

**Context injected into the agent:**
```json
{
  "symbol": "RELIANCE",
  "atlas": {
    "conviction_score": 0.74,
    "conviction_tier": "T1",
    "sector_state": "Neutral",
    "rs_pctile_cross_sector": 0.68,
    "regime": "Cautious"
  },
  "cts": {
    "stage": 2,
    "sma_150_slope": 0.0023,
    "trp": 1.82,
    "avg_trp": 1.45,
    "trp_ratio": 1.25,
    "is_ppc": false,
    "ppc_strength": null,
    "is_contraction": true,
    "trigger_level": 1342.5,
    "last_ppc_date": "2026-04-28",
    "last_ppc_strength": 0.71
  },
  "history": {
    "ppc_count_60d": 2,
    "npc_count_60d": 1,
    "pivot_balance_sector": 0.12
  }
}
```

**Agent prompt (system):** Reuse `atlas/intelligence/briefs/prompts.py` pattern. Single paragraph output. SEBI guard: no forward return predictions, no buy/sell instructions.

---

## Frontend Surfaces

### Stock Screener — new columns (low effort)
- `Stage` badge: `S1 / S1B / S2 / S3 / S4` — colour-coded (S2 = teal, S4 = red)
- `Signal` badge: `PPC / NPC / Contraction / —` with date
- `Trigger` price for Contraction setups

### Stocks Page — Deep Dive drawer addition
- CTS signal card: Stage, today's signal, trigger level if Contraction
- PPC/NPC 60-day sparkline (signal frequency over time)
- "Request Brief" button → calls `/cts_brief` → LLM paragraph

### Sectors Page — Sector Pivot Balance panel
- Add a `PPC / NPC Balance` column to SectorDecisionTable
- Positive (more PPCs) = green chip, negative (more NPCs) = red chip
- Tooltip: "X PPCs and Y NPCs today across Z tradeable stocks"

### Admin page — CTS Calibration (new tab alongside Composite Proposals)
- Hit Rate Lift table: signal × horizon × current lift × trend
- Param Proposals queue: same approve/reject UI as weight proposals
- Timing IC chart: rolling IC for `ppc_strength` over last 180 days

---

## Implementation Sequence

**Phase A — Compute foundation (no UI)**
1. Migration 043: create 5 tables above
2. `atlas/compute/cts/primitives.py` + `stage.py` + `signals.py`
3. `scripts/compute_cts_signals.py` (vectorised, ~750 stocks in < 60s)
4. `scripts/backfill_cts_signals.py` (2Y history to bootstrap IC)
5. Unit tests: `tests/unit/cts/` — verify PPC/NPC detection against known candles

**Phase B — Calibration data**
6. `scripts/update_cts_fwd_returns.py`
7. `scripts/compute_timing_ic.py` (reuse `validation.ic_engine` directly)
8. `scripts/compute_cts_hit_rates.py`
9. Wire into `run_atlas_intelligence_nightly.sh`
10. Let it run for 20+ trading days before generating proposals

**Phase C — Self-calibration loop**
11. `atlas/intelligence/cts/auto_calibration/` module
12. `scripts/generate_cts_param_candidates.py`
13. Admin frontend: CTS Calibration tab

**Phase D — Stock Screener + Frontend**
14. Add Stage + Signal columns to screener API + UI
15. Sector Pivot Balance on sectors page
16. CTS Deep Dive card on stock page

**Phase E — On-demand brief**
17. `/api/v1/stocks/{symbol}/cts_brief` endpoint
18. Hermes agent context builder + SEBI guard
19. "Request Brief" button in stock deep dive

---

## What "zero static weights" means operationally

Every calibratable parameter starts at the Jhaveri/CTS documented default and then moves based on measured performance:

1. `atlas_thresholds` stores current values (not hardcoded in Python)
2. Loop A (IC) adjusts `ppc_strength` composite weights nightly
3. Loop B (lift ratio) proposes detection threshold changes nightly
4. Bayesian smoothing (15%) ensures no single bad day causes a wild swing
5. Admin approval is the human gate before any change goes live
6. `atlas_threshold_history` auto-logs every change with timestamp and IC delta
7. Auto-revert: if applied threshold produces lift < 1.0 for 30 consecutive days, propose reverting to previous value

At steady state: a PPC that fires reliably in Indian market conditions will have a different volume multiplier than the Jhaveri default, tuned to the actual IC observed on NSE data. The Pine Script is the prior; Atlas data is the posterior.
