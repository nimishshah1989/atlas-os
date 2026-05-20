# Atlas v2 — Decision Engine Design Spec

**Date:** 2026-05-20
**Branch:** feat/atlas-consolidation
**Status:** Design locked via brainstorming; pending /plan-design-review then writing-plans.
**Input analysis:** [Decision-flow review](2026-05-20-atlas-decision-flow-design.md) (the page-by-page UX audit + 64-element interactivity map that seeded this design).
**Anchors:** [Signal Consolidation spec](2026-05-18-atlas-signal-consolidation-design.md), [State Engine spec](2026-05-18-atlas-state-engine-design.md).

## Problem

Atlas v2 has the data but no path. A fund manager lands on a page, reads a wall of numbers, and has nowhere to go next. It is a set of dashboards, not a decision tool. Three structural gaps: no regime page (nav "Regime" → the stock table), ~64 dead-end static elements, and broken surfaces on the critical path. The deeper gap: Atlas hands the fund manager signals but never connects them to *their* mandate or *their* book. The recommendations are generic; a fund manager's decisions are not.

## The core model — Layered targets + Policy rails

Atlas's unit of action is a **layered target**:
- **Sector targets** (the WHAT) — "be 12% Banking" — set at the regime + rotation layer.
- **Instrument-level picks** (the WHICH) — the stocks / ETFs / funds that fill a sector target.

Every recommendation is the intersection of two things:
- **Engine signal** — the IC-validated Weinstein state, bottom-up from stock states.
- **Policy constraint** — the fund manager's mandate, configured per portfolio.

`recommendation = engine_signal ∩ policy_constraint`. Same engine, different fund manager's Policy → different recommendations. That intersection is what turns a research tool into a tool that fits how a specific desk runs money.

## The Policy — the spine

A **Policy** is the fund manager's trade philosophy, expressed as configuration. It is **per-portfolio**, inheriting a **house default**; each portfolio overrides only what differs (a retiree book tightens stops and lowers the small-cap ceiling vs the house default). New portfolios start sensible, not blank.

Policy fields:

| Group | Field | Meaning |
|---|---|---|
| Deployment | `cash_floor_pct` | Never fully invested; minimum cash |
| Deployment | `respect_regime_cap` | When on, the regime's deployment % is the hard ceiling on invested capital |
| Concentration | `max_per_stock_pct` | Single-instrument concentration cap |
| Concentration | `max_per_sector_pct` | Single-sector cap — the ceiling on any sector target |
| Concentration | `max_small_cap_pct` | Cap-tier ceiling |
| Concentration | `min_holdings` | Diversification floor (count) |
| Concentration | `max_positions` | Holdings ceiling (count) — a focused book caps total names |
| Entry | `buy_states` | Which Weinstein states qualify to buy (e.g. Stage 2A, 2B; optionally Stage 1 base accumulation) |
| Entry | `min_within_state_rank` | Minimum conviction to enter |
| Entry | `min_rs_rank` | Minimum 12m RS rank to enter |
| Exit | `hard_stop_pct` | Exit if down X% from entry |
| Exit | `state_exit` | Trim on Stage 3 entry; full exit on Stage 4 |
| Exit | `trailing_stop` | Optional trailing stop |
| Instrument | `instrument_universe` | `direct_equity` / `etf` / `mutual_fund` / `mixed` — what fills sector targets for this book |
| Benchmark | `benchmark` | The index alpha is measured against (Nifty 50 / 500 / custom) |
| Cadence | `rebalance_cadence` | daily / weekly / monthly |

Every flow step reads the Policy: step 2 reads sector caps, step 3 reads entry rules + instrument universe, step 5 reads sizing caps, step 6 reads exit rules.

## The decision flow — six steps

A continuous decision. Each step hands the next a piece of context (the **session context**: active portfolio + its Policy + the regime deployment cap).

