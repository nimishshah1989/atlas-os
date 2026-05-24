# Frontend Feedback Pass — 2026-05-21 Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. This plan
> covers a UI/UX feedback batch, so tasks are change-then-verify rather than strict
> TDD blocks; items flagged **DIAGNOSE** need a data/runtime check before the fix.

**Goal:** Address a 21-item review-feedback batch across the Today, Regime/Daily Brief,
Stocks, and Stock Detail surfaces of the Atlas frontend.

**Architecture:** Next.js 15 App Router, all pages `force-dynamic`, server components
query Supabase Postgres directly via `frontend/src/lib/queries/*`. Charts use Recharts.

**Tech Stack:** Next.js 15, React 19, TypeScript, Recharts, Tailwind, postgres.js.

---

## Blocker (RESOLVED 2026-05-21)

Sector page blank + Stocks universe all-zeros. Root cause: 8-day-old `next dev`
process with corrupted `node_modules` — survived in memory, could not recompile
routes. Fix: `rm -rf node_modules && npm ci`, kill stale server, `rm -rf .next`,
restart. Verified: `/sectors` 200 with data, `/stocks` shows 7 / 62 / 313.
DB and query layer were never at fault — data is fresh through 2026-05-20.

---

## Phase 1 — Stocks page quick wins (crisp, low-risk)

### Task 1.1: Intraday bar-time timezone label
**Files:** `frontend/src/components/stocks/IntradayRSLeaders.tsx:102-112`,
`frontend/src/components/regime/IntradayNiftyStrip.tsx:21-25`

- [ ] DIAGNOSE: log a raw `bar_time` ISO string from `/api/intraday?endpoint=rs-leaders`.
      Determine if the API returns UTC or already-IST. The displayed "7:50 IST" at
      10:45 IST wall-clock means either the value is UTC of a stale bar or the
      offset is wrong.
- [ ] Fix `formatBarTime` / `formatAsOfTime` so the label matches the value:
      if source is UTC, add 330 min and label "IST"; if already IST, label without
      re-offsetting. Prefer `toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })`
      over manual minute math (consistent with `daily-brief/page.tsx:fmtTimestampIST`).
- [ ] Verify: render the panel during market hours, confirm displayed time == IST wall clock.

### Task 1.2: Live Leaders Intraday → collapsible, hidden by default
**Files:** `frontend/src/components/stocks/StocksClientShell.tsx:72`,
`frontend/src/components/stocks/IntradayRSLeaders.tsx`

- [ ] Wrap `<IntradayRSLeaders />` in a collapsible `<details>`/disclosure with a
      "Live RS Leaders (intraday)" summary button, collapsed by default.
- [ ] Only start the 30s `setInterval` poll when expanded (lift `fetchLeaders` to fire
      on first expand) — avoid background polling while hidden.
- [ ] Verify: panel hidden on load; clicking the toggle reveals it and begins polling.

### Task 1.3: Cap vs Index filter — dedupe, add Top-N filter
**Files:** `frontend/src/components/stocks/StockBubbleChart.tsx:9-10,76-91,352-379`

- [ ] Remove the `DisplayFilter` (Index: n100/n500/all) control — it overlaps Cap.
- [ ] Replace with a `UniverseFilter` = `top100 | top200 | top300 | top500` driven by
      `cap_rank` (`x.cap_rank <= 100` etc.). Keep the Cap (large/mid/small) filter.
- [ ] DIAGNOSE: confirm `cap_rank` is present on the bubble dataset; if not, add it to
      `getAllStocks` select (`u.cap_rank`) and the row type.
- [ ] Verify: four Top-N buttons filter the bubble population correctly.

### Task 1.4: "RS vs Nifty 66.06x" relabel
**Files:** `frontend/src/components/stocks/StockScreener.tsx`, `StockBubbleChart.tsx`

- [ ] DIAGNOSE: find which field renders as "RS vs Nifty …x". Likely `rs_3m_nifty500`
      or a ratio. A 66x multiplier is not a meaningful RS ratio — confirm the field
      and its true unit.
- [ ] Relabel to its real meaning: if it is a relative-strength *percentile*, show
      "RS Pctile (3M)" 0–100; if a relative return, show "RS vs Nifty (3M) +X.X%".
      Remove the "x" suffix. Add a tooltip with the definition.
