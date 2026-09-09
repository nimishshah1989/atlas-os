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

**Source (2026-09-09):** the Jhaveri Rebalance desk tool's stylesheet — its live `html.rb` token
set and its component rules (top bar, cards, KPI tiles, chips, tables, segmented control, buttons,
inputs, links, focus), copied into `frontend-global/src/app/globals.css` verbatim so the board and
the desk tool read as one product. Where the board needed something the desk's stylesheet does not
define (a search box on the bar, a decile ramp, prose columns in tables) it is marked *extension*.

### Principles
1. **Instrument, not dashboard.** One memorable element — the **Lens bar**: a proportional bar
   whose segments are the lens weights and whose fill is each lens score, with the composite as a
   single large tabular numeral beside it. It appears identically on every row, card and detail
   page, so a reader learns it once.
2. **Prose explains, numbers don't.** The rationale behind a classification or a score is written
   in sentences, never as a raw stat. Raw statistics live only on `/methodology` and admin.
3. **Structure by hairlines, not cards.** Tables and rules carry the hierarchy; a card is reserved
   for an entity (an ETF, a country, a basket). One radius (6 px), one hairline (`line`, navy at
   16%); a 2 px rule, not a darker one, carries emphasis. No stacked shadows (`--shadow-lift` is
   the one lift).
4. **Calm density.** 14.5 px body on cream, 13.5 px tables with tabular numerals, 4/8/12/16/24/32
   spacing, prose at `--measure` (66ch). Colour is spent on signal (RAG) and the navy accent;
   gold marks focus and the active section.
5. **Dated everywhere.** Every surface carries "as of <session>" and a freshness dot; a stale
   surface says so in words.
6. **One theme, light only** (`color-scheme: light only`). No dark theme, no theme toggle, no
   `data-theme` bootstrap; print uses the same tokens on white.

### Tokens
The names are the CSS custom properties in `globals.css`. `--color-*`, `--font-*`, `--text-*`,
`--radius-*` and `--shadow-*` sit under Tailwind's `@theme`, so each also produces its utility
(`bg-panel`, `text-ink-2`, `text-meta`, `rounded-panel`, `shadow-lift`, …); `--decile-*` and
`--measure` are on `:root`. Names the components already referenced are kept with new values.

| Token | Value | Desk name | Use |
|---|---|---|---|
| `--color-ground` | `#f4f0e5` | ground | page, cards, chips, controls (cream paper) |
| `--color-panel` | `#ffffff94` | panel | tables, tiles, notices (translucent white on cream) |
| `--color-panel-solid` | `#fbf9f4` | panel-solid | what panel composites to: sticky heads and the sticky symbol column |
| `--color-raised` | `#fbf9f4` | panel-solid | table heads, group rows |
| `--color-inset` | `#25394a17` | accent-soft | meter tracks, code, wells |
| `--color-line` = `--color-hair` = `--color-rule` | `#25394a29` | line | the one hairline |
| `--color-ink` | `#25394a` | ink | primary text |
| `--color-ink-2` = `--color-muted` | `#5e6b75` | muted | secondary text, labels |
| `--color-ink-3` | `#5e6b75` | grey | tertiary text (the desk has one muted level; size and case carry the rest) |
| `--color-accent` | `#25394a` | accent | links, selection, the primary button, value bars (navy: the ink itself) |
| `--color-accent-soft` | `#25394a17` | accent-soft | selected chips, the hero card, hover |
| `--color-navy-deep` | `#16294d` | navy-deep | the top bar |
| `--color-pos` / `--color-pos-soft` | `#2c6b41` / `#e3ede5` | pos / pos-soft | RAG green |
| `--color-neg` / `--color-neg-soft` | `#ab4425` / `#f3e1d9` | neg / neg-soft | RAG red |
| `--color-warn` = `--color-amber` / `--color-amber-soft` | `#8a5d10` / `#f5ebd0` | amber / amber-soft | RAG amber |
| `--color-gold` / `--color-gold-soft` | `#a17c2b` / `#f5ebd0` | gold / gold-soft | focus ring, the active section, selection |
| `--color-tint-info` / `-pos` / `-neg` / `-warn` | `#f1f5fc` / `#f0f7f2` / `#fdf1ed` / `#fdf7e8` | tints | row hover (info), notices (warn) |
| `--color-white`, `-72`, `-60`, `-6` | `#ffffff`, `#ffffffb8`, `#fff9`, `#ffffff0f` | the bar's whites | text, nav links, `.who`, link hover on navy |
| `--color-white-18` | `#ffffff2e` | *extension* | the search box's border on navy |
| `--shadow-lift` | `0 1px 2px #16212b0d, 0 4px 14px #16212b0d` | lift | the one shadow |
| `--radius-panel` / `--radius-lg` | `6px` / `10px` | radius / radius-lg | |
| `--measure` | `66ch` | measure | prose width |
| `--decile-1..10` | `#ab4425` `#af5622` `#b3671e` `#b67816` `#b58510` `#9d8125` `#847c30` `#6a7738` `#4e713d` `#2c6b41` | *extension* | deciles only: neg → amber `#b8860b` → pos, ten steps at equal OKLab arc length; 1 = worst. The chip is ink on a 30% tint of its step (≥ 6.9:1 on all ten) with the step as its border |

