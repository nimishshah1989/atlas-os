# Atlas v4 — Stocks pages (detail + list) · TV-first charts · RS-everywhere

## Context
v4 replaces the live Atlas surfaces page-by-page behind `NEXT_PUBLIC_LENS_V4`, reading only from
`foundation_staging`. Markets-Today, Sectors⊕Markets-RS, and the Sector deep-dive are shipped. Next:
the **Stocks** surfaces. The current `/stocks` is conviction-heavy (BUY/WATCH/AVOID *firing*, HeroStories,
ConvictionLandscape bubble + 24-cell tier×tenure matrix, composite trajectories, six-picks) — all stripped.

## Locked decisions (from the brainstorm)
1. **Detail = the atom / parent.** The stock detail page is the canonical object; the list page is a funnel
   into it. Everything links: sector constituent → detail, 2×2 dot → detail, table row → detail, (later)
   fund/ETF holding → detail; detail links back to its sector + peers.
2. **TV-first chart rule (Atlas-wide):** if a TradingView **symbol** exists, embed the **direct TV widget**
   (their data, their servers, zero data/zero code). Hand-build only what TV can't make (our analytics).
3. **RS is a first-class citizen everywhere** — vs Nifty 50, Nifty 500, and Sector, across timeframes.

## TV-first chart rule — the split + retrofit
**Direct TV widgets** (zero data/code): stock **price + EMA 20/50/200**; stock **RS-vs-baseline** via ratio
symbol (`NSE:TCS/NSE:NIFTY`) + EMA studies; **Technical rating / Financials / News / Profile** (already TV).
Candidates to **retrofit** from our Lightweight charts → direct TV **iff the TV symbol exists**: sector
index RS-ratio (D/W/M, `NSE:CNXIT/NSE:NIFTY`), cap-tier RS (index ratios).
**Stay ours** (TV can't): breadth count charts, 2×2 scatters, RRG, sector lens heatmap, decile tables,
leadership distributions, the regime overlay (Nifty 500 + our regime shading).
**Gate:** verify TV's exact NSE symbols first (esp. Nifty Midcap 150 / Smallcap 250 / Microcap 250 / Next 50
and ratio support). Replace only what renders cleanly; keep ours otherwise. Caveats accepted by FM:
TV widgets are external iframes (heavier runtime, TV branding, off-brand styling, no rebasing/overlay of our
scores) — fine for instrument charts; weigh per-case for the index RS charts.

## RS-everywhere standard
Data already in `foundation_staging.technical_daily`: `rs_{1d,1w,1m,3m,6m,12m}_n50`, `..._n500`,
`rs_{1m,3m,6m,12m}_sector`.
- **Every instrument table** (list decile table, sector constituents, later ETF/fund holdings): a compact RS
  read — **RS vs Nifty 500 at 1M/3M/6M + a vs-Sector chip**, color-coded.
- **Stock detail**: the **full RS matrix, always visible** — rows {Nifty 50, Nifty 500, Sector} × cols
  {1D,1W,1M,3M,6M,12M}, color-scaled.

## A. Stock DETAIL page (`/stocks/[symbol]`) — BUILD FIRST (the parent/atom)
Behind `LENS_V4`; new `StockDetailV4`. Layout:
1. **Header** — symbol · name · cap cohort · sector (back-link) · **Strength + Leadership badge**
   (co-primary headline). Drop the trader-view verdict header.
2. **Lens decile card (centerpiece)** — the 6 lenses as **deciles within cap cohort** (Tech/Fund/Cat/Flow +
   Valuation as its own), each row = decile + raw + bar; **each expands to sub-components + the actual
   evidence** (the buyback/block driving Catalyst, rising delivery driving Flow, PE-vs-sector driving
   Valuation — from the journal `evidence` JSONB + the sub-score columns).
3. **RS matrix** (always-on panel) — {N50,N500,Sector}×{1D..12M}.
4. **Charts (TV-first):** (a) **price + EMA 20/50/200** TV Advanced Chart; (b) **RS-vs-baseline + EMAs** TV
   ratio symbol (fallback: our ratio via Lightweight w/ EMA overlays) — baseline toggle N50/N500/Sector.
5. **Keep:** TV Technical / Financials / News / Profile; **Weinstein lifecycle**; peer/sector context.
6. **Strip:** verdict header, conviction-decomposition, 24-cell/confidence, redundant sparkline grids.

## B. Stock LIST page (`/stocks`) — simple, 4 parts
Behind `LENS_V4`; new `StocksPageV4`.
1. **Leadership strip** — "N multi-factor leaders today · X large/Y mid/Z small" + a few **"top doing
   great"** cards (lead 3–4) → detail.
2. **ONE strong 2×2 bubble** — dots = stocks, deciles within cohort; **x = Strength, y = Leadership** (or a
   toggle to Momentum×Quality — FM to pick); size = liquidity, color = leadership; respects the filter bar;
   dot → detail.
3. **Filter + smart-screen bar** — filters: Cap tier · Sector · Lens focus · Min leadership · Liquidity.
   Pre-made screens: Multi-factor leaders (≥3) · Cheap & strong · Rising accumulation · Fresh catalyst ·
   Momentum breakouts · Quality compounders. Sort: Strength · Leadership · any lens decile · RS · return · liq.
4. **Decile table** — Symbol · Cap · Sector · 5 lens deciles · Strength · Leadership · **RS (1M/3M/6M vs
   N500 + sector chip)** · liquidity. Sortable; row → detail.
**Strip:** HeroStories, ConvictionLandscape bubble, 24-cell matrix, composite trajectories, six-picks,
firing/conf hero tiles, old screener.

## Data layer (native `foundation_staging`) — new `lib/queries/v6/stock_lens.ts`
- `getStockDecile(symbol)` — the stock's per-lens deciles within cohort + leadership + strength + raw lens
  scores + sub-components + `evidence` (reuse the SQL ntile-within-cap pattern from `sector_lens.ts`).
- `getStockRSMatrix(symbol)` — the RS matrix from `technical_daily`.
- `getStocksDecileList(filters)` — the universe with deciles + leadership + strength + compact RS +
  liquidity (from `mv_stock_landscape.liquidity_proxy_cr` or computed), for the 2×2 + table.
- Reuse `getStockBySymbol`, Weinstein/lifecycle, peer queries (repoint to fs where needed).

## Build sequence + sub-agent breakdown
1. **Verify TV NSE symbols** (sub-agent research) — gates the chart approach.
2. **Detail page** (parent) first: data layer → `StockDetailV4` + lens-decile-card + RS matrix + TV charts.
3. **List page**: data layer → 2×2 + filter/smart-screens + decile table + leadership strip.
4. **Retrofit** sector/markets RS-ratio charts → direct TV where symbols verified.
Sub-agents (Agent tool) for well-isolated presentational components (carry design-system + data-shape +
gotchas: pool-batching, coerce postgres NUMERIC strings, LENS_V4 branch). I own the data layer, integration,
and the demo-verify loop.

## Skills + review cycle
Build in the TDD/grill spirit (assert vs real DB rows; terms vs CONTEXT.md). Per page: build → demo
(`curl` + Playwright screenshot + RULE#0 DB spot-check) → **`/code-review`** the diff → **`/verify`** →
**`/simplify`** → commit on `feat/v4-six-lens`.

## Verification (definition of done, per page)
HTTP 200, no error boundary; Playwright screenshot shows every panel with real data; RS numbers match
`technical_daily`; deciles match the within-cohort SQL; TV widgets render for the test symbols (fallback
where not); flag-off path unchanged; `/code-review` + `/verify` clean.
