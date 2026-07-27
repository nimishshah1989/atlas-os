# Wealth Glass-Box Redesign — Design + Build Spec

Date: 2026-07-24 · Author: FM + Claude (brainstormed, FM-approved)
Builder: **a fresh Claude session (Sonnet)** — this document assumes ZERO prior
context. Everything you need is here or in the files it points to. Read this
whole document before writing any code.

---

## 0. Mission and framing (read this twice)

Rebuild the Jhaveri wealth capability app's frontend as a **glass-box,
ELI5-simple, visually powerful** three-page board over data that already exists.

- This is **NOT a pitch, NOT a presentation, NOT a demo deck**. It is a
  capability demonstration for smart wealth-firm principals: *"when we have
  access to this kind of data, here is what becomes visible."* No sales
  furniture, no scroll-story chapters, no call-to-action lists.
- The organizing idea is a **clean bifurcation**, stated on screen:
  1. **HOLDINGS** — what clients own, audited through the seven questions
     (the Stockizen 7-prompt framework, `docs/wealth-seven-prompts-framework.md`).
  2. **BEHAVIOUR** — what 37 years of transactions reveal, computed by the
     Python engines (benchmarking, behaviour gap, panic fingerprints, advice
     ledger, what-ifs).
- **Every number explains itself, inline.** The single biggest complaint about
  the current app: numbers like "if they had kept investing it would be ₹55cr"
  appear with no visible derivation — a black box. The fix is structural (§5):
  every exhibit carries a `How is this calculated? ▾` drawer with inputs, rule,
  assumptions (with bias direction), arithmetic, and the real underlying rows.
- **Rich, not minimal.** Each question is a full-width *exhibit*: a verdict,
  a KPI strip, and 2–3 coordinated charts showing the same question from
  different angles, plus the working. Magazine density. It is explicitly NOT
  a typeform/stepper and NOT one-tile-per-question.

Success = a smart non-quant scrolls either page and can (a) understand every
exhibit unaided, (b) answer "how was this number derived?" for any number on
screen using only what's on screen.

---

## 1. Non-negotiable rules

1. **Rule #0 — no synthetic data, ever.** Every number on screen is computed
   from `wealth.*` (or `atlas_foundation.*`) tables at build time. No
   placeholder, default, or invented number. Tests assert on REAL database
   output, never fixtures. (Project-level absolute rule — see `CLAUDE.md`.)
2. **Banned words in UI text** (enforced by `scripts/wealth/validate_wealth_app.py`,
   regex, case-insensitive): `xirr`, `alpha`, `disposition`, `pgr`, `plr`,
   `counterfactual`. These are column/engine names, fine in code — but on
   screen say "grew at N% a year", "extra growth vs the index (pp/yr)",
   "the what-if", "sold winners / kept losers". The validator walks every
   renderable string; a hit fails the build.
3. **Honesty labels.** Any number resting on assumptions carries a chip:
   `exact` · `estimate` · `upper bound` · `floor`. Any partial-coverage
   visual states its coverage (e.g. "sector identified for 67% of look-through
   value"). Where data doesn't exist (prompt 6 bloat check; per-client
   volatility; per-fund tax attribution) render an honest empty state that
   names the missing feed — never fabricate. Assumption text in the UI MUST
   match what the engine code actually does (read the engine before writing
   the card).
4. **No new DB tables, no new schemas** (FM directive: no table sprawl).
   All new aggregates are build-time queries in the app's data layer.
