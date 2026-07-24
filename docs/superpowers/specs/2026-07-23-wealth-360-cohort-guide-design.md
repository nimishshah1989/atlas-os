# Wealth capability app v2 — Client 360°, Cohort Dashboard, Guide

Date: 2026-07-23 · Status: FM-approved (brainstorm in session) · Extends: `2026-07-23-wealth-capability-demo-design.md`

## Goal

Turn the shipped capability app (chapters + calls + client audit pages) into the full
management demo: a **client 360°** that shows a client's whole life with the book, a
**cohort dashboard** that segments all 242 clients and prices their behaviour, and a
**guide** that explains every engine in layman's terms. One artifact, same URL, same
design language (warm paper / ink / peacock, serif big numbers, tabular-nums).

All numbers real (Rule #0). All new derived tables: `atlas_foundation`-style hygiene
(revoke anon/authenticated). Language rules unchanged (no XIRR/alpha/disposition/
PGR/PLR/counterfactual in UI text; "yearly growth", "ahead of/behind an index fund").

## New engines

### 1. `build_segments.py` → `wealth.client_segments`

One row per client: `client_id bigint PK, segment text, reason text, whatif_rs
numeric(18,0), traits jsonb`.

Primary segment — precedence order, first match wins:
1. **Too New to Tell** — insufficient history (no behaviour fingerprint AND no benchmark row).
2. Dominant ₹ cost among {panic loss (`client_behaviour.panic_loss_out_rs`), dividend
   leak (`div_leak_rs`), dead-SIP what-if (`counterfactuals.cf_sip_alive_rs`)} when the
   max ≥ materiality floor → **Crash Sellers** / **Dividend Spenders** / **SIP Quitters**.
   Floor lives in `atlas_thresholds` (`wealth_segment_material_cost_rs`, seed ₹50,000,
   idempotent insert like `wealth_drawdown_armed_floor_pct`).
3. **Drifted Away** — disengagement (no fresh money ≥ 12m + SIPs stopped, per
   call-lists' disengaged basis) with no dominant cost above floor.
4. **Steady Compounders** — everyone else.

`whatif_rs` = sum of the client's ≥0 cost components (upper bound, labelled — same
semantics as `value_statements.coaching_opportunity_rs`). `traits` = independent chips:
crash_seller, chaser (`chase_hot_share ≥ 0.25`), div_spender, sip_quitter, disengaged,
high_churn_risk (top-quartile churn score). Chasers stay a trait (no ₹ cost column
exists for chasing); do NOT invent one.

Counts across segments must sum to the number of clients in scope. Tests (real DB):
sum invariant; a known crash-seller (top panic_loss client) lands in Crash Sellers; a
client with no fingerprint+benchmark lands Too New; whatif_rs matches an independent
SQL sum for a sampled client.

### 2. `build_equity_curves.py` → `wealth.client_curves` + `wealth.client_curve_events`

`client_curves(client_id, month date, value_rs numeric(18,0), net_flow_rs
numeric(18,0), coverage_pct numeric(5,2))` — month-end portfolio value: units held per
mapped scheme (from `wealth.transactions`) × month-end NAV (`engine_common.nav_series`).
Coverage honesty: `coverage_pct` = share of current book MV in mapped schemes with NAV;
clients < 70% coverage get curves flagged insufficient in the app (no fake curves).
Series starts at first transaction, monthly, ≤ ~360 points/client.

`client_curve_events(client_id, event_date, kind, amount_rs, note)` — kinds:
`panic_sell` (sell inside a drawdown window — reuse `behaviour_fingerprints.
drawdown_windows`), `sip_stop` (stream's last SIP), `big_inflow`/`big_outflow`
(|flow| ≥ client's p90). Every event traces to real transactions.

Tests (real DB): sampled client's final curve point within tolerance of current
holdings MV × coverage; no negative values; every event date has a matching real txn;
a known panic-seller has ≥1 panic_sell event inside a shaded window.

### 3. App data layer widening (in `build_capability_app.py`)

Embed per client: holdings rows (fund, asset class, mv, label verdict, Atlas quality
tint from `fund_rank_daily` composite via scheme mstar_id — reuse `build_scorecard`'s
join), `client_scorecard` row (outcome grade, gate verdict, laggard share),
`client_flags` actions (rule, action, est_value, evidence), `client_churn_risk`,
top-10 `client_stock_exposure`, segment row, curve series + events. Cohort data is
**binned in Python at build time** (histogram buckets, segment aggregates, scatter
points, waterfall components) — testable, and keeps the embed small. Byte gate stays
6 MB; builder prints the size; if over budget, curves quantize to whole ₹ and drop
`net_flow_rs` from the embed first.

## Frontend

### `#client/<id>` — the 360° "Kundli" (rebuilt; FM's five-part structure)

1. **Identity band**: name, household chip, segment chip (→ that segment's page),
   tenure, book ₹, churn-risk gauge, freak-out score.
2. **Story curve** (centerpiece, inline SVG): monthly value line; drawdown windows
   shaded; panic-sells as crit-coloured dots; SIP stops marked; big flows as ticks;
   coverage note when < 100%. No ghost line (deferred by FM choice).
3. **The floor**: holdings table grouped by asset class (fund · mv · label verdict ·
   quality tint), allocation donut, overlap dial + worst pairs.
4. **What they did right** (wins, explicitly celebrated with ₹): SIPs kept alive in
   crashes, holding through falls, ahead-of-index years — from value_statements'
   realized components + behaviour data. Every client gets their genuine wins first.
5. **Areas of improvement**: behaviour costs with the habit named and priced
   (panic, dividend leak, dead SIPs, chasing) — from segments/behaviour tables.
6. **Changes we recommend — with WHY and TAX**: scorecard outcome grade +
   evidence-gate verdict sentence, then ranked `client_flags` actions, each carrying
   (a) the action verb-first, (b) the ₹ evidence for why (est_value + the evidence
   string), (c) the tax implication of making the change (from wealth.lots: bucket,
   unrealized gain, exemption headroom via tax_harvest). Gate philosophy verbatim:
   a client compounding well gets "no changes forced".
7. **Seven-prompt MF overview** (see `docs/wealth-seven-prompts-framework.md`):
   the client's funds audited under the Stockizen headings. Prompts 1–4 are
   PRESENTATION of existing data (map, label-check, overlap, fees/closet-index);
   prompts 5 & 7 are NEW ENGINES (below). Prompt 6 DROPPED (no factsheet data).
   Prompt 4 = present only (closet-index flag + ₹ annual cost where ER known);
   **regular-vs-direct dropped per FM — not shown.** Rendered as a per-fund
   expander in the holdings table (per-fund prompts 2/5) + a portfolio-level
   panel (prompts 3/7, inherently whole-portfolio).
8. **Audit expanders**: the 8 narrated sections as "how we know this" proof layer.

### NEW ENGINE — `build_fund_performance.py` → `wealth.fund_performance` (Prompt 5)

Per held equity fund with ≥5y NAV (~122 funds): rolling 3y & 5y returns
(annualised, from `atlas_foundation.de_mf_nav_daily`); downside capture in the 3
worst market falls (reuse `behaviour_fingerprints.drawdown_windows`); luck-vs-
consistency (return with best 12m stripped vs full); benchmark-relative legs
(excess vs `primary_benchmark`→NSE index, beat-count over 20 rolling windows) —
**coverage-limited & labelled**: NSE price-return vs the funds' TR benchmarks, so
the benchmark legs carry a `benchmark_note` and funds without a mappable benchmark
show the NAV-only legs as certain. Columns: scheme_id, roll_3y, roll_5y, dn_capture,
best_year_stripped_return, beat_count, windows, benchmark_note, verdict. Money math
per repo rule. **Model: Opus 4.8 implementer + Opus 4.8 reviewer** (subtle financial
correctness — annualisation, window edge cases, downside alignment).

### NEW ENGINE — `build_cut_list.py` → `wealth.cut_list` (Prompt 7)

Per client: redundant funds = those adding the least new exposure (from
`client_fund_overlap` >50% pairs) ∩ weak (label mismatch / bottom-quartile
`fund_rank_daily` / scorecard laggard); smallest fund set holding the same exposure
(greedy set-cover over the overlap graph); unwind ORDER minimising tax+load
(ascending `lots.tax_if_sold_now`; exit load inferred 0 where holding_days>365,
else flagged). Evidence-gated: a well-diversified client with no redundancy gets
"nothing to cut — say so plainly." Columns: client_id, keep jsonb, cut jsonb
(fund, reason, exit_tax, unwind_order), min_fund_count, note. **Model: Opus 4.8
implementer + Opus 4.8 reviewer** (set-cover + constrained ordering = design judgment).

### Model assignments (v2 build)

- Prompts 5 & 7 engines + their reviews: **Opus 4.8** (both implementer & reviewer).
- `build_segments`, `build_equity_curves`, all frontend (360°/cohort/guide),
  prompt 1–4 presentation: **Sonnet 5** (proven adequate on v1's 9 presentation tasks).
- Controller/planner + final whole-branch review: **Opus 4.8**.

### `#cohort` — management dashboard (Atlas-style drill: cohort → segment → client)

Top level `#cohort`: headline band (book / clients / families / realized value
delivered / coaching opportunity, labelled); **segment bar** (counts sum to 242, ₹
what-if per segment); **6 histograms** (book size, tenure, growth-gap vs index fund,
freak-out, effective bets, SIP health) with median markers; **behaviour-cost
waterfall** (panic + dividend leak + dead SIPs → total); **churn × book scatter**
(top-right quadrant highlighted "valuable and at risk"); **call-list funnel**
(segments → armed lists → tonight's 20 names, → `#calls`). Every segment element is
clickable → the segment page.

`#segment/<key>` (NEW, the middle drill tier — like Atlas's sector page): a mini-
dashboard scoped to one segment, colour-coded to that segment: its **behaviour
profile** (how these clients act — panic/chase/SIP-stop shares vs cohort), its
**risk-return profile** (their growth vs index fund, own-flow volatility, drawdown
behaviour — a small matrix/scatter), book share and ₹ what-if, then the **client list**
for the segment (name · book · the one number that put them here · churn) → each row
→ `#client/<id>`. This is the callout structure the FM asked for: cohort → segment →
client, mirroring market → sector → instrument.

### `#guide` — simplified for management

Card per engine (12: the 9 shipped + 3 new). Each card: the engine's job in one plain
sentence, then **3–4 layman bullets** — *what it read · what it did · what it found
tonight (with the number)* — no jargon. Technical detail (script name, tables,
formula) lives in a collapsed expander beneath, for anyone who wants it. Inline-SVG
flowchart: ledger → parse → engines → tables → this app. Replication note: runs for
any book with a ledger export, one command (`run_wealth_engine.sh`). Honesty box:
deterministic auditable analytics + one language layer with a number validator; **no
fitted ML** at n=242 — heuristic scores are documented as heuristics; management can
always ask "why is this client on this list?" and get a one-sentence answer.

## Validation & process

- `validate_wealth_app.py` gains routes `#cohort`, `#guide` in the browse gate;
  banned-word and byte gates unchanged and must stay green.
- Orchestrator: `build_segments` and `build_equity_curves` run after `build_household`,
  before `build_audit_packs`.
- Narration/audit-pack contracts untouched (SECTION_NAMES unchanged; audit packs still
  upsert; prose preserved).
- Artifact republish to the same URL after rebuild.
- Visual gate: screenshots of #cohort, #guide, one rebuilt #client in both themes at
  1280px + 390px, read before done.
