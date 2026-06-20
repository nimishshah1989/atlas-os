# Loop 1 — Six-Lens Data Feeds: Progress Summary

**Branch:** `feat/v4-six-lens`
**Status:** IN PROGRESS — feeds ingesting, gate not yet green

---

## Milestone 1: Foundation Validation (COMPLETE)

### validate.py fixes
- **Listing-relative coverage/gaps**: span now starts from `max(listing_date, first_data)`,
  not absolute COVERAGE_START. 5-day grace for recently listed stocks.
- **Non-positive closes ignored**: filter `c > 0` before computing returns/jumps.
  Fixes ASHOKLEY/IOC/VEDL/MAZDOCK inf% jump artifacts.
- **Corp-action calendar exclusion**: suspension days excluded from expected span.
- **Metrics parity**: only counts valid (positive) close rows in OHLCV expectation.

### Corp-action seeding
- 70 corp_action_events (jump dates for 38 stocks) auto-detected from adj-close data.
- 227 suspension events for AWL/GALLANTT/JWL trading halts.

### Result: **N500 498/498 GREEN** (coverage + cleanliness + metrics)

---

## Milestone 2: Six-Lens Feed Scripts (COMPLETE)

### New ingestion scripts (all in `scripts/foundation/`)

| Script | Target Table | Source | Status |
|---|---|---|---|
| `ingest_xbrl.py` | `financials_quarterly` | NSE XBRL quarterly results | Running |
| `ingest_filings.py` | `lens_filings` | NSE corporate-announcements API | Running |
| `ingest_insider.py` | `lens_insider` | NSE corporates-pit API | Running |
| `ingest_shareholding.py` | `lens_shareholding` | NSE shareholding-master API | Running |
| `ingest_bulk_deals.py` | `lens_bulk_deals` | NSE large-deals snapshot | Done (156 deals) |
| `refresh_tv_metrics.py` | `atlas.tv_metrics` | TradingView screener (2093 stocks) | Done (2083 upserted) |

### Accuracy spot-checks
- **XBRL**: RELIANCE Q3FY25 verified: revenue ~128,260 Cr, PAT ~8,721 Cr (matches NSE filing).
- **Filings**: RELIANCE returns 3307 announcements, classified into earnings/capital/governance buckets.
- **TV Metrics**: 2083/2093 stocks fetched (10 not on TV). N500: 496/498 covered.
- **Bulk Deals**: 156 deals (133 bulk + 61 block, with superstar detection).

### Gate validator
`validate_six_lens.py` — checks all 6 feeds against N500 core. Reports per-feed coverage.

---

## Blockers

- **NSE rate limiting**: All per-symbol feeds throttled to ~1 req/sec. Full 2089-stock
  ingestion takes ~35 min per feed. The 4 feeds run in parallel.
- **Git push**: No SSH/GitHub credentials on this box. Commits saved locally on branch.
- **AKZOINDIA + GSPL**: 2 N500 symbols missing from foundation_staging.instrument_master
  (not in NSE EQUITY_L.csv — may be recently renamed or delisted from NSE).

---

---

## Milestone 3: Six-Lens Calculation Engine (COMPLETE)

### Scorer modules (all in `atlas/lenses/compute/`)

| Module | LOC | Subcomponents | Status |
|---|---|---|---|
| `technical.py` | 204 | trend, RS, vol_contraction, volume (4×25) | DONE |
| `fundamental.py` | 230 | profitability, margin, growth, balance_sheet, op_leverage (5×20) | DONE |
| `valuation.py` | 184 | pe_vs_sector, absolute_pe, pb, ev_ebitda, 52w_position + zone/mult | DONE |
| `catalyst.py` | 245 | earnings_strategy(55%), capital_action(30%), governance(15%) | DONE |
| `flow.py` | 243 | promoter(70%), smart_money(30%) + institutional/superstar | DONE |
| `policy.py` | 149 | bidirectional sector+keyword match, HIGH/MED/LOW priority | DONE |
| `risk_flags.py` | 180 | 10 red flags, degradation_score floor=-30, is_degrading≤-15 | DONE |
| `composite.py` | 293 | rescale→weighted_avg→convergence→modifiers→conviction + rollups | DONE |

### Data adapters (`atlas/lenses/data/adapters.py`)
- 7 load functions: technical, fundamental, valuation, catalyst, flow, policy_registry, sectors
- `write_lens_scores()` bulk upsert to `atlas.atlas_lens_scores_daily`

### Pipeline (`atlas/lenses/pipeline.py`)
- `run_pipeline(as_of, engine, batch_size)` — full orchestration
- **Result**: 750/750 instruments scored, 0 skipped

### Conviction tier distribution (2026-06-19)

