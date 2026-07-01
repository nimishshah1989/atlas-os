# Atlas v4 Backend Consolidation Plan (2026-07-01)

Branch: `release/v4-consolidation-live`

## North star

**One source of truth.** The Python backend computes *everything* — stock lens
atoms → deciles → leadership → holdings-weighted fund/sector/ETF composites → fund
category ranks (with the <12m gate) — and writes **final numbers** to
`foundation_staging`. The frontend does **zero scoring/ranking/roll-up math**: it
`SELECT`s pre-computed columns and renders them.

FM constraint carried in: **NO table sprawl** (v6-data-remediation). Prefer
*extending existing* `foundation_staging` tables over minting new ones. Exactly one
new table is proposed (`etf_rank_daily`, the missing peer of the existing
`fund_rank_daily`).

## Verified current state (the two-pipeline reality)

The **live v4 lens path** is entirely on `foundation_staging`:

```
Kite ingest ─▶ fs.ohlcv_stock / fs.ohlcv_etf / fs.index_prices   (close_adj = close; Kite pre-adjusted)
              │
   compute_all.py ─▶ fs.technical_daily        (EMA/RSI/RS/flags/vol; TA-Lib)
              │
   atlas/lenses/pipeline.run_pipeline ─▶ fs.atlas_lens_scores_daily   (6 lens atoms + composite + conviction_tier per STOCK)
              │
   rollup_sectors.py       ─▶ fs.sector_lens_daily     (cap-wt lens vector + breadth + dispersion)   [manual]
   build_fund_rank_history ─▶ fs.fund_rank_daily        (holdings-wt composite + cat rank + deciles)   [--latest]
              │
   frontend queries/v6/*.ts  ── RECOMPUTES deciles/leadership/composite/ETF roll-ups/fund gate ON READ
```

The **old M2–M5 pipeline** (`atlas/compute/stocks.py` reading `public.de_equity_ohlcv`,
writing `atlas.atlas_*_daily`; macro ingest; conviction) is a *separate, retired*
cluster. It is **out of scope** for this task except where its `atlas.*` tables sit
on the live-lens read path (see §3).

### What the frontend still computes on-read (must move)
- **Stock deciles** (`ntile(10) OVER (PARTITION BY cap ...)`), **leadership** (`d_composite>=10`),
  **strength** (2-lens decile mean) — embedded SQL CTEs in `stock_lens.ts`, `sector_lens.ts`,
  `etf_lens.ts`, `fund_lens.ts`. Recomputed universe-wide on every page load.
- **cap_cohort** derivation (large/mid/small/micro from `de_index_constituents`).
- **Composite** blend — `sectorScore.ts` / `fundScore.ts` (weights from `atlas_thresholds`
  via `lens_weights.ts`), duplicating the composite already in `atlas_lens_scores_daily`.
- **Fund** holdings-weighting + within-category rank + **<12m NAV gate** — `fund_lens.ts` SQL + `fundScore.ts`.
- **ETF** holdings-weighting + breadth — `etf_lens.ts` SQL (NO Python equivalent exists).
- **Fund** EMA-breadth, golden-cross count, RS matrix, NAV returns — `fund_metrics.ts`.
- **Sector breadth/dispersion** — `sector_breadth.ts` reads a *dead* table
  (`atlas_scorecard_daily.features` JSONB); should read the already-computed
  `sector_lens_daily.breadth_*` columns instead.

---

## Work item 1 — Backend computes the roll-ups; frontend becomes a pure reader

