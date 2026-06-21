# Atlas / Jhaveri — Clean Data Foundation (design + loop spec)

> Goal: one strong, consistent, Supabase-native market-data backend that every
> Jhaveri app can build on. Own the ingest from NSE Bhavcopy; derive all
> technicals with a standard library; validate everything against a quantifiable
> harness; run the build as an autonomous loop until the harness is all-green.

## 1. Current state (confirmed live in Supabase, project `nanvgbhootvvthjujkvs`)
- **Storage is NOT the problem — both layers already live in Supabase:**
  - Core OHLCV: `public.de_equity_ohlcv` (year-partitioned, partitions 2007→2034),
    `public.de_etf_ohlcv`, `public.de_index_prices` (139 indices, 2014→2026),
    `public.de_global_prices`, `us_atlas.stock_ohlcv`.
  - Derived/materialized: `atlas.atlas_stock_metrics_daily` (EMA/RS/ret, 2016-04-07→today),
    `atlas.atlas_index_metrics_daily`, the `atlas.mv_*` views (refreshed via pg_cron).
- **The flaky part is the SUPPLY (the "JIP data core" ingest)** that writes `de_*`.
  When it stalls or feeds bad rows, everything downstream breaks.
- **Concrete cleanliness gaps found:**
  - `de_index_prices`: **24 of 139 indices have <1,500 rows**; worst (`NIFTY CEMENT`,
    `NIFTY SMALLCAP 500`, `NIFTY REITS REALTY`) = **28 rows** (new, May 2026).
    Gappy long series too (e.g. NIFTY FMCG spans 2016–26 but only 756 rows →
    missing months → produced the bogus **FMCG 3M +249.8%** the app showed).
  - No automated validation/completeness contract — bad data surfaces only when a
    chart looks wrong.

## 2. Source of truth: NSE Bhavcopy
- Authoritative, free, official EOD source covering **stocks + ETFs (listed
  securities) + indices**. **Corporate actions** (splits/bonus/dividends) also
  published by NSE → we compute **adjusted** prices ourselves, deterministically.
- 10y = a finite downloadable archive → fully reproducible (re-pull a day, recompute).
- This **replaces the JIP-fed core** with a self-owned pipeline (confirmed scope).

## 3. Target architecture
```
NSE Bhavcopy (EOD) + Corp Actions
   │  own ingest job (idempotent, validated)
   ▼
RAW OHLCV  ──►  ADJUSTED OHLCV         (Supabase, 10y, stocks/ETFs/indices)
   │
   ▼
TECHNICALS via TA-Lib  (EMA 21/50/200, RSI, RS, returns, breadth, …)
   │
   ▼
Materialized views  ──►  Atlas + every future Jhaveri app
```

## 4. Locked decisions
- **Technicals library: TA-Lib** (industry-reference C impl via Python wrapper).
  **No hand-rolled formulas.** Fallback if C-lib install friction: `pandas-ta`.
- **Build on a clean STAGING schema** in Supabase → validate to all-green → **cut over**.
  Never mutate live `de_*`/`atlas_*` in place.
- **Metrics (already wired in Atlas):** baselines **Nifty 50 + Nifty 500**;
  RS windows **1d / 1w / 1m / 3m / 6m / 12m**.
- **Membership:** accept **current** Nifty 500 membership for all history (no
  point-in-time membership in v1).
- **EMA period:** breadth uses **21-EMA** (not 20), plus 50 / 200.

## 5. The quantifiable goal = a verification harness (definition of done = 0 failures)
Three axes, each a set of SQL/validation checks:
1. **Coverage:** every active stock/ETF/index has ≥10y Bhavcopy-sourced OHLCV
   (target ≥ 2016, further where it exists); every universe member present;
   per-instrument row-count ≥ expected trading days.
2. **Cleanliness:** no gaps vs the NSE trading calendar; no zero/negative/NULL
   closes; adjustments reconcile; series ≤1 trading day stale; no absurd 1-day
   jumps (split/adjustment errors). *(This is the check that catches FMCG +249.8%.)*
3. **Metrics:** TA-Lib technicals + RS (N50/N500 × 6 windows) + breadth present for
   every (instrument, date) that has a price; **recompute-and-diff matches stored**.

## 6. The autonomous loop
- **Model split:** Opus for one-time high-value scaffolding (harness, schema,
  adjustment correctness, PoC); **cheaper model (Sonnet or external DeepSeek/Qwen)
  for the loop grind** — the harness is the objective gate, so downshifting is safe.
- **Execution is token-free:** the model writes deterministic Python scripts and
  reads small pass/fail harness output; the actual grind (download 2,500 Bhavcopy
  files, compute TA-Lib over millions of rows) runs as plain Python — **0 model
  tokens regardless of data volume**. Token cost is bounded by design + debug.
- **Loop cycle:** run harness → get failing list → fix top failure (idempotent
  writes) → re-check → repeat until 0 failures → report. Progress = green-count ↑.
- **Run in tmux against staging**, with a token/time budget, kill switch, and a
  heartbeat reporting green-count.

## 7. Execution plan (phases)
1. **Verification harness** (read-only) — the goal made concrete; shows distance to green.
2. **Architecture/scope doc** (this file).
3. **Thin PoC** — ingest ONE day of Bhavcopy → adjust → TA-Lib technicals for a
   handful of symbols → harness green. De-risks before the 10y loop.
4. **Full 10y loop** in tmux on staging → all-green.
5. **Cutover** staging → prod (swap `de_*`/`atlas_*` reads to the clean tables).

## 8. Open items / decisions still pending
- Where the ingest job runs (EC2 cron vs GitHub Action vs Supabase edge function).
  *Recommendation: keep nightly-on-EC2 writing to Supabase for v1; revisit later.*
- Exact staging schema name + cutover mechanics.
- ETF table key column (`de_etf_ohlcv` — verify; not `symbol`).
- Whether to also rebuild global/US series in v1 or India-only first.
  *Recommendation: India (stocks/ETFs/indices) first.*

## 9. Reference facts
- Atlas Supabase project: `nanvgbhootvvthjujkvs`. DB URL in `frontend/.env.local` (`ATLAS_DB_URL`).
- Prod serves from `/home/ubuntu/atlas-frontend-v2` (pm2 `atlas-frontend-v2`, :3002, behind nginx).
- Dev tree `/home/ubuntu/atlas-os`; deploy source checkout `/home/ubuntu/atlas-prod-src`.
- Per-stock EMA already exists 2016→ in `atlas_stock_metrics_daily` (but 20-EMA, not 21).