5. **No hardcoded methodology numbers.** Any new threshold (e.g. "overlap
   above X% counts as duplicate") is read from
   `atlas_foundation.atlas_thresholds` (category `wealth`); seed it there if
   missing.
6. **Self-contained output.** One HTML file, CSP-safe: no CDN, no external
   fonts, no fetch, no images (inline SVG only). All charts are hand-rolled
   inline SVG (the current app already does this — reuse its helpers).
7. **File-size limits** (hook-enforced): 600 LOC per source file, 800 per test
   file. The current 1,966-line builder only survives via an `# allow-large`
   pragma — the rebuild SPLITS it into a package (§10). Prefer the split to
   the pragma.
8. **Real names / PII.** The app shows real client names (existing convention).
   Consequence: the Artifact republish is done by FM, not by you (§13).

---

## 2. Ground truth — environment, code, data

### 2.1 Repo bootstrap (do this first)

The wealth code is **merged to origin/main** (PR #192, merge `856634d8`).
Other branches carry stale copies — always start from origin/main. The main
checkout at `/home/ubuntu/atlas-os` may sit on an unrelated dirty branch; do
not touch it. Work in a worktree:

```bash
cd /home/ubuntu/atlas-os && git fetch origin
git worktree add ~/atlas-worktrees/wealth-glass-box -b feat/wealth-glass-box origin/main
cd ~/atlas-worktrees/wealth-glass-box
ln -s /home/ubuntu/atlas-os/.venv .venv     # shared venv (gitignored)
ln -s /home/ubuntu/atlas-os/.env .env       # shared secrets (gitignored)
# bring this spec onto the build branch (it may not be on origin/main yet):
cp /home/ubuntu/atlas-os/docs/superpowers/specs/2026-07-24-wealth-glass-box-redesign-design.md docs/superpowers/specs/
git add docs/superpowers/specs/2026-07-24-wealth-glass-box-redesign-design.md
git commit -m "docs(wealth): glass-box redesign spec"
```

Run everything with `set -a; source .env; set +a` and `.venv/bin/python`.
Ad-hoc SQL: `psql "${ATLAS_DB_URL/postgresql+psycopg2/postgresql}"` (the env
var is a SQLAlchemy URL; psql needs the prefix stripped).

### 2.2 Files you must read before coding (in this order)

| File | Why |
|---|---|
| `scripts/wealth/README.md` | module map of the whole wealth pipeline |
| `scripts/wealth/build_capability_app.py` | the current app: data assembly, `_f()` JSON hygiene, en-IN L/cr formatting, SVG helpers, route/JS pattern — you are replacing its layout, keeping its plumbing idioms |
| `scripts/wealth/validate_wealth_app.py` | the gate you must keep green: banned-word walk, data-embed extraction, headless route checks |
| `scripts/wealth/engine_common.py` | DB connection + shared helpers |
| `scripts/wealth/build_audit_packs.py` | per-client 8-section packs (map, label_check, overlap, fees, benchmark, habits, value, actions) — Client 360 reuses these |
| `scripts/wealth/counterfactuals.py` | the what-if engines — you must mirror their ACTUAL assumptions into the UI assumption cards |
| `scripts/wealth/behaviour_fingerprints.py` | panic/drawdown-window logic + SIP stream detection — reuse, never reimplement |
| `scripts/wealth/exact_benchmark.py`, `behaviour_gap.py`, `advice_ledger.py`, `build_overlap.py`, `build_label_check.py`, `build_fund_performance.py`, `build_cut_list.py`, `build_equity_curves.py` | the engines behind each exhibit |
| `docs/wealth-seven-prompts-framework.md` | the seven questions, verbatim — Page 1's skeleton |

### 2.3 The `wealth` schema (live row counts, 2026-07-24)

Read-only inputs; all populated by engines that have already run.

| Table | Rows | Use in this build |
|---|---|---|
| `clients` | 242 | identity (client_id, full_name, family_group) |
| `transactions` | 210,634 | ledger atoms 1989→2026; weekly-flow charts; "see the rows" samples |
| `holdings` | 3,309 | current per-client per-scheme market value |
| `schemes` | 1,320 | scheme master (names, category) |
| `lots` | 185,438 | FIFO slices (realized/unrealized, tax-if-sold) |
| `client_benchmark` | 234 | per-client: xirr_client, xirr_bench, alpha, first_flow, gross_in/out, terminal_mv |
| `behaviour_gap` | 3,336 | per client×scheme: mwr_pct, twr_pct, gap_pp, gap_rs, invested |
| `client_behaviour` | 234 | fingerprints: panic_out_rs, panic_loss_out_rs, panic_share, div_leak_rs, sip_streams/active/stopped, sip_stops_in_drawdown, chase_*, pgr/plr/disposition |
| `advice_ledger` | 33,312 | paired switches with 1y/3y forward verdicts |
| `advice_waves` | 992 | coordinated push waves: scheme, window, n_clients, inflow_rs, fwd1y/3y scheme vs bench |
| `counterfactuals` | 234 | per-client what-ifs: cf_index_rs, cf_no_panic_rs, cf_sip_alive_rs + input tallies (`\d wealth.counterfactuals` for full columns) |
| `client_curves` | 48,068 | per-client monthly value_rs, net_flow_rs, coverage_pct |
| `client_curve_events` | 24,270 | per-client dated events (kind, amount_rs, note) — timeline markers |
| `client_stock_exposure` | 246,573 | look-through: holding_name, isin, instrument_id, exposure(₹), bucket |
| `client_fund_overlap` | 4,556 | per-client fund-pair overlap_pct |
| `client_overlap` | 216 | per-client overlap rollup |
| `fund_label_check` | 402 | per-fund label-vs-SEBI-cap reality |
| `fund_performance` | 298 | per-fund vs its benchmark: full_period_pct, beat_count/windows (rolling consistency), dn_capture_pct, verdict, benchmark_note |
| `cut_list` | 216 | flagged funds with rule/evidence/action/est_value/basis |
| `audit_packs` | 242 | per-client 8-section pack incl. narration (validated text) |
| `client_segments` | 242 | segment membership |
| `value_statements`, `tax_harvest`, `households`, `client_reports`, `client_scorecard`, `client_churn_risk`, `churn_curves`, `call_lists`, `client_profile_ext`, `ledger_blocks` | — | available; only used where §6–8 says so. `call_lists` is deliberately DROPPED from the UI. |

Sector join: `client_stock_exposure.instrument_id → atlas_foundation.instrument_master.sector`.
Measured coverage: instrument_id on 76% of rows / **67% of exposure value**;
bucket totals (₹): atlas_scored_stock 259.8cr, etf_units 66.7cr, cash_other
26.2cr, identified_stock_unscored 22.2cr, other 17.1cr,
indian_stock_unidentified 16.0cr, debt_instrument 10.8cr, foreign 0.2cr.
Render sector over the identified portion and SAY the coverage (§8).

### 2.4 Book headline facts (for orientation; recompute, don't hardcode)

234 clients with transactions · 210,634 transactions · 1989–2026 · ₹650.6cr
gross in · median per-client extra growth vs index +3.80pp/yr (173 of 212
beat) · invested-weighted behaviour gap −1.32pp · ₹27.8cr sold below cost ·
₹23.8cr dividend leakage · 781 SIPs stopped (331 during drawdowns) · what-ifs:
no-panic +₹181cr (upper bound), SIP-alive +₹67cr, index-everything −₹129cr
(i.e. the book BEAT indexing). Equity-curve coverage is honest-partial:
median ~49%, ~72% of clients <70% — the UI renders "insufficient history"
rather than pretending.

### 2.5 Pipeline and output

`scripts/wealth/run_wealth_engine.sh` = engines → packs → narration → app →
validate. Keep its interface: the LAST TWO steps
(`build_capability_app.py`, `validate_wealth_app.py`) must keep their CLI
names and exit codes. Output: `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html`
(NOT committed; lives outside the repo). Current size 5.0MB; budget ≤8MB.

---

## 3. What replaces what

| Current (5 hash-routes) | Fate |
|---|---|
| `#book` 6-chapter scroll-snap pitch | **DELETE** (its numbers reappear as exhibits) |
| `#calls` three call lists | **DELETE** (FM explicitly: no calls) |
| `#cohort` + `#segment/<key>` | **ABSORBED** into the two book-level pages (segments become a filter on the client index) |
| `#client/<id>` 8-section audit | **REBUILT** as Client 360 (§8), reusing audit-pack content |
| `#guide` standalone explainer | **DELETE as a page** — its explanations move inline into each exhibit's `how? ▾` drawer |

New routes: `#holdings` (default) · `#behaviour` · `#client/<id>`.
Update `validate_wealth_app.py`'s route list accordingly (§12).

---

## 4. Information architecture

```
 ┌──────────────────────────────────────────────────────────────────┐
 │ JHAVERI · THE BOOK          data as of <date>   [Holdings] [Behaviour] │
 ├──────────────────────────────────────────────────────────────────┤
 │ #holdings   7 exhibits (Q1–Q7) + client index                    │
 │ #behaviour  5 exhibits (B1–B5) + client index                    │
 │ #client/<id>  Client 360: header → timeline → their holdings     │
 │               (7 questions scoped) → their behaviour → what-ifs  │
 └──────────────────────────────────────────────────────────────────┘
```

- Navigation = exactly two links top-right + client names as links everywhere.
  No tab strips, no steppers, no scroll-snap.
- **Full width.** Kill the 820–920px `.wrap` cap; use a responsive 12-col grid
  (max ~1600px, generous gutters). Exhibits span full width; charts sit 2–3
  across inside an exhibit on wide screens, stack on narrow.
- Each page opens with a one-line frame in plain words, e.g. Holdings:
  "234 investors. ₹Xcr across N funds. Seven questions any fee-only adviser
  would ask." Behaviour: "210,634 transactions across 37 years. What they
  reveal about investors — and about advice."
- A sticky mini-index (the 7 questions / 5 exhibits) for jumping; all content
  is on the page (no hiding behind steps).

---

## 5. The universal exhibit grammar

Every exhibit on every page has the same anatomy (build ONE renderer,
`exhibit()`, and feed it specs):

```
┌ EXHIBIT ─────────────────────────────────────────────────────────┐
│ Q3 · How much is duplicated?                    [honesty chip]   │
│ VERDICT: one plain-English sentence with the key number(s).      │
│ [KPI tile] [KPI tile] [KPI tile]                                 │
│ ┌─ chart A ────────┐ ┌─ chart B ────────┐ ┌─ chart C ─────────┐ │
│ └──────────────────┘ └──────────────────┘ └───────────────────┘ │
│ ▸ How is this calculated?            ▸ Table view               │
└──────────────────────────────────────────────────────────────────┘
```

`How is this calculated? ▾` — five fixed parts, ALWAYS in this order:

1. **What we counted** — the real inputs with counts/sums (from the same
   queries that fed the charts, so they cannot disagree).
2. **The rule** — one plain sentence.
3. **The assumptions** — bulleted; each with its bias direction, e.g.
   "we assume sale proceeds were NOT reinvested elsewhere → this makes the
   number an upper bound".
4. **The arithmetic** — the actual chain with intermediate numbers
   (computed in Python at build time and embedded; JS never re-derives math).
5. **See the rows** — a real sample (≤20 rows) of the underlying transactions
   or holdings, with a count of the total ("20 of 4,214").

All derivation content is precomputed into the data embed as a `working`
object per exhibit: `{inputs:[{label,value}], rule:str,
assumptions:[{text,bias}], steps:[{label,value}], sample_rows:[...],
sample_of:int, honesty:"exact|estimate|upper bound|floor"}`.

Interaction defaults (per the dataviz method): crosshair+tooltip on
line/area, per-mark tooltip on bars/dots/cells; `Table view` renders the
chart's data as an HTML table (accessibility + trust); legend whenever ≥2
series; never a number printed on every mark.

---

## 6. Page 1 · HOLDINGS — seven exhibits

Skeleton = the seven prompts verbatim (`docs/wealth-seven-prompts-framework.md`).
For each exhibit: data → charts → drawer. Verdict sentences are TEMPLATES —
fill numbers at build time from the same queries (never hardcode).

**Q1 · What do you actually own?**
- Data: `holdings` × `schemes` (category, AMC parsed from scheme name or
  master) + counts; funds-per-client distribution.
- Charts: (a) treemap of current value, category → AMC → fund, click to
  descend one level; (b) histogram of funds-held-per-client, median flagged;
  (c) horizontal bar: top-10 funds' share of total value.
- Verdict: "₹X cr across N funds and M fund houses. The median client holds
  K funds — and the top 10 funds hold P% of all the money."
- Drawer inputs: holdings row count, value sum; rule: "current value per fund
  = units × latest NAV, summed"; honesty: `exact`.

**Q2 · Do the labels tell the truth?**
- Data: `fund_label_check` (join value from `holdings`).
- Charts: (a) per-category stacked horizontal bar of where money ACTUALLY
  sits per SEBI-cap data, off-mandate slice in warning tone; (b) offenders
  table: funds ranked by % outside label, ₹ affected; (c) stat tile "₹X cr
  sits in funds whose name doesn't match their contents".
- Honesty: `exact` (portfolio-disclosure based); note the disclosure month.

**Q3 · How much is duplicated?**
- Data: pairwise overlap for the top ~15 funds by book value — compute at
  build time with the SAME function `build_overlap.py` uses (import it; do
  not reimplement); clusters where overlap > threshold — reuse whatever
  duplicate threshold `build_overlap.py`/`build_cut_list.py` already apply;
  if you must introduce a new one, put it in `atlas_thresholds` (category
  `wealth`) and flag the chosen value in the PR body for FM sign-off.
  Evidence stocks from `client_stock_exposure` aggregated to fund level.
- Charts: (a) overlap heatmap top-15×top-15 (% common holdings, sequential);
  (b) cluster panel: "these 6 funds are effectively one" + the stock-level
  evidence table (each cluster fund's weight in HDFC Bank, ICICI, Infosys…);
  (c) KPI tiles: median overlap among held pairs, # pairs >50%, ₹ duplicated.
- This exhibit's evidence table is the persuasion core — do not summarize it
  away.

**Q4 · What do you actually pay?**
- Data: fees logic lives in `build_audit_packs.py` (fees section) — locate
  it, reuse it, roll up to book level. If TERs are category-estimates rather
  than per-scheme actuals, the assumption card MUST say exactly that, and the
  honesty chip is `estimate`.
- Charts: (a) hero figure: ₹X cr per year; (b) dumbbell per category:
  regular-plan vs direct-plan annual cost (ONLY if direct TERs exist in the
  data — otherwise render the honest empty state naming the missing feed);
  (c) 10-year projected cost line, assumption card visible by default (flat
  value, today's TERs) — this exhibit is where readers should FIRST meet the
  assumption-card pattern.

**Q5 · Does it beat the benchmark?**
- Data: `fund_performance` (full_period_pct, beat_count/windows,
  dn_capture_pct, verdict, benchmark_note).
- Charts: (a) diverging bar strip, one bar per fund: excess vs ITS OWN
  benchmark, sorted; (b) consistency heatmap: fund × rolling window,
  beat/miss; (c) tiles: "X of Y funds beat their benchmark over 3y",
  "₹Z cr sits in chronic laggards".
- Include `benchmark_note` in tooltips (which index each fund is judged
  against — transparency).

**Q6 · Is anything bloated?**
- No factsheet/SID feed exists. Render a compact honest card: the question,
  what data would answer it (manager load, AUM growth, turnover), and "we
  don't guess". NO invented proxy. Small — a third of an exhibit's height.

**Q7 · What would we cut?**
- Data: `cut_list` (rule, evidence, action, est_value, basis).
- Charts/blocks: (a) the list with evidence chips (`off-label` ·
  `duplicate` · `laggard` · `expensive`), each chip an anchor link to the
  exhibit above that proved it; (b) before→after dumbbells: # funds, ₹
  fees/yr, median overlap; (c) consolidation flows: cut fund → kept fund
  (simple from→to list or thin sankey).
- Verdict: "Cutting N of M funds — every reason shown above — saves ₹X/yr
  in fees and removes P% duplication."

**Client index (bottom of page):** searchable table, one row per client:
name → `#client/<id>`, value, # funds, flag cells (off-label ₹>0 · any pair
overlap>threshold · holds a chronic laggard · fees `estimate` above
category median). Flag thresholds from `atlas_thresholds`. Segment filter
chips above (from `client_segments`) — this replaces the old #cohort page.

---

## 7. Page 2 · BEHAVIOUR — five exhibits

**B1 · Did the advice beat the index?**
- Data: `client_benchmark` (per-client alpha, xirr pair, first_flow),
  book equity curve from `client_curves` summed (with coverage honesty),
  index path from the benchmark NAV series `exact_benchmark.py` uses.
- Charts: (a) emphasis line: book value path (accent) vs same-cashflows-in-
  index path (gray) — coverage note visible; (b) histogram of 212 per-client
  outcomes (pp/yr vs index), diverging around 0, median line at +3.8, count
  labels "173 beat · 39 lagged"; (c) scatter: outcome vs years with the firm
  (tenure = today − first_flow).
- UI language: "extra growth vs the index, per year" — NEVER the banned word.

**B2 · What investors cost themselves**
- Data: `behaviour_gap` aggregated per client (invested-weighted) and to book.
- Charts: (a) dumbbell: what the funds returned vs what investors actually
  got (invested-weighted, −1.32pp gap highlighted); (b) two stacked panels
  sharing one time axis (NOT dual-axis): index level above, monthly net
  client inflows below — money visibly arrives at peaks; (c) per-client gap
  histogram diverging around 0.
- Drawer rule: "money-weighted return uses your actual deposit/withdrawal
  dates; time-weighted is what the fund did. The difference is timing."

**B3 · The panic pattern**
- Data: drawdown windows via `behaviour_fingerprints.py`'s own logic
  (IMPORT it; if not importable, refactor its window function into
  `engine_common.py` and have both callers use it — never a second
  implementation); weekly net flows from `transactions`; `client_behaviour`
  for tallies; SIP stream starts/stops from the fingerprint engine's
  detector (same reuse rule).
- Charts: (a) crisis anatomy: index drawdown area on top, weekly net client
  flow diverging bars below (red = net selling), shared time axis, crisis
  windows shaded and labeled (2008 / 2011 / 2013 / 2020 / 2022…);
  (b) client × crisis heatmap: % of each client's lifetime exits that
  happened inside each window (sequential; sort clients by total);
  (c) SIP lifeline: monthly SIP starts (up) vs stops (down) with the same
  windows shaded — "781 stopped; 331 of those during a crash".
- Tiles: ₹27.8cr sold below cost · ₹23.8cr dividend leakage (recompute).

**B4 · Was each switch worth it?**
- Data: `advice_ledger` (per-switch fwd verdicts), `advice_waves`.
- Charts: (a) diverging stacked bars centered on neutral: switches judged at
  1y and at 3y (good | neutral | bad) with ₹ net impact tiles; (b) push
  waves: weekly switch counts over time, the 992 waves highlighted, Aug-2020
  Banking&PSU wave annotated by name; (c) waves vs one-offs: two diverging
  bars comparing forward outcome of coordinated waves vs individual switches.
- Drawer rule: "a switch = a sell and a buy within N days (read the exact
  pairing rule from `advice_ledger.py` and quote it faithfully); judged by
  comparing what the money did vs what it would have done if left."

**B5 · The what-if machine** (the flagship transparency piece)
- Data: `counterfactuals` (per-client cf_index_rs / cf_no_panic_rs /
  cf_sip_alive_rs + input tallies), summed to book; per-what-if path series
  computed at build time by reusing `counterfactuals.py` logic for the book
  aggregate (if per-month paths are too heavy, chart actual-vs-what-if END
  states as paired bars per era and keep the twin-path chart for the
  client-level version — but derivation chain is mandatory either way).
- One sub-exhibit per what-if — `no-panic +₹181cr (upper bound)` ·
  `SIP-alive +₹67cr (estimate)` · `index-everything −₹129cr (estimate;
  negative = the book BEAT indexing)`:
  - (a) twin paths (actual accent vs what-if dashed, divergence shaded, end
    gap labeled);
  - (b) **assumption card rendered ABOVE the headline number**, honesty chip
    on the number itself. Derive the assumption text by READING
    `counterfactuals.py` — the card must state what the code does (e.g.
    "we assume panic-sold units were simply held to today; proceeds NOT
    reinvested elsewhere → upper bound");
  - (c) derivation chain with real intermediates (e.g. "4,214 panic sells ·
    ₹X cr proceeds · units at sale-date NAV · valued at today's NAV = ₹Y cr;
    actual outcome ₹Z cr; gap ₹181 cr") expandable to sample rows;
  - (d) top-10 contributing clients (horizontal bar, names linked).

**Client index (bottom):** same component as Page 1, behaviour columns:
extra growth vs index (pp/yr), panic share, SIPs stopped, gap (pp/yr).

---

## 8. Page 3 · CLIENT 360 (`#client/<id>`)

One client, every slice, same bifurcation. Reuse `audit_packs` content
(including its validated narration paragraphs) inside the new layout.

1. **Header strip**: name, family group, "with the firm since YYYY",
  put in / taken out / worth now / "grew at N% a year" (from
  `client_benchmark`, plain words), segment chip.
2. **Timeline** (full width): monthly value area vs cumulative net-invested
  line (`client_curves`), event markers from `client_curve_events`
  (`select distinct kind` first; legend from real kinds), crisis windows
  shaded. Reuse the SAME insufficient-history rule the current app applies
  (find it where `build_equity_curves.py` output is consumed in the current
  builder — the convention is coverage below ~70% renders as "insufficient
  NAV history (covers N%)" instead of a pretend curve).
3. **Their holdings — the seven questions scoped to them**: funds table
  (value, category, per-fund verdict from `fund_performance`); label check
  hits; **sector look-through**: horizontal bars of their equity exposure by
  sector via `client_stock_exposure → atlas_foundation.instrument_master`,
  with the coverage line "sector identified for N% of look-through value;
  rest: ETF units / debt / cash / unidentified" (per §2.3 ≈67% book-wide —
  compute per client); their fund-pair overlap heatmap
  (`client_fund_overlap`); their fees (audit-pack fees section, honesty
  chip); their cut list with evidence chips.
4. **Their behaviour**: their crisis flows strip (sells marked inside shaded
  windows); their switch history and verdicts; their SIP streams
  (active/stopped, stops-in-drawdown flagged); dividend leakage tile.
5. **Their what-ifs**: the three counterfactual values for THIS client with
  the same assumption cards + twin paths (client-level paths ARE feasible
  from `client_curves` + engine logic), each with `how? ▾`.
6. Every exhibit here uses the SAME `exhibit()` renderer and drawer grammar.

---

## 9. New data work (build-time queries only — no new tables)

- **D1 sector rollup** (book + per client): join
  `client_stock_exposure.instrument_id = instrument_master.instrument_id`
  (verify the join key by `\d atlas_foundation.instrument_master`), sum
  exposure by sector; carry unidentified/debt/cash buckets explicitly;
  emit coverage %.
- **D2 book rollups**: fees/yr; label-lie ₹; overlap pairs of top-15 funds;
  funds-per-client distribution; weekly net flows; monthly inflows vs index;
  SIP start/stop series; per-client outcome histograms. Each lives in
  `capability_app/data.py` as one function returning plain dicts through the
  existing `_f()` JSON hygiene.
- **D3 derivation payloads**: every exhibit's `working` object (§5) filled
  from the SAME query results + engine-mirrored assumption text.
- **D4 do NOT build**: churn/CLV surfaces (`churn_*`, `client_churn_risk` —
  FM-gated); anything needing factsheet/SID (Q6); per-client volatility
  (no source); per-fund tax attribution (no scheme_id on `client_flags`).

---

## 10. Code layout (replaces the 1,966-line single file)

```
scripts/wealth/capability_app/
  __init__.py
  data.py          # all SQL + rollups + working-payloads  (<600 LOC; split data_holdings.py / data_behaviour.py if needed)
  render.py        # page shells, exhibit() renderer, nav, client index
  page_holdings.py # exhibit specs Q1–Q7
  page_behaviour.py# exhibit specs B1–B5
  page_client.py   # Client 360
  assets/app.css   # tokens + layout (read at build, inlined)
  assets/charts.js # SVG chart kit (see below)
  assets/app.js    # router, drawers, tooltips, table-view, search/filter
scripts/wealth/build_capability_app.py   # thin CLI shim → capability_app (keeps run_wealth_engine.sh + validator interfaces)
```

> **As-built note (Task 7):** `assets/app.js` was never built as a separate
> file — no task in the plan's decomposition ended up owning it. Router,
> drawers, tooltips, and search/filter live inline (native `<details>`,
> anchor-scroll, inline `oninput`) across `assets/charts.js` and the page
> templates instead. This ships fine — all gates pass, zero console errors
> across all five routes — because a client-side router adds complexity with
> no benefit when every page ships in one self-contained HTML blob anyway.
> Flagged by the final whole-branch review so a future reader doesn't go
> looking for a file that was deliberately never built.

`assets/charts.js` — one small hand-rolled SVG kit, no dependencies, exactly
these forms: treemap, histogram, horizontal bar, diverging bar strip,
diverging stacked bar, dumbbell, heatmap, line/area (with series emphasis +
shaded windows + event markers), scatter, stacked-shared-x panel pair, stat
tile/hero. Each takes `(el, data, opts)` and reads colors from CSS custom
properties (never hardcoded hex in JS). Salvage the current app's SVG/curve
helpers where they fit.

Data embed stays ONE `<script id="data" type="application/json">` block;
`_f()` rounding discipline and en-IN lakh/crore formatting are kept.

---

## 11. Design language + chart rules

Tokens (FM-locked, keep): warm paper `#FAF7F1` light / dark mode equivalent,
ink text, peacock `#0E5A6D` accent, Georgia/serif for big numerals,
`font-variant-numeric: tabular-nums`, generous whitespace, light+dark both
first-class.

Chart rules (from the `dataviz` skill — the builder session should load that
skill before writing `charts.js`):
- ONE axis per chart, never dual-axis (the crisis-anatomy and inflow-timing
  visuals are two stacked panels sharing an x-axis, each with its own y).
- Sequential (one hue, light→dark) is the default; categorical ONLY when
  series identity is the subject (≤7 series, fixed hue order, never cycled);
  diverging (two hues + neutral gray midpoint) only for above/below zero;
  emphasis (accent + gray) for book-vs-index.
- Status/warning colors reserved for genuine state (off-label slice, bad
  switches); never used as "series 4".
- Legends for ≥2 series; direct labels selectively; text in ink tokens,
  never in series color; recessive grids.
- Validate the final categorical/status palette with the dataviz skill's
  `scripts/validate_palette.js` in BOTH light and dark modes against the
  actual surface colors; fix FAILs before shipping.
- Every chart: hover tooltip + `Table view`. Hero numbers are stat tiles,
  not one-bar charts.

---

## 12. Validation, testing, CI

**Gate 1 — `validate_wealth_app.py`** (extend, never weaken):
- keep: banned-word walk over all renderable strings; size report; data-embed
  extraction.
- update: route list → `#holdings`, `#behaviour`, `#client/<id>` (headless
  Chromium route checks; env `GSTACK_CHROMIUM_NO_SANDBOX=1`, and copy the
  HTML under `/tmp` first — sandboxed Chromium can't read `~`).
- add: (a) every exhibit id present on its page; (b) every exhibit has a
  non-empty `working` object with all five parts; (c) every headline number
  string in the HTML also exists in the data embed (no JS-invented numbers);
  (d) zero occurrences of deleted routes (`#book`, `#calls`, `#cohort`,
  `#segment/`, `#guide`).

**Gate 2 — real-DB tests** (`tests/wealth/`, run
`.venv/bin/python -m pytest tests/wealth/ -x -q` with `.env` sourced; they
hit the live DB per Rule #0 and are NOT in the CI `-m unit` sweep):
- keep all existing tests green. KNOWN pre-existing failure:
  `test_audit_packs` (upsert-vs-computed drift) — do not chase unless your
  changes touch audit packs; do not delete it.
- add `tests/wealth/test_capability_data.py`: for each data.py rollup, assert
  the embedded aggregate equals an independent SQL aggregate computed in the
  test (e.g. book fee total, label-lie ₹, counterfactual book sums, sector
  rollup total = sum of identified exposure; coverage % in [0,100]).
- add `tests/wealth/test_working_payloads.py`: every exhibit's `working`
  passes shape checks; every assumption entry has a bias direction; honesty
  chip ∈ the four allowed values; `sample_rows` are real rows re-fetchable
  from `wealth.transactions`/`holdings` by their ids.
- extend `test_capability_app_data.py` conventions (read it first) for the
  new embed keys.

**Gate 3 — repo CI** (required check "Lint, types, unit tests"): run locally
before pushing — `ruff check scripts/wealth tests/wealth`,
`ruff format --check`, the pyright ratchet, and the repo unit sweep, exactly
as `.github/workflows/` defines them. `pyproject.toml` already carries
`extraPaths` + baselined pandas-stubs noise for `scripts/wealth` — keep the
ratchet at or below baseline.

**Gate 4 — eyes on it**: headless-browse all three routes plus THREE real
clients (one high-coverage curve, one <70% coverage, one flagged panic
seller); screenshot each; check label collisions, dark mode, empty states.
The dataviz validator checks color, not layout — you must look.

---

## 13. Definition of done

1. `run_wealth_engine.sh` end-to-end green (engines untouched, app+validator
   rebuilt) producing `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html` ≤8MB.
2. All four gates in §12 pass; palette validator passes light+dark.
3. Grep the built HTML: zero `#book|#calls|#cohort|#segment/|#guide`, zero
   banned words, `wrap`-cap removed.
4. The ₹55cr-class complaint is dead: pick any headline number on any page
   and its `how? ▾` shows inputs→rule→assumptions→arithmetic→rows without
   leaving the exhibit.
5. Branch `feat/wealth-glass-box` pushed; PR opened to `main` titled
   `feat(wealth): glass-box three-page redesign (holdings/behaviour/client-360)`,
   body summarizing §3's route changes + gate evidence. CI green.
6. **Artifact republish is FM's step** (real-name PII pages are
   classifier-blocked for agent republish). Note in the PR: "FM: republish
   `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html` to the
   existing artifact URL
   (`https://claude.ai/code/artifact/b46282fc-d9db-441f-aaa4-c9356cf1c208`)."

## 14. Out of scope / do-not

- No new tabs/routes beyond the three; no typeform/stepper; no scroll-snap.
- No new DB tables/schemas; no synthetic or proxy numbers anywhere; no
  churn/CLV UI; no Q6 guessing; no per-client volatility metric.
- No CDN/fonts/images/external requests; no chart libraries.
- Don't touch `atlas/`, `frontend/`, `migrations/`, crontabs, pm2, or the
  Atlas board deploy — this app is a standalone HTML artifact.
- Don't "fix" the two accepted honest gaps (aggregate-FY tax note;
  growth×panic scatter instead of risk-return) — reviewer-ruled correct.
- Don't rewrite engines. If an engine function needs to be importable,
  refactor it INTO `engine_common.py` (both callers share one truth) —
  that's the only engine edit allowed.

## 15. Build order (each phase ends green before the next)

- **P0** Bootstrap worktree (§2.1); read §2.2 files; `\d` the tables you'll
  query; run the existing pipeline once to confirm a green baseline.
- **P1** `capability_app/data.py`: all rollups + working payloads + embed
  contract; `test_capability_data.py` + `test_working_payloads.py` green.
- **P2** `assets/charts.js` + `app.css` tokens + palette validation (both
  modes); a scratch page rendering every chart form from real embed data;
  eyeball it.
- **P3** Page HOLDINGS (Q1–Q7 + client index) + validator route update;
  gates 1–2 green.
- **P4** Page BEHAVIOUR (B1–B5 + client index); gates green.
- **P5** CLIENT 360; gates green.
- **P6** Full §12 sweep incl. CI + screenshots; commit series
  (`feat(wealth): …` per phase is fine); push; open PR; write the FM
  republish note. Done means §13, all six items.