### Step 1 — Regime (`/`)
The `/intelligence` content is promoted to `/`. The page gains, on top of everything it shows today:
- **One verdict sentence** — e.g. *"Cautious — deploy 40%. Add only Leader/Strong names in leading sectors. Trim Stage 3→4 holdings. Avoid fresh small-cap exposure."* Copies the `/global` pattern.
- **4-signal scorecard** — bottom-up state breadth: **Trend** = % of universe in Stage 2 · **Breadth** = MA participation · **Momentum** = Stage-2 inflow rate · **Participation** = leadership concentration.
- **Today's worklist** — "N sectors entered favour · N fresh breakouts · N holdings deteriorating", each clickable.
- A **portfolio selector** — which book the fund manager is working.

**Nothing is removed.** The existing 4-state market classifier, the VIX / A/D / McClellan / Net NH-NL panel, the MA-participation charts, the bullish/bearish trend charts all stay — they move *below* the verdict + scorecard as the supporting evidence. Carries forward: deployment cap + leading sectors.

### Step 2 — Sector rotation (`/sectors`)
Sectors ranked by bottom-up stage breadth (`pct_stage_2/3/4`). For the active portfolio, each sector row shows **current exposure vs policy-capped target**: "Banking: now 8% · engine strong · policy cap 15% → target 12% · fill +4%." This is where sector targets are set. Carries forward: chosen sector + target gap.

### Step 3 — Fill the target (`/sectors/[name]` → `/stocks` pre-filtered)
The sector's instruments, ranked by `within_state_rank`, filtered to the Policy's entry rules (`buy_states`, `min_within_state_rank`, `min_rs_rank`). The instrument type shown = the Policy's `instrument_universe` (a direct-equity book sees stocks; an ETF book sees sector ETFs). Suggested fill weights respect `max_per_stock_pct`. Carries forward: candidate instruments + policy-sized weights.

### Step 4 — Conviction check (`/stocks/[symbol]` or fund/ETF detail)
The IC-validated evidence page — already the strongest surface, mostly unchanged. Every static token becomes a link (sector chip → `/sectors/[name]`, "N peers in this state" → the peer list, index label → index peers). Ends with the **Act** affordance. Carries forward: act / pass on one name.

### Step 5 — Act (`/portfolios/[id]`)
"Add to [book]" produces a **proposed portfolio change**, not a raw trade ticket and not a passive watchlist. Position size is pre-filled from `target_gap ∩ max_per_stock_pct ∩ regime_deployment_cap`. The trade lands in the portfolio as a pending change with a **policy-compliance check** (does the resulting book still satisfy every Policy constraint). This is the destination — the flow is complete only when a decision becomes a portfolio change.

### Step 6 — Deterioration loop (`/portfolios/[id]` as a start point)
`/portfolios` is **bidirectional** — the destination of steps 1-5 and the origin of the trim flow. Holdings that hit a Policy exit rule (`hard_stop_pct`, `state_exit`) auto-surface on the portfolio page. Each → click → stock detail → confirm the trim. The regime page's deterioration-watch is the cross-portfolio version of the same.

## ETF / Fund ranking — two-tier

An ETF or fund is a basket of stocks the engine already classifies. The ETF aggregator (rebuilt on `de_etf_holdings`) and fund aggregator produce the bottom-up truth: `dominant_state`, `pct_stage_2/3/4`, `mean_within_state_rank`, `mean_rs_rank_12m`.

