# LOOP B — ROLL-UP FRAMEWORK (sector → ETF/index → fund) — design to lock with FM

Supersedes the compute steps in `loopB_etf_sector.md` with the newer decisions
(D15 free-float + IC-per-altitude + 2×2; D18 MF; D19 on-read). **Build the COMPUTE
only after the stock atom is FINAL (delivery-% + sector-RS in, atom locked).** Design +
data/schema audit can proceed now (this doc). Discuss the open decisions with the FM
BEFORE building the compute (D15).

## Principle — one fractal vector, computed ON-READ

The six-lens vector is the same at every altitude. A higher altitude's vector is the
**weight-weighted average of its constituents' lens SUB-scores**, then the composite is the
**same on-read function** (sub-scores × live `atlas_thresholds` weights). So — like the stock
composite (D19) — roll-ups are **NOT materialised**; they are derived at query time from the
atom's stored sub-scores. A weight edit or an atom rebuild flows up for free, nothing to recompute.
(Only the per-altitude IC weights are persisted, because they are learned, not derived.)

## The four altitudes (verified data 2026-06-22)

| Altitude | Members | Weight | Benchmark | IC target (forward return of…) |
|---|---|---|---|---|
| **Sector** | stocks where `instrument_master.sector = S` | **free-float cap** (the one gap — see Decision 1) | `atlas_sector_master.primary_nse_index` | the sector NSE index (`index_prices`) |
| **ETF** | `de_etf_holdings` (ticker→holdings) | disclosed `weight` ✓ | the ETF's tracked index | ETF price series (see Decision 2) |
| **Index** | `de_index_constituents` (time-versioned) | disclosed `weight_pct` ✓ | the index itself | the index (`index_prices`) |
| **Fund** | `de_mf_holdings` look-through (`instrument_id`, append-only by `as_of_date`) | disclosed `weight_pct` ✓ | `de_mf_master.primary_benchmark` (Category Benchmark) | fund NAV (`de_mf_nav_daily`) |

**Weighting rule (resolves the tv_metrics.market_cap concern):** ETF/index/fund carry their OWN
disclosed weights → use them directly. Free-float cap weighting (`market_cap × (1−promoter%)`, D15)
is needed ONLY for the **sector** fold-up, where members have no given weights. Equal-weight stays a
secondary "breadth view" toggle at every altitude.

## Per-altitude extras

- **Sector** also gets **breadth** (% of members strong per lens), **dispersion** (spread), and
  **rotation** (sector momentum vs market) → the **2×2** (momentum × IC-conviction, D15). Stored in a
  new `atlas.atlas_sector_lens_daily` (the ONE materialised roll-up — sectors are few + the breadth/
  dispersion stats aren't a pure weighted-avg of sub-scores, so they're computed + stored per date).
- **ETF/index**: holdings/constituent-weighted vector + active tilt vs the tracked index (already in
  `composite.rollup_holdings`/`rollup_index`). On-read.
- **Fund (D18)** — the differentiated altitude:
  - **Universe**: Regular plan · Equity category · **Growth** option (Decision 3 — confirm the
    `de_mf_master` encoding: `purchase_mode`, `category_name`/`broad_category`, Growth-vs-IDCW field).
  - **Recommend-not-advise** (distributor posture) — ranking + transparency, never personalised advice.
  - **Ranked WITHIN its SEBI `category_name`** vs the **Category Benchmark** (`primary_benchmark`).
  - **FULL sub-component transparency** on the fund page — roll up EVERY sub-component (not just the
    composite), so a user sees why a fund scores where it does, lens by lens, down to sub-scores.
  - **Edge = holdings look-through + active-movement**: the MoM **holdings delta** (this `as_of_date`
    vs prior, from the append-only `de_mf_holdings`) shows whether the manager is *actively* tilting
    toward improving-atom names — the genuine differentiator (D7/D18). Pair with NAV returns.
  - **Fund IC calibrated PER category** (a small-cap fund's predictive lenses differ from a large-cap's).

## What EXISTS vs gaps

- EXISTS: all holdings/constituent/NAV/master tables above; sector map (22 actionable, D13); the
  roll-up math (`composite.rollup_sector/rollup_holdings/rollup_index`); the atom (locked once Loop C +
  delivery land).
- GAPS / decisions: (1) free-float market-cap source for SECTOR weighting; (2) ETF price series for
  ETF IC; (3) MF universe-filter encoding; (4) whether to wait for the FM's Morningstar APIs or build
  on the existing `de_mf_*` (which already look substantial: 1,359 funds, 243K holdings, daily NAV).

## Build sequence (after atom is FINAL)

1. Sector fold-up (free-float-weighted 6-lens + breadth + dispersion + rotation + sector IC + 2×2).
2. ETF + index roll-up (disclosed-weight; on-read; their IC).
3. Fund roll-up (look-through + active-movement + per-category rank + fund IC + full sub-component page).
4. Frontend (only once the whole backend is A) — behind `NEXT_PUBLIC_LENS_V4`.

Each altitude: real-data tests (a known basket → known weighted result), gate (`validate_lenses
--check B` + a new per-altitude assertion), commit, before the next.

## FM decisions

1. **RESOLVED (D21a) — sector weighting = proxy from the matching NSE sector-index constituent weights**
   (`de_index_constituents`) where a sector index exists; equal-weight + breadth elsewhere. No
   unreliable market-cap; ships now.
2. **OPEN — ETF IC** — need an ETF price/NAV series for ETF forward returns. Confirm source (ohlcv for
   listed ETFs, or a `de_etf_nav`?). Without it, ETF inherits its tracked-index IC as a proxy.
3. **RESOLVED (D21b) — build MF on the existing `de_mf_*` now**; fold in Morningstar later if it adds
   depth. Still to verify in build: the Regular/Equity/Growth filter encoding in `de_mf_master`
   (`purchase_mode`, `category_name`/`broad_category`, Growth-vs-IDCW field).
