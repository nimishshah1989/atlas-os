# Atlas v4 frontend — next-session handoff (stocks list · ETF pages · sector-RS backfill)

Paste the prompt below into a fresh `claude --dangerously-skip-permissions` session (run it in
the tmux `atlas-v4` build window, cwd `/home/ubuntu/atlas-os`).

---

Continue the **Atlas v4 frontend build** on branch `feat/v4-six-lens` (cwd `/home/ubuntu/atlas-os`).
A Next.js dev server is ALREADY running in tmux session `atlas-v4` window `dev` on
http://localhost:3000 with `NEXT_PUBLIC_LENS_V4=1` (log at `/tmp/atlas-v4-dev.log`). Do NOT start
another dev server — just `curl` it.

## READ FIRST
- `docs/v4/2026-06-23-stocks-pages-plan.md` (the stocks-page design + TV-first chart rule)
- `scripts/loops/DECISIONS.md` (D19–D27: deciles within cap cohort + leadership-breadth; on-read
  composite; everything in `foundation_staging`)
- `scripts/loops/frontend_inventory.md`, `scripts/loops/table_stocktake.md`
- `CLAUDE.md` — esp. **RULE #0**: every number traces to a REAL DB source; never ship a
  synthetic/placeholder/misleading value. Verify rendered numbers against the DB.

## WHAT'S DONE (behind LENS_V4, all native `foundation_staging`, demo-verified + committed)
- Page A Markets Today (`/`): regime + 4 breadth charts (2×2, incl golden-cross) + breadth/tier/macro tables
- Page B Sectors⊕Markets-RS (`/sectors`): SectorsPageV4 — pulse + leading/lagging → six-lens vector →
  sortable heatmap (no verdict cols) → breadth table → cap-tier RS charts → cross-market RS grid → RRG bottom
- Page C Sector deep-dive (`/sectors/[sector]`): SectorDeepDiveV4 — lens read + two 2×2s + within-breadth +
  fundamentals + fund-flow; verdict/open-signals/industry/methodology dropped
- **Stock DETAIL (`/stocks/[symbol]`): StockDetailV4** — lens decile card (sub-component + evidence
  drill-down) + always-on RS matrix + 2 Lightweight EMA charts (price + RS) + reused TV widgets + Weinstein.
  Data layer `frontend/src/lib/queries/v6/stock_lens.ts` (getStockDecile / getStockRSMatrix / getStockChartSeries).

## CONVENTIONS / GOTCHAS (critical — learned the hard way)
- **All v4 data reads `foundation_staging` only.** Mirror small atlas tables additively via
  `scripts/foundation/consolidate_tables.py` (idempotent; run from `scripts/foundation/`). Scripts use
  `scripts/foundation/_db.py` (`read_df`/`scalar`/`exec_sql`/`exec_script`, 20-min timeout).
- **Postgres NUMERIC comes back as STRINGS** — in frontend code coerce via `toNumber`/`toNumberOr` from
  `@/lib/v6/decimal` (NOT `Number()` — ESLint bans it). In python it's fine.
- **Supabase session pooler caps clients at 15.** The dev server holds ~14, so: (a) batch page fetches
  into ≤3–4-wide `Promise.all` groups (see SectorsPageV4 / StockDetailV4), and (b) do NOT run python DB
  scripts while demoing (they steal connections → EMAXCONNSESSION). Verify rendered numbers via the HTML,
  not a side query, while the server is up.
- **Pattern for every page:** branch `if (LENS_V4_ENABLED) return <XPageV4 .../>` at the top of the route,
  leave the flag-off path byte-identical. v4 layout lives in its own component file.
- **Deciles within cap cohort (D27):** cap from `de_index_constituents` membership (NIFTY 100 = large,
  MIDCAP 150 = mid, SMLCAP 250 = small, else micro); `ntile(10) OVER (PARTITION BY cap,(score IS NULL)
  ORDER BY score)` with the null partition trick (see `stock_lens.ts` / `sector_lens.ts`). Leadership =
  # of 4 conviction lenses (technical/fundamental/catalyst/flow) at decile 10; strength = avg conviction decile.
- **Design system:** `font-serif` headings, `font-sans`/`font-mono`, `text-ink-primary/secondary/tertiary`,
  `text-signal-pos/neg/warn`, `bg-paper`, `border-paper-rule`, sections `px-8 py-9/py-10 border-b border-paper-rule`.
  Copy look/feel from the sector components.

## TV-FIRST CHART RULE (verified) — symbols confirmed from TradingView's production bundles
Embed **direct TradingView widgets** (zero data/code) wherever a TV symbol exists; hand-build only our
analytics. Existing direct-TV components: `frontend/src/components/v6/stock-detail/TVWidgets.tsx` +
`StockChartPanel.tsx`. Our-data charts use `frontend/src/components/charts/AtlasLightweightChart.tsx`
(pass `overlays:['ema20','ema50','ema200']` and it auto-draws the EMAs).
- Confirmed symbols: `NSE:NIFTY` (N50), `NSE:CNX500` (N500), `NSE:NIFTYMIDCAP150`, `NSE:NIFTYSMLCAP250`
  (SML), `NSE:NIFTY_MICROCAP250` (underscore), `NSE:NIFTYJR` (Next 50), sector e.g. `NSE:CNXIT`, stocks `NSE:<SYM>`.