- [ ] Verify: column header + cell values read sensibly.

### Task 1.5: EMA-20 column clarity
**Files:** `frontend/src/components/stocks/StockScreener.tsx:302` ("EMA20 %")

- [ ] DIAGNOSE: the page shows EMA-20 as a rupee value and an "EMA −20" — confirm
      whether `ema_20_ratio` (a ratio, e.g. 1.03 = 3% above EMA-20) is being shown
      raw vs. as a price.
- [ ] Render `ema_20_ratio` as "vs EMA-20" = `((ratio-1)*100).toFixed(1)%` with
      green/red sign. Drop any rupee-denominated EMA display unless explicitly a price.
- [ ] Verify: column reads as a signed % distance from the 20-EMA.

### Task 1.6: Bubble + state colors consistency
**Files:** `frontend/src/components/stocks/StockBubbleChart.tsx:51-59,128`,
`frontend/src/lib/chart-colors.ts`

- [ ] Replace local `navStateColor` with the shared `rsStateColor` from `chart-colors.ts`
      (adds the missing `Average` case; single source of truth).
- [ ] Verify state-badge colors elsewhere (StockScreener) also use `rsStateColor`.
- [ ] Verify: bubbles colour by `rs_state` (Leader dark-green, Strong teal, Average
      grey, Weak/Laggard red, etc.); no all-grey when data is present.

### Task 1.7: Column tooltips / explanations
**Files:** `frontend/src/components/stocks/StockScreener.tsx:257-314`

- [ ] Add `title`/tooltip to every column header lacking one — especially "Effort"
      (`effort_ratio_63`), "Stage" (`cts_stage`), "RS Pctile", gate dots.
- [ ] Source the definitions from `atlas/compute` docstrings / methodology.
- [ ] Verify: hovering each header shows a one-line definition.

---

## Phase 2 — Today page metric cards + breadth charts

### Task 2.1: Make Trend/Breadth/Momentum/Participation cards richer + clickable
**Files:** `frontend/src/components/regime/{Trend,Breadth,Momentum,Participation}Section.tsx`,
the shared `SectionHeader` component.

- [ ] Make each card header expandable (disclosure). Expanded view shows: the formula
      / derivation of each sub-metric, and a short interpretive commentary line
      ("50-EMA slope +0.4σ → trend strengthening").
- [ ] Use the empty card space to surface existing-but-unshown derivatives
      (e.g. EMA-20 breadth `pct_above_ema_20`, McClellan summation, A/D line slope).
- [ ] Verify: cards no longer look empty; clicking expands formula + commentary.

### Task 2.2: 52-week highs/lows + high-low ratio + cumulative line accuracy
**Files:** `frontend/src/components/regime/HighsLowsChart.tsx`,
`frontend/src/components/regime/IndicatorChart.tsx`, `atlas/compute/breadth.py`

- [ ] DIAGNOSE: compare `new_52w_highs`, `new_52w_lows`, `new_high_low_ratio`,
      `net_new_highs` in `atlas_market_regime_daily` against a hand recomputation
      from `de_equity_ohlcv` for 2–3 recent dates. The user reports these look
      inaccurate — confirm whether the bug is in `compute_new_highs_lows` (window,
      adjusted vs raw close, universe filter) or in the chart rendering.
- [ ] Fix root cause (compute or chart) once identified. Likely candidates:
      252-day window on too-short history; raw vs `close_adj`; cumulative series
      reset.
- [ ] Verify: spot-checked dates match recomputation.

### Task 2.3: Breakouts summary — add ETFs/funds/sectors
**Files:** locate the "~11 stocks" breakouts component first (NOT
`mv_breakout_candidates`, which is LIMIT 5). Check `intelligence/page.tsx` and any
`stocks` breakout panel.

- [ ] DIAGNOSE: identify the exact component the user sees with 11 breakout stocks.
- [ ] Extend it to also list ETF, fund, and sector breakouts for a combined summary view.
- [ ] Verify: breakouts panel shows all four asset classes.

---

## Phase 3 — Regime / Daily Brief

