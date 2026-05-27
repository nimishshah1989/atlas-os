---
chunk: B.5
project: atlas-os
date: 2026-05-26
status: in-progress
---

# B.5 — Position Sizing Recommendation Function: Approach

## Step 1 Grep Results

Exactly ONE canonical `computeSizing` found at:
- `frontend/src/lib/position-sizing.ts` (22 lines of logic)
- Consumer: `frontend/src/app/stocks/[symbol]/page.tsx` lines 34, 112
- Tests: `frontend/src/lib/__tests__/position-sizing.test.ts` (8 cases)

No other implementations found. Decision: PORT this canonical logic.

## V2 Logic (source of truth)

```
regimeCap   = deploymentMultiplier * 100   // v2: multiplier is 0.0–1.0 fraction
regimeRoom  = regimeCap - currentInvestedPct
targetGap   = maxPs                         // sector gap not wired in v2
raw         = min(targetGap, maxPs, regimeRoom)
suggested   = max(0, raw)
binding     = max_per_stock | regime_cap | target_gap
```

## V6 Input Schema Mapping

V6 `SizingInput` replaces v2 params:
- `current_weight_pct`     — per-stock current weight (was missing in v2 — v2 used portfolio total)
- `max_per_stock_pct`      — same as v2 `maxPerStockPct`
- `deployment_multiplier`  — 0.5/1.0/1.5 scalar (per plan spec). NOTE: actual DB stores 0.0/0.4/0.7/1.0 (regime.py); plan spec docs 0.5/1.0/1.5 as display examples. The function accepts whatever numeric is passed.
- `sector_gap_pp`          — new v6 input (v2 had this stubbed as 0). Positive = overweight.
- `cell_conviction_depth`  — 0..5, new v6 input (no v2 equivalent)

## Chosen Approach

Port v2 logic with v6 extensions:

1. **Effective cap** = `max_per_stock_pct * deployment_multiplier` (v2's regimeCap / 100 expressed as %-of-stock, not portfolio)
   - When multiplier = 1.0: full cap
   - When multiplier = 0.5: halved (bear regime)
   - When multiplier = 1.5: boosted (bull regime)

2. **Remaining room** = `effective_cap - current_weight_pct`
   - Binding = `deployment_cap` if this < max_per_stock_pct

3. **Sector adjustment**: if `sector_gap_pp > 5` (overweight >5pp), cap add to 0 → `sector_cap`

4. **Conviction floor**: if `cell_conviction_depth === 0`, suggested = 0 → `conviction_floor`

5. **Binding constraint priority**: `conviction_floor` > `max_per_stock` > `deployment_cap` > `sector_cap`
   - If room > 0, apply sector adjustment (scale down if overweight, scale up if underweight, capped by max_per_stock)

6. **Rationale string**: `"+{N}% — {description}"`

## Sector Gap Logic

- `sector_gap_pp > 5`: sector overweight → binding = `sector_cap`, suggested = 0 or reduced
- `sector_gap_pp < -5`: sector underweight → boost suggested by 20% (scaled up, still ≤ remaining room)
- `-5 ≤ sector_gap_pp ≤ 5`: neutral, no sector adjustment

## Edge Cases

- `current_weight_pct >= max_per_stock_pct`: suggested = 0, binding = `max_per_stock`
- `conviction_depth === 0`: suggested = 0, binding = `conviction_floor`
- `deployment_multiplier = 0`: effective cap = 0, suggested = 0, binding = `deployment_cap`
- NaN/negative inputs: treat as 0

## Files

- `frontend/src/lib/v6/sizing.ts` — pure function, ≤180 LOC
- `frontend/src/lib/v6/__tests__/sizing.test.ts` — 8 cases, ≤280 LOC

## Expected Runtime

Pure CPU function — sub-millisecond. No DB calls. No async.
