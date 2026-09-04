# Global Atlas — frontend design language, capabilities, pages (proposal for FM sign-off)

Status: **proposal, 2026-09-04** — nothing in `frontend-global/` is built until this is signed off.
Companion canvas: the "Global Atlas board" design artboards (link in the session summary).

## 1. What the board is for

An adviser's instrument for the US ETF universe (plus the S&P 500): **find** an exposure across a
classified universe, **understand** why it scores what it scores, and **assemble** a basket — first
for the FM, later for advised clients under the IA licence. Every number on screen is real, dated
("as of"), and explainable in one click. The India board is the ancestor: same glass-box ethos,
same muted RAG palette the FM already approved; the global board is calmer, more editorial, and
designed around baskets rather than single-stock calls.

## 2. Design language

### Principles
1. **Instrument, not dashboard.** One memorable element — the **Lens bar**: a proportional bar
   whose segments are the lens weights and whose fill is each lens score, with the composite as a
   single large tabular numeral beside it. It appears identically on every row, card and detail
   page, so a reader learns it once.
2. **Prose explains, numbers don't.** The rationale behind a classification or a score is written
   in sentences (serif), never as a raw stat. Raw statistics live only on `/methodology` and admin.
3. **Structure by hairlines, not cards.** Tables and rules carry the hierarchy; a card is reserved
   for an entity (an ETF, a country, a basket). One radius (6 px), one hairline (10% ink), no
   stacked shadows.
4. **Calm density.** 14 px UI type, 13 px tables with tabular numerals, 8 px spacing grid,
   line length under 80 characters for prose. Colour is spent on signal (RAG) and one accent.
5. **Dated everywhere.** Every surface carries "as of <session>" and a freshness dot; a stale
   surface says so in words.
6. **Both themes from day one.** Tokens define light ("Daylight Desk" lineage) and dark
   ("Graphite Terminal" lineage); no colour exists outside the token set.

### Tokens (light · dark)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--ground` | `#ECEFF3` | `#0D1014` | page |
| `--panel` | `#FFFFFF` | `#161B22` | tables, entity cards |
| `--raised` | `#F5F7FA` | `#1C232D` | table heads, stat tiles |
| `--inset` | `#E2E7ED` | `#0A0D11` | meter tracks, wells |
| `--hair` | `rgba(12,20,33,.10)` | `rgba(255,255,255,.08)` | hairlines |
| `--rule` | `rgba(12,20,33,.16)` | `rgba(255,255,255,.14)` | table rules |
| `--ink` | `#15202E` | `#E8ECF1` | primary text |
| `--ink-2` | `#4A5665` | `#99A3B2` | secondary |
| `--ink-3` | `#7C8797` | `#5E6979` | tertiary |
| `--accent` | `#2D63D8` | `#5B9DF9` | links, selection, Leader mark (sparingly) |
| `--pos` / `--neg` / `--warn` | `#2D8561` / `#B84D45` / `#A07A2B` | `#4FC490` / `#DE7870` / `#DDAC4A` | RAG, muted (FM-approved on India) |
| decile ramp | India's muted red→olive→green (`--decile-1..10`) | India's dark ramp | deciles only |

### Type
- **Instrument Sans** — UI, body, all numbers (`font-variant-numeric: tabular-nums` on every numeric
  cell). Fallback `system-ui`.
- **Instrument Serif** — page titles, entity names on detail pages, and the written rationale.
  Fallback `Georgia`.
- Scale (px / line-height): 12/16 meta · 13/18 table · 14/20 body · 16/24 lead · 22/28 section ·
  32/36 page title · 44/44 the composite numeral. Weights: 400/500/600 only.

### Layout
- Left rail 232 px: product mark, sections (Today · ETFs · Countries · Sectors · Stocks · Baskets ·
  Methodology · Admin), theme toggle, user. Top bar: global symbol search (⌘K), "as of" stamp
  with freshness dot.
- Explorer pages: facet rail 260 px + a virtualised table; row height 44 px; sticky header; sort
  on any column; the Lens bar in every row.
