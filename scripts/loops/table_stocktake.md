# v4 backend table stock-take — 2026-06-22

Goal (FM): every table used in v4 development must live in ONE environment
(`foundation_staging`). This is the complete inventory of what v4's backend touches and
where it lives. Additive consolidation only — clear/drop NOTHING now (D23).

Scope = the v4 backend pipeline: `scripts/foundation/*.py` + `atlas/lenses/**` + `atlas/db.py`.
(The frontend replication adds a separate, larger set of `atlas.*` MV dependencies —
handled later at frontend-wiring time, not in this pass.)

## A. Already HOME — `foundation_staging` (25 tables, 5.7 GB) ✓
Data foundation already consolidated here:
`ohlcv_stock` (1.6 GB), `technical_daily` (3.3 GB), `delivery_daily` (319 MB),
`index_prices` (107 MB), `ohlcv_etf` (51 MB), `financials_quarterly/annual`,
`lens_filings/insider/shareholding/bulk_deals` (+ their `_state`), `sector_lens_daily`,
`instrument_master`, `corp_action(_event)`, `equity_marketcap`, `technical_stock`,
`backfill_state`, `compute_state`, `ingest_run`, various `_state`.

## B. OUTSIDE foundation_staging — MUST BRING IN

### B1. `atlas.*` — v4's OWN outputs + config (sitting in the live Atlas schema)
| table | rows | size | used by | action |
|---|---|---|---|---|
| `atlas.atlas_lens_scores_daily` | 3.87M | **4.1 GB** | 13 files (backfill_lenses writes; decile_core/validate/rollup/calibrate read) | **bring in — the big one.** v4's primary OUTPUT. Old frontend also reads it (shared). |
| `atlas.atlas_thresholds` | 112 | 104 kB | calibrate/validate/composite-view (+ `atlas.db.load_thresholds`) | bring in; repoint `load_thresholds` |
| `atlas.atlas_sector_master` | 31 | 32 kB | calibrate_sectors, sector_view | bring in |
| `atlas.atlas_signal_weights` | 122 | 128 kB | calibrate_loopC, validate_loopC | bring in (v4 calibration output) |
| `atlas.atlas_signal_ic` | 30 | 88 kB | calibrate_loopC, validate_loopC | bring in (v4 calibration output) |

### B2. `atlas.*` — verify if the ACTIVE v4 path needs (may be old-Atlas incidental)
| table | rows | size | used by | note |
|---|---|---|---|---|
| `atlas.atlas_stock_metrics_daily` | 1.42M | 1.87 GB | harness.py only | harness = clean-data rebuild track; confirm if live v4 needs |
| `atlas.atlas_universe_stocks` | 750 | 600 kB | adapters.py, ingest_screener.py | lens universe input — likely needed |
| `atlas.tv_metrics` | 2091 | 8 MB | adapters.py, refresh_tv_metrics, validate_six_lens | TradingView metrics feed lenses — likely needed |
| `atlas.policy_registry` | — | 32 kB | adapters.py | policy-lens input — likely needed |

### B3. `public.de_*` — borrowed feeds. Some already copied to `foundation_staging`; repoint. MF/ETF not yet copied.
| table | rows | size | used by | fs equivalent? | action |
|---|---|---|---|---|---|
| `public.de_equity_ohlcv` | 4.72M | (part.) | backfill_delivery, fetch_delivery, harness, poc, validate_loopC | ✓ `fs.ohlcv_stock` | repoint to fs |
| `public.de_etf_ohlcv` | 441k | 110 MB | ingest_bhavcopy | ✓ `fs.ohlcv_etf` | repoint to fs |
| `public.de_index_prices` | 265k | 41 MB | harness, poc | ✓ `fs.index_prices` | repoint to fs |
| `public.de_instrument` | 2743 | 912 kB | build_universe, harness, ingest_*, poc, validate_six_lens, views.sql | ✓ `fs.instrument_master` | repoint to fs |
| `public.de_mf_holdings` | 242k | 74 MB | fund_view, sample_deciles, test_fund_ic | ✗ | **COPY in** (fund look-through) |
| `public.de_mf_master` | 1359 | 432 kB | fund_view, sample_deciles, test_fund_ic | ✗ | **COPY in** |
| `public.de_mf_nav_daily` | (part.) | (part.) | test_fund_ic | ✗ | **COPY in** (fund NAV) |
| `public.de_etf_holdings` | 12.5k | 2.2 MB | decile_core, rollup_sectors, test_sector_via_etf, validate_lenses | ✗ | **COPY in** (cap buckets + sector weights) |
| `public.de_etf_master` | 443 | 160 kB | test_sector_via_etf | ✗ | **COPY in** |
| `public.de_index_constituents` | 2910 | 864 kB | validate_lenses | ✗ | **COPY in** |
| `public.de_trading_calendar` | 7305 | 656 kB | adapters.py | ✗ | **COPY in** |

## C. BROKEN / STALE references to FIX (code points at non-existent tables)
- `atlas.atlas_sector_lens_daily` — **MISSING**. Stale ref; the real table is `fs.sector_lens_daily`. Clean it.
- `foundation_staging.mv_instrument_latest` — **MISSING** (referenced, doesn't exist).
- `foundation_staging.mv_breadth_nifty500_daily` — **MISSING** (referenced, doesn't exist).

## D. Consolidation plan (additive, no drops)
1. **`public.de_*` MF/ETF/calendar/constituents (B3 "COPY in")** — small/medium (largest 74 MB);
   `CREATE TABLE fs.<name> (LIKE … INCLUDING ALL); INSERT … SELECT`. Cheap, safe. Then repoint code.
2. **`atlas.*` v4 outputs (B1)** — bring `atlas_thresholds`, `atlas_sector_master`, `atlas_signal_weights`,
   `atlas_signal_ic` into fs (tiny). Repoint `atlas.db.load_thresholds` + the loop scripts.
3. **`atlas.atlas_lens_scores_daily` (4.1 GB)** — the big decision. v4 produces it; old frontend reads it.
   Options: (a) make `fs.atlas_lens_scores_daily` the canonical and have the lens pipeline write there
   (old frontend keeps reading the atlas copy until cutover); (b) copy once now + dual-write until cutover.
   Needs FM call (it's the one heavy item).
4. **Repoint the already-copied de_* (B3 ✓ rows)** — change code from `public.de_*` to the `fs.*` equivalent;
   validate the fs copies are as fresh as de_* before flipping.
5. **Fix the 3 broken refs (C).**

After repoint + validation, v4 backend reads/writes ONLY `foundation_staging` (+ `atlas.db` config code).
Old Atlas keeps its `atlas.*` copies until v4 is live and it's retired (D23) — then drop legacy.
