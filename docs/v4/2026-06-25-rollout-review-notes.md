# Atlas v4 frontend rollout — review notes (2026-06-25)

Design language LOCKED + FM-approved (see memory `v4-design-language-locked`). This
session rolled the locked language across every instrument/roll-up surface, fixed the
frontend-fixable §6 data bugs, and documented the data-layer ones below.

## Shipped (committed + pushed on `feat/v4-six-lens`)
| Surface | Notes |
|---|---|
| Design system | Two themes (Daylight Desk light default / Graphite Terminal dark) + nav toggle; locked RAG (theme-scoped ramp + signals); Inter numerals; `DecileLadder` + `Panel`/`StatCard`/`DecileMeter`/`InfoTip`; `useThemeTokens` (live-recolour charts); flat 7-page nav |
| Market Pulse `/` | Native-fs only (drops Weinstein verdict/scorecard/worklist); StatCards, sector leadership, breadth/cap-tier/macro panels, spotlight DecileLadder, **breadth-history charts (§3.e, integer counts)** |
| Stocks `/stocks` (+ detail) | List: StatCards, RAG-ramp decile table, theme-aware 2×2. Detail: **DecileLadder** (real numbers; §1.1 sub-bars dropped), price/VWAP StatCards, theme-aware EMA/RS charts, re-skinned financials/announcements/RS-matrix |
| Sector View `/sectors` (+ deep-dive) | Full re-skin; **removed** Cross-market RS + RS-vs-baseline tables; **heatmap RS columns no longer double-×100**; cap-tier RS labelled; 2×2 bubble = cap tier + colour by leadership + click→stock; all sector Recharts theme-aware |
| ETF `/etfs` (+ detail) | StatCards, RAG lens bars + look-through deciles, theme-aware charts (DecileLadder N/A — ETF lens is a 0–100 holdings-weighted vector, not a per-lens decile) |
| Funds `/funds` (+ detail) | StatCards, RAG lens bars, **active-movement (MoM holdings Δ)** with RAG adds/exits, look-through deciles |

## Static review
- **tsc**: 0 type errors in any v4 source file (15 repo errors are all pre-existing `__tests__`).
- **eslint**: clean on every file touched in this rollout. 4 pre-existing errors remain in
  files NOT rendered by v4 (legacy `*TraderViewHeader`, unused `FundamentalsStrip`,
  unrendered `PremiumDiscountScatter`) — not regressions, left as-is.
- **Flag-off byte-identical**: preserved by construction — new token NAMES, env-gated nav/body,
  early `LENS_V4` branches, dispatcher `TopNav`. Legacy components untouched.

## §6 data bugs — frontend-FIXED
- Sector multi-window heatmap **RS columns** were ×100 twice (returns are decimal → correct ×100,
  but RS is already pp). Split the formatter → RS renders `pp`, returns render `%`.
- Cap-tier RS "123.70" was correct (rebased-to-100) but unlabeled → added explicit caption
  ("123.7 = +23.7% vs Nifty 500 since window start").

## §6 data bugs — DATA-LAYER (need backend/MV work, NOT frontend)
1. **Sector EMA20/EMA200 participation blank** — `mv_sector_breadth.pct_above_ema20/200` appears
   null for sectors; the cells render `—`. Verify the MV populates these.
2. **RRG no rotation** — `mv_sector_rrg.trail_6w` (JSONB) is empty/null, so no trail polylines.
   The render is correct + theme-aware; the MV must compute/store the 6-week trail.
3. **Sector taxonomy 29 → 21** — sectors come from `atlas_sector_master` (is_active, excludes
   conglomerate). There is NO folding of MNC/Rural/Diversified into real sectors (D13). True
   folding re-attributes constituents → must happen in the MV/master, not the frontend.
4. **Heatmap 12m return (e.g. Defence ~113%)** — `mv_sector_cards.ret_12m` is decimal; if a value
   is genuinely wrong, verify the MV's 12m return computation (units / lookback).

## Deferred §3 Market Pulse items (need query work, not yet built)
- Breadth table extra periods (−3m/−6m/−1y) — `getBreadthTable` returns today/Δ1w/Δ1m only.
- Sectors **improving vs deteriorating** — needs a MoM sector-strength delta (current panel shows
  leading/lagging by current avg conviction).
- Nifty regime chart with 21/50/200-EMA overlays — needs a Nifty 500 index price series wired in.
- Card → filtered stock list — needs an "above-EMA" boolean on the `getStocksDecileList` row.

## Other
- §1.1 resolved: dropped the non-reconciling 0–100 sub-component bars from the DecileLadder; the
  real numbers + decile carry the breakdown.
- Portfolio Manager: **cut** for now per FM.
- Admin: re-skin in progress.