- **Ratio symbols** work in the Advanced Chart widget: `NSE:TCS/NSE:NIFTY`, `NSE:NIFTYMIDCAP150/NSE:CNX500`,
  `NSE:CNXIT/NSE:NIFTY` — smoke-test one live render. The **one gap:** the free iframe can't preset EMA
  20/50/200 (one global length only) → keep our Lightweight charts for any "price/RS + 20/50/200 EMA" chart.

## TASKS (in order)

### 1. BACKEND: sector-RS backfill (do FIRST — "RS vs sector" is empty everywhere)
`foundation_staging.technical_daily.rs_{1m,3m,6m,12m}_sector` is NULL for all rows. Compute it like the
existing `rs_*_n500` (which = stock trailing return − index trailing return), but vs the stock's SECTOR
index: `instrument_master.sector` → `atlas_sector_master.primary_nse_index` → `index_prices`. So
`rs_3m_sector = ret_3m(stock) − ret_3m(sector_index)` etc. (ret_* already in technical_daily).
- Build it in `scripts/foundation/` with the load-once+vectorize pattern (COPY + pandas/numpy; NOT a slow
  per-row UPDATE — an in-place UPDATE on technical_daily (6.35M rows) hung before). Cheapest correct option:
  precompute per-(sector_index, date) trailing returns, then write rs_*_sector. **Latest date is enough for
  the RS matrix** if a full-history rebuild is too heavy — but full history lets the sector-RS chart work.
- Verify: a few stocks' rs_3m_sector = their ret_3m − sector index ret_3m. Then the StockDetailV4 RS-matrix
  "Sector" row + sector chips light up automatically (no frontend change needed).

### 2. Stocks LIST page (`/stocks`) — StocksPageV4 behind LENS_V4
Per `docs/v4/2026-06-23-stocks-pages-plan.md` section B. Strip the conviction cruft (HeroStories,
ConvictionLandscape bubble, 24-cell matrix, composite trajectories, six-picks, firing/conf hero tiles).
Build: (1) lean **leadership strip** + a few "top doing great" cards; (2) ONE strong **2×2 bubble** —
x=Strength, y=Leadership, size=liquidity, color=leadership, deciles within cohort, respects the filter bar,
dot→detail (custom Recharts scatter, like SectorStock2x2); (3) **filter + smart-screen bar** (Cap · Sector ·
Lens focus · Min leadership · Liquidity; pre-made screens: Multi-factor leaders ≥3 / Cheap & strong / Rising
accumulation / Fresh catalyst / Momentum breakouts / Quality compounders; sort by any); (4) **decile table** —
Symbol · Cap · Sector · 5 lens deciles · Strength · Leadership · **compact RS (1M/3M/6M vs N500 + sector chip)**
· liquidity, row→detail. Data: add `getStocksDecileList(filters)` to `stock_lens.ts` (the same ntile CTE,
unfiltered, + compact RS from technical_daily + liquidity — mirror `mv_stock_landscape.liquidity_proxy_cr`
via consolidate_tables, or compute 20d turnover from `ohlcv_stock`).

### 3. Retrofit RS-ratio charts → direct TV ratio widgets
Replace our Lightweight RS charts with TV Advanced-Chart ratio widgets where the symbol is confirmed:
`CapTierRSCharts` (sectors page) and `SectorRSRatioCharts` (sector deep-dive). Keep ours only if a live
smoke-test of the ratio symbol fails. (Breadth/2×2/RRG/decile/regime-overlay stay ours.)

### 4. ETF pages — same philosophy as stocks (detail = parent, then list)
ETF detail + list behind LENS_V4. ETF = holdings-weighted roll-up of the stock lenses (look-through via
`de_etf_holdings.instrument_id` → the journal), + **leadership-breadth** (% of holdings that are multi-factor
leaders) + tracking quality + the same RS-everywhere standard + TV-first charts (the ETF's own `NSE:<TICKER>`
price+widgets; RS vs benchmark via ratio symbol). Strip the old conviction/scorecard cruft. Reuse the stock
detail patterns. (Funds come after, similarly — holdings-weighted leadership-breadth + active-movement.)

## WORKFLOW (per task)
Build (delegate well-scoped UI to a sub-agent with the templates above as reference; you own data layer +
integration). Then the review cycle: **demo** (`curl` + Playwright fullPage screenshot from `frontend/` via
`require('playwright')`, viewport 1440, waitForTimeout ~7000; Read the PNG) + **DB spot-check** (RULE #0) →
**`/code-review`** the diff → fix → **`/verify`** → **`/simplify`** → commit + push
(`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`). Note: TV widgets render blank under headless
Playwright (TV blocks headless) — that's expected; they work in a real browser.
