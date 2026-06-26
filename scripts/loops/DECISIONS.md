# Atlas v4 six-lens — DECISION LOG (durable, append-only; newest on top)

The single source of truth for locked decisions. Every non-obvious call lands here
with a date and a why. Do not re-litigate a decision recorded here without adding a
new dated entry that supersedes it.

---

## 2026-06-22 — D27: SCORING METHODOLOGY (FM) — per-dimension DECILES + LEADERSHIP-BREADTH, not the cap-weighted composite.
**FM call. The decile/leadership framing is the better DISPLAY at every altitude (interpretable, honest,
transparent) — that stands on its own. As a PREDICTOR it is altitude-dependent (see evidence below): better
than the composite at the fund level, no better at the sector level.** The single composite score is hard to
interpret and (at the fund roll-up) actively misleading. Replace the *headline* with a decile + leadership
framing; keep the IC-composite only as one optional sort.
- **Instrument level:** each lens shown as a cross-sectional **decile D1-D10** (rank-based: robust, scale-free,
  comparable across time) + a **leadership badge = how many of the 4 conviction lenses (technical/fundamental/
  catalyst/flow) are TOP-DECILE** (top-decile in all 4 = a genuine multi-factor leader). Valuation = its own
  decile (cheap->expensive), shown openly, not a hidden multiplier. Every lens drills down to its
  sub-components + the actual evidence (the corporate action driving catalyst, the rising delivery ratio
  driving flow accumulation, etc.) — Atlas is a research/transparency tool, not a 'buy this' oracle.
- **Roll-ups (fund/sector/ETF):** headline = **LEADERSHIP BREADTH** = the weight/% of constituents that are
  top-decile leaders (top-decile in >=2 lenses), NOT a cap-weighted composite average. Plus active-movement
  (is the manager adding leaders MoM).
- **Evidence — FUND (6 recent snapshots, ~1 regime):** cap-weighted composite fund IC = -0.21/-0.24 (60/90d,
  actively negative); **leadership-breadth fund IC = +0.016/+0.007 (POSITIVE)** — the decile/leadership
  framing FLIPS the sign. Theoretically sensible (funds ARE bottom-up stock-pickers). Honest caveat: tiny
  recent sample, so +0.016 is *suggestive, not proven* — weakly positive, not strong.
- **Evidence — SECTOR (90 monthly sessions, 7.5y, ALL regimes):** cap-weighted composite sector IC =
  -0.006/-0.025/-0.039 (1m/3m/6m); **leadership-breadth sector IC = -0.011/-0.061/-0.057** — *both* mildly
  contrarian; counting leaders does NOT manufacture a sector-rotation predictor. Well-sampled = a real
  finding (consistent w/ D25): high-leadership sectors slightly mean-revert; sector TIMING is not predicted
  by bottom-up stock leadership.
- **Synthesis:** leadership-breadth is the right FRAME everywhere, a better METRIC than the composite where it
  can be (funds), and honestly NOT a sector-timing signal. Roll-ups lead with TRANSPARENCY (per D26), not a
  timing claim; the fund predictive hint is revisited when historical holdings exist. (Evidence scripts
  inline; supersedes the 'composite is the headline' assumption in D19/D21 for the PRODUCT surface. The
  on-read composite + IC weights still exist as one sortable signal.)
- **Why it works:** cap-weighting + averaging washes out the leaders (a few mega-caps dominate; the average
  is a momentum proxy that mean-reverts); COUNTING genuine multi-factor leaders preserves the signal and is
  legible. This is the methodology for the product surface (instrument page + roll-up pages + the 2x2).

## 2026-06-22 — D26: Fund IC negative on available data; roll-ups don't carry the atom's edge -> roll-ups = TRANSPARENCY, atom = the predictor.
- **Fund IC test (`test_fund_ic.py`):** holdings-weighted atom composite vs forward fund NAV return,
  cross-sectional across ~1300 equity funds. **IC = -0.12 (30d), -0.21 (60d), -0.24 (90d)** — strongly
  NEGATIVE, worsening with horizon. **HEAVY CAVEAT:** de_mf_holdings only spans 6 monthly snapshots
  (2026-01..05) — ONE regime, 5 usable points; the atom was validated over 1854 days. No historical
  holdings exist to test other regimes. So this is INCONCLUSIVE on whether the fund composite is truly
  contrarian vs a momentum-reversal-regime artifact (the atom tilts to technical/catalyst/accumulation =
  'hot' names that mean-revert in a reversal window).
- **Synthesis across both tested altitudes:** sector IC ~0/contrarian (D25) + fund IC negative -> rolling
  the atom up does NOT produce a validated PREDICTOR. The atom's proven edge is STOCK SELECTION
  (composite IC +0.034 @6m, 7.5y walk-forward). Bottom-up selection alpha does not transfer to top-down
  sector-timing or fund-ranking on the data we have.
- **Reframe (for FM decision):** build the roll-ups (sector / ETF / fund) as DESCRIPTIVE + TRANSPARENCY
  tools — what's held, how the holdings score on the atom, fund active-movement (MoM holdings delta),
  per-category context — which directly serves the D18 'recommend-not-advise + full sub-component
  transparency' goal — and do NOT position the roll-up composite as an outperformance predictor (no
  per-altitude IC claim) until historical holdings allow a real multi-regime test. The STOCK atom remains
  the validated signal. test_sector_via_etf.py / test_fund_ic.py are the evidence.

