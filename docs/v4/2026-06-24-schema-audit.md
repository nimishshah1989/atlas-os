# v4 schema audit — what reads `foundation_staging` only (for legacy retirement)

Date: 2026-06-24. Goal: confirm every v4 (LENS_V4) surface reads ONLY
`foundation_staging`, so `atlas.*` and `public.de_*` can be retired.

## ✅ FS-ONLY — the 8 dedicated v4 pages (instrument + roll-up surfaces)

All branch early via `if (LENS_V4_ENABLED) return <…V4 …/>`; their components read
`foundation_staging` exclusively:

| Page | Component | Query layer (all `foundation_staging`) |
|---|---|---|
| `/stocks` | StocksPageV4 | `stock_lens.ts` |
| `/stocks/[symbol]` | StockDetailV4 | `stock_lens.ts` (header/decile/RS/evidence/financials/announcements) |
| `/sectors` | SectorsPageV4 | `v6/sectors` (`mv_sector_*`), `sector_index_rs`, `sector_lens`, `lens-scores`, `rs_charts`, `markets_rs` |
| `/sectors/[sector]` | SectorDeepDiveV4 | `v6/sectors`, `sector_index_rs`, `sector_lens` |
| `/etfs` | ETFsPageV4 | `etf_lens.ts` |
| `/etfs/[ticker]` | ETFDetailV4 | `etf_lens.ts` |
| `/funds` | FundsPageV4 | `fund_lens.ts` |
| `/funds/[mstar_id]` | FundDetailV4 | `fund_lens.ts` |

Notes:
- `StockDetailV4` was the last gap — it reused the legacy `getStockBySymbol` /
  `getStockState` / `getStockMetricHistory` (atlas `atlas_stock_metrics_daily` /
  `atlas_stock_state_daily` / `atlas_universe_stocks` / `atlas_market_regime_daily`).
  Repointed: header → new `getStockHeader` (fs `instrument_master`); the **Weinstein
  lifecycle panel was dropped** — its only inputs were those legacy atlas metrics, and
  the Technical lens now shows the real trend numbers (price vs EMAs, 52w, RSI) the
  panel's stage label summarised.
- The `foundation_staging.atlas_*` / `foundation_staging.mv_*` tables (mirrored by
  `scripts/foundation/consolidate_tables.py`) ARE in `foundation_staging` — fs-only ✓.
  Only a bare `FROM atlas.…` / `FROM public.…` is a legacy read.

## ⚠ REMAINING — the home "Markets Today" / regime page (hybrid, not a clean v4 swap)

`/` (`app/page.tsx`) is a HYBRID: `LENS_V4` adds native breadth/tier/macro sections but
KEEPS the legacy regime dashboard (RegimeVerdict, SignalScorecard, IndicatorCharts,
RegimeJourney). Those still read `atlas.*` (regime/scorecard/indicator queries). The
regime state itself is already mirrored to `foundation_staging.atlas_market_regime_daily`
+ `atlas_macro_daily`, so repointing is mechanical but spans several queries
(`queries/regime.ts` is already fs; the scorecard/indicator/journey queries are not).
`/markets-rs` and `/india-pulse` (legacy, not in the primary v4 nav) similarly read MVs.

**Retirement punch-list:** repoint the home regime dashboard's scorecard/indicator/journey
queries to `foundation_staging.atlas_market_regime_daily` (+ the breadth MVs) before
dropping `atlas.*`. The 8 instrument/roll-up pages are already safe to cut over.