- Detail pages: two columns 7/5 — left = identity, classification card, written rationale,
  holdings; right = the score instrument, exposures, risk, any-period return calculator.
- Responsive: rail collapses under 1024 px; tables become card lists under 720 px (read-only
  surfaces first; admin stays desktop).

### Motion and states
- One motion: the Lens bar fills on first paint of a detail page (240 ms, respects
  `prefers-reduced-motion`). Everything else is instant.
- Empty states are instructions ("No ETF above the liquidity floor matches these facets — widen
  AUM or clear a facet"); errors say what failed and what to do; loading is a skeleton of the
  real layout.

## 3. Capabilities (what the board can do)

| Capability | Where | Notes |
|---|---|---|
| Global symbol/name search (⌘K) | everywhere | instruments + countries + sectors + baskets |
| Facet explorer over every classification dimension + AUM / ADV$ / expense sliders + structure flags | `/etfs`, `/stocks` | facets are URL state (shareable screens); saved screens per user |
| Sort on any metric; column picker; CSV export of the current view | explorer tables | export is the real query result, dated |
| Lens bar + composite + peer decile + conviction tier on every row and card | all lists/detail | identical component everywhere |
| Score derivation tree (glass box) | detail pages | port of India's `ScoreDerivationTree` |
| Classification card: dimensions, confidence, method (rule/LLM/human), written rationale citing holdings, review status | ETF + stock detail | "Suggest a correction" sends to the admin queue |
| Exposures: country and sector vectors, concentration, look-through coverage | ETF detail | donut + ranked bars; holdings table with per-holding decile where scored |
| Any-period return calculator (total return vs price return vs SPY) | ETF/stock detail | two date pickers; uses `close_tr`/`close_adj` |
| Compare 2–4 ETFs side by side | `/etfs/compare` | lens bars, exposures, cost, risk, returns |
| Countries grid with representative ETF, RS heatmap, member list | `/countries` | the surface of the country-basket product |
| Basket builder: constituents, weights (fraction), eligibility checks, live preview NAV/metrics, fractional-ready flag | `/baskets/new` (M2) | country kind only accepts `country_pure` ETFs (DB-enforced) |
| Basket pages: NAV chart, metrics vs SPY, look-through exposure, drift since last version, versions | `/baskets/[id]` (M2) | |
| Thresholds input layer: edit any threshold within its allowed range → Preview (re-blend) → Commit → **Rerun** (enqueue rescore/reclassify job) with live job status and score deltas | `/admin/thresholds` | audit row per change; jobs table |
| Classification review queue: sort by AUM / low confidence / disagreements; confirm or override per field; overrides sticky | `/admin/classify` | |
| Data status + health: freshness per table, last runs, gate outcomes, provider call budgets | `/admin/data-status`, `/health` | port of India's health panels |
| Methodology appendix with IC tables and thresholds in force; raw stats allowed here only | `/methodology`, `/methodology/signal` | |
| Auth (invite-only; fm/analyst/client roles), dark mode, keyboard navigation, print styles for basket pages | all | |
| Conversational basket builder | `/chat` (M3) | model proposes, deterministic code validates + previews, explicit confirm to save |

## 4. Page inventory (M1 unless marked)

| Route | Purpose | Key components | Reads |
|---|---|---|---|
| `/` Today | Where the US market is today and what moved, by classification | benchmark strip (SPY, QQQ, IWM, VXUS, AGG, GLD), breadth by peer group, top/bottom movers with Lens bars, freshness | `technical_daily`, `etf_scores_daily`, `macro_daily` |
| `/etfs` | The universe, explorable | facet rail, virtualised table, Lens bar rows, `lenses_active` chip, add-to-basket | `etf_scores_daily`, `etf_classification`, `etf_meta`, `technical_daily` |
| `/etfs/[symbol]` | Understand one ETF | identity header (issuer, index, AUM + source/as-of, ADV$, expense, structure flags, fractionable), classification card + rationale, exposures, holdings look-through, score instrument + derivation tree, risk stats, return calculator, chart | + `etf_holdings`, `etf_exposure_daily`, `ohlcv_daily` |
| `/etfs/compare` | Choose between candidates | side-by-side instrument | same |
| `/countries` | The country product's front door | country grid (representative ETF, RS heatmap 1m–12m, n ETFs, AUM), ex-US toggle | `country_daily`, `etf_classification` |
| `/countries/[iso2]` | Everything for one country | member ETFs with scores, hedged/unhedged, expense, liquidity; region context; "build a basket from here" (M2) | same + `etf_scores_daily` |
| `/sectors`, `/sectors/[id]` | Sector → sub-sector → theme drill; pure-play vs picks-and-shovels | tree + peer-group score distribution + representative ETFs | `taxonomy_*`, `etf_classification`, `etf_scores_daily` |
| `/stocks`, `/stocks/[symbol]` | S&P 500 board and six-lens detail | explorer + derivation tree + fundamentals/valuation/catalyst/flow evidence | `lens_scores_daily`, `stock_financials_pit`, `filings_8k`, `insider_form4` |
| `/methodology`, `/methodology/signal` | Lens definitions, thresholds in force, IC evidence, taxonomy version, data sources + freshness | tables, IC charts | `atlas_thresholds`, `atlas_signal_ic` |
| `/admin/thresholds` | The input layer + Rerun | grouped threshold editor, preview diff, job status | `atlas_thresholds`, `job_queue` |
| `/admin/classify` | Review queue | queue table, per-row editor, override history | `etf_classification*` |
| `/admin/data-status`, `/health` | Operations | freshness table, runs, validators, provider budgets | ops tables |
| `/baskets`, `/baskets/new`, `/baskets/[id]` (M2) | Build and follow baskets | builder, preview, NAV, metrics, versions | `basket_*` |
| `/chat` (M3) | Conversational builder | chat + draft basket panel | `chat_*` |

## 5. Component system (built once, reused everywhere)

`LensBar` · `CompositeNumeral` · `DecileMeter` (ported) · `ConvictionChip` · `FreshnessStamp` ·
`FacetRail` · `DataTable` (virtualised, sortable, tabular) · `EntityHeader` · `ClassificationCard`
· `RationaleProse` · `ExposureDonut` + `ExposureBars` · `HoldingsTable` · `DerivationTree` (ported)
· `ReturnCalculator` · `CountryTile` · `RsHeatmap` · `ThresholdEditor` · `JobStatus` · `BasketBuilder`
(M2). Charts follow the `dataviz` skill (literal hex from the token table; one series colour per
lens). Icons: one stroke set, inline SVG, 16/20 px. No emoji.

## 6. Decision log

- **2026-09-04 — Direction: Option A "Chart room" chosen by the FM.** Feedback folded in: the ETF
  explorer shows every classification dimension as its **own column** — Country (dot coloured by
  region), Sector (swatch coloured by taxonomy sector), Sub-sector (text), Role (icon: filled
  circle = pure play, pick = picks & shovels, three dots = diversified) — each with its **own
  filter group** in the rail. Sector colours are a fixed categorical palette owned by the taxonomy
  table (one hex per level-1 sector), so the same colour means the same sector on every page. The
  role dimension stays, labelled plainly and explained in the table legend; if it does not earn its
  place in Phase 2's review queue it is a one-column removal.

## 7. Decisions still requested from the FM

1. **Direction**: the leading direction ("Chart room": cool paper, Instrument Sans/Serif, Lens bar
   as the hero) vs the two alternates on the canvas ("Instrument panel": dark, dense, monospace
   numerals; "Atlas folio": warm editorial, magazine layout).
2. **Density default**: calm (proposed) or dense (India-like).
3. **Client-facing pages**: which surfaces clients will eventually see (this decides how much
   plain-English translation goes into `/etfs/[symbol]` now).
4. **Rerun scope from the admin page**: latest date only (fast, minutes) vs full backfill
   (hours) — proposed: both, with the backfill behind a confirmation.
