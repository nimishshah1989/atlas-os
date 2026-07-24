# Wealth Capability App v2 — Client 360°, Cohort Dashboard, Guide, Seven-Prompt MF Overview

**Execute with:** superpowers:subagent-driven-development. Resume ledger at
`.superpowers/sdd/progress.md`. Branch: `feat/intraday-cross-eod-fill` (v1 lives here,
commits `cbd458b5..4cecdd35`).

**Spec:** `docs/superpowers/specs/2026-07-23-wealth-360-cohort-guide-design.md`
**Framework:** `docs/wealth-seven-prompts-framework.md` (the Stockizen 7 prompts, verbatim + engine mapping)

**Goal:** Turn the shipped v1 app (chapters + calls + 8-section client audit) into the full
management demo: Client 360° "Kundli", cohort dashboard with Atlas-style drill
(cohort→segment→client), a layman guide, and the funds audited under the seven-prompt
framework. One artifact, same URL (`b46282fc-...`), same design language.

## Global Constraints (bind every task)

- **Rule #0:** no synthetic/derived data anywhere incl. tests — every test reads real rows
  from the live DB and asserts on real computed output. Derived numbers need explicit FM OK.
- Money = `numeric` in DB; python `Decimal` for tax/money math; float OK for display aggregates.
- Every derived table: `drop table if exists` (EXCEPT audit_packs which upserts — see v1) +
  create + `revoke all ... from anon, authenticated`.
- **Language rules (UI + narration):** never XIRR/alpha/disposition/PGR/PLR/counterfactual;
  use "yearly growth", "ahead of/behind an index fund", "sells winners keeps losers", "what-if".
  No table visible without opening an expander. The app validator's banned-word gate enforces this.
- Coverage honesty: where a source is partial (fund NAV <5y, no benchmark, no ER), show an
  honest insufficient/caveat line — never fake a number. Follow the v1 pattern (T2 coverage_note).
- **Thresholds** live in `atlas_foundation.atlas_thresholds` (category 'wealth'), seeded
  idempotently — see `wealth_drawdown_armed_floor_pct` precedent in build_call_lists.py.
- Env: `set -a; source .env; set +a; .venv/bin/python ...`. Tests: `pytest tests/wealth/test_X.py -v`.
- Commit only each task's own files. Unrelated dirty tree (mean-reversion) must stay untouched.

## Model assignments

| Tasks | Implementer | Reviewer |
|---|---|---|
| 1, 2 (prompt-5/7 financial engines) | **Opus 4.8** | **Opus 4.8** |
| 3–8 (segments, curves, app data, 360°, cohort, guide) | Sonnet 5 | Sonnet 5 |
| Final whole-branch review | — | Opus 4.8 |

---

## Task 1: Fund-performance engine — Prompt 5 (`build_fund_performance.py`) · OPUS

**Files:** create `scripts/wealth/build_fund_performance.py`, `tests/wealth/test_fund_performance.py`.

**Consumes:** `atlas_foundation.de_mf_nav_daily` (mstar_id, nav_date, nav — 2006→now, 2.4M rows,
122 held funds have ≥5y), `atlas_foundation.de_mf_master.primary_benchmark`,
`atlas_foundation.index_prices` (index_code, date; NSE price-return, 2000→now),
`wealth.schemes` (held equity funds, mstar_id), `behaviour_fingerprints.drawdown_windows`.

**Produces:** `wealth.fund_performance(scheme_id bigint primary key, mstar_id text,
roll_3y_pct numeric(8,2), roll_5y_pct numeric(8,2), dn_capture_pct numeric(8,2),
best_year_stripped_pct numeric(8,2), full_period_pct numeric(8,2), beat_count int,
windows int, benchmark_note text, verdict text)`. One row per held equity fund.