Ranking splits into two uses:
1. **Standalone verdict** — the recommendation label (`Recommended / Hold / Reduce / Exit`). "Is this fund worth owning at all." Unchanged taxonomy.
2. **In-flow rank** — when filling a sector target, funds/ETFs are ranked by **bottom-up holdings quality**: primary = `mean_within_state_rank` + `pct_stage_2`; secondary filter = `nav_state` (the fund's own NAV trend — catches manager drag where good holdings still underperform).

Inside the flow, funds/ETFs compete on the same Weinstein states as their underlying stocks. The verdict label is shown alongside but the *ranking* is bottom-up — the full bottom-up promise made good.

**Coverage caveat:** bottom-up ranking works cleanly for the 17 equity ETFs with real `de_etf_holdings` constituent data. The 17 commodity / F-id-only ETFs fall back to their own price-state. Funds are capped at the 2026-01-31+ holdings history (upstream `de_mf_holdings` data limit per the DB audit).

## Page-by-page change list

**Role changes:** `/` → Regime page (was the stock table; duplicate route killed). `/sectors` → step-2 rotation + target-setting (was read-only cards). `/portfolios` → bidirectional flow endpoint (was a flat list, currently full of test fixtures — clean those out).

**Content additions, same role:** `/stocks` → arrives pre-filtered from a sector, default sort conviction desc, policy-filtered in flow mode. `/stocks/[symbol]` → gains the Act affordance + policy context. `/sectors/[name]` → becomes the step-3 fill surface. `/funds/[id]`, `/etfs/[ticker]` → holdings become clickable to stock detail; gain Act for fund/ETF-universe books.

**Clickability only:** `/global`, `/methodology`, `/strategies` — inherit the 64-element rule, no role change.

## Interactivity — the connection rule

Every ticker symbol, sector name, fund name, ETF name, country name, and state badge anywhere in the product is a link or a hover-card. No such token rendered as plain text. The 64-element map in the input analysis doc is the concrete checklist.

## Data model changes

- **New: `atlas_portfolio_policy`** — one row per portfolio (plus one `is_house_default` row). Columns mirror the Policy field table above. A portfolio's effective policy = house default with the portfolio's non-null overrides applied.
- **New: portfolio target/holding shape** — the existing portfolio tables gain a notion of *target weight* per sector and per instrument, alongside current weight, so step 5's current-vs-target and step 6's deterioration can be computed. (Exact column changes deferred to the implementation plan.)
- **Session context** — the active portfolio id is a client-side selection; the Policy and regime cap are fetched per page from it. No new server session state.

## Build phasing — three waves

1. **Wave 1 — Wiring (fast, no new data model).** Promote `/intelligence` → `/` with verdict + bottom-up scorecard + worklist. Make all 64 elements clickable. Wire steps 1→4 handoffs (regime → sector → stock pre-filter → conviction). The flow becomes navigable end-to-end for browsing.
2. **Wave 2 — The Policy.** `atlas_portfolio_policy` table + the house-default seed. The Policy config surface (a panel on `/portfolios/[id]`). Recommendations across steps 2-4 start reading the Policy (entry-rule filtering, sector caps, instrument universe).
3. **Wave 3 — The Act loop.** "Add to book" with policy-aware position sizing. Portfolio current-vs-target. Deterioration surfacing from Policy exit rules. Step 5 and step 6 become real.

## What this does NOT do

- No automated trade execution — Atlas proposes, the fund manager disposes. "Act" produces a *proposed* change.
- No multi-user / per-fund-manager auth model — the Policy is per-portfolio; multi-tenant is out of scope here.
- No change to the IC-validated state engine itself — this spec consumes its output, it does not modify the classifier.
- No backtesting of the Policy — that is a separate future capability.

## Definition of done

1. A fund manager lands on `/`, reads one verdict sentence, and within ~60 seconds is clicking into the first item of the worklist.
2. Every step of the flow hands the next a pre-filtered context; no step requires manual re-navigation.
3. No ticker / sector / fund / state token anywhere is un-clickable.
4. The active portfolio's Policy demonstrably changes the recommendations (two portfolios with different policies show different sector targets and different eligible stocks from the same engine output).
5. "Act" on a stock produces a policy-sized proposed change in the chosen portfolio.
6. Deteriorating holdings surface on the portfolio page without the fund manager hunting for them.

## Open questions

None — Q1 (layered), Q2 (house default + per-portfolio policy), Q3 (instrument universe as a Policy field), Q4 (bottom-up scorecard) all resolved in the brainstorming session.