### Task 3.1: Daily Brief — relocate + rethink content
**Files:** `frontend/src/app/page.tsx` (Regime), `frontend/src/components/nav/TopNav.tsx`,
`frontend/src/app/intelligence/daily-brief/page.tsx`, `frontend/src/lib/queries/briefs.ts`

- [ ] DIAGNOSE: find the "Daily Brief" element on the Regime page the user clicks
      and where it currently routes (reportedly `/admin/...`). Fix the link target so
      it lands on the proper Daily Brief view, not an admin page.
- [ ] Content rethink: define a more useful brief — e.g. regime delta vs yesterday,
      top 3 actionable sector rotations, new breakouts/breakdowns, watch-list moves,
      not just LLM narrative. (Brainstorm with user before building.)
- [ ] Verify: clicking Daily Brief on Regime page opens the intended view.

---

## Phase 4 — Stock detail page

### Task 4.1: "Peers in Stage 1" table — move, expand, fix peer logic
**Files:** `frontend/src/components/stocks/WithinStatePeers.tsx`,
`frontend/src/lib/queries/states.ts:133-154`, `frontend/src/app/stocks/[symbol]/page.tsx:109-116`

- [ ] Move the peers table from top to bottom of the detail page.
- [ ] Make it collapsible (collapsed by default) and expandable.
- [ ] Reconsider peer selection: currently same-Weinstein-state on same date — the
      user expects industry/sector peers. Add an industry filter (peers = same
      `sector`/industry AND comparable state) or clearly relabel as "Others in same
      stage". Decide with user.
- [ ] Add columns: RS pctile, return 1M/3M, conviction, stage, dwell — beyond the
      current bare `RS rank / Dwell / Within-rank`.
- [ ] Verify: table at bottom, collapsible, richer columns, peers make sense.

### Task 4.2: OBV trend chart scaling
**Files:** `frontend/src/components/stocks/OBVContinuousChart.tsx:100-105`

- [ ] Set the `<YAxis>` `domain` to `['dataMin', 'dataMax']` (or padded) so the OBV
      line uses the full chart height instead of rendering near-horizontal.
- [ ] Format y-axis ticks in lakh/crore so the 0→900-lakh range is legible.
- [ ] Verify: OBV trend has visible slope and readable axis.

### Task 4.3: Volume/ATR contraction clarity
**Files:** `frontend/src/components/stocks/ATRContractionGauge.tsx`, plus the
OBV "+19.3L/day accumulating" copy.

- [ ] Clarify the labels: explain that ATR ratio < 1.0 = volatility contracting
      (base-forming) with a tooltip; restate the OBV volume delta in plain terms.
- [ ] Verify: a fund manager can read the gauge without guessing.

### Task 4.4: Drawdown from 252-day peak — chart + table
**Files:** `frontend/src/components/stocks/StockDeepDiveBody.tsx:211-214,394-409`,
`frontend/src/lib/queries/stocks.ts:getStockMetricHistory`

- [ ] DIAGNOSE: the user reports the drawdown chart looks incomplete and "table
      numbers not populated". Confirm whether `drawdown_ratio_252` /
      `max_drawdown_252` are NULL/sparse for recent dates, and whether a drawdown
      table exists (exploration found only the chart).
- [ ] Fix sparse data at source if NULL; if a table is expected, add one
      (current DD, max DD 252d, days since peak, recovery %).
- [ ] Verify: chart spans the full range; table cells populated.

### Task 4.5: Detail page "what should the FM conclude" summary
**Files:** `frontend/src/app/stocks/[symbol]/page.tsx` header / `MasterStateCard`.

- [ ] Add a top-of-page verdict line: state + conviction + the one action it implies
      (accumulate / hold / avoid / exit), so the page leads with a conclusion.
- [ ] Verify with user.

---

## Self-Review Notes

- Items marked **DIAGNOSE** must not be "fixed" before the data/runtime check —
  several reported "inaccuracies" may be display bugs, not compute bugs.
- Phase 1 is independent and shippable on its own. Phases 2–4 each touch separate
  surfaces and can ship as separate PRs.
- Two ambiguities to resolve with the user before building: the exact "11 stocks
  breakouts" component (Task 2.3) and the Daily Brief content redesign (Task 3.1).