### 1a. Materialize stock deciles + leadership + cap cohort (Python)
Add a post-pipeline stage (extend `atlas/lenses/pipeline.run_pipeline`, using the
existing `scripts/foundation/decile_core.py` logic) that, for the scored date,
writes the universe-relative post-process. **Extend `atlas_lens_scores_daily`** with
columns (no new table): `cap_cohort`, `d_technical, d_fundamental, d_catalyst,
d_flow, d_valuation, d_composite`, `lead` (composite-D10, 0/1), `strength` (2-lens
decile mean). The per-stock `composite` already exists — reconcile the frontend's
renormalized formula to it so there is exactly ONE composite (Python's).

### 1b. Sector composite (Python)
Extend `rollup_sectors.py` → add blended `composite` (+ its rank/decile) to
`sector_lens_daily`. Breadth/dispersion already there. Frontend reads them.

### 1c. ETF roll-ups (Python — genuinely missing)
New `scripts/foundation/build_etf_rank_history.py` mirroring the fund builder,
using the exported-but-unused `composite.rollup_holdings()`. Writes **one new table**
`fs.etf_rank_daily` (holdings-wt lens vector, composite, breadth, decile, leadership).

### 1d. Fund roll-ups: add the <12m gate + fund metrics (Python)
`build_fund_rank_history.py` already writes holdings-wt composite + cat rank +
deciles + breadth. Add: **`has_12m` gate** (funds with <12m NAV history are
unranked / excluded from `cat_size`) — currently only in `fundScore.ts`. Fold the
`fund_metrics.ts` aggregates (EMA-breadth, golden-cross, RS matrix, NAV returns)
into `fund_rank_daily` (or a sibling), computed nightly.

### 1e. Frontend → pure reader
Delete `fundScore.ts` / `sectorScore.ts` math and the decile/leadership/holdings
CTEs; repoint `queries/v6/*.ts` to `SELECT` the new pre-computed columns. Keep
trivial *display* formatting only (×100 scaling). **Open decision for review:**
whether the small `market_pulse.ts` period-arithmetic (tier returns, index strip,
macro deltas) also moves to a nightly `market_pulse_daily`, or stays as thin
render-time arithmetic. Default: move the scoring/ranking/roll-up math now; treat
market-pulse arithmetic as a fast-follow.

---

## Work item 2 — `compute_all.py` incremental **by date**

Today `targets()` skips any instrument whose `compute_state.status='done'`
([compute_all.py:73-75]) — so a new trading day computes nothing; 06-30 needed a full
`--redo` (~10 min, rewrites all history).

Fix:
- `targets()`: select instruments where `max(ohlcv.date) > max(technical_daily.date)`
  (per-instrument date coverage), not a sticky flag. Keep `compute_state` for
  error/no_data visibility only.
- `compute_one()`: still compute the full series (EMAs need full lookback) but only
  **UPSERT rows newer than the stored max** (with a small warmup overlap). Cuts a
  daily run from ~2,500 writes/instrument to ~1.
- Flags: `--full`/`--redo` (force full rewrite), `--asof DATE`.

---

## Work item 3 — Finish killing `atlas.*` on the **live-lens** path

Scope = the live v4 lens pipeline only (the broad retired M2–M5 `atlas.*` refs —
macro/conviction/decisions — are a separate legacy sweep, not this task).

- `adapters.py:417` — `LEFT JOIN atlas.atlas_universe_stocks` (sector/industry) →
  repoint to the `foundation_staging` equivalent (`instrument_master` + sector cols;
  verify columns exist, else an fs universe table).
- `adapters.py:397` — `atlas.atlas_decision_policy` / `atlas.policy_registry` → move
  `policy_registry` into `fs` (migration + seed) and read from `fs`. (Policy weight
  is 0 today → low blast radius, but must move for a clean drop.)
- `calibration.py:94` — `FROM atlas.atlas_lens_scores_daily` → `fs`. This is a live
  **correctness bug**: calibration reads the stale `atlas` table while the pipeline
  writes `fs`.
- Centralize the schema name in one config constant for the lens context (today
  `atlas.config.SCHEMA_NAME="atlas"` is unused and misleading).
- Physical `DROP SCHEMA atlas` stays **gated** on a green Kite nightly (per prior
  consolidation memo) — final step, not part of this PR.

---

## Work item 4 — `build_index_metrics` StringDataRightTruncation

`index_code VARCHAR(32)` (migration 004:171, PK) overflows on NSE's full names
(e.g. `NIFTY MIDSMALL FINANCIAL SERVICES` = 33 chars). Sector-page RS
(`sector_index_rs.ts`) lags because the write fails. Fix: **widen** `index_code` to
`VARCHAR(64)` on `atlas_index_metrics_daily` (+ `_quarantine`) via a new migration;
handle the PK. Widen beats truncate (truncation risks code collisions). Verify the
`foundation_staging` copy of the table is widened too (the writer targets `fs.`).

---

## Work item 5 — Clean daily Kite orchestrator + env + source discipline

### 5a. Orchestrator
New `scripts/ops/daily_ingest.sh` (or Python) chaining:
1. **Fresh Kite token** — attempt `kite_autologin` **once**; on TOTP/login failure,
   **abort loudly** with the relay recovery steps (do NOT retry — lockout guard).
2. **Ingest** — `ingest_kite.py` over the full scored universe derived from
   `instrument_master WHERE kite_token IS NOT NULL` (no manual `--symbols`; make that
   the default when `--symbols` omitted).
3. `compute_all.py` (now date-incremental) → `run_pipeline` → roll-ups (sector/fund/
   etf/index) → `validate_lenses.py` gate → frontend refresh.

### 5b. Kite auth hardening
Codify the documented recovery: relay `start` → `finish <code>`; the 127.0.0.1
redirect SSL error is caught but `request_token` is still valid — exchange it
directly via `auth.exchange_request_token` + `store_access_token`. Stale-TOTP
detection must stop before repeated login attempts. (Also flag:
`atlas.atlas_kite_session` token store is an `atlas.*` table on the live path →
move to `fs` in the atlas.* sweep.)

### 5c. Environment
`talib` and `pyotp` are installed on the box but absent from `pyproject.toml`
(reproducibility gap). Codify them (with a note that TA-Lib needs the C library).

### 5d. Bhavcopy source discipline
Both `ingest_kite.py` and `ingest_bhavcopy.py` upsert `fs.ohlcv_stock` (different
`source` tags, last-write-wins) — so bhavcopy can silently become the v4 scorer's
stock price source. Guard: `ingest_bhavcopy.py` must **refuse** to write
`ohlcv_stock`/`ohlcv_etf` (raise unless an explicit override flag). **Open decision
for review:** indices — `index_prices` is still legitimately bhavcopy-fed today
(`ind_close_all`); keep bhavcopy for indices only, or move indices to Kite too?
Default: keep bhavcopy for `index_prices`, bar it from stock/ETF OHLCV.

---

## Execution sequence & gates

1. Item 4 (index widen) — smallest, unblocks sector RS immediately.
2. Item 2 (incremental compute) — needed before the orchestrator is safe to run daily.
3. Item 1a–1d (backend materialization) — the heart; each with unit tests on REAL
   lens vectors, gated by `validate_lenses.py` (asserts on REAL produced output).
4. Item 1e (frontend pure-reader) — only after the columns exist and validate.
5. Item 3 (atlas.* live-lens migration) — after materialization proves fs is complete.
6. Item 5 (orchestrator/env/guard) — wraps it into a repeatable nightly.

**Definition of done gate (rule #0):** `validate_lenses.py` (and new roll-up checks)
must pass on REAL recomputed output — never synthetic fixtures. Every number traces
to a real Kite/DB source.

## Open decisions surfaced for the eng review
1. Extend `atlas_lens_scores_daily` with decile/leadership columns vs a companion
   `stock_rank_daily` (default: extend — no sprawl).
2. Does market-pulse period-arithmetic move to backend now, or fast-follow? (default: fast-follow).
3. Index price source under the bhavcopy guard: keep bhavcopy for `index_prices`, or move to Kite? (default: keep bhavcopy for indices).
4. atlas.* physical drop scope: live-lens refs now, full retired-cluster removal later? (default: yes, scoped).
