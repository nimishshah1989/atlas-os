# Regime + India Pulse fix chunk — build plan (2026-05-30)

Backend-first (user-chosen). RS backfill depth ~2yr. Days-since-call:
recompute ~2yr history (user chose this over honest tracking-start).
Return: BOTH absolute + excess. Terminology locked in CONTEXT.md.

Live DB: Supabase `atlas-os` (nanvgbhootvvthjujkvs), alembic head = **121**.
New migration = **122**, down_revision="121".

## Live-verified diagnosis (clean queries, 2026-05-30)

Date lag is the master clue: regime/sector/index/MV all at **2026-05-29**,
**macro at 2026-05-27**. `mv_india_pulse` joins macro `ON date=as_of_date`
(exact) → newest MV row gets NULL macro/vix.

| # | Symptom | Confirmed root cause | Fix |
|---|---|---|---|
| Term structure blank | `vix_9d` IS populated (2752/2752); MV exact-date join misses it (macro lags) | MV date-tolerant lateral join + keep macro ingest current |
| Macro context blank | same exact-date join; `macro_cards`/`narrative_ribbon` NULL on latest row | same lateral-join fix |
| Sector RS 1w blank | `atlas_sector_metrics_daily.rs_1w` 30/30 populated; live MV null = stale (rs_1w backfilled 18:05 after 03:37 refresh) | refresh after RS compute; MV unchanged here |
| % above 100 EMA / 4-wk high | hardcoded `data_gap:true` in MV; `pct_above_ema_100`/`pct_4w_high` never computed | compute cols + un-stub MV breadth_table |
| "DMA" labels | breadth_table labels say "DMA"; data is EMA; no 20-EMA row | relabel + add 20-EMA row in MV |
| Dispersion flat line | `cross_sectional_dispersion` only 3 dates populated | backfill ≥60 trading days |
| Sector heatmap only rs_1w | MV emits only rs_1w/ret_1m/ret_3m | emit rs_1w/1m/3m/6m/12m (+1d/24m after compute) |
| tier_leadership | actually populated (returns_table) — re-verify in UI | likely frontend parse |
| Avoids on top | 527 NEG vs 109 POS, sorted confidence DESC | frontend buy/avoid toggle |
| d8 for everyone | engine minted 2026-05-22 (8d); user chose ~2yr history recompute | M6 + history recompute |
| return-since-call | not stored; ledger empty(0); price to 2007 | compute abs+excess via price join |
| ETFs missing | 9 active etf_signal_calls exist | frontend tab fix |
| RS not across baselines | only tier + nifty500; `mv_markets_rs_grid` exists (mig 098/117) — verify coverage | extend to 9×7 |
| RS 7 windows | sectors have 1w/1m/3m/6m/12m; missing 1d+24m | compute + ~2yr backfill |

RS storage: **excess centred on 0** (NOT ratio). Code inconsistent —
`bottomup_rs_3m_nifty500` uses relative form `(1+rI)/(1+rB)-1`;
`rs_1w/1m/6m/12m` use plain diff `rI-rB`. Standardize to relative form.

## Real code locations (verified — earlier `atlas/features/rs_ratios.py` was a phantom)
- Sector RS + EMA breadth + 52wh: `atlas/compute/sectors.py`
- Stock RS (tier benchmarks): `atlas/compute/benchmarks.py` (via `stocks.py:330`)
- Market breadth (pct_above_ema_20/50/200, new highs): `atlas/compute/breadth.py` + `regime.py`
- Cross-sectional dispersion: `atlas/regime/cron.py` (`compute_cross_sectional_dispersion`, window=20)
- Macro ingest: `atlas/ingest/macro/runner.py` (+ fred/nse_vix/fii_dii/mospi)
- Nightly: `scripts/m3_daily.py` (A indices, B sectors, C regime); `m4/m5_daily.py`
- MV def: `migrations/versions/100_mv_india_pulse.py` (full CTE; live viewdef captured)
- MV cron: `migrations/versions/121_v6_cron_complete_mv_refresh.py`

## Backend wave (strict backend-first)
- **M1 — migration 122: CREATE OR REPLACE mv_india_pulse**
  - Macro/vix/narrative: replace exact-date joins with LATERAL "latest macro row ≤ as_of_date".
  - breadth_table: relabel DMA→EMA; add `% above 20 EMA` row; wire `pct_above_ema_100` + `pct_4w_high` (un-stub once M2 computes them).
  - sector_heatmap: emit rs_1w/1m/3m/6m/12m (1d/24m after M3).
  - Recreate unique index; keep CONCURRENTLY refresh.
- **M2 — breadth compute**: `pct_above_ema_100` + `pct_4w_high` in `breadth.py`/`regime.py`; migration adds columns to `atlas_market_regime_daily`; backfill.
- **M3 — RS 1d + 24m**: add to `sectors.py` (+ stock path); standardize relative form; ~2yr backfill on EC2.
- **M4 — Markets RS grid 9×7**: verify `mv_markets_rs_grid` (mig 098/117) coverage; extend windows/baselines to 7×9 vectorized.
- **M5 — dispersion backfill**: ≥60 trading days via `atlas/regime/cron.py`.
- **M6 — return-since-call + days**: abs + excess via price join; conviction query; recompute ~2yr signal/scorecard history for real entry dates.
- **M7 — ingest currency + refresh order**: macro incremental current; nightly order = compute RS → REFRESH MVs.

## Frontend wave (after backend)
F1 tooltip placement/sizing (`ui/InfoTooltip.tsx`); F2 regime 12w labels-in-blocks;
F3 conviction buy/avoid toggle + buys-first + abs+excess cols + ETF rows;
F4 funds return+expectation cols; F5 worklist FM enrichment;
F6 sort/filter on all tables + 1w/1d/24m temporal filters.

## Deploy
EC2 backfills (m3_daily + RS/dispersion/breadth/history backfills) → REFRESH MVs
→ verify live → git push → frontend build + pm2 restart atlas-frontend (fold restart into deploy cmd).

## Anomaly to flag
git shows untracked `frontend/src/lib/queries/v6/*.ts` (10 files) + stale
funds `__tests__/*.test.tsx`. Not mine. Steer around with selective `git add`;
ask user before touching.
