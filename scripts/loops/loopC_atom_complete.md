ultracode

# AUTONOMOUS LOOP C — complete & CALIBRATE the stock atom (point-in-time + IC)

**FIRST read `scripts/loops/GUARDRAILS.md` and obey it absolutely.** Branch `feat/v4-six-lens`.
**DEPENDS ON LOOP A (done).** Loop A made the journal CLEAN (276 real NSE sessions, calendar from
`index_prices['NIFTY 50']`, RULE #0 real-data tests). Loop C makes it CORRECT THROUGH TIME and
CALIBRATED. **This loop blocks the ETF/index/fund/sector roll-ups** (Loop B+) — the atom must be
final before anything rolls up, or every roll-up is computed twice.

## CURRENT STATUS (2026-06-21) — data layer READY; this loop = wiring + blockers + rebuild + IC

The input data is now in place and deep enough (verify with `validate_lenses.py --check A` + the
queries below). What changed since the spec was first written:
- **Fundamentals NOW HAVE HISTORY** (the old hard gap): income statement to **2026-03** (97% of
  ~2,093, ~39 quarters/stock median) + a real **balance sheet** `foundation_staging.financials_annual`
  (Equity/Borrowings → ROE/D-E, ~86%, ~12y/stock) — both via `ingest_screener.py` (warm-session fix)
  with `ingest_xbrl.py` as the official backup. Reconciled to XBRL on the overlap.
- **Technical vol-contraction/volume/52w are now PIT** (derived from 25y OHLCV in `technical_daily`:
  `atr_14, bb_width, vol_ratio_30d/60d, pos_52w`). EMA/RSI/RS already PIT.
- **Insider `signal_type` fixed** (real `acqMode`/`tdpTransactionType`) → promoter/pledge fire.
- **Sector map complete** to 95.6% on `instrument_master.sector` (22 actionable, no 'Other', D13 rule).
- Decisions locked: free-float weighting + IC-driven conviction at every altitude (D15); journal depth
  from 2019-01-01 (D5); see `DECISIONS.md` D1–D16 and `docs/atlas-six-lens-coverage-map.md` (state).

**STILL OWED — this loop's work (in order):**
1. The two co-equal blockers (Step 0 below): composite flat→nested weights; forward-return fix.
2. Wire every lens to the PIT source (Step 2): fundamental from `financials_quarterly` +
   `financials_annual` as-of; **valuation history BUILT here** (it is snapshot-only today — `tv_metrics`,
   no time dimension) from 25y price ÷ as-of TTM EPS + as-of sector-median PE; **P/B unit-safe** (do
   NOT use `tv_metrics.market_cap` — unreliable units; use price × verified shares ÷ equity, or
   Screener Book Value); **valuation 52w** wired to `technical_daily.pos_52w` (not the snapshot);
   **sector-RS** (`rs_*_sector` = stock ret − its sector-index ret; 29/30 sector indices ready in
   `technical_daily`/`index_prices`); flow as-of shareholding/insider.
3. Rebuild the journal PIT 2019→now (Step 4). 4. IC calibration (Step 6). → journal C+ **→ A**.

## Why this loop exists (the core defect, verified against the live DB)

Only the *appearance* of history exists. Measured on `atlas.atlas_lens_scores_daily` (asset_class
='stock'), within-instrument variation across dates is essentially ZERO for three lenses and
PARTIAL for a fourth — today's values stamped backward = a **lookahead leak** that makes any IC
calibration a fiction:

| lens | instruments that VARY across dates | reality |
|---|---|---|
| technical | 2082/2093 | EMA/RSI/RS are real PIT… **but price/52w/volume/ATR/BB come from the `tv_metrics` snapshot** (adapters.py `load_technical_data` LEFT JOIN) — partially leaky |
| catalyst | varies | real (date-filtered `lens_filings`) — but only ~1,340 instruments have filings in 2019 |
| fundamental | **0/2073** | today's `tv_metrics` stamped on every date |
| valuation | 333/2083 | today's `tv_metrics` stamped |
| flow | 833/2001 | latest shareholding/insider stamped; **`lens_insider.signal_type` is 100% 'other'** so promoter/pledge paths never fire |
| policy | 0/2093 | static by design (fine) |

Two further **capital-correctness defects** (confirmed) make calibration meaningless until fixed:
- **Composite ignores DB weights.** `compute_composite` reads nested `th.get('lens_weights')` /
  `'conviction_tiers'` / `'convergence'` / `'breakpoints_*'`, but `atlas.db.load_thresholds()`
  returns FLAT keys (`lens_weight_technical=0.20`, `lens_conviction_high_score=58`, …). The engine
  ALWAYS falls back to `_DEFAULT_*` → **IC-learned weights are silently discarded.**
- **Forward returns are actually TRAILING.** `calibration._load_fwd_returns` loads
  `technical_daily.ret_1m/3m/6m` as `fwd_return`, but `ret_1m` == the **trailing** 21-day close
  return (verified equal to 1e-9). IC then correlates a lens with the PAST → a tautology (worst for
  technical). No forward shift exists in `_compute_lens_ic`.

## THE GATE — the goalpost (your only definition of done; do NOT weaken)

A NEW independent validator **`scripts/foundation/validate_loopC.py`** (hand-written, NOT by the
build loop; `validate_lenses.py` is immutable and stays green too). It asserts on REAL produced
output. Loop C is done iff `python scripts/foundation/validate_loopC.py --mode full` exits 0 AND
`validate_lenses.py --check A` still exits 0 AND `pytest atlas/lenses` is green.

- **C1 — Time-variance, ALL SIX lenses.** For technical, fundamental, valuation, catalyst, flow,
  (policy exempt — structural): a large majority of instruments with >5 dated rows have >1 distinct
  value across the journal. (fundamental/valuation/flow go from ~0 to the majority.)
- **C2 — No snapshot stamping.** For fundamental/valuation/flow the share of instruments whose value
  is byte-identical on EVERY scored date is < 5% (today ~100%).
- **C3 — PIT correctness, fundamental/valuation, NO lookahead.** On a real past `as_of` (e.g.
  2022-03-15) over ≥20 real instruments, the inputs implied by the journal use ONLY data with
  `period_end <= as_of` (respecting the reporting-lag) and `close` from that date; reconcile to the
  raw feed (e.g. INFY rev_ttm/eps_ttm; RELIANCE pe_ttm = close ÷ trailing-4Q EPS).
- **C4 — PIT correctness, flow/catalyst, NO lookahead.** Every filing feeding catalyst on `as_of`
  has `filing_date <= as_of`; every shareholding row `period_end <= as_of`; every insider txn
  `transaction_date <= as_of`.
- **C5 — Depth.** `count(distinct date)` for stocks in 2019-01-01..2026-06-19 equals the **NIFTY 50
  session count DERIVED AT RUNTIME** from `index_prices` (≈ **1,920** — NEVER hardcode), and ≥80% of
  the ~2,093 instruments have ≥ that-minus-listing-grace dates.
- **C6 — Composite consumes DB weights (blocker proven fixed).** Load DB `lens_weight_*` via
  `load_thresholds`, recompute the weighted avg for ≥20 real journal rows, and assert it matches the
  stored composite; perturb a DB weight in a test schema → composite changes.
- **C7 — Forward returns are forward + walk-forward IC ≥ floor + persisted.** Assert the returns fed
  to IC are TRUE forward returns (shifted h NIFTY sessions ahead, not trailing); walk-forward
  (purged+embargoed) produces ≥4 non-overlapping test folds with a per-date cross-section ≥5 floor;
  out-of-sample test-IC ≥ `IC_FLOOR` (0.03) for ≥ the top-2 lenses; weights persisted to
  `atlas_signal_weights` + `atlas_thresholds` with provenance (the 30 stale NaN `atlas_signal_ic`
  rows superseded by as_of/rolling-window versioning).
- **C8 — Graceful degradation is REAL, not fabricated.** Average `coverage_factor` on early-year
  rows (2019-2020, financials cover ~1,200 instruments) is measurably LOWER than late-year; every
  metric with no PIT source is `None` (never 0/neutral) — fundamental profitability/balance-sheet
  and valuation P/B carry `evidence.*.reason = 'missing'`; the 287 `xbrl_state='no_data'` names have
  `fundamental IS NULL` on every date.

## The model — what "point-in-time" means here

For each historical NSE session D and each stock, score the lens vector using ONLY information a
human had on D: that day's `close` (real OHLCV), the latest XBRL quarter with `period_end <= D −
reporting_lag`, the latest shareholding with `period_end <= D`, insider txns dated `<= D`, filings
dated `<= D`. No future quarter, no today's snapshot. What the feed cannot support as-of (a real
balance sheet) is `None`, never fabricated.

## Data available (real, verified — reuse, do NOT re-fetch unless a task says so)

- `foundation_staging.financials_quarterly` — XBRL quarterly **income statement** (revenue, ebit,
  ebitda, pbt, pat, eps, finance_costs, net_margin, ebitda_margin; `consolidated` flag; **NO balance
  sheet**). 64,860 rows, 1,806 instruments, 2016-12..**2024-12 (STALE)**; `xbrl_state` = 1806 done /
  287 no_data (genuine sparsity). Dedup rule: prefer `consolidated=true` else standalone (≤2 rows per
  instrument+period, verified).
- Historical price for as-of valuation/technical: the real OHLCV (`ohlcv_stock` / `de_equity_ohlcv` /
  `technical_daily` 2000→now) — the as-of source for `close`, 52w hi/lo, volume, ATR, BB. **Not
  `tv_metrics`.**
- `foundation_staging.lens_shareholding` (quarterly `period_end`, 2001→2026), `lens_insider`
  (2008→2026, `signal_type` defect), `lens_filings` (2002→2026), `lens_bulk_deals` (BROKEN snapshot).
- Sector: `atlas/universe/sectors.py` (22-actionable rollup) + `atlas.atlas_sector_master`; only
  750/2093 stocks mapped today — Loop C completes it.
- IC machinery: `atlas/lenses/calibration.py`, `atlas.atlas_signal_ic`, `atlas.atlas_signal_weights`,
  `atlas.atlas_thresholds`.

## Tasks — STRICT dependency order (each stage validated before the next)

**0. PRE-FLIGHT — the two co-equal blockers (cheap, no rebuild; verify on the existing 276-date
journal).**
   - **0a. Composite uses DB weights.** Add a flat→nested thresholds adapter (`atlas/lenses/compute/
     thresholds_view.py`) feeding `compute_composite` the `lens_weights`/`conviction_tiers`/
     `convergence`/`breakpoints_*` shapes built from the flat `load_thresholds` keys (or rewrite
     `compute_composite` to read flat). Prove C6 on today's journal.
   - **0b. Forward returns are forward.** Rewrite `calibration._load_fwd_returns` / `_compute_lens_ic`
     to build TRUE forward returns shifted h NIFTY-50 sessions AHEAD of each scoring date (purge +
     embargo), NOT `ret_1m`. Prove C7's forward-return assertion on real rows. **Learned weights are
     worthless until BOTH 0a and 0b land.**

**1. Atom prerequisites (parallel).**
   - **1a. XBRL refresh → 2026** for all 2,093 incl. the ~11 insurers (non-Ind-AS taxonomy) + a
     `--redo` over the recoverable `no_data` tail; never fabricate a missing quarter.
   - **1b. Complete instrument→sector map** — migration adds `foundation_staging.instrument_master.
     sector`; populate all ~2,093 via `sectors.py` (22 actionable, **no "Other"**). Feeds valuation's
     as-of sector-median PE.

**2. Make EVERY leaking lens point-in-time** (as-of loaders + scorer extensions; pure modules, real-
   data tests):
   - **2a. Fundamental** — `load_fundamental_data_asof` (DISTINCT ON dedup, trailing-8Q panel);
     `fundamental_pit.py` derives TTM/YoY + the NEW trend signals (margin streak, EBIT-margin
     inflection labelled **ROCE_PROXY** not fake ROCE, deleveraging via finance_costs trajectory).
     ROE/ROA/ROIC/D-E/CR/QR = **None** (no balance sheet) → profitability+balance_sheet subcomponents
     None; the renorm already handles it.
   - **2b. Valuation** — as-of PE = that-day close ÷ as-of TTM EPS; as-of EV/EBITDA; P/B = None
     (no equity feed, documented); as-of cross-sectional sector-median PE (needs 1b). Fixes the
     thin-data bias (more dims fire once sector + real ratios exist).
   - **2c. Flow** — shareholding as-of latest `period_end<=D` + prior quarter for QoQ (steps
     quarterly); insider as-of rolling dated window; bulk = explicit `unavailable_snapshot_only`
     marker, never fabricated.
   - **2d. Technical (the missed leak)** — source price/52w-hi/lo/volume/ATR/BB from historical OHLCV
     as-of D, not `tv_metrics`. EMA/RSI/RS already PIT from `technical_daily`.
   - **2e. risk_flags** — audit its inputs (pipeline.py) for snapshot sources; make as-of or declare
     + gate it as not-yet-PIT so no consumer treats it as a signal.

**3. Insider ingest fix + re-ingest (DB-mutating, FM-approved).** Repoint `_classify` to the real
   txn-type/acq-mode fields so `signal_type` is no longer uniformly 'other'; keep the `_parse_date`
   bound (Loop A); re-ingest (~35-60 min, resumable). Flow cannot clear C1/C2 without this.

**4. Rebuild the journal 2019-01-01..2026-06-19** (~1,920 sessions × ~2,093 stocks ≈ 3.9M rows).
   `backfill_lenses.py` (NIFTY 50 dates), chunked by calendar window, **resumable**, **≤6 workers**
   on the shared box; run `validate_loopC.py --mode progress` between chunks to catch a re-introduced
   leak early. Stream/batch — never load all in memory.

**5. Validate** — `validate_loopC.py --mode full` exits 0; `validate_lenses.py --check A` no
   regression; `pytest` green.

**6. Calibrate IC** — `calibrate_lens_ic` + `propose_weights` (walk-forward, purge/embargo, per-date
   cross-section ≥5 floor, record n per date) on the clean forward-return-correct journal → persist
   IC (superseding the stale NaN rows) + weights to `atlas_thresholds`.

**7. Confirm consumption** — re-run C6/C7: the composite uses the newly written DB weights. Only
   then is Loop C done and the roll-ups (Loop B+) may proceed.

## Accuracy discipline (GUARDRAILS §2)

Before each commit: run `validate_loopC.py` (relevant mode) + `pytest` + spot-check 2 real names per
reworked lens against the raw feed AS-OF a real past date with NO lookahead (e.g. INFY fundamental
as_of 2025-01-20; RELIANCE PE as_of 2025-02-12; SUZLON flow quarter-step + pledge). Adversarially
review each lens diff. NEVER claim green you haven't proven by the gate on REAL produced output.

## Open FM decisions (resolve before/within the loop)

1. **Reporting-lag** for financials availability — one `atlas_thresholds` value (proposal: **60
   days** conservative; the only honest as-of availability proxy without a filing-date column).
2. **Staleness policy** — for as_of in 2025-26 the latest quarter can be >180d old (XBRL stale to
   2024 until task 1a); score on last real filing + flag `data_age_days`, or null past N days?
3. **Banks/insurers** — `is_bank` rows file a different P&L; score on the bank template or exclude +
   flag? (~11 insurers + banks.)
4. **Frontend None-rendering** — narrowed lenses + early-year sparsity produce many `None`; the
   `NEXT_PUBLIC_LENS_V4` surfaces must render "insufficient data", never coerce None→0/neutral.
5. **Depth honesty** — fundamental/valuation are predominantly None in 2019-2020 (financials cover
   ~1,200/2,093); confirm that early-year composites legitimately lean on technical/catalyst with a
   lower `coverage_factor` (C8) rather than being suppressed.
