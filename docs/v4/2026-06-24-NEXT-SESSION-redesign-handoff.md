# Atlas v4 — redesign + correctness handoff (next session)

Synthesis of the FM's 2026-06-24 review. This is a **major design + IA + correctness
pass across every page**, to run after a **design consult** (gstack + a ui/ux-pro skill).
Do NOT start coding the visuals until the design language is decided — §1 + §7 first.

Read FIRST next session: this doc, then `docs/v4/2026-06-24-schema-audit.md`, then the
existing component files per page. Dev server: tmux `atlas-v4` window `dev`, :3000, LENS_V4=1.

---

## 0. What's already shipped this session (9 commits on feat/v4-six-lens)
Speed fix (11–50s→<2s), TV-embeds→Lightweight everywhere, stock-detail "real numbers behind
every score" (lens drill-downs + VWAP snapshot + 8-quarter financials + corporate
announcements), ETF + Funds lens pages (leadership-breadth + look-through + fund
active-movement), ISIN/holdings mapping, schema audit (8 instrument/roll-up pages are fs-only;
the home regime page is the remaining atlas reader). The stock-detail real-numbers drill-down
is the SEED of the design language §1.2 wants everywhere.

---

## 1. THE FUNDAMENTAL SHIFTS (cross-cutting — decide these first)

### 1.1 Kill the composite "black box" → deciles + real sub-components everywhere
- The FM repeatedly rejects composite scores: *"can a fund manager make sense of it?"*,
  *"how is the composite >80 when component scores are <60?"*, *"just a black box."*
- **Root cause of composite>components (confirmed):** the on-read composite applies a
  **convergence multiplier (~1.15×)** + valuation multiplier on top of the weighted sub-score
  average (see the journal `evidence` JSONB: `convergence_multiplier`, `valuation_multiplier`).
  So a sector/stock with 4 converging lenses scores ABOVE its component average — opaque + confusing.
- **Shift:** drop the composite as a headline anywhere it's still shown. Lead with **deciles**
  (already the methodology, D27) + a **designed sub-component breakdown** showing the REAL inputs
  (the stock-detail lens drill-down — "THE ACTUAL NUMBERS" — is the prototype). The single hardest
  design problem: a reusable, scannable **"score → sub-components → real numbers" visual** adopted
  across sector-depth, stock-depth, ETF, fund pages. Also: when a sub-component IS shown as 0–100,
  it must reconcile with the headline (right now Technical lens shows D9/82 with sub-scores ~20 —
  different scales; either show both consistently or drop the 0–100 sub-scores for raw numbers).

### 1.2 Design language: "stop looking like a newspaper"
FM: *"elements should feel different — spaced yet dense, right borders, glass-like; the font
(especially the numbers) doesn't look professional."* Current = flat stacked tables.
- Needs: a real component system — card surfaces with subtle borders/shadows ("glass"),
  denser-but-breathing spacing, a **professional numeric typeface** (tabular figures; consider a
  finance-grade mono/sans), consistent section rhythm. → **design consult + a ui/ux-pro skill**
  (§7). This is a design-system decision, not per-page CSS.

### 1.3 Everything clickable + drill-down (passive → actionable)
- Regime cards (e.g. "341 stocks > 50-EMA") → click → that filtered stock list.
- 2×2 / RRG dots → the instrument/sector page; **bubble size = market cap**.
- Tables: **top-10 by default + "expand"** (no 25+-row dumps); every column sortable.
- The extensive table should be ONE view, not the only view (§1.5).

### 1.4 Self-explaining visuals (consistent across pages)
Every table/chart gets a **tooltip / explanatory note**: what it shows, how to read it, what to
infer. Plus a one-line commentary per section so the page reads as a narrative, not random tables.

### 1.5 Beyond tables — creative, powerful visualizations
FM wants us to think about the data we have and visualize it so the FM finds it *powerful*. Tables
are a fallback; lead with positioning/flow/leadership visuals that drive a decision.

---

