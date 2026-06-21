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

## Milestone 5: Loop A round-2 — calendar correctness + RULE #0 sweep + feed-gap proofs

Driven by an independent diagnosis (calendar source, RULE #0 audit, feed-gap proofs,
coverage-residual classification) cross-checked against real DB data. `validate_lenses.py
--check A` stayed **green throughout** (now `2093/2093`, 276 clean trading dates).

### A1 — Calendar correctness (the `date.today()` bug)
- **Root cause**: `pipeline.py` derived its run date from wall-clock `date.today()`, so on a
  weekend/holiday it scored a non-trading day from stale feeds (it wrote Sat 2026-06-20 rows).
- **Fix**: run date now resolves from the **NIFTY 50 session calendar**
  (`foundation_staging.index_prices`) via new membership helpers `latest_trading_day()` /
  `is_trading_day()` (adapters.py). No `as_of` → snap to latest session; explicit `as_of` →
  **raise** if not a real session. `backfill_lenses.py` now sources dates from NIFTY 50 too.
- **Why NIFTY 50, not the obvious sources** (all proven wrong on real data):
  - `technical_daily` DISTINCT carries 2-/10-row junk rows on NSE holidays.
  - `de_trading_calendar` mislabels the Budget-day **Sunday** session (2026-02-01) as a
    weekend and is synthetically future-dated to 2026-12-31.
  - bhavcopy (`de_equity_ohlcv`) carries **stale duplicates** on holidays (e.g. 2025-10-22
    Balipratipada and 2025-11-05 Guru Nanak are byte-identical carry-forwards of the prior
    session — RELIANCE same close *and* volume). NIFTY 50 correctly excludes them while
    KEEPING the real Diwali Muhurat special session (2025-10-21) and the Budget Sunday.
- **Journal cleanup (FM-approved)**: removed **11 non-session dates** (23,023 rows — 6 in 2026,
  5 in 2025, all NSE holidays absent from NIFTY 50) + **9 stale rows** (universe-shrink drift,
  the old 2102-vs-2093 gap). New `purge_stale_lens_scores()` runs post-pipeline so the journal
  always equals exactly the scored universe. Symmetric check: **0** real NIFTY 50 sessions are
  missing from the journal. Journal = exactly the **276** in-window NIFTY 50 sessions.
- **Test**: `atlas/lenses/data/tests/test_calendar.py` — 11 real-data cases proving membership
  (Budget-Sunday True, Republic-Day False) — no synthetic inputs.

### A2 — RULE #0 sweep (synthetic tests + the one stub score)
- **`test_scorers.py` fully rewritten** from 65 hand-typed-literal tests (the exact pattern that
  let the catalyst bug ship green) to **25 real-data tests**. Backbone = **reconciliation**: each
  scorer is invoked through the pipeline's own plumbing (`_to_float`/`_group_by_iid`) on real
  adapter inputs for real instruments and asserted equal to the value persisted in
  `atlas_lens_scores_daily`. Plus relational, structural, real-feed-reality, and roll-up checks.
- **Valuation stub removed**: no-data now returns `None`/`UNKNOWN`/`1.00×` (was a fabricated
  `35/FAIR`); thin-data names renormalise over **present dimensions only** (dropped the 0.6
  imputation that manufactured up to 60% of a score from always-absent `pb_fbs`/`revenue_growth`).
  Re-ran the 2026-06-19 journal so produced output reflects the fix.
- ⚠️ **FM checkpoint flag**: renormalisation biases **thin-coverage** valuation upward (162
  single-dimension names avg ~74; `val_pb` is 100% null in tv_metrics, 1,352 names lack
  sector-median PE). Root cause is dimension coverage — **Loop B** (sector mapping → adds
  sector-median PE) and **Loop C** (valuation PIT rework) both raise coverage and self-heal it.
- **Cross-check correction**: the audit's "fundamental scores 287 zero-financial names = RULE #0"
  was a **false positive** — fundamental sources `tv_metrics` (real), not XBRL; 284/287 have a
  real `tv_metrics` row, so scoring them is legitimate.

