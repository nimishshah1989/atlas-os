# Markets Today redesign — running spec

> The "Regime" page **is the homepage** (`/` → `frontend/src/app/page.tsx`); it
> sits with **India Pulse** (`/india-pulse`) under the "MARKETS TODAY" nav group.
> Sections are specced incrementally. Section 1 below is LOCKED except where noted.

## Section 1 — Regime page consolidation (LOCKED)

### A. Consolidate Regime + India Pulse → one page
- Merge India Pulse's **Breadth table** into the regime/home page; **delete the rest of India Pulse**.
- Remove: `app/india-pulse/`, `components/v6/india-pulse/*` (except the breadth table + `helpers.ts`), `lib/queries/v6/india_pulse.ts`.
- Nav: remove the `India Pulse` link in `components/nav/TopNav.tsx`.
- ⚠️ `SectorPulseGrid.tsx` imports `fmtPct` from `india-pulse/helpers` → **relocate `helpers.ts` to a shared path** before deleting that dir.

### B. Signal cards (`components/regime/SignalScorecard.tsx`)
Keep **Trend**, **Breadth**, **Momentum**; **drop Participation** (`buildParticipationTile`).
- **Trend** — keep as-is for now (details in a later section).
- **Breadth** — drop the A/D part; show **counts** of Nifty 500 stocks above **21-EMA / 50-EMA / 200-EMA** (today it shows % above 50/200 → switch to absolute **counts**).
- **Momentum** — keep, populate with **3 simple momentum indicators** (PROPOSED, pending confirm):
  1. Nifty 500 trailing **3-month return** (price momentum)
  2. **Net new highs** = # Nifty 500 at 52-week high − # at 52-week low
  3. **RSI(14)** of Nifty 500
  *(swap any if you prefer)*

### C. Charts — remove most, replace breadth
- **Remove** sections: `TrendSection`, `MomentumSection`, `ParticipationSection`, the
  old `BreadthSection` charts, `RegimeClassifierInputs` ("how we got here"), and
  `TodayConvictionTabs` (**Top Conviction** — off the first page).
- **Keep:** `RegimeOverlayChart` (Nifty 500 price + regime shading = "risk-on / Nifty 500
  regime history") and **`RegimeJourney12w`** (12-week regime grid — your call to keep).
- **Add 3 breadth line charts:** absolute **counts** of Nifty 500 stocks above
  **21 / 50 / 200-EMA**; line charts; Nifty 500 only; each with **history toggle
  (10y / 5y / 2y)** + **frequency toggle (1d / 1w / 1m)**.

### D. Universe / membership
- **Everything is Nifty 500** (card + charts). Not the broad ~5,500.
- Accept **current** Nifty 500 membership for all history.

### E. Untouched-but-present (assume KEEP unless told otherwise)
`RegimeVerdict`, `TodayWorklist`, `RegimeHeadline`, `IntradayNiftyStrip`.

### Dependencies / gating
- The **3 breadth charts (10y)** and the breadth-card **counts** depend on the
  **data foundation** (see `atlas-data-foundation.md`): today breadth is only
  ~3 months deep and stored as %, period is 20-EMA not 21. Build the UI now;
  it lights up when clean 10y Nifty-500 breadth **counts** (21/50/200) exist.
- 20→21-EMA: stored data is 20-period; 21-EMA must be computed (via TA-Lib) in the
  foundation work.

### Open
- Confirm the 3 momentum indicators.

## Section 2+ — (to be added as the FM provides them)

---

## Outstanding repo hygiene (carry-over)
- **Open PRs to merge** (merging `feat/sortable-sector-tables` carries BOTH the
  cap-weighted-returns data fix AND the heatmap sorting → one merge clears it and
  triggers the first real auto-deploy):
  - `feat/sortable-sector-tables` (sorting + data fix)
  - `fix/sector-index-returns-from-prices` (data fix, standalone — redundant if above merges)
- **Close** stale PR **#114** (`feat/v6-m3-rs-baselines` — tangled M3 branch).
- Deploy pipeline already fixed + merged (#118): git-pull on EC2, dedicated dir
  `/home/ubuntu/atlas-frontend-v2`, no rsync action.
