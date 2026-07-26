# Wealth Glass-Box Redesign — SDD Plan

Executes `docs/superpowers/specs/2026-07-24-wealth-glass-box-redesign-design.md`
(read it once yourself before dispatching Task 1 — this plan assumes it, it
does not repeat it). Worktree `~/atlas-worktrees/wealth-glass-box`, branch
`feat/wealth-glass-box` off `origin/main` (856634d8). P0 (bootstrap, spec
commit, schema read, baseline green-check) is DONE — start at Task 1 (= spec's P1).

## Global Constraints (apply to every task — paste into every dispatch and every reviewer's constraints block)

1. **Rule #0 — no synthetic data, ever.** Every number traces to a live
   `wealth.*`/`atlas_foundation.*` query at build time. Tests assert on REAL
   database output (`tests/wealth/` convention: connect via
   `engine_common.connect()`, no fixtures, no mocks). This applies to unit
   tests too — zero exceptions.
2. **Banned words** (case-insensitive regex, enforced by
   `scripts/wealth/validate_wealth_app.py`): `xirr`, `alpha`, `disposition`,
   `pgr`, `plr`, `counterfactual`. Fine as column/function names in Python;
   never in a string that reaches the HTML. Say "grew at N%/year", "extra
   growth vs index (pp/yr)", "the what-if", "sold winners / kept losers".
3. **Honesty chips.** Every assumption-bearing number carries one of exactly
   four values: `exact` · `estimate` · `upper bound` · `floor`. Any
   partial-coverage visual states its coverage inline (e.g. "sector
   identified 67% look-through value"). Where a data feed genuinely doesn't
   exist (Q6 bloat check, per-client volatility, per-fund tax attribution),
   render an honest empty state naming the missing feed — never a fabricated
   proxy. Assumption text shown in the UI must match what the engine code
   *actually does* — read the engine before writing the card text.
4. **No new DB tables, no new schemas.** All new aggregation is a build-time
   query in the app's data layer over existing tables. Adding a new *row* to
   the existing `atlas_foundation.atlas_thresholds` table is allowed and is
   the prescribed mechanism for constraint 5.
5. **No hardcoded methodology numbers.** Any new threshold (e.g. "overlap
   above X% counts duplicate") is read from `atlas_foundation.atlas_thresholds`
   (`category='wealth'`), seeded via a plain `INSERT` if missing — never a
   Python/JS literal. Existing `wealth` category rows already there (reuse,
   don't duplicate): `wealth_grandfather_date`, `wealth_tax_nonequity_ltcg_days`,
   `wealth_tax_nonequity_slab_pct`, `wealth_drawdown_armed_floor_pct` (`-0.10`),
   `wealth_segment_material_cost_rs` (`50000`).
6. **Self-contained single HTML file.** No CDN, no external fonts, no
   `fetch`, no `<img>` — inline SVG only, hand-rolled (no chart library).
   File-size limits: 600 LOC source / 800 LOC tests / 250 LOC page-shell
   files, `# allow-large: <reason>` escape valve if a file must exceed it —
   prefer splitting over the escape valve.
7. **Real client names/PII render on screen** (existing, approved
   convention) — this is why the final HTML artifact republish is FM's
   action, never the builder's.
8. **Don't touch** `atlas/`, `frontend/`, `migrations/`, crontabs, pm2, or
   the Atlas board deploy — this app is a standalone HTML artifact written to
   `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html` (≤8 MB).
9. **Don't rewrite engines.** If an engine's internal logic needs to be
   importable and isn't, the only allowed engine edit is refactoring that one
   function into `scripts/wealth/engine_common.py` so both the engine and the
   app call the same code — never a second implementation of the same logic.
10. **JSON embed contract** (exact, mirror verbatim): one
    `<script id="data" type="application/json">` blob built via
    `json.dumps(data, allow_nan=False, ensure_ascii=False, separators=(",", ":"))`,
    then `.replace("</", "<\\/")` before interpolating into the HTML.
    `_f(x)` hygiene helper (currently at `build_capability_app.py:44`, moves
    into the new package):
    ```python
    def _f(x):
        """-> float rounded, or None (never NaN/Inf — strict-JSON safe)."""
        if x is None:
            return None
        v = float(x)
        if not math.isfinite(v):
            return None
        return round(v, 4)
    ```
    Every float that reaches the embed goes through `_f()`.
11. **en-IN lakh/crore formatting** — exact client-side JS (any new
    `app.js`/`charts.js` reproduces this precisely; do not rederive):
    ```javascript
    const enIN = n => Math.round(n).toLocaleString("en-IN");
    function lcr(n){ if(n==null) return "—"; const a=Math.abs(n);
      if(a>=1e7) return "₹"+(n/1e7).toFixed(2)+" cr";
      if(a>=1e5) return "₹"+(n/1e5).toFixed(2)+" L";
      return "₹"+enIN(n); }
    function pct(n){ return n==null?"—":n.toFixed(1)+"%"; }
    // ponytail: overlap_pct has a known upstream dup-ISIN bug (max observed 192) —
    // clamp the DISPLAYED value to 100 here, never touch the underlying data.
    function ovPct(n){ return n==null?"—":Math.min(100,n).toFixed(0)+"%"; }
    ```
    Python-side mirror for build-time story text (`lcr_py`, currently at
    `build_capability_app.py:54`, moves into the new package):
    ```python
    def lcr_py(n: float) -> str:
        a = abs(n)
        if a >= 1e7:
            return f"₹{n / 1e7:.2f} cr"
        if a >= 1e5:
            return f"₹{n / 1e5:.2f} L"
        return f"₹{round(n):,}"
    ```
12. **`_degarble()`** (currently `build_capability_app.py:67`, moves into the
    new package) — strips literal "XIRR" text out of raw DB text fields
    (`client_flags.evidence`, `client_scorecard.attention_reasons`) before
    embedding, so the banned-word gate doesn't trip on data that already says
    "XIRR" in the database:
    ```python
    def _degarble(s):
        return None if s is None else _XIRR_RE.sub("yearly growth", s)
    ```
13. **FM-locked design tokens** (exact, from the current `HTML` template,
    `build_capability_app.py:824` — carry forward verbatim into `app.css`):
    ```css
    :root{
      --paper:#FAF7F1; --card:#FFFFFF; --ink:#232019; --muted:#6B6357; --line:#E7E0D4;
      --accent:#0E5A6D; --good:#256C3C; --warn:#9A6A0A; --crit:#A63A32; --soft:#0E5A6D12;
      --serif:Georgia,'Times New Roman',serif;
      --sans:-apple-system,'Segoe UI',Roboto,sans-serif;
    }
    ```
    Light default + night toggle (dark-mode overrides needed, was previously
    handled in the deleted chapters — reintroduce a `[data-theme="dark"]`
    block with equivalent dark tokens). Serious Inter/system numerals,
    `font-variant-numeric: tabular-nums`. Kill the 820–920px `.wrap` cap —
    responsive 12-col grid, max ~1600px, generous gutters.
14. **Universal exhibit `working` object** (exact shape, every exhibit,
    every page — spec §5):
    ```
    {inputs:[{label,value}], rule:str, assumptions:[{text,bias}],
     steps:[{label,value}], sample_rows:[...], sample_of:int,
     honesty:"exact"|"estimate"|"upper bound"|"floor"}
    ```
    `sample_rows` ≤20 real rows, `sample_of` = true total count (UI shows
    "20 of 4,214"). Every `assumptions[].bias` states the direction (e.g.
    "assumes proceeds NOT reinvested → upper bound"). Steps show the actual
    arithmetic chain computed in Python at build time — JS never re-derives
    math, it only renders precomputed numbers.
15. **Engine functions to import, never reimplement** (all confirmed
    importable, no `argparse`/`__main__`-only gating):
    - `scripts/wealth/engine_common.py`: `connect()` (raw psycopg2 connection,
      caller must `conn.close()`), `BENCH_ID="F0GBR06R0H"`,
      `EXTERNAL_IN=("purchase","sip")`, `EXTERNAL_OUT=("redemption","swp","div_payout")`,
      `xirr(flows)`, `nav_series(conn, mstar_id)`, `NavLookup` (`.at(date)`
      forward-fill), `external_flows(conn)`.
    - `scripts/wealth/build_overlap.py`: `latest_fund_weights(conn)` (dict
      `mstar_id -> {isin: (holding_name, weight_pct)}`),
      `pairwise_overlap(wa, wb)` (weighted min-overlap, NOT Jaccard:
      `sum(min(wa[i][1], wb[i][1]) for i in wa.keys() & wb.keys())`, rounded
      to 2dp — this is the exact "% common holdings" metric, reuse it for Q3).
    - `scripts/wealth/behaviour_fingerprints.py`: `drawdown_windows(nav, floor=-0.10)`
      — computes real crisis windows live from a NAV series (verified live:
      13 real windows including 2008, 2011–13, 2020, 2022, an open window
      from 2026-03-12 — richer than any hardcoded "2008/2011/2013/2020/2022"
      list; never hardcode the window list, always call this against
      `nav_series(conn, BENCH_ID)`).
    - `scripts/wealth/counterfactuals.py`: no importable function (pure
      top-to-bottom script) — its exact formulas must be mirrored, reading
      the file first: `cf_index_rs` (diff of `client_benchmark.terminal_mv`
      vs `bench_terminal`), `cf_no_panic_rs` (imports `drawdown_windows`;
      `units_sold × today's_NAV − proceeds`; upper bound, proceeds assumed
      held as idle cash), `cf_sip_alive_rs` (continues SIP at trailing-6mo
      median installment every ~30 days to ledger end; `extra_val − extra_cash`).
      Docstring to quote verbatim in assumption cards: *"all four are
      historical replays of NAV series that actually happened — no
      forward-return claims. Panic/SIP scenarios are upper bounds and
      labelled so on the dashboard."* (a 4th, `cf_no_switch_rs`, exists in
      `wealth.counterfactuals` but nothing downstream reads it and spec §7 B5
      only names three — leave it unused.)
16. **`docs/wealth-seven-prompts-framework.md`** is Page 1's skeleton — the
    seven prompts (verbatim quotes) are in the Task 4 brief below; do not
    paraphrase them for verdict/framing copy, quote the intent faithfully.

## Task 1: `capability_app` package scaffold + Holdings-side data layer (Q1, Q2, Q3, Q6)

Read `scripts/wealth/build_overlap.py`, `build_label_check.py`,
`build_cut_list.py` in full before writing SQL — every constant below is
sourced from them, do not re-derive independently.

Create `scripts/wealth/capability_app/__init__.py` (empty) and
`scripts/wealth/capability_app/data_holdings.py` containing book-level and
per-client rollups + `working` payloads for exhibits Q1, Q2, Q3, Q6 (Q4/Q5/Q7
land in Task 2 — Q7's fee-savings figure depends on Q4's fee rollup, so both
live together to avoid a backward dependency). Move `_f`, `lcr_py`,
`_degarble`/`_XIRR_RE` into
`scripts/wealth/capability_app/data.py` (this becomes the shared home + the
top-level `fetch_book(conn) -> dict` orchestrator that Task 2 extends and
Task 4-6 read from — for now `fetch_book` calls only the Task 1 functions and
returns their keys; Task 2 adds the rest).

**Q1 · What do you actually own?**
- Source: `wealth.holdings` (3,309 rows) × `wealth.schemes` (1,320 rows;
  category, AMC parsed from scheme name or master) joined per client.
- Book rollup: total ₹ value, total distinct funds, total distinct AMCs
  (fund houses), distribution of funds-held-per-client (for the histogram +
  median marker), top-10 funds by book-wide value (share of total).
- Verdict template (fill at build time from the query, never hardcode the
  numbers): "₹X cr across N funds, M fund houses. Median client holds K
  funds."
- Honesty: `exact` (raw holdings data, no assumption).
- `working`: inputs = book totals; steps = the treemap rollup chain
  (category → AMC → fund); sample_rows = a real 20-row slice of
  `wealth.holdings` joined to scheme name/category/AMC/value, `sample_of` =
  3309.

**Q2 · Does the label match the contents?**
- Source: `wealth.fund_label_check` (402 rows: `scheme_id, mstar_id,
  category, equity_pct, large_pct, mid_pct, small_pct, unclassified_pct,
  verdict, detail`). `verdict='mismatch'` means the fund's actual
  large/mid/small composition fails the SEBI minimum mandate for its
  regex-matched category label (see `build_label_check.py`'s
  `CATEGORY_RULES`); `verdict='no_data'` = no classifiable holdings;
  `verdict='ok', category='Other'` = no cap-mandate regex matched (e.g.
  sectoral fund) — not a mismatch, don't flag it as one.
- Book rollup: ₹ value sitting in `mismatch` funds (join to `wealth.holdings`
  for client-held value), a per-category "actual vs mandate" bar comparison,
  an "offenders" table (funds ranked by how far outside label, ₹ affected).
- **Gap to work around:** `wealth.fund_label_check` does NOT store the
  disclosure `as_of_date` used to compute it (it's pinned to `max(as_of_date)`
  per `mstar_id` internally in `build_label_check.py` but never persisted).
  To show "as of <month>" per the honesty-chip requirement, run a small
  separate query against `atlas_foundation.de_mf_holdings`
  (`max(as_of_date)` grouped by `mstar_id`) and join it in.
- Verdict template: "₹X cr sits in funds whose name doesn't match their
  contents (as of <month>)."
- Honesty: `exact` (portfolio-disclosure based) — note the disclosure month
  inline as required by constraint 3.

**Q3 · How much duplicated?**
- Source: `wealth.client_fund_overlap` (4,556 rows, only pairs with
  `overlap_pct >= 20` are stored — `build_overlap.py` only persists pairs at
  or above that storage cutoff) and `wealth.client_overlap` (216 rows:
  `client_id, eff_bets, top_stock_isin, top_stock_name, top_stock_rs,
  top10_share, n_funds, n_stocks`).
- **New threshold, mandatory:** the ">50% overlap = duplicate pair" cutoff
  currently lives ONLY as a hardcoded `> 50` literal inside
  `build_cut_list.py`'s SQL — it is not sourced from `atlas_thresholds`,
  violating constraint 5. This task must INSERT a new row into
  `atlas_foundation.atlas_thresholds`: key `wealth_overlap_duplicate_pct`,
  `category='wealth'`, `threshold_value=50.0`, `units='pct'`, a description
  noting it mirrors `build_cut_list.py`'s existing cutoff, and flag this new
  row explicitly in the eventual PR body for FM sign-off (constraint 5's
  "flag chosen value" requirement — do not silently introduce it). Read this
  new threshold at build time rather than hardcoding `50` in `data_holdings.py`.
- Book-wide top-15×top-15 funds by book value: compute pairwise overlap
  using `build_overlap.latest_fund_weights()` + `build_overlap.pairwise_overlap()`
  imported directly — do not reimplement the overlap math.
- Stock-level evidence: no `client_stock_exposure` table exists as such —
  `build_overlap.py` computes stock exposure per-client inline
  (`stock[isin] += mv * w / 100.0`) and only persists `top_stock_*`/
  `top10_share` on `wealth.client_overlap`. For Q3's "each cluster fund's
  weight in HDFC Bank, ICICI, Infosys…" evidence table, reconstruct the
  full per-stock weight dict the same way `build_overlap.py` does (via
  `latest_fund_weights`), scoped to the top-15 funds' union of ISINs — do
  not invent a new persisted table (constraint 4).
- KPI tiles: median overlap among held pairs (from `client_fund_overlap`),
  count of pairs above the new `wealth_overlap_duplicate_pct` threshold, ₹
  duplicated (sum of `min(value_a, value_b)`-style overlap in rupee terms,
  document the exact method in `working.rule`).
- Verdict template: "N fund pairs overlap more than X%; ₹Y cr sits in
  effectively duplicated exposure."
- Honesty: `estimate` (top-15 book-wide sample, not exhaustive over all
  fund pairs — state the sample scope in `working.assumptions`).

**Q6 · Is anything bloated?**
- No factsheet/SID feed exists anywhere in the pipeline. This exhibit is a
  compact, honest empty-state card (roughly a third the height of a normal
  exhibit): state the question (manager tenure, AUM growth, turnover ratio,
  mandate changes), state plainly "we don't have this data — [feed] would be
  needed" per constraint 3. **No invented proxy, no partial guess.** Provide
  a `working` object even for this — `honesty` is not one of the four scale
  values here since there's no number at all; instead render `inputs: []`,
  `rule: "no factsheet/SID feed exists in the pipeline"`,
  `sample_rows: []`, `sample_of: 0` — the reviewer should confirm this reads
  as an honest gap, not a broken exhibit.

**Client index rollup** (bottom of Holdings page, shared with Task 4): one
row per client — name → `client_id`, current value, fund count, flag cells
(off-label ₹>0, pair overlap above the new threshold, holds a chronic
laggard, fees `estimate` above category median). Flag thresholds sourced from
`atlas_thresholds`, not hardcoded. Segment filter chips from
`wealth.client_segments` (216 rows).

**Tests:** `tests/wealth/test_capability_data.py` (new file; read
`tests/wealth/test_capability_app_data.py` first for the existing real-DB
test convention — `connect()`, no fixtures, `SAMPLE_CLIENT` picked by
confirmed-real-rows-via-psql) — assert book fee/label-lie ₹ totals are
positive reals, coverage percentages fall in `[0,100]`, sector rollup total
equals the sum of identified exposure, every `working` object for the Q1/Q2/Q3/Q6
functions built in this task has all five parts and a valid honesty chip.

**Report to:** the path printed by `scripts/task-brief`. Status contract:
DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, commits, one-line test
summary, concerns.

## Task 2: Behaviour data layer (B1–B5) + Q4/Q5/Q7 + Client 360 rollups + working-payload tests

Read `scripts/wealth/build_audit_packs.py`, `counterfactuals.py`,
`behaviour_fingerprints.py`, `exact_benchmark.py`, `behaviour_gap.py`,
`build_fund_performance.py`, `client_analytics.py`, `advice_ledger.py`,
`build_equity_curves.py` in full before writing SQL.

Create `scripts/wealth/capability_app/data_behaviour.py` with book-level and
per-client rollups + `working` payloads for Q4, Q5, Q7 (the three remaining
Holdings exhibits), B1–B5, and the Client 360 timeline/what-if sections.
Extend `capability_app/data.py`'s `fetch_book(conn)` to also call these and
merge their keys into the returned dict.

**Q4 · What do you actually pay?**
- Fee/TER math lives in `scripts/wealth/client_analytics.py` (not in the
  spec's own reading list but confirmed the true source): `INDEX_ER = 0.20`
  (assumed achievable index expense ratio), closet-indexer heuristic =
  `r2 >= 0.93 AND expense_ratio >= 0.8 AND asset_class == "Equity"`, real
  per-scheme `expense_ratio` joined from `atlas_foundation.de_mf_master`.
  `build_audit_packs.py`'s `sec_fees(cid, f)` does zero fee math itself — it
  only reads `wealth.value_statements.fee_save_yr_rs` +
  `wealth.client_flags` (rule text contains "closet"). Roll this up to book
  level yourself (a `sum()` over `value_statements`, following the existing
  per-client pattern — no book-level rollup exists yet for this metric).
- TERs are REAL per-scheme actuals (from `de_mf_master`), but the fee-save
  number is still `estimate` (not `exact`) because of the heuristic
  classification + the assumed `INDEX_ER` replacement value — the assumption
  card must say this exactly.
- Charts: hero ₹X cr/yr figure; dumbbell per category (regular-plan vs
  direct-plan annual cost) — **only direct-plan TERs exist in the data**, so
  label the regular-plan side clearly as a category-median estimate, not a
  per-scheme actual, in the assumption card (constraint 3).
- Honesty: `estimate`.

**Q5 · Did the funds beat their benchmark?**
- Source: `wealth.fund_performance` (298 rows: `scheme_id, mstar_id,
  roll_3y_pct, roll_5y_pct, dn_capture_pct, best_year_stripped_pct,
  full_period_pct, beat_count, windows, benchmark_note, verdict`).
  `verdict='scored'` has a `roll_5y_pct`; `'insufficient_history'` has none —
  render those as an honest gap per fund, not a zero.
- Charts: (a) one bar per fund = excess return vs its own mapped benchmark,
  sorted; (b) consistency heatmap fund × rolling window (beat/miss, derived
  from `beat_count`/`windows` — note `build_fund_performance.py` evaluates up
  to 20 trailing monthly-spaced rolling-1y windows, not calendar years); (c)
  tiles "X of Y funds beat benchmark over 3y", "₹Z cr sits in chronic
  laggards" (laggard = `beat_count < windows/2`, same rule
  `build_cut_list.py`'s `weak_funds()` uses — reuse that exact `<` half
  cutoff, don't invent a new one).
- Every tooltip must include `benchmark_note` verbatim (it names which index
  a fund is judged against and flags PR-vs-TR mismatches — this is a
  transparency requirement, not decoration).
- Honesty: `exact` for the return numbers themselves (real fund NAV
  history), but `benchmark_note`'s PR-vs-TR caveat must be visible, not
  hidden in a tooltip nobody opens by default — surface it in the working
  drawer's `assumptions` too.

**Q7 · What would we cut?**
- Source: `wealth.cut_list` (216 rows: `client_id, keep jsonb, cut jsonb,
  min_fund_count int, note text`). `cut` entries: `{fund, scheme_id, reason,
  exit_tax_rs, unwind_order}` (NOT `rule/evidence/action/est_value/basis` —
  the spec's expected column names don't literally exist on this table;
  `reason` combines the rule+evidence text, `exit_tax_rs` is the
  est_value-equivalent, `unwind_order` is the ordering rank). `keep` entries:
  `{fund, scheme_id, evidence}`.
- Evidence chips: derive `off-label` / `duplicate` / `laggard` / `expensive`
  tags per cut entry by pattern-matching `reason` text (it already encodes
  which of these applied — see `build_cut_list.py`'s `weak_funds()` reason
  strings: `"label mismatch (...)"`, `"bottom-quartile fund_rank (...)"`,
  `"downside capture ...%"`, `"beat benchmark only .../..."`, plus
  `"redundant vs held peer"` for the duplicate case). Each chip should anchor
  (`<a href="#q2">`, etc.) back to the exhibit above that proved it.
- **Gap, document don't silently patch:** `build_cut_list.py` does NOT
  persist a from→to consolidation mapping (which specific kept fund a cut
  fund's money would flow into) — the pairing between a redundant pair's two
  members is discarded before the final JSON is built. For Q7's
  "consolidation flows" sankey/from-to list, re-derive this yourself: re-run
  the same `>50%`-threshold query Task 1 already introduced for Q3
  (`wealth.client_fund_overlap where overlap_pct > wealth_overlap_duplicate_pct`,
  reading the `atlas_thresholds` row Task 1 seeded — do not re-seed it, just
  read it) per client, and for each pair where one member is in that
  client's `cut` list and the other is in `keep`, emit a `{from: cut_fund,
  to: keep_fund}` edge. Where a cut fund's overlap partner is not itself a
  kept fund (rare, e.g. both members cut), omit that edge rather than
  guessing — an incomplete sankey is honest, a fabricated edge is not.
- Verdict template: "Cutting N of M funds — saves ₹X/yr in fees, removes P%
  duplication." (fee delta = sum of cut funds' TER-implied annual cost,
  computed from this same task's Q4 fee rollup — no cross-task dependency
  since both live here).
- Honesty: `estimate` (evidence-gated but the fee delta rests on the Q4 TER
  assumptions).

**B1 · Did advice beat the index?**
- Source: `wealth.client_benchmark` (234 rows: `client_id, xirr_client,
  xirr_bench, alpha, first_flow, gross_in/out, terminal_mv`) —
  `exact_benchmark.py` replays every external cash flow into the Nifty-50
  index fund at flow-date NAV and computes both XIRRs on the same dated
  flows (apples-to-apples cashflow-matched comparison).
- Charts: (a) hero distribution of per-client excess (pp/yr), book median
  +3.80pp/yr, "173 beat · 39 lagged" (recompute these counts live, don't
  hardcode — the book totals in spec §2.4 are orientation only); (b) scatter
  outcome vs years-with-firm (tenure = today − `first_flow`).
- UI language: "extra growth vs index, per year" — never the word "alpha".
- Honesty: `exact` (cashflow-matched replay, not a point-to-point comparison).

**B2 · How investors cost themselves**
- Source: `wealth.behaviour_gap` (3,336 rows, per client×scheme: `mwr_pct,
  twr_pct, gap_pp, gap_rs, invested`) aggregated invested-weighted at book
  level. MWR via XIRR, TWR via CAGR of scheme NAV (Morningstar "Mind the
  Gap" methodology).
- `gap_rs` uses `avg_cap = invested / 2` — an explicit
  `# ponytail:` flat-average-proxy simplification in `behaviour_gap.py`;
  carry this exact caveat into the UI assumption text, don't smooth it over.
- Also encode the Hayley (2014) caveat already in the engine: part of any
  MWR−TWR gap is mechanical (a function of flow timing), not investor skill
  or mistake — state this in the drawer rule text, it's the difference
  between an honest and a misleading B2.
- Charts: (a) dumbbell fund-return vs investor-actual-return
  (invested-weighted, book gap −1.32pp highlighted); (b) two stacked panels
  sharing one time axis, NOT dual-axis (index level above, monthly net
  client inflows below); (c) per-client gap histogram diverging around 0.
- Honesty: `exact` (real dated cash flows and NAV series), with the
  mechanical-vs-behavioural caveat surfaced per constraint 3.

**B3 · The panic pattern**
- Crisis windows: `behaviour_fingerprints.drawdown_windows(nav_series(conn,
  BENCH_ID))` — import directly, never hardcode the window list (constraint
  15). Weekly net flows from `wealth.transactions`. SIP stream starts/stops:
  reuse `behaviour_fingerprints`' own detector logic (import it; if any
  piece isn't importable, the ONLY allowed engine edit per constraint 9 is
  moving that piece into `engine_common.py` so both callers share it).
- Charts: (a) crisis anatomy — index drawdown area on top, weekly net client
  flow diverging bars below (red = net selling), shared time axis, crisis
  windows shaded and labeled with their real years (from `drawdown_windows`,
  not a hardcoded label list); (b) client × crisis heatmap — % of each
  client's lifetime exits that happened inside each window, sequential
  palette, sorted by total; (c) SIP lifeline — monthly SIP starts (up) vs
  stops (down), same shaded windows, "781 stopped; 331 during a crash"
  (recompute live from `wealth.client_behaviour`'s `sip_streams/active/stopped`
  + `sip_stops_in_drawdown` — book totals in spec §2.4 are orientation only).
- Tiles: ₹27.8cr sold below cost, ₹23.8cr dividend leakage (recompute live
  from `client_behaviour.panic_loss_out_rs` / `div_leak_rs` sums).
- Honesty: `exact` (real transaction-dated events against a live-computed
  drawdown series).

**B4 · Advice switches**
- Source: `wealth.advice_ledger` (33,312 rows, paired switches with 1y/3y
  forward verdicts) and `wealth.advice_waves` (992 rows: scheme, window,
  n_clients, inflow_rs, fwd1y/3y scheme vs bench) — e.g. the Aug-2020
  Banking&PSU wave, annotate it by name if it appears in the data (don't
  hardcode which wave — pick whichever wave rows actually exist).
- Charts: (a) per-switch outcome distribution (money did vs would-have-done
  if left, per `advice_ledger`'s forward verdicts); (b) named coordinated
  waves annotated; (c) waves vs one-offs — two diverging bars comparing
  forward outcomes of coordinated waves vs individual switches.
- Drawer rule: quote `advice_ledger.py`'s exact switch-pairing definition
  faithfully (read the file for the exact N-day sell/buy pairing window —
  do not approximate it) — "a switch = sell + buy within N days... judged by
  comparing what the money did vs what would have happened if left."
- Honesty: `estimate` (forward verdicts rest on a benchmark-comparison
  assumption — state which benchmark).

**B5 · The what-if machine** (flagship transparency piece)
- Source: `wealth.counterfactuals` (234 rows: `cf_index_rs, cf_no_panic_rs,
  cf_sip_alive_rs` + input tallies — `\d wealth.counterfactuals` for full
  columns) summed to book level: no-panic +₹181cr (upper bound), SIP-alive
  +₹67cr (estimate), index-everything −₹129cr (estimate; negative = book
  BEAT indexing — state this explicitly, it's a genuinely good-news honest
  result, don't bury it).
- Per-what-if path series: mirror `counterfactuals.py`'s exact formulas
  (constraint 15) at book-aggregate granularity. If a full per-month path
  series is too heavy to compute for all 234 clients at build time, fall
  back to paired actual-vs-what-if END-state bars per era — but keep the
  full derivation chain mandatory either way (constraint 3): "4,214 panic
  sells · ₹X cr proceeds · units × sale-date NAV = ... · valued at today's
  NAV = ₹Y cr; actual outcome ₹Z cr; gap ₹181cr."
- One sub-exhibit per what-if, **assumption card rendered ABOVE the
  headline number** (not below, not in a collapsed drawer only — this is an
  explicit layout requirement, not a data requirement, flag it clearly to
  Task 5 which builds this page), honesty chip on the number itself.
- Assumption text must be derived by reading `counterfactuals.py`, not
  invented — e.g. "we assume panic-sold units are simply held today;
  proceeds NOT reinvested elsewhere → upper bound."
- Honesty: per-what-if as listed above (`upper bound` / `estimate` / `estimate`).

**Client 360 rollups** (per-client, parametrized versions of everything
above, for Task 6):
- Header strip: name, family group, "with firm since <year of first_flow>",
  put-in/taken-out/worth-now, "grew at N%/year" (from `client_benchmark`,
  plain words — never "XIRR"/"alpha"), segment chip.
- Timeline: `wealth.client_curves` (48,068 rows: `client_id, month,
  value_rs, net_flow_rs, coverage_pct`) monthly value area vs cumulative
  net-invested line, event markers from `wealth.client_curve_events`
  (24,270 rows: `event_id, client_id, event_date, kind, amount_rs, note`).
  **`select distinct kind` first and build the legend from the real
  values** — confirmed enum (4 distinct, from `build_equity_curves.py`
  source): `panic_sell`, `big_inflow`, `big_outflow`, `sip_stop`. Crisis
  windows shaded (same `drawdown_windows` call, reused not recomputed
  per-client — the window list is book-wide).
  **The <70% coverage → "insufficient" rule is NOT in `build_equity_curves.py`**
  — its own docstring says the engine "just records the number" and the
  70% flag is "the app's own insufficient flag." Find where the CURRENT
  `build_capability_app.py` applies this convention (grep it) and reuse the
  exact same cutoff and wording — don't invent a new threshold or a new
  string.
- Sector look-through: `client_stock_exposure` (246,573 rows, look-through)
  → `atlas_foundation.instrument_master.sector` via `instrument_id`.
  Coverage line "sector identified N% look-through value; rest: ETF units /
  debt / cash / unidentified" — compute N per client (book-wide it's ≈67%
  per spec §2.3; don't hardcode that book number on a client page, compute
  it fresh per client). Book-wide bucket totals for reference (₹):
  `atlas_scored_stock` 259.8cr, `etf_units` 66.7cr, `cash_other` 26.2cr,
  `identified_stock_unscored` 22.2cr, `other` 17.1cr,
  `indian_stock_unidentified` 16.0cr, `debt_instrument` 10.8cr,
  `foreign` 0.2cr.
- Fund-pair overlap heatmap: `wealth.client_fund_overlap`, fees (Task 2's
  Q4 rollup, per-client slice), cut-list evidence chips (Task 2's Q7 rollup,
  per-client slice).
- Behaviour section: crisis flows strip, switch history verdicts, SIP
  streams (active/stopped, stops-in-drawdown flagged), dividend leakage
  tile — all per-client slices of the book-level B1-B4 functions above.
- What-ifs: three counterfactual values for this one client, same
  assumption cards + twin paths as B5 (client-level paths ARE feasible
  directly from `client_curves` + the mirrored engine logic — this is
  explicitly easier than the book aggregate, not harder).

**Tests:** extend `tests/wealth/test_capability_data.py` with the B1-B5 +
Q4/Q5 + Client-360 assertions (book fee total, counterfactual book sums
match `wealth.counterfactuals` aggregates, sector rollup total = sum of
identified exposure, coverage % always in `[0,100]`). Add
`tests/wealth/test_working_payloads.py`: every exhibit's `working` object
(across BOTH `data_holdings.py` and `data_behaviour.py`) passes shape
checks — all five keys present, every `assumptions[].bias` non-empty,
`honesty` ∈ the four allowed values, `sample_rows` are real rows
re-fetchable from `wealth.transactions`/`wealth.holdings` by their ids (not
just shape-valid, actually re-queryable).

**Report to:** the path printed by `scripts/task-brief`. Same status
contract as Task 1.

## Task 3: `assets/charts.js` SVG kit + `assets/app.css` tokens + palette validation

No DB access needed for this task — it consumes whatever shape of data
Task 1/2 already committed (read their `working`/rollup output shapes from
`capability_app/data_holdings.py` and `data_behaviour.py` directly) plus a
small synthetic-shape scratch harness for visual iteration only (constraint
1's "no synthetic data" governs what ships in the final HTML, not a
throwaway local preview page you delete before merge — make sure any scratch
preview file is NOT committed, or is clearly out-of-band under something
like `scripts/wealth/capability_app/_scratch_preview.html` excluded from the
final build).

Create `scripts/wealth/capability_app/assets/charts.js`: one small
hand-rolled SVG kit, zero dependencies, exactly these forms, each a function
`(el, data, opts) => void` that reads CSS custom properties for color (never
hardcodes hex in JS):
- `treemap` (category → AMC → fund, click descends one level)
- `histogram` (with a median marker line)
- `horizontalBar` (top-N bar list)
- `divergingBarStrip` (e.g. weekly net flow, red = net selling)
- `divergingStackedBar`
- `dumbbell` (two-point comparison per category, e.g. before→after,
  regular-vs-direct)
- `heatmap` (sequential, e.g. overlap matrix, client×crisis)
- `lineArea` — with three composable additions: emphasis series (accent vs
  gray), shaded crisis windows (from `drawdown_windows` date ranges), and
  event markers (from `client_curve_events` kinds)
- `scatter`
- `stackedSharedX` — a PAIR of panels sharing one x-axis, each with its own
  y-axis (this is the mandated replacement for any dual-axis chart —
  constraint: **never build a dual-axis chart**, e.g. B2's index-level +
  net-inflow panel, B3's crisis anatomy)
- `statTile` / `hero` (for headline numbers — a hero number is a stat tile,
  never a one-bar chart)
- a thin `sankey` (from→to list only, for Q7's consolidation flows — simple
  enough it doesn't need a general graph layout, just fixed left/right
  columns and curved connectors)

Every chart: hover tooltip (crosshair+tooltip on line/area per dataviz
convention, per-mark tooltip on bars/dots/cells) + a `Table view` toggle
that renders the same data as an HTML `<table>` (accessibility + trust,
required by spec — not optional polish). Legend whenever a chart has ≥2
series. Never print a number on every mark.

Palette rules (exact, from spec §11 — invoke the `dataviz` skill for the
full reference, but these constraints are non-negotiable regardless of what
the skill's defaults suggest):
- Sequential (one hue, light→dark) is the default for ranked/ordered data.
- Categorical ONLY when series identity is the subject (≤7 series, fixed hue
  order, never cycled/reused across different meanings).
- Diverging (two hues + a neutral gray midpoint) only for above/below-zero
  data (e.g. B2's gap histogram).
- Emphasis (accent + gray) for book-vs-index comparisons (B1, B5 twin paths).
- Status/warning colors (`--warn`, `--crit` from constraint 13) are reserved
  for genuine flagged states (off-label slice, bad switches) — never reused
  as "just another series color."
- Validate the final categorical/status palette with the `dataviz` skill's
  `scripts/validate_palette.js` (found via the `dataviz` skill — it exists
  at `<dataviz-skill-dir>/scripts/validate_palette.js`) against the ACTUAL
  surface colors in BOTH light and dark mode. Fix every FAIL before this
  task is done — do not defer palette failures to a later task.

`assets/app.css`: the exact `:root` tokens from constraint 13, plus a
`[data-theme="dark"]` override block, the responsive 12-col grid (kill the
820–920px `.wrap` cap), `font-variant-numeric: tabular-nums` on all numeric
displays, and layout for the `exhibit()` anatomy (verdict → KPI strip → 2-3
charts → drawer) that Task 4/5/6 will instantiate.

Build a throwaway local scratch HTML page (not committed, or committed under
a clearly-scratch path and deleted before Task 6 finishes) that renders one
instance of every chart form above using a REAL small slice of Task 1/2's
actual query output (constraint 1 still applies even to a preview — pull a
real client's real rows, don't synthesize placeholder numbers) — eyeball it
yourself before marking this task done; a chart kit that only looks right in
your imagination is not done.

**Report to:** the path printed by `scripts/task-brief`. Include in the
report: confirmation the palette validator passed in both modes (paste its
final output), and which scratch-preview approach you took (committed vs
deleted).

## Task 4: `render.py` + `page_holdings.py` (Q1–Q7 + client index) + validator route update — Gate 1 & 2 green

Depends on Task 1 (data), Task 2 (fee rollup for Q7's savings number, and the
`fetch_book` merge), Task 3 (charts.js/app.css). Confirm all three are
`Task N: complete` in the ledger before starting.

Build `scripts/wealth/capability_app/render.py`: the ONE universal
`exhibit()` renderer (constraint 14's anatomy — verdict sentence, KPI tile
strip, 2-3 coordinated charts, `How is this calculated? ▾` drawer with the
five-part `working` object), the top nav (exactly two links, "Holdings" /
"Behaviour", plus client-name links everywhere client IDs appear — no tab
strips, no steppers, no scroll-snap), and the client-index table renderer
(shared by Holdings and Behaviour pages per spec §4).

Build `scripts/wealth/capability_app/page_holdings.py`: instantiate `exhibit()`
seven times using Task 1/2's Q1–Q7 data functions, in the exact order and
using the exact verbatim prompt framing below (Page 1's skeleton — from
`docs/wealth-seven-prompts-framework.md`, quote the intent faithfully, do
not paraphrase away the framing sentence for each):

1. **Q1 · What do you actually own?** — framing: *"pull out, as one clean
   table, every scheme with SEBI category and AMC, invested/current/gain,
   direct-vs-regular, weight %, total schemes and AMCs."*
2. **Q2 · The Label Lie** — framing: *"check actual large/mid/small split
   vs the SEBI minimum for its category... if the fund doesn't match its
   label, say so plainly."*
3. **Q3 · The Overlap Trap** — framing: *"Owning eight funds isn't
   diversification if they hold the same thirty stocks."*
4. **Q4 · What You Actually Pay** — framing: *"act like a cost auditor, not
   a salesman... every figure in rupees."*
5. **Q5 · Beat the Benchmark?** — framing: *"A single great year can carry
   a ten-year number. Strip that year out and tell me what's left."*
6. **Q6 · The Bloat Check** — framing: honest empty-state per Task 1.
7. **Q7 · The Cut List** — framing: *"Do not suggest new funds. Judge only
   what I already own. If the data doesn't support a cut, say so plainly."*

Page opens with one plain-English frame line (spec §4 exact template): "234
investors. ₹Xcr across N funds. Seven questions any fee-only adviser would
ask." (fill X/N live, never hardcode). A sticky mini-index (7 questions)
for in-page jumping — all content stays on the page, nothing hides behind a
step.

Full-width layout: no 820–920px cap, responsive 12-col grid (~1600px max),
charts 2-3 across on wide screens, stacking on narrow.

**Validator update** (`scripts/wealth/validate_wealth_app.py` — extend,
never weaken existing checks):
- Update the headless-Chromium route list to include `#holdings` (in
  addition to `#behaviour`/`#client/<id>` which Task 5/6 add later — if
  those routes don't exist yet when this task runs, only add `#holdings` now
  and leave a `# TODO(Task 5/6)` marker, don't fake the other routes).
- Add: (a) every exhibit id (`q1`..`q7`) is present on the Holdings page;
  (b) every exhibit's `working` object round-trips through the embed with
  all five parts non-empty; (c) every headline number string rendered in the
  HTML also exists in the JSON data embed (no JS-invented numbers — grep the
  rendered text against the embed's numeric values); (d) zero occurrences of
  the deleted routes `#book`, `#calls`, `#cohort`, `#segment/`, `#guide`
  anywhere in the output HTML.
- Keep existing checks: banned-word walk over all renderable strings, size
  report, data-embed extraction — all must still pass.

**Gate 1 & 2 must be green** before this task is marked complete: run
`validate_wealth_app.py` against a build containing at least the Holdings
page, and `tests/wealth/test_capability_data.py` +
`tests/wealth/test_working_payloads.py`.

**Report to:** the path printed by `scripts/task-brief`.

## Task 5: `page_behaviour.py` (B1–B5 + client index) — gates green

Depends on Task 2 (behaviour data), Task 3 (charts.js/app.css), Task 4
(`render.py`'s `exhibit()` + nav — reuse it, don't build a second renderer).

Build `scripts/wealth/capability_app/page_behaviour.py`: five exhibits via
the same `exhibit()` renderer, in order:

1. **B1 · Did advice beat index?**
2. **B2 · How investors cost themselves**
3. **B3 · The panic pattern**
4. **B4 · Advice switches**
5. **B5 · The what-if machine** — **the assumption card renders ABOVE the
   headline number for each sub-exhibit** (constraint from Task 2 — this is
   a layout requirement on this page specifically, verify it visually, the
   validator's automated checks cannot catch card ORDER).

Page opens with the exact frame line (spec §4): "210,634 transactions
across 37 years. [what they] reveal about investors — [and] about advice."
(the compressed spec source has gaps here — write natural connecting words,
the intent is unambiguous: transactions reveal patterns about investor
behaviour and about the advice given). Sticky mini-index (5 exhibits) for
in-page jumping. Full-width layout, same grid as Holdings.

Client index (bottom of page): reuse Task 4's client-index table renderer —
same component, do not build a second one — but with behaviour-relevant flag
columns (panic seller, dead SIP, chronic switcher) instead of Holdings' flag
set.

**Validator update:** add `#behaviour` to the headless-Chromium route list
in `validate_wealth_app.py` alongside Task 4's `#holdings` addition; add the
same exhibit-id / working-object / headline-number-traceability checks for
`b1`..`b5`.

**Gates 1 & 2 must be green**, including everything Task 4 already required
still passing (this task must not regress the Holdings page).

**Report to:** the path printed by `scripts/task-brief`.

## Task 6: `page_client.py` (Client 360) — gates green

Depends on Task 2 (client-360 rollups), Task 3, Task 4's `exhibit()`/nav.

Build `scripts/wealth/capability_app/page_client.py`: the `#client/<id>`
route, six sections per spec §8, ALL using the same `exhibit()` renderer +
drawer as pages 1/2 (constraint: no bespoke Client-360-only rendering
pattern):

1. Header strip (name, family group, "with firm since <year>", put-in/
   taken-out/worth-now, "grew at N%/year", segment chip).
2. Timeline (full width): monthly value area vs cumulative net-invested
   line, event markers with a legend built from the real `distinct kind`
   values (`panic_sell`, `big_inflow`, `big_outflow`, `sip_stop`), crisis
   windows shaded, the `<70%` "insufficient NAV history (covers N%)"
   convention reused verbatim from wherever the current builder applies it
   (Task 2 located this — use its exact wording, don't reinvent the string).
3. Their holdings, seven questions scoped to this one client: funds table
   (value, category, per-fund verdict from `fund_performance`), label-check
   hits, sector look-through bars with the coverage line, fund-pair overlap
   heatmap, fees (honesty chip), cut-list evidence chips.
4. Their behaviour: crisis flows strip, switch history verdicts, SIP streams
   (active/stopped, stops-in-drawdown flagged), dividend leakage tile.
5. Their what-ifs: three counterfactual values for this client, twin paths,
   assumption cards above the headline number (same B5 layout rule).
6. Confirm every exhibit on this page truly reuses the shared `exhibit()`
   renderer — this is the explicit spec requirement, a reviewer should be
   able to see zero duplicated rendering logic between this file and
   `page_holdings.py`/`page_behaviour.py`.

**Validator update:** add `#client/<id>` to the headless-Chromium route
check — per Gate 4 (Task 7), test against at least three real client ids:
one high-coverage curve (`coverage_pct` clearly ≥70%), one below the 70%
threshold, one flagged panic seller (`client_behaviour.panic_share > 0` or
similar — pick real ids via a quick psql check, don't guess). Pick these
three ids yourself from the live data and record them in your report so
Task 7 doesn't have to re-derive them.

**Gates 1 & 2 must be green**, including everything Task 4/5 already
required still passing.

**Report to:** the path printed by `scripts/task-brief`.

## Task 7: Final sweep — thin CLI shim, full pipeline run, all four gates, CI, screenshots, commit series, PR

Depends on Tasks 1-6 all complete. This is the P6 phase — full definition of
done (spec §13).

1. Write `scripts/wealth/build_capability_app.py` as a thin CLI shim:
   `main()` calls `capability_app.data.fetch_book(conn)` →
   `capability_app.render.render_page(...)` (or whatever Task 4 actually
   named the top-level render entrypoint — check its report) → writes to
   the same `OUT = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")`
   — this preserves `run_wealth_engine.sh`'s and `validate_wealth_app.py`'s
   existing CLI interface (same script name, same exit codes) per spec §2.5's
   explicit "keep interface" instruction. Delete the old monolithic body
   (1,966 lines) once the shim is confirmed working — don't leave dead code
   behind.
2. Run `scripts/wealth/run_wealth_engine.sh` end-to-end (engines untouched —
   confirm you have NOT edited any engine file except whatever single
   function, if any, Task 2 moved into `engine_common.py` per constraint 9)
   producing the HTML at ≤8MB.
3. **Gate 1** (`validate_wealth_app.py`): full pass — banned words, size,
   data-embed extraction, all three routes (`#holdings`, `#behaviour`,
   `#client/<id>`), exhibit-id presence, working-object shape, headline
   number traceability, zero deleted-route occurrences.
4. **Gate 2** (`tests/wealth/`): `.venv/bin/python -m pytest tests/wealth/ -x -q`
   (or whatever exact invocation the repo's test runner convention uses —
   check `tests/wealth/test_capability_app_data.py`'s existing convention
   first) — full green, including the two new test files from Tasks 1/2.
5. **Gate 3** (repo CI): `ruff check scripts/wealth tests/wealth`,
   `ruff format --check`, pyright (keep the existing ratchet below baseline
   — `pyproject.toml` already carries `extraPaths` + baselined pandas-stubs
   noise for `scripts/wealth`, don't widen it), and the full repo unit
   sweep, run locally exactly as `.github/workflows/` defines the required
   check "Lint, types, unit tests" — all green before pushing.
6. **Gate 4** (eyes on it): headless-browse all three routes plus the three
   real client ids Task 6 picked; screenshot each; check for label
   collisions, dark-mode correctness, and that empty states (Q6, any
   `insufficient_history`/`insufficient NAV history` case) read as honest
   gaps, not broken UI. The palette validator checks color only, not layout
   — this step is a genuine visual look, not a re-run of Task 3's automated
   check.
7. Grep the final HTML: zero occurrences of `#book|#calls|#cohort|#segment/|#guide`,
   zero banned words, no `wrap`-cap class remaining.
8. Confirm the ₹55cr-class "no visible derivation" complaint (spec's
   motivating example) is now structurally impossible — pick one number on
   the Behaviour page, open its drawer, confirm the full derivation chain is
   visible.
9. Commit series: `feat(wealth): ...` per phase is fine (this task can
   squash/organize the final handful of commits sensibly — use judgment, the
   spec explicitly allows per-phase commits).
10. Push the branch, open the PR against `main` with a body that: summarizes
    the three-page redesign, calls out the new `atlas_thresholds` row
    (`wealth_overlap_duplicate_pct`) for FM sign-off per constraint 5, notes
    the CI required check passed, and includes an explicit **"FM: please
    republish the artifact"** note with the file path
    `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html` (per
    constraint 7 — PII means the builder never republishes the artifact
    itself, only points FM at the file).

**Report to:** the path printed by `scripts/task-brief`. This report is the
one the final whole-branch review reads alongside its own diff package —
include the exact commands run for gates 1-4 and their output summaries.