### Type
- One family for display and body: `"Iowan Old Style", "Palatino Linotype", Palatino, Georgia,
  "Times New Roman", serif`. Both `--font-serif` and `--font-sans` resolve to it, so `font-serif`
  and `font-sans` utilities keep working; nothing is loaded through next/font.
- Body 14.5 px / 1.5. Scale: `--text-meta` .78rem (xs) · `--text-table` .86rem (sm) ·
  `--text-body` 14.5px · `--text-lead` .95rem (md) · `--text-h2` 1.05rem (lg, the h2) ·
  `--text-section` 1.28rem (a card's value, the status headline) · `--text-title` 1.3rem (the h1) ·
  `--text-composite` 2rem (hero). Tables are 13.5 px with 10.5 px uppercase heads, chips 12.5 px,
  labels 11 px, the bar's links 13 px, `.who` 11.5 px — set directly, as the desk does.
- Weights 400 / 500 / 600 / 650 / 700. `.num { font-variant-numeric: tabular-nums }` on every
  numeric cell.

### Layout
- Top bar (`.topbar`): navy-deep, 48 px, sticky. The product mark (serif 1.05rem/600, white), the
  sections — Today · Countries · ETFs · Stocks · Health; Portfolios joins with its page (the hook
  is one commented line in `Rail.tsx`) — as 13 px links, gold-underlined when current; the search
  box (⌘K); and `.who` at the right, 11.5 px dimmed, holding the "as of" stamp and its dot.
- Main: `max-width: 1440px`, centred, `padding: 0 24px 60px`. Page head: h1 1.3rem/600, h2
  1.05rem/600.
- Explorer pages: facet rail 260 px of chips (a chosen value is a chip that is `.on`) + a
  virtualised table; row height 44 px (`DataTable`'s `ROW_HEIGHT`, set outright in CSS); sticky
  uppercase header; sort on any column; the Lens bar in every row.
- Detail pages: two columns 7/5 — left = identity, classification card, written rationale,
  holdings; right = the score instrument, exposures, risk, any-period return calculator. Fact
  lists sit on hairlines with the card's uppercase labels.
- Responsive: under 1024 px the bar tightens and hides the stamp, explorer and detail pages stack;
  under 720 px the bar scrolls sideways. Tables become card lists under 720 px later (read-only
  surfaces first; admin stays desktop).

### Component contracts
Every class the pages use keeps its name and restyles in place: `.page` / `.page-wide`, `.panel`,
`.tile`, `.tbl`, `.btn` / `.btn-primary` / `.btn-quiet`, `.field`, `.decile-chip`,
`.lens-fill--animate`, `.dot`, `.explorer`, `.notice`, `.facets` / `.facet-*`, `.dt` / `.dt-table`
/ `.dt-sort` / `.dt-symbol`, `.detail`, `.facts` / `.fact`, `.timeline`, `.slots`, `.num`, `.main`,
`.topbar`, `.search`, `.rail`. Added from the desk: `.card` (+ `.hero`, `.k` / `.v` / `.s`),
`.tile .l` / `.v` / `.s`, `.chip` (+ `.on`, `.ghost`), `.seg`, `td.valbar` (+ `.neg`), `tr.sec`
(+ `.red` / `.amber` / `.grey`), `.who`, `.dot-pos` / `.dot-warn` / `.dot-grey`. Deviations from the
desk, on purpose: `.tbl` prose cells may wrap (only `.num` / `.r` cells are nowrap) because the
health tables carry notes columns; the last row of a bordered panel drops its hairline.

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
