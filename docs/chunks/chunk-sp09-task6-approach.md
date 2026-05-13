# SP09 Task 6 — Backfill Conviction Boost + EC2 Deploy + IC Validation

## Scope
Update `scripts/backfill_cts_bulk.py` to:
1. Load market regime state per date
2. Apply sector (+10 pts) and regime (+10 pts) bonuses to `cts_conviction_score`
3. Recompute `cts_action_confidence` with full 100-pt threshold (55)
4. Upsert new columns (`cts_conviction_score`, `cts_action_confidence`) to signals table
5. Upsert enhanced sector pivot columns (`stage2_count`, `stage2_pct`, `avg_ppc_conviction`, `action_alert_count`)

Then push to EC2, apply migration 044, run 504-day backfill, run IC engine, validate IC ≥ 0.05.

## Data Scale

- `atlas_cts_signals_daily`: 504 target dates × ~500 universe stocks = ~250K rows
- `atlas_market_regime_daily`: ~504 rows (one per trading day)
- `atlas_cts_sector_pivot_daily`: ~504 dates × ~15 sectors = ~7.5K rows

Scale bucket: 100K–1M → SQL aggregation + vectorized pandas only. No iterrows/apply.

## Chosen Approach

### `_load_regime` helper
Simple SQL read of `atlas.atlas_market_regime_daily` for the date window. Returns ~504 rows — trivial.

### `_boost_conviction` — VECTORIZED (spec had iterrows, we fix it)
The spec's implementation uses `iterrows` twice (sector bonus loop, regime bonus loop).
With 250K rows, `iterrows` would be ~50x slower than vectorized. Instead:

- **Sector bonus**: Build a MultiIndex lookup from `sector_pivot.set_index(["date","sector"])["pivot_balance"]`, then use `df.merge` or `map` with a tuple key. Since we need (date, sector) pairs, create a `_bonus_key` column = zip(date, sector), convert pivot to dict, use `Series.map()` — fully vectorized.
- **Regime bonus**: Merge `regime_df` on `date` column, then `np.where` on `regime_state == 'Risk-On'`. One merge, one vectorized condition.

### Order of operations in `run_bulk`
1. `detect_signals` → raw signals with base conviction (0-80)
2. `compute_sector_pivot(today_signals)` → pivot (needs signals first)
3. `_boost_conviction(today_signals, pivot, regime_df)` → boosted signals (up to 100)
4. `_upsert_signals(engine, boosted_signals)` — with new cols
5. `_upsert_pivot(engine, pivot)` — pivot computed from pre-boost signals (sector counts don't change)

### `_upsert_signals` columns
Add `cts_conviction_score`, `cts_action_confidence` to the existing 19-column list (→ 21 cols).

### `_upsert_pivot` columns
Add `stage2_count`, `stage2_pct`, `avg_ppc_conviction`, `action_alert_count` to the existing 6-col list (→ 10 cols). Guard missing columns with `df[c] = None` fill.

## Wiki Patterns Checked
- `data-engineering.md`: vectorize or SQL for >1K rows; no iterrows
- `database.md`: bulk upsert via `bulk_upsert` helper (already used)
- `financial-domain.md`: row counts before/after transform

## Edge Cases
- `regime_df` empty (new DB, regime not computed yet): sector/regime bonus = 0, safe
- `sector_pivot` empty or `pivot_balance` column missing: bonus = 0, safe
- Stock has no sector in universe: sector lookup returns 0, bonus skipped
- `cts_conviction_score` + 20 bonus → clips at 100 via `.clip(0, 100)`
- Migration 044 already partially applied: use `ADD COLUMN IF NOT EXISTS` in migration

## Expected Runtime (t3.large / EC2)
- OHLCV load + detect_signals: ~5-8 min (existing, unchanged)
- `_load_regime`: <1s (504 rows)
- `_boost_conviction` vectorized: <1s (250K rows)
- `_upsert_signals`: ~30s bulk upsert
- `_upsert_pivot`: <5s
- Total: ~10-12 min (same as before, boost adds negligible time)

## IC Validation Target
- `ppc_strength_stage2` vs `fwd_ret_5d`: IC ≥ 0.05
- `cts_conviction_score_stage2` vs `fwd_ret_5d`: IC ≥ 0.05