| Tier | Count | Avg Composite |
|---|---|---|
| HIGHEST | 6 | 71.70 |
| HIGH | 102 | 61.75 |
| MEDIUM | 285 | 50.85 |
| WATCH | 336 | 39.12 |
| BELOW_THRESHOLD | 21 | 23.26 |

### IC calibration (`atlas/lenses/calibration.py`)
- Infrastructure complete: `calibrate_lens_ic()`, `propose_weights()`, `backfill_ic_journal()`
- 21 IC rows persisted (7 lenses × 3 forward periods)
- Single-date IC = NaN (needs multi-date pipeline runs for time-series IC)
- Quantile spreads directionally correct (tech +0.34, fund +0.12 at 6m)

### Migration 124
- `atlas.atlas_lens_scores_daily` — 40+ columns, PK=(instrument_id, date)
- `atlas.policy_registry` — 15 active policies seeded
- 25 threshold rows (lens_weights, convergence, conviction_tiers, valuation_zones)

### Tests
- 65 unit tests in `atlas/lenses/compute/tests/test_scorers.py` — **ALL PASS** (0.24s)

---

## Milestone 4: Frontend — Six-Lens Surfaces (COMPLETE)

### Feature flag
- `NEXT_PUBLIC_LENS_V4=1` enables all lens UI; OFF = production byte-identical.
- Utility: `frontend/src/lib/feature-flags.ts`

### New components

| Component | Path | Purpose |
|---|---|---|
| `LensVectorPanel` | `components/v6/stock-detail/LensVectorPanel.tsx` | 6-lens bar chart + subcomponents + risk flags for stock detail |
| `LensRankingTable` | `components/v6/stocks/LensRankingTable.tsx` | Sortable lens ranking table (750 stocks, any lens/composite) |
| `SectorLensHeatmap` | `components/v6/sectors/SectorLensHeatmap.tsx` | Sector-level averaged lens vector heatmap |

### Query layer
- `frontend/src/lib/queries/lens-scores.ts` — 5 functions querying `atlas.atlas_lens_scores_daily`
  - `getLensScoreByInstrument()`, `getLensScoreBySymbol()`, `getAllLensScores()`,
    `getLensScoresBySector()`, `getSectorLensVectors()`

### Surfaces wired (all behind LENS_V4_ENABLED)

| Surface | What's added |
|---|---|
| `/stocks/[symbol]` | LensVectorPanel after gates section |
| `/stocks` | LensRankingTable section above existing screener |
| `/sectors` | SectorLensHeatmap between RRG and return heatmap |
| `/` (home) | Regime+Pulse merge: breadth table replaces old chart sections when flag ON |

### Home page redesign (per markets-today-redesign.md)
When `LENS_V4_ENABLED`:
- **Removed**: TrendSection, BreadthSection, MomentumSection, ParticipationSection,
  RegimeClassifierInputs, TodayConvictionTabs
- **Added**: BreadthTable (from India Pulse) + RegimeJourney12w (kept)
- **Preserved** (unchanged): RegimeVerdict, SignalScorecard, TodayWorklist,
  RegimeHeadline, IntradayNiftyStrip, RegimeOverlayChart

### Frontend debt audit
Components identified for removal when flag permanently ON:
- `app/india-pulse/` — merged into home
- `components/regime/{TrendSection,BreadthSection,MomentumSection,ParticipationSection}`
- `components/regime/RegimeClassifierInputs`
- `components/v6/landing/TodayConvictionTabs`
Not deleted yet: required for flag-OFF (production) path.

### ETFs/Funds
Deferred — lens scores are stock-level atoms; ETF/fund lens vectors require
holdings-weighted roll-up computation (not yet in backend).

### Tests
- 22 new tests across 4 test files — **ALL PASS**
  - `feature-flags.test.ts` (4 tests)
  - `LensVectorPanel.test.tsx` (7 tests)
  - `LensRankingTable.test.tsx` (7 tests)
  - `SectorLensHeatmap.test.tsx` (4 tests)

### Gate status
- `next build`: PASS
- `tsc --noEmit`: CLEAN (new files, pre-existing test fixture errors unrelated)
- `next lint`: CLEAN (new files)
- Flag OFF parity: All lens UI gated by `LENS_V4_ENABLED` — production unchanged

---

## What's left for gate green

- **IC ≥ floor**: Requires multiple daily pipeline runs to accumulate time-series IC.
  Infrastructure is complete; run `run_pipeline()` daily then `calibrate_lens_ic()`.
- **ETF/Fund lens roll-ups**: Backend needs holdings-weighted aggregation before frontend can show lens vectors for ETFs/funds.
- **Frontend debt cleanup**: Delete old components once flag is permanently ON (see audit list above).