## 2026-06-22 — D25: Roll-ups Phase 1 — sector roll-up built (free-float from ETF holdings); rotation IC weak → sectors need own calibration.
- **Sector taxonomy (FM):** merged Telecom (5 names) → Media → **21 actionable sectors**.
- **Free-float weighting source (FM: "proper weights or free-float"):** every in-DB candidate failed
  (de_index_constituents weights NULL, tv_metrics.market_cap inconsistent 47-96× off, shares_outstanding
  empty; Screener market_cap is reliable but per-stock scraping is flaky + throttled at ~2000 scale).
  **SOLUTION (already local, no fetch): the index-ETF holding weights ARE free-float-cap weights** —
  `public.de_etf_holdings` for the Angel One Nifty Total Market ETF (750) + Motilal Nifty 500 (501) +
  size-index ETFs; verified HDFCBANK 6% / RELIANCE 5% = the NIFTY 500 free-float weights. Covers the
  ~795 investable names; the micro-cap tail (not in any broad ETF) has ~0 free-float weight (correctly
  ~excluded from cap-weighting, still counted in breadth). `rollup_sectors.py` `_weights()` uses it.
- **Sector roll-up built (`rollup_sectors.py` → `foundation_staging.sector_lens_daily`, 21×1854 = 38,934
  rows in 68s):** free-float-weighted 6-lens vector + per-lens breadth (% members ≥60) + dispersion;
  composite ON-READ (sub-scores × DB lens weights). Load-once COPY + vectorized.
- **Sector IC (`calibrate_sectors.py`) — HONEST negative result:** cross-sectional sector-rotation IC
  (does the composite rank which sector outperforms its NSE index) = **+0.008 (1m), +0.003 (3m),
  −0.007 (6m)** — essentially uncorrelated. The bottom-up composite with STOCK lens weights does NOT
  predict sector rotation. This is the D15 thesis confirmed: **each altitude needs its OWN IC** — sector
  rotation is macro/flow-driven, not an average of stock conviction. **Open (FM):** (a) calibrate
  sector-specific lens weights / use the breadth-momentum 2×2 as the rotation signal, or (b) treat the
  sector roll-up as a DESCRIPTIVE view (the vectors/breadth/dispersion are correct + useful) and not a
  rotation predictor. The roll-up DATA is sound; only the predictive conviction at the sector altitude
  is unproven.
- **FM hypothesis tested (derive a sector from its SECTOR ETF — the exact index basket — for tighter
  benchmark alignment):** `test_sector_via_etf.py` over 15 sectors with a clean tracking ETF =
  **−0.006 (1m) / −0.025 (3m) / −0.039 (6m)** — NOT stronger; mildly CONTRARIAN, worsening with horizon.
  **Conclusion: the atom is a stock-SELECTION signal (stock composite IC +0.034 @6m — picks the right
  stocks), NOT a sector-TIMING signal** (rotation is macro/flow-driven; strongest sectors have already
  run → mild mean-reversion). Bottom-up selection alpha ≠ top-down sector-timing alpha. → Sector roll-up
  stays a DESCRIPTIVE view; the atom's edge is leveraged at the FUND altitude (does a fund hold the right
  STOCKS, where IC should be POSITIVE). Recommend proceeding to the fund roll-up (D18).

## 2026-06-22 — D24: Delivery-% accumulation lands; Flow IC ~4×'d; Flow is now the top lens (atom FINAL inputs).
The agreed atom-input enrichment (D19) is built, validated, and recalibrated on COMPLETE data.
- **New input — delivery % accumulation (Flow lens).** `foundation_staging.delivery_daily` (own table,
  LEFT-joined into the daily frame; delivery feeds ONLY Flow, NOT the technical score — FM-clarified):
  raw delivery_pct + 30/60d averages + up/down-day asymmetry, PIT (trailing windows ≤ D), computed
  vectorized (load-once COPY + groupby-rolling; the slow per-group transform-lambda was replaced).
  Coverage 2019-09-30→2026-06-19, 2.27M rows, 99% with a 30d avg. Source `public.de_equity_ohlcv`; the
  standard CM bhavcopy carries NO delivery, so the missing 2026-04-07→06-19 (~50 sessions, feed was
  stale) were fetched from NSE **sec_bhavdata_full** (`fetch_delivery.py`) — 101,915 rows filled. "Can't
  run IC on incomplete data" (FM) — so the feed was completed BEFORE recalibration.
