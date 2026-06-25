# Atlas data remediation — durable handoff (2026-06-25)

Diagnosis complete + sourced; the acceptance gate + the missing lens entrypoint are
committed; the actual fixes + refresh are the next (monitored) pass. **Nothing here is a
synthetic number — every defect was confirmed against REAL rows in the DB.**

## The contract: `scripts/foundation/validate_data_integrity.py`
Run it first thing: `.venv/bin/python scripts/foundation/validate_data_integrity.py`.
Baseline today = **12/15 FAIL**. It is the falsifiable definition of done (companion to
`validate_lenses.py`). **Do NOT edit it to pass — fix the pipeline.** Wire it into the
nightly + CI so bad data can never silently ship again.

## Root causes (traced to file:line)
1. **Staleness** — `atlas.lenses.pipeline.run_pipeline()` (the six-lens scorer) is in **neither
   nightly cron**; it only ran via the manual historical backfill → `atlas_lens_scores_daily`
   stuck at 06-19 while MVs auto-advanced to 06-22. FIX shipped: `scripts/lens_daily.py` (daily
   entrypoint, validated 2,093 stocks/~26s, idempotent). STILL TODO: wire it into the nightly
   **after the technicals compute** (`scripts/foundation/compute_all.py`) and before the MV
   refresh + `consolidate_tables.py`.
2. **Lens sub-scores collapsed** (placeholders → 5–9 distinct over 2,093 stocks):
   - `fund_profitability` 5-bucket step on ROE (`atlas/lenses/compute/fundamental.py::_profitability`);
     the +2 ROIC bonus is dead (`fundamental_pit.py` hard-sets `roic=None`).
   - `val_pe_vs_sector` 5-bucket step (`valuation.py::_score_pe_vs_sector`); also starved when
     sector median PE is NULL (the 368 unmapped + thin sectors).
   - `flow_institutional` modal **50.0** (`flow.py::_score_institutional`) — no real FII/DII/MF
     delta wired; `public.de_mf_holdings` exists (latest 2026-05-04).
   - `policy_tailwind` only **15 policies seeded** (migration 124 `_POLICY_SEEDS`) → most stocks 0.
   → These four are the **methodology redesign** that needs the FM's before/after sign-off (RULE #0).
3. **Sector breadth EMA blank** — nightly `atlas/compute/sectors.py` `METRICS_COLUMNS` omits
   `pct_above_ema20/200` and `_run_pipeline` never calls `compute_breadth_per_sector`. Also it's
   EMA**20** (`ema_20_ratio` from the metrics layer) but the **system standard is EMA 21**
   (`technical_daily.above_ema_21`). FIX: compute `pct_above_ema21` + `pct_above_ema200` from the
   canonical `above_ema_21`/`above_ema_200`, add to `METRICS_COLUMNS`, call it in `_run_pipeline`;
   rename column → ema21 in the MV (migration 103) + frontend (`sectors.ts`, `SectorBreadthMVPanel`).
4. **Returns** — `mv_sector_cards` (migration 102) passes through `bottomup_ret_6m` (Defence
   +111% = outlier-weighted constituent; audit `close_approx`); `ret_12m` NULLs when NIFTY-500
   12m is absent. FIX: store true `bottomup_ret_12m`; backfill NIFTY-500 12m.
5. **368 unmapped stocks** — actives outside the ~750-name curated universe (`atlas/universe/stocks.py`
   ⨝ NSE membership). FIX: COALESCE fallback (de_instrument.sector / industry→sector / index→
   `atlas_sector_master.primary_nse_index`) OR extend the universe.
6. **Taxonomy 29→21 (D13)** — DECIDED, NOT BUILT. Fold map is locked in `CONTEXT.md` L955-983;
   the `atlas_sector_rollup` table **does not exist**. FIX: create+seed it, add
   `canonical_sector = COALESCE(parent, sector_name)` in the sector MVs + universe assignment.

## Data picture (so we don't mis-diagnose again)
- Raw Kite OHLCV (`atlas.atlas_v6_clean_ohlcv` / `public.de_equity_ohlcv`) is **fresh to 06-24**.
  Staleness = un-run compute, NOT an ingestion gap. The refresh CAN reach yesterday.
- Run-chain: `compute_all.py` (technicals, sharded 7-worker) → `lens_daily.py` → `m2_daily.py` →
  `m3_daily.py` (sectors/breadth) → `_refresh_mvs.py`/pg_cron (atlas.mv_*) → `consolidate_tables.py`
  (mirror atlas → foundation_staging, the frontend read layer).
- DB access: `ATLAS_DB_URL` in `frontend/.env.local` (Supabase **session pooler, cap 15**; the
  frontend dev server holds `max=14`). Don't run heavy DB scripts while the dev server serves demos.

## ⚠ DB / codebase HYGIENE (FM directive — no chaos, no table sprawl)
- **Do NOT proliferate tables/MVs.** The ONLY justified new object in this plan is
  `atlas_sector_rollup` (a tiny mapping table for D13). Everything else = ALTER/reuse existing.
- Before creating ANY new table/column/MV: confirm nothing existing serves it; if you must, document
  it + get FM sign-off.
- Worth a cleanup audit: there is visible sprawl already (e.g. `de_equity_ohlcv_y2000..y2031`
  yearly partitions, overlapping MVs). Catalogue redundant/dead objects → propose dropping (FM
  approves drops). Keep `foundation_staging` as the single frontend read surface.

## Execution plan (one focused, monitored pass)
- **Stage A** (deterministic, gate-verifiable, no methodology change): breadth→EMA21 · 368 mapping ·
  `atlas_sector_rollup` fold · ret_12m. Commit each.
- **Stage B** (methodology — needs FM before/after on real names; the pipeline runs fast so generate
  it empirically): the 4 scorer redesigns.
- **Stage C**: run the chain to 06-24 · wire `lens_daily`+`consolidate` into the nightly · drive the
  gate to GREEN · verify the frontend (both themes).

## Frontend (already shipped this session, both themes, ~13 commits on feat/v4-six-lens)
Design language LOCKED (see memory `v4-design-language-locked`). Market Pulse · Sector View · Stocks ·
ETF · Funds · Admin all rolled out. Portfolio Manager intentionally cut. Frontend review notes:
`docs/v4/2026-06-25-rollout-review-notes.md`.