**Logic (Decimal/careful — this is why it's Opus):**
- roll_3y/5y = annualised CAGR over trailing 3y/5y from NAV series (calendar-anchored, not
  point-to-point off a single day — average of rolling windows).
- dn_capture = fund's return in the 3 worst drawdown windows ÷ NIFTY 50's return in those
  windows (reuse drawdown_windows + index_prices NIFTY 50). <100% = protected on the downside.
- best_year_stripped = full-period annualised return with the single best rolling-12m window
  removed, vs full_period — the "one lucky year" test.
- benchmark legs (beat_count over 20 rolling windows, excess return): map primary_benchmark →
  nearest index_code. **These are NSE price-return vs the funds' TR benchmarks** → set
  `benchmark_note` = "approx: price-return index, not the fund's total-return benchmark" and
  keep them clearly separate from the NAV-only legs. Funds with no mappable benchmark: benchmark
  legs NULL, note explains; NAV-only legs still computed.
- Funds with <5y NAV: verdict='insufficient_history', roll_5y NULL, note explains.

**Test (real DB, RED first):** a known ≥5y large-cap fund has roll_3y/roll_5y > 0 and
dn_capture computed; a fund with <5y history gets verdict='insufficient_history'; best_year_stripped
< full_period for a fund carried by one year (assert the relationship holds for a sampled real fund,
not a magic number); no NaN/Inf in any numeric column.

**Steps:** RED test → implement → GREEN → run engine (expect ~122 funds scored, rest insufficient) →
spot-read 3 funds' rows for plausibility → commit `feat(wealth): fund-performance engine (prompt 5)`.

## Task 2: Cut-list engine — Prompt 7 (`build_cut_list.py`) · OPUS

**Files:** create `scripts/wealth/build_cut_list.py`, `tests/wealth/test_cut_list.py`.

**Consumes:** `wealth.client_fund_overlap` (pairwise %, T1 v1), `wealth.fund_label_check`
(mismatch), `wealth.client_scorecard` (laggard/grade), `atlas_foundation.fund_rank_daily`
(bottom-quartile), `wealth.lots` (tax_if_sold_now, holding_days, tax_bucket, unrealized_gain),
`wealth.holdings`, `wealth.fund_performance` (T1, weak-performer signal).

**Produces:** `wealth.cut_list(client_id bigint primary key, keep jsonb, cut jsonb,
min_fund_count int, note text)`. `cut` = [{fund, reason, exit_tax_rs, unwind_order}], `keep` =
[{fund, evidence}].

**Logic (design judgment — why it's Opus):**
- redundant funds = those in >50% overlap pairs that add the LEAST new exposure (the fund in
  each pair with more overlap into the rest of the portfolio) ∩ weak (label mismatch OR
  bottom-quartile fund_rank OR poor fund_performance).
- min_fund_count = greedy set-cover: smallest fund subset whose combined look-through stock
  weights cover ≥X% of the current portfolio's exposure (define X in code, document it).
- unwind_order = among cut funds, ascending `lots.tax_if_sold_now` (sell the cheapest-to-exit
  first). exit load: inferred 0 where all lots holding_days>365, else flag "exit load may apply".
- Evidence-gated: a client with no >50% pairs and no weak funds → cut=[], note="nothing to cut —
  portfolio holds genuinely different bets" (the "say so plainly" rule).

**Test (real DB, RED first):** a client with known heavy overlap (from client_fund_overlap) gets
a non-empty cut list with ascending exit_tax unwind_order; a well-diversified client gets cut=[]
with the plain-language note; every cut fund's exit_tax_rs matches an independent SQL sum over
that client×scheme's lots; min_fund_count ≤ the client's actual fund count.

**Steps:** RED → implement → GREEN → run (report cohort: how many clients have ≥1 cut candidate) →
spot-read 3 clients → commit `feat(wealth): cut-list engine (prompt 7)`.

## Task 3: Segmentation engine (`build_segments.py`) · SONNET

Per spec §"build_segments.py". `wealth.client_segments(client_id PK, segment, reason,
whatif_rs, traits jsonb)`. One primary segment per client (precedence: Too New → dominant-cost
{Crash Seller/Dividend Spender/SIP Quitter} above `wealth_segment_material_cost_rs` floor
[seed ₹50k idempotent] → Drifted Away → Steady Compounder), counts sum to 242. traits = independent
chips. Test: sum invariant; known crash-seller → Crash Sellers; no-history → Too New; whatif_rs
matches independent SQL for a sampled client. Commit `feat(wealth): behaviour segmentation engine`.

## Task 4: Equity-curve engine (`build_equity_curves.py`) · SONNET

Per spec §"build_equity_curves.py". `wealth.client_curves(client_id, month, value_rs, net_flow_rs,
coverage_pct)` + `wealth.client_curve_events(client_id, event_date, kind, amount_rs, note)`
(kinds: panic_sell / sip_stop / big_inflow / big_outflow). Month-end value = units held ×
month-end NAV (nav_series), mapped schemes only; coverage_pct honest; <70% flagged insufficient.
Events trace to real txns; panic_sell inside drawdown_windows. Test: sampled client's final point ≈
current holdings MV × coverage; no negative values; every event has a matching real txn; a known
panic-seller has ≥1 panic_sell event in a shaded window. Commit `feat(wealth): monthly equity curves + story events`.

## Task 5: App data-layer widening + orchestrator wiring · SONNET

Widen `build_capability_app.py` embed per client (holdings w/ quality tint from fund_rank_daily,
client_scorecard, client_flags actions, client_churn_risk, client_stock_exposure top-10, segment
row, curve series+events, fund_performance per held fund, cut_list). Bin cohort data in Python at
build (histograms, segment aggregates, scatter, waterfall). Byte gate stays <6MB — if over,
quantize curves to whole ₹ + drop net_flow first. Add `build_segments`, `build_equity_curves`,
`build_fund_performance`, `build_cut_list` to `run_wealth_engine.sh` (after build_household, before
build_audit_packs for segments/curves; fund_performance + cut_list before build_audit_packs too so
packs can reference them). Test: embed parses, <6MB, all new per-client keys present for a sampled
client. Commit `feat(wealth): widen app data layer + wire new engines into orchestrator`.

## Task 6: Client 360° rebuild — the Kundli · SONNET

Per spec §"#client/<id>". Rebuild the client route into the 8-part Kundli: identity band (segment
chip → segment page) → story curve (inline SVG, drawdown shading + panic dots + SIP stops + flow
ticks + coverage note) → the floor (holdings grouped by asset class w/ quality tint + label verdict,
allocation donut, overlap dial + worst pairs) → **what they did right** (wins w/ ₹) → **areas of
improvement** (behaviour costs) → **changes we recommend** (scorecard grade + gate verdict, then
actions each w/ verb-first / ₹-why-evidence / TAX implication from lots+tax_harvest) → **seven-prompt
MF overview** (per-fund expander: prompt 2 label + prompt 5 performance; portfolio panel: prompt 3
overlap + prompt 7 cut list; prompt 1 map + prompt 4 fees/closet-index presented — NO reg-vs-direct)
→ audit expanders (the 8 v1 sections as proof). Language rules hold. Visual gate: screenshot both
themes 1280+390px, READ them. Commit `feat(wealth): client 360 Kundli + seven-prompt MF overview`.

## Task 7: Cohort dashboard + segment drill · SONNET

Per spec §"#cohort" + "#segment/<key>". `#cohort`: headline band, segment bar (sums to 242, ₹
what-if, clickable), 6 histograms w/ median markers, behaviour-cost waterfall, churn×book scatter
(valuable-and-at-risk quadrant), call-list funnel. `#segment/<key>`: segment mini-dashboard
(behaviour profile, risk-return profile, book share, ₹ what-if) + client list → `#client/<id>`.
Atlas-style drill cohort→segment→client. Visual gate: screenshot both themes 1280+390px, READ.
Commit `feat(wealth): cohort dashboard + segment drill`.

## Task 8: Guide page + final run/validate/publish · SONNET

Per spec §"#guide" (simplified): card per engine (12) — one plain sentence + 3–4 layman bullets
(what it read / what it did / what it found tonight w/ the number) + collapsed technical expander;
SVG pipeline flowchart; replication note; honesty box (deterministic + validated narration, no
fitted ML). Extend `validate_wealth_app.py` browse gate with `#cohort`, `#guide`, `#segment/<key>`
routes (banned-word + byte gates unchanged). Run full `run_wealth_engine.sh` end-to-end; validate
ALL GREEN; republish to existing URL (b46282fc-...) via Artifact same file path. Commit
`feat(wealth): guide page + v2 validation + shipped`.

## Then: final whole-branch review (Opus) over v1+v2, address Critical/Important, then finishing-a-development-branch (PR).