## 2. NEW INFORMATION ARCHITECTURE (7 pages — update TopNav)
a. **Market Pulse** (today's regime page; ABSORBS the India-Pulse breadth table — see §3.h)
b. **Sector View**
c. **Stocks**
d. **ETF**
e. **Funds**
f. **Portfolio Manager** — NEW, to be built (scope TBD with FM)
g. **Admin** → sub-pages: **Methodology · Data Health · Thresholds · IC Optimization**
- **Remove the India-Pulse page** (its breadth table moves to Market Pulse; the rest retires).

---

## 3. MARKET PULSE (regime page) — punch list
a. **Drop all Weinstein remnants** — the "Stage 2" first card + the "Today's worklist" card
   shouldn't exist (Weinstein removed). Re-do the top cards: well-formatted, well-spaced, bigger
   internal fonts, **right-hand numbers highlighted** (these are the FIRST thing the FM sees).
b. **Cards must be clickable** → the relevant filtered stock list (e.g. "341 stocks > 50-EMA"
   → that list).
c. **Replace the worklist card** with regime substance: **sectors in green vs sectors
   deteriorating** (named). No instrument cards here.
d. **Nifty regime chart:** overlay **21d / 50d / 200d EMA of Nifty 500**.
e. **4 breadth charts:** the x-axis date navigation is buggy (keeps shifting); the in-box
   "# stocks" shows 2 decimals — must be **integer** (count of instruments).
f. **Market breadth table:** add time periods **today · −1w · −1m · −3m · −6m · −1y**, show
   **# stocks (not %)**; drop the McClellan Oscillator; add a more breadth-driven parameter.
g. **Commentary + tooltips** on every table (the §1.4 standard) — Tier Leadership "Returns" table
   is unreadable as-is (unclear what it shows).
h. **Adopt the India-Pulse breadth-table FORMATTING** as the table standard (the FM likes it; the
   others look bland) — move that breadth table here.
i. Overall: tables look disconnected/bland — apply the §1.2 design language + §1.4 commentary.

---

## 4. SECTOR VIEW — punch list
a. **21 actionable sectors, not 29** — MNC / Rural / Diversified (and other thin-tail labels)
   must be folded into the right sector, never standalone (this is D13 — the frontend is showing
   the un-merged set; fix the sector taxonomy used by the sector page/MVs).
b. **6-lens vector:** composite >80 while components <60 (the §1.1 convergence-multiplier issue);
   colours are wrong; **all tables need sorting**.
c. **Drop the composite headline; lead with deciles** + the sub-component breakdown (§1.1). The
   lens table looks empty/unformatted; **show top-10 + expand**; design action-enabling views.
d. **Multi-window return heatmap — DATA BUG:** Defence ≠ 113% 12m absolute return. Audit every
   number in this heatmap vs the DB.
e. **Sector breadth / EMA participation table:** EMA20 + EMA200 columns are **unpopulated**
   (bug). "Top movers" % is unexplained — clarify or remove.
f. **Cap-tier relative strength "123.70" is unclear** — if rebased-to-100, label it ("small-cap
   23% above Nifty 500 since window start"); make the meaning explicit.
g. **Remove** the "Cross-market relative strength" table.
h. **RRG chart shows no movement** — the trails/rotation are broken; fix the RRG data/render.
i. **Remove** the "RS vs baseline · 5 windows" table on the sector deep-dive (empty/useless).
j. **Both 2×2s:** circles are all equal-sized — **size = market cap**; circles must be
   **clickable → instrument page**.
k. Tables are disjoint — **stack side-by-side, well-formatted**; and the persistent
   sub-component-breakdown design (§1.1) belongs here (sector-depth + stock-depth need the
   clearest breakdown of all sub-component levels — figure out the reusable visual).

---

## 5. STOCKS / ETF / FUNDS — punch list
- Apply ALL the §4 + §1 feedback (deciles+sub-components, sorting, top-10+expand, clickable,
  tooltips/commentary, design language).
- **Think beyond the table** (§1.5): the extensive decile table is useful but must not be the
  only view — design positioning/leadership/flow visuals the FM finds powerful.
- (Stock detail already has the real-numbers drill-down + 8-quarter financials + announcements —
  carry that bar to the list views + ETF/fund depth.)

---

## 6. DATA-CORRECTNESS BUGS (verify each vs the DB before/while redesigning)
1. Sector multi-window heatmap absolute returns (Defence 113% 12m is wrong) — §4.d.
2. Sector breadth EMA20 / EMA200 columns unpopulated — §4.e.
3. RRG rotation/trails not rendering movement — §4.h.
4. Sector "RS vs baseline 5-windows" empty — §4.i (or remove).
5. Composite > component scores (convergence/valuation multipliers) — §1.1; decide display.
6. Sector count 29 → 21 (taxonomy merge) — §4.a.
7. Regime breadth "# stocks" shown with 2 decimals — §3.e.
8. Cap-tier RS scale/label (123.70) — §4.f.

---

## 7. DESIGN CONSULT + TOOLING (set up before executing the visuals)
- **gstack**: install + use for the design/eng plan (CLAUDE.md already references
  `~/.gstack/projects/atlas-os/ceo-plans` + `eng-plans`). [Install attempted this session — see the
  session notes for status; finish in next session if incomplete.]
- **ui/ux-pro skill**: download/enable a frontend-design skill (the repo already references
  `frontend-design:frontend-design`) — evaluate whether to adopt a new design language / component
  shifts so the app stops feeling like a newspaper (§1.2).
- **Run the consult** on §1 (design language + the sub-component-breakdown visual) BEFORE building,
  then convert §3–§5 into an ordered build plan.

### Suggested next-session sequence
1. Design consult → lock the design language + the "score→sub-components→real numbers" visual (§1).
2. New IA + TopNav (§2) + Market Pulse rework (§3, incl. India-Pulse breadth move).
3. Sector View rework + the §6 data bugs.
4. Stocks/ETF/Funds redesign to the new language (§5).
5. Portfolio Manager (new) + Admin sub-pages (scope with FM).