- **Accumulation sub-component is MEDIUM-TERM (matches Flow's cadence + the 3-6m horizon — FM point):**
  it reads SMOOTHED quantities (this-month avg vs prior-2-month avg + month-long up/down asymmetry), NOT
  today's raw delivery, so Flow stays a slow conviction signal that merely fills the gap between
  quarterly shareholding updates. Composite weights promoter/smart/accumulation, renormalised over
  PRESENT sub-components (delivery-absent names keep the prior 70/30 exactly; RULE #0 None below the
  liquidity floor = no 30d-avg). Thresholds in `atlas_thresholds` (DB-editable). `flow_accumulation`
  stored per row (full sub-component transparency, D18).
- **Journal rebuilt PIT 2019-01-01→2026-06-19** with delivery (1854/1854 dates; accumulation fires for
  95% of names on a recent session). Then **recalibrated on the delivery-enriched journal**:
  - **Flow OOS IC 0.0058 → 0.0232 (~4×), sign-stability 1.00** (every one of 15 folds positive). Flow
    went from the WEAKEST conviction lens to nearly the strongest (technical 0.0252).
  - **Learned weights (persisted to `atlas_thresholds` + `atlas_signal_weights`): flow 0.302 (now the
    HIGHEST), technical 0.279, catalyst 0.231, fundamental 0.188** (policy/valuation 0). Composite OOS
    IC 0.0317 > equal-weight 0.0287 (calibration still adds value).
  - Composite stays ON-READ (D19): `calibrate_loopC --commit` was fixed to persist weights + IC ONLY,
    NOT re-materialise the 3.9M composite column (which the on-read path ignores). Caveat: the --commit
    IC-sweep guard skipped re-writing `atlas_signal_ic` (saw recent pre-delivery rows); the load-bearing
    WEIGHTS are correct, the per-row IC provenance table lags — refresh on a future cleared-state run.
- **C9 gate added** to `validate_loopC` (delivery populated + PIT-reconciled to source + accumulation
  fires/None-not-0 + Flow weight elevated). Atom FINAL once C1-C9 + check A + pytest green.

## 2026-06-22 — D23: GO-LIVE SEQUENCE (FM) — make v4 live+accurate FIRST; replicate (not rebuild) the frontend; clear tables DEAD LAST.
**Decision (FM, sequencing — overrides any urge to clean up early):**
1. **Clear NOTHING now.** No table drops until the very end. The keep/crap audit (D22/data_catalog) is a
   STAGED plan for later, not an action item. The shared DB still serves the LIVE old Atlas.
2. **First: get THIS version (v4 six-lens) absolutely live, working, fully wired, and numbers-accurate
   exactly as the FM needs** — backend complete (atom → delivery → roll-ups, all on the self-contained
   `foundation_staging`) + validated against ground truth.
3. **Frontend = REPLICATE the current Atlas frontend, do NOT rebuild it.** Reuse the existing Atlas
   pages/components, wire them to the validated v4 data (+ the lens surfaces already added behind
   `NEXT_PUBLIC_LENS_V4`, OFF). Same product, now powered by the clean v4 backend. It goes live only
   when everything is proper + numbers validated.
4. **Then retire the old Atlas → THEN clear out all the legacy tables** (the D22 crap-list), FM-approved,
   once nothing live depends on them.
- **Implication for the consolidation (D22):** "bring tables into `foundation_staging`" is part of
  WIRING v4, done as the roll-up build proceeds — additive, safe, no drops. The drop step is the last
  thing that happens, after go-live + old-Atlas retirement.

## 2026-06-22 — D22: SELF-CONTAINED ENVIRONMENT (FM) — every table Atlas v4 needs lives in the Atlas env; NO cross-environment reads.
**Decision (FM, foundational):** this version of Atlas must be fully self-contained — **every single table
it reads must exist in the Atlas environment** (the `foundation_staging` raw/derived schema + the `atlas`
computed-output schema in THIS Supabase project). It may NOT read from any other environment. Anything
currently borrowed from the legacy `public.de_*` layer must be **brought in or duplicated** into the Atlas
environment, and the code repointed — so the legacy `public.de_*` environment(s) can then be CLEARED.
- **D22a (FM) — ONE schema: everything in `foundation_staging`.** Every table Atlas needs — raw feeds,
  derived feeds, AND the computed outputs currently in the `atlas` schema (atom, thresholds, signals,
  regime, decisions, roll-ups) — consolidates into `foundation_staging`. Single place to point at when
  clearing other environments.
  - **Sequencing (honest):** NEW brought-in feed tables (de_etf_*, de_mf_*, de_index_*, delivery, etc.)
    land in `foundation_staging` immediately (no conflict). Moving the EXISTING `atlas.*` outputs is a
    deliberate, validated **consolidation pass** — the immutable gate `validate_lenses.py` and ~26 code
    refs point at `atlas.atlas_lens_scores_daily` etc., so the atom table is moved with a parity check +
    a coordinated repoint AFTER the atom is locked (don't destabilize the just-greened atom mid-flight).
    End-state: nothing in `atlas` or `public.de_*`; everything in `foundation_staging`.

- **D22b (FM) — classify + NAME tables by role.** `raw_*` for direct external feeds (prices, NAV,
  holdings, filings, masters) — MANDATORY; `ref_*` masters, `derived_*` computed, `cfg_*` config,
  `ops_*` pipeline state — recommended, naming "optional" per FM. Full mapping in
  `scripts/loops/data_catalog.md` (the source of truth). NEW + brought-in tables follow it now; EXISTING
  tables rename via backward-compat VIEWS in a sequenced pass after the atom lock (non-breaking). Apply
  to the INSTRUMENT/stock tables too (ohlcv_stock→raw_equity_ohlcv, technical_daily→derived_technical_daily,
  atom→derived_lens_scores_daily, …), not just the roll-up tables. **Scope reality:** v4 uses ~30 real
  tables; the `atlas` schema's other ~125 tables (old/v6/strategy, mostly empty) + the `public.de_*`
  legacy (incl. empty yearly partitions) are OUT of v4 scope and part of the environment-clearing.
- **Already native (no action):** `foundation_staging.{ohlcv_stock, instrument_master, index_prices,
  technical_daily, financials_quarterly, financials_annual, lens_filings, lens_insider, lens_shareholding}`
  + the `atlas.atlas_*` outputs — the clean foundation already replaces de_equity_ohlcv / de_instrument /
  de_index_prices etc.
- **Still borrowed from `public.de_*` → must be brought in (audit 2026-06-22):** `de_equity_ohlcv`
  (delivery_pct — already the loopD migration), `de_etf_holdings`, `de_etf_ohlcv`, `de_etf_master`,
  `de_index_constituents`, `de_index_master`, `de_mf_master`, `de_mf_holdings`, `de_mf_nav_daily`,
  `de_sector_mapping` (already covered by instrument_master.sector + atlas_sector_master — verify),
  `de_corporate_actions`, `de_global_prices`. (`de_trading_calendar` is NOT to be used — D9.)
- **Method:** duplicate each into `foundation_staging` (copy as-is is acceptable per FM; clean-model later
  if needed), repoint every code reference off `public.de_*`, validate row-parity, THEN the legacy env is
  clearable. Mostly mechanical; runs as background migration jobs. The roll-up build (Loop B) reads the
  LOCAL copies, never `public.de_*`. loopB_rollup_framework.md + loopD_delivery.md updated to reflect this.

## 2026-06-22 — D21: Roll-up framework locked (on-read; weighting; sector-proxy; MF on existing de_mf_*).
Design settled with FM for the sector→ETF/index→fund roll-ups (`loopB_rollup_framework.md`). Build the
COMPUTE only after the atom is FINAL (delivery-% + sector-RS in); design is done now.
- **Roll-ups are ON-READ too (extends D19):** a higher altitude's vector = weight-weighted average of
  constituents' lens SUB-scores, composite via the same on-read function. NOT materialised — an atom
  rebuild or weight edit flows up for free. Only per-altitude IC weights are persisted (learned, not derived).
- **Weighting rule:** ETF/index/fund carry their OWN disclosed weights (`de_etf_holdings.weight`,
  `de_index_constituents.weight_pct`, `de_mf_holdings.weight_pct`) → use them directly. Free-float cap
  weighting (D15) is needed ONLY for the **sector** fold-up (members have no given weights). Equal-weight
  stays a secondary "breadth view" toggle.
- **D21a (FM) — sector weighting = proxy from the NSE sector-index constituent weights**
  (`de_index_constituents` for the matching sector index) where one exists; equal-weight + breadth
  elsewhere. Chosen over ingesting a free-float cap source because `tv_metrics.market_cap` units are
  unreliable (D17) and the sector-index weights are already free-float-based and trustworthy. Ships now.
- **D21b (FM) — mutual funds build on the existing `de_mf_*` tables NOW** (1,359 funds, 243K append-only
  holdings with `instrument_id` look-through + `as_of_date`, daily NAV) — they already support
  look-through, active-movement (MoM holdings delta), per-SEBI-category ranking vs Category Benchmark
  (`primary_benchmark`), and NAV returns. Fold in the FM's Morningstar APIs later if they add depth;
  do NOT block fund roll-up on them.
- **Fund altitude (D18 carried):** universe = Regular plan · Equity · Growth option; recommend-not-advise;
  rank WITHIN `category_name`; FULL sub-component transparency on the fund page; edge = look-through +
  active-movement; fund IC calibrated PER category. ETF IC: use an ETF price/NAV series if available,
  else inherit the tracked-index IC as a proxy (open item 2).

## 2026-06-22 — D20: Loop C closed ON-READ; DB statement_timeout root-cause fixed; lens_filings indexed.
- **On-read gate repoint DONE:** `validate_loopC.py` C6/C8 and the 3 composite-dependent pytest tests now
  compute the composite/coverage **on-read** from stored sub-scores × live DB weights (never the
  vestigial/stale stored composite column, which is 0/60-reconciling at recent dates). C6 asserts the
  on-read composite computes, is weight-sensitive, and tracks the DB (IC-learned) weights not the
  hard-coded defaults; C8 computes coverage on-read (early 0.628 < late 0.955) + a scan-free no-source
  invariant. `validate_lenses --check A` = **GREEN 12/12** on the 3.9M-row journal.
- **Root-cause found + fixed (the "gate is slow/timing out" saga):** Supabase's pooler multiplexes
  physical backends per-transaction, so `_db.py`'s connect-time `SET statement_timeout` only stuck to
  ONE backend — sibling checkouts fell back to the **2-minute role default** (proven: fresh checkouts
  alternated 10min/2min; a `pg_sleep(130)` died at exactly 120.0s). Invisible until Loop C grew the
  journal 7× (276→1854 dates = 3.9M rows) so heavy gate aggregates crossed 2 min. **Fix:** `_db.read_df`
  /`scalar` now run each query in one transaction with `SET LOCAL statement_timeout` (pooler-proof,
  configurable via `ATLAS_STMT_TIMEOUT_MS`, default 20 min) — verified every checkout now reports 20min.
  No gate logic or data touched. This also de-risks the delivery rebuild + every future recalibration.
- **lens_filings(instrument_id) index added** (CONCURRENTLY, 2.2s) — the immutable gate's catalyst checks
  were scanning the 297 MB index-less table twice (~224s each → ~11 min run); near-instant now.
- **Gate hygiene lesson:** run the heavy full-table gates (`validate_lenses --check A`, `validate_loopC
  --mode full`) SOLO — concurrent full scans contend and trip the per-query budget (it was self-inflicted
  contention, not bloat: the journal is only 1.1% dead tuples, VACUUMed 2026-06-22 03:00).

## 2026-06-22 — D19: Composite is ON-READ (not materialized); next data enrichment = delivery % via a tmux goal-loop.
- **Composite/conviction/coverage are computed ON READ** from the stored lens sub-scores × the live
  `atlas_thresholds` weights — NOT stored. Proven: a full date's composites compute in **0.075s** in
  pandas. Materializing the 3.9M-row composite into Supabase repeatedly hung (dropped connections) +
  bloated the table (wasted ~a day). The stored composite columns are deprecated/vestigial. The atom
  stores only the expensive immutable **sub-scores**; composite is derived at query time → a weight
  edit is instant, zero rows rewritten. Gate + tests + product must compute composite on-read.
  (`create_composite_view.py` has the verified SQL — but the multi-CTE view didn't push the date
  filter down; ship it as an app-level helper or a pushdown-friendly view.)
- **6 lenses, not 4:** all six are computed/stored/shown. The composite's weighted AVERAGE is over the
  4 conviction lenses (technical/fundamental/catalyst/flow); valuation = a MULTIPLIER; policy = FYI.
- **Next atom-input enrichment (do as ONE batch before roll-ups, then one rebuild + one recalibration —
  D6 build-once):**
  - **Delivery %** (`public.de_equity_ohlcv.delivery_pct`, ~79% coverage, fresh; NOT in ohlcv_stock):
    a daily accumulation-quality signal (delivery vs intraday churn). Add to the **Flow** lens as an
    "accumulation" sub-component (delivery-trend vs 30/60d avg + up/down-day asymmetry; liquidity floor;
    thresholds in atlas_thresholds). Likely lifts Flow's IC (currently weakest, 0.012) → its weight.
  - **rs_*_sector** (sector RS, currently inert/0%).
  - **Options/F&O proxies** (PCR/OI-buildup/IV) — NO feed exists yet; net-new ingestion; decide in/defer.
- **Execution vehicle = tmux goal-loop:** run the long jobs (delivery backfill, journal rebuild, IC
  recalibration) inside **durable tmux sessions** (survive disconnects, watchable via capture-pane,
  no nohup hangs), with a goal spec + falsifiable gate (extend validate_loopC) + resumable state file,
  iterating to green. Adding a lens INPUT forces a rebuild + recalibration; composite refresh is free
  (on-read). Sequence: finalize atom inputs → 1 rebuild → 1 recalibration → lock atom → THEN roll-ups.
- **Table restock** is a POST-backend exercise (FM); the table-manifest audit is a working reference only.

## 2026-06-21 — D18: IC calibration outcome — policy is FYI-only; atom is a 3–6m signal; weights are DB variables.
Walk-forward (purge+embargo) OOS IC on the clean 1854-date PIT journal, across 21/63/126-day
horizons × 5 folds. **Honest result (leakage removed → modest IC, as the IC spec warned):**
- Per-lens OOS IC: **policy +0.070**, technical +0.025, catalyst +0.017, flow +0.012, fundamental +0.011
  (all POSITIVE and sign-stable — none inverse).
- **Policy is REMOVED from the conviction score (FM decision).** Its high IC is a STATIC + hand-curated
  (15 themes = this decade's winners) + selection-biased **regime artifact**, not a forward signal, and
  it's our thinnest-data lens. It is kept as an **FYI overlay only** — still computed/stored/shown as
  context — but excluded from the composite average, the conviction tier, and the convergence bonus
  (`_LENS_NAMES` and convergence in `composite.py`; `lens_weight_policy=0`).
- **Learned weights over the four conviction lenses** (regularized IC-tilt, equal-weight shrink, capped):
  **technical 0.32, catalyst 0.26, flow 0.22, fundamental 0.20** — technical-led (it's the strongest
  medium-term predictor: 6m IC 0.047). Close to the FM's priors.
- **The atom is a MEDIUM-TERM (3–6 month) conviction signal**, not a 1-month one — composite OOS IC
  RISES with horizon: 1m 0.022, 3m 0.029, **6m 0.034** (clears the 0.03 'meaningful' floor at 6m); the
  learned weighting beats equal-weight OOS at 3m & 6m (calibration adds value). Do NOT position/judge the
  atom as a high-frequency signal. C7's honest bar = composite ≥ floor at the 6m design horizon +
  learned ≥ equal at 3m/6m (the spec's blended-0.03 was set WITH the policy artifact inflating it).
- **Weights are NOT hardcoded (FM requirement).** They live as `atlas_thresholds` rows (DB variables),
  read at runtime via `load_thresholds`→`nest_thresholds`→`compute_composite`. A future admin frontend
  can display AND edit them; the backend picks them up next run, no redeploy. Code defaults are fallback
  only and never fire once the DB is populated. Same pattern will extend to the per-altitude
  sector/ETF/fund weights. Provenance also persisted to `atlas_signal_weights` + `atlas_signal_ic`.
- **Caveat (honest):** weights are learned from the same folds the uplift is measured on (mild optimistic
  bias), mitigated by heavy regularization; per-fold train/test is a future hardening. Runtime re-calibration
  should adopt a new weight set only if it beats the incumbent OOS (drift guardrail).

## 2026-06-21 — D17: Loop C wiring decisions (PIT lenses, RS-scale fix, P/B=None, lags, rebuild).
The six-lens stock atom is now genuinely point-in-time. Concrete calls made this loop:
- **Technical PIT:** price = as-of **adjusted close** from `ohlcv_stock` (not the tv_metrics snapshot);
  ATR/BB-width/vol_ratio_30d/60d/pos_52w/rs_*_sector come from `technical_daily` on the scoring date.
- **RS silent-zero defect FIXED:** the RS tier breakpoints assumed ratios ~1.0 but `technicals.py`
  produces return DIFFERENCES centered on 0 → `tech_rs` was 0 for **2075/2090** names. Corrected to
  difference-scale breakpoints (+0.15/+0.08/+0.02/−0.08/−0.15). Sector-RS is blended 50/50 with
  market-RS when present (inert until `rs_*_sector` is populated — a deferred enhancement, not gated).
- **Fundamental PIT:** `fundamental_pit.py` derives as-of TTM/YoY + real **ROE = PAT_ttm/equity** and
  **D/E** (reported quarterly ratio, else borrowings/equity) from `financials_quarterly` +
  `financials_annual`, dedup consolidated-else-standalone. ROA/ROIC/current/quick/gross = None (no source).
- **Valuation PIT:** PE = that-day close ÷ as-of trailing-4Q EPS; as-of cross-sectional sector-median PE;
  52w from `pos_52w`. **P/B and EV/EBITDA = None** (documented): `tv_metrics.book_value_per_share` units
  are unreliable (RELIANCE 7.14 ⇒ 126,554 Cr shares vs real ~1,353 Cr, ~90× off) and there is NO
  face-value feed to turn `paid_up_equity_capital` into a verified share count. RULE #0 forbids a guessed
  P/B. Revisit only if Screener "Book Value per share" is ingested. (FM agreed P/B is not load-bearing —
  it's a valuation sub-dimension, renorm covers its absence; matters mainly for banks/financials.)
- **Reporting lags (FM-proposed):** a filing is knowable `period_end + lag` days later —
  `fundamental_reporting_lag_days = 60` (quarterly income), `annual_reporting_lag_days = 90` (balance
  sheet). Persisted to `atlas_thresholds` in the IC step; defaulted in code so the rebuild needs no write.
- **Forward returns = TRUE forward** over h NSE sessions via NIFTY-50 **calendar reindex** of adjusted
  close (not the trailing `ret_1m`). Caveat: `ohlcv_stock.close_adj` is ≈ raw (only 62/2.87M rows differ)
  — corp-action adjustment is thin; revisit when a real adjusted series lands.
- **Rebuild architecture:** chunk-preload (each worker loads its date-range once → scores in memory via
  the shared `pipeline.score_all`). Chosen over a per-date pipeline + a new `ohlcv_stock(date)` index so
  the shared DB is range-scanned a handful of times, not 1,854× full-scanned — and **no shared-infra
  index/DDL was needed** (the index ask was declined by the safety classifier; this avoids it entirely).
  `backfill_lenses.py --validate-date` proves the chunk path is byte-identical to `run_pipeline`.
- **IC weights consumed:** because per-lens IC is weight-independent, calibrate on the (default-weighted)
  rebuilt journal, write learned weights to `atlas_thresholds` + `atlas_signal_weights`, then recompute
  ONLY the composite/conviction/coverage columns (lens sub-scores untouched) so the journal tracks the
  DB weights — closing C6's default-vs-DB discriminator and C7's persistence.

## 2026-06-21 — D16: Data layer (Phase 1a/1b) DONE; Loop C is the active work.
The six-lens INPUT data is in place and deep: technical 25y; fundamentals NOW historical (income
97% to 2026-03 ~39q/stock + a real balance sheet `financials_annual` 86% ~12y/stock, via the
Screener warm-session fix, XBRL backup); catalyst/flow decades-deep; insider classify fixed; sector
map 95.6% (no 'Other'). Two honest data-layer holes are FOLDED INTO Loop C: **sector-RS** (0%) and
**P/B** (0% — `tv_metrics.market_cap` units are unreliable; compute unit-safe in Loop C from price ×
verified shares ÷ equity or Screener Book Value). **Valuation has NO time history** (`tv_metrics` is a
single snapshot) — its history is RECONSTRUCTED in Loop C, not backfilled. The journal stays C+ until
Loop C recomputes on this data. Next = Loop C (`loopC_atom_complete.md`): 2 blockers → wire lenses to
PIT → rebuild 2019→ → IC. State detail: `docs/atlas-six-lens-coverage-map.md`.

## 2026-06-21 — D15: Free-float weighting; IC-driven conviction at every altitude; backend sequence.
**Weighting (FM):** roll-ups are **free-float market-cap weighted** (= `market_cap × (1 − promoter_%)`,
from tv_metrics + lens_shareholding) — reflects actual tradeable market exposure, the way NIFTY
weights. NOT equal-weight, NOT raw full-cap. Equal-weight is a secondary toggle ("breadth view") only.
**Conviction/composite (FM):** the composite, conviction tier, and BOTH axes of the sector 2×2 are
the **IC-calibrated weights**, not hand-set blends. EACH altitude gets its OWN IC calibration —
stock IC (atom), sector IC, ETF IC, fund IC — because the lenses that predict returns differ by
altitude. The IC calibration is therefore the linchpin: nothing above the atom has trustworthy
conviction until it lands.
**Backend build sequence (entire backend BEFORE any front-end):**
1. Finish the **stock atom → A**: data coverage + Loop C wiring (PIT lenses) + journal rebuild +
   **IC calibration** (conviction becomes IC-driven). [in progress]
2. **Sector roll-up** (free-float-weighted 6-lens + breadth + dispersion + rotation; sector IC; the 2×2).
3. **ETF + Index roll-up** (holdings/constituent-weighted; same machinery; their IC).
4. **Mutual funds** (the final backend part): MF tables + fund lens roll-up + active-movement (MoM
   holdings) + fund ranking + fund IC. Gated on Morningstar APIs + table design (D14).
5. THEN front-end (only once the entire backend is A).

## 2026-06-21 — D14: Priority = journal C+→A first; MF build guidance (deferred).
**Priority order (FM):** (1) get `atlas_lens_scores_daily` from C+ → A — finish data coverage +
re-run the lenses on the new PIT data (Loop C wiring); (2) get ETF-holdings + index-constituents
data to A (small fixes only — they're ~complete); (3) MF later.
**MF guidance (captured for the deferred build):**
- **Universe = GROWTH option, REGULAR plan funds** — the major starting universe.
- `de_mf_nav_daily` must refresh **DAILY** (verify it's a daily job, not a one-off snapshot).
- Holdings refresh MONTHLY on Morningstar; funds typically update ~10th–15th of the month.
  `de_mf_holdings` is **APPEND-ONLY** with `as_of_date` — NEVER overwrite. Every monthly snapshot is
  kept so month-over-month holdings change is preserved (the active-movement / "is the manager
  proactively acting" signal — the differentiator).
- FM will share **Morningstar APIs**; then design the MF table set (master/holdings/nav/risk).

## 2026-06-21 — D13: Sector taxonomy — no thin standalone sector; merge <5 into relevant.
**Rule (FM):** any sector with **fewer than 5 names** in our universe, and any raw thin-tail label
(Conglomerate, Rural, Diversified, Services, MNC, Power, Housing, Consumption, EV & Auto), must be
**merged into the relevant actionable sector** — never kept standalone, never 'Other'. The final
taxonomy is the 22 actionable sectors only. Applies to ALL sector mapping including the Screener
gap-fill (map Screener's taxonomy → the 22, merging anything thin).
**Current state (verified 2026-06-21):** instrument_master.sector = the 22 actionable, min count
Telecom=5 (not <5), zero thin-tail labels — already compliant. Rule is enforced going forward
(esp. the 92-gap Screener fill).

## 2026-06-21 — D12: Full DATA COVERAGE first; roll-ups GATED on a framework discussion.
**Decision (FM):** finish the ENTIRE instrument-level data scope to full coverage BEFORE any
roll-up. The roll-up of ETF / index / sector / mutual-fund is NOT to be started until the whole
roll-up framework is discussed with the FM first. Right now: sole focus = full data coverage.
**Data-coverage scope (the atom's inputs, all 6 lenses to real full coverage):**
1. Finish the running fundamentals backfills (XBRL annual balance sheet + Screener recent quarters).
2. Derive technical sub-components from OHLCV (we hold 25y): ATR(14), BB-width (vol contraction),
   volume-vs-30/60d-avg (participation), 52w-position — stop using the tv_metrics snapshot; + add
   sector-relative RS.
3. Complete the instrument→sector map 750 → 2,093 (22 actionable, no 'Other') — unblocks valuation
   sector-median-PE AND policy matching.
4. Derive P/B from the balance-sheet equity now available (tv_metrics pb_fbs is 0%).
5. Fix the insider `signal_type` classify (currently 100% 'other' → flow promoter + pledge-flag dead).
Then the scoring/journal/IC wiring (loopC) completes the atom. ONLY AFTER all that + a framework
discussion do roll-ups (Loop B+) begin. See `docs/atlas-six-lens-coverage-map.md`.

## 2026-06-21 — D11: Recent-quarters backfill from SCREENER; then LOCK the tables.
**Decision (FM):** the NSE XBRL source reachable here stops at 2024-12-31, but the
fundamental/valuation lenses need the trailing-4-quarter (TTM) financials for the recent
period. **Backfill the 2025-26 quarterly P&L + balance sheet from Screener.in** into
`financials_quarterly` / `financials_annual` (with a `source` provenance marker), then
**LOCK these tables** (treat them as frozen reference once filled + reconciled).
**Why Screener over yfinance:** filing-sourced, India-specific, deep (≈12 quarters + ~10y
annual + balance sheet + ROCE/ROE/D-E), and verified to expose Mar-2025..Mar-2026; yfinance
India fundamentals are shallow/patchy. `tv_metrics` already supplies CURRENT TTM (fresh to
2026-06-20) so the live product is not blind in the meantime.
**Source-of-truth rule:** per (instrument, period) NSE XBRL wins on the overlap (official);
Screener fills only the periods XBRL lacks. Reconcile a known overlap quarter (RELIANCE
Dec-2024 ≈ ₹243,865 Cr consolidated) before trusting Screener numbers. No fabrication.
**Go-forward (separate, later op decision):** pick ONE source for ongoing nightly fundamentals
and align on it — NOT decided here; this entry is only the one-time backfill + lock.

## 2026-06-21 — D10: Fundamentals = COMPLETE, no partial. Full statement, all quarters.
**Decision (FM, emphatic):** the fundamental feed must be COMPLETE — **income statement
AND balance sheet**, for **every quarter NSE has filed through the latest (2025–26)**, for
the whole ~2,093-stock universe. No stopping at 2024. No income-statement-only.
**Why:** historical ROE / debt-to-equity / ratios require the balance sheet, and the journal
must reflect every real quarter. Income-statement-only + stale-to-2024 is the exact partial
work that has been happening for months.
**VERIFIED against real NSE filings (RELIANCE, 2026-06-21) — the data is ALL there, we only
fetched one filing type and parsed a fraction of it:**
- `period=Quarterly` filing (what we fetch today): full P&L (have) PLUS disclosed
  **`DebtEquityRatio`**, `DebtServiceCoverageRatio`, `PaidUpValueOfEquityShareCapital`
  (context `OneD`) — never parsed.
- `period=Annual` filing (NOT fetched today): the FULL balance sheet — `Equity` (₹925,788 Cr
  for RELIANCE), `BorrowingsNoncurrent`/`BorrowingsCurrent`, trade payables, `EquityAndLiabilities`
  (context `OneI`) + the full cash-flow statement → real **ROE = PAT/Equity** and real D/E.
**How to apply (complete, not partial):**
1. Extend the quarterly parser to capture `DebtEquityRatio`/`DebtServiceCoverageRatio`/paid-up
   equity from the `OneD` context (add columns to `financials_quarterly`).
2. ADD an annual fetch (`period=Annual`) + balance-sheet parser (`OneI` context: Equity,
   Borrowings*) → new `foundation_staging.financials_annual` table → ROE/D/E history.
3. The "2024 cap" is NOT a cutoff — the ingester skips instruments marked `done` in `xbrl_state`.
   Run with **`--redo`** to re-fetch ALL periods (quarterly + annual) for ALL ~2,093 instruments
   through the latest filed period. Resumable via `xbrl_state`; safe to kill/restart.
4. Balance sheet is annual/half-yearly under SEBI LODR — ROE/D/E are annual-grain; never fabricate
   the off quarters (carry the latest annual value forward as-of, flagged with its age).

## 2026-06-21 — D9: Calendar source of truth = NIFTY 50 `index_prices` (Loop A, shipped).
Trading dates come from `foundation_staging.index_prices WHERE index_code='NIFTY 50'`
(membership), never `date.today()`, raw `technical_daily` (junk holiday rows), or
`de_trading_calendar` (mislabels Budget-Sunday, future-dated). 2019-01-01..2026-06-19 = **1,920**
sessions — derive at runtime, never hardcode.

## 2026-06-21 — D8: Two prerequisites block IC and must land FIRST.
(a) `compute_composite` reads nested threshold keys that `load_thresholds()` (flat) never
returns → DB/IC weights are silently ignored. (b) `calibration._load_fwd_returns` uses
`technical_daily.ret_1m`, which is the **trailing** 21-day return, as "forward" → IC is a
tautology. Both must be fixed before any weight is learned.

## 2026-06-21 — D7: Funds deferred to Loop B+ (after the atom). Active-movement is the edge.
All fund work parked until the atom is calibrated, built once on it (same roll-up as ETFs).
Most fund infra already exists (`de_mf_master`, time-versioned `de_mf_holdings`, NAV,
`fund_scorecard.py`, M4 lenses). The genuine differentiator = the **month-over-month
holdings-delta (active-movement) lens** — not yet built; needs deeper monthly holdings history
from Morningstar. See memory `v4-fund-ranking`.

## 2026-06-21 — D6: Sequence = Loop A (hygiene) → Loop C (atom) → Loop B+ (roll-ups).
Reversed the earlier A→B→C. The roll-up output is a pure function of the atom, so building
roll-ups before the atom is calibrated means computing them twice. Finish + calibrate the atom
first. See `loopC_atom_complete.md`.

## 2026-06-21 — D5: Journal depth target = 2019-01-01 onward (~7.5y, ~1,920 sessions).
Inside every feed once XBRL is refreshed. IC calibrated on this clean PIT history.

## 2026-06-21 — D4: Valuation — no fabricated scores (Loop A, shipped).
No-data → `None`/`UNKNOWN`/1.00× (was a 35/FAIR stub). Renormalise over present dimensions
only (dropped the 0.6 imputation). As-of PE (price ÷ as-of TTM EPS) is built in Loop C.

## 2026-06-21 — D3: RULE #0 — tests assert on REAL DB records (Loop A, shipped).
`test_scorers.py` rewritten 65 synthetic → 25 real-data reconciliation tests. Definition-of-done
is a real-data gate (`validate_lenses.py`, immutable), never synthetic fixtures.

## 2026-06-21 — D2: bulk_deals deferred (forward-only).
Proven load-failure (snapshot-only ingester); document + run nightly going forward. Flow scores
via insider + shareholding regardless.

## 2026-06-21 — D1: No synthetic/derived data anywhere (CLAUDE.md RULE #0, standing).
Every number traces to a real source. What a feed cannot support is `None`, never a stub.