### A3 — Feed integrity + gap proofs (each gap proven genuine-vs-load-failure)
- **bulk_deals = LOAD-FAILURE, not sparsity** (proven): `ingest_bulk_deals.py` hits a snapshot
  endpoint with no date loop, so it only ever holds the latest session (156 rows / 2 dates / one
  ingest timestamp). A re-run recovers **zero** history. **Decision (FM): defer** — document as
  forward-only daily-snapshot data, run nightly going forward; the historical NSE large-deals
  fetcher is a Loop-C/follow-up build. Flow is unaffected (it scores via insider + shareholding).
- **financials_quarterly 287 no_data = GENUINE SPARSITY** (proven via live NSE probes): RELIANCE
  control returned 53 quarterly XBRLs while 12/12 no-data symbols returned 0 / broken stub URLs.
  Sub-causes: ~251 recently-listed (2025-26) names with no/few filed quarters yet; ~10
  insurers/financials (LICI, SBILIFE, HDFCLIFE, ICICIPRULI, ICICIGI, GICRE, NIACL, STARHEALTH,
  GODIGIT) + MCX that file a non-Ind-AS taxonomy the parser doesn't target; ~5 Dec-fiscal MNCs
  (ABBOTINDIA, BAYERCROP, GOODYEAR, NOVARTIND, KENNAMET) NSE surfaces with empty/broken URLs.
  No re-run recovers these. XBRL is also **stale to 2024-12** — refresh is Loop C.
- **insider = HEALTHY** full-history crawl (22,832 rows / 1,624 names / 2,520 dates, all 2,093
  universe instruments processed). Fixed a data-quality defect: `_parse_date` now **bounds**
  transaction dates to `[2000, today+2]` so garbage like a typo'd year **2924** can't enter.
  (6 pre-existing corrupt rows are **harmless** — flow filters `transaction_date <= as_of`, so
  future dates are never scored; their purge was blocked by the safety classifier and is a
  one-line optional cleanup — see checkpoint.)
- **Coverage** on 2026-06-19: all per-lens NULLs are **genuine** (no point-in-time source), **zero**
  fixable join/guard bugs — so no imputation was added (that would violate RULE #0). The only
  remaining `tv_metrics` gap is **10 live-universe names**: 7 are TradingView symbol-format
  mismatches (hyphen/DVR: BAJAJ-AUTO, BOSCH-HCIL, HCL-INSYS, UMIYA-MRO, NAM-INDIA, JISLJALEQS,
  GATECHDVR) and 3 are recently-listed SME (ADVAIT, KLBRENG-B, MCCHRLS-B). **Deferred to Loop C**
  (tv_metrics widen/refresh); coverage of names-with-data is ~100%.

### Loop A status
- `validate_lenses.py --check A`: **GREEN** (12/12). `pytest atlas/lenses`: **36 green**
  (11 calendar + 25 real-data scorer). Commits pushed to `feat/v4-six-lens`.

### FM checkpoint — open items (pause after Loop A, per the agreed cadence)
1. Valuation thin-data upward bias (above) — accept + self-heal via Loop B/C, or adjust now?
2. The 6 corrupt insider rows: classifier-blocked one-line delete (harmless) — approve a permission
   rule or run manually? Recurrence is already prevented by the parser bound.
3. **Point-in-time gap (the big one, deferred to Loop C)**: only 2 of 6 lenses (technical,
   catalyst) are genuinely point-in-time in the journal; fundamental/valuation/flow are today's
   `tv_metrics`/snapshot stamped backward. IC is therefore **not yet trustworthy** — Loop C makes
   fundamental/valuation/flow as-of, extends the journal to **2019-01-01**, then calibrates IC.

---

## What's left (post Loop A)

- **Loop B** — ETF/index holdings-weighted roll-up + sector fold-up (`--check B`).
- **Loop C** — point-in-time rebuild (fundamental/valuation/flow as-of) + XBRL refresh to 2026 +
  journal from 2019-01-01 + walk-forward IC calibration. (FM-sequenced after hygiene + Loop B.)
- **Frontend debt cleanup**: delete old components once the lens flag is permanently ON.
