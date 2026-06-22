# LOOP D — delivery-% accumulation enrichment (atom input) + rs_*_sector

**Read `GUARDRAILS.md` first and obey it absolutely.** Branch `feat/v4-six-lens`.
**DEPENDS ON LOOP C being green + the atom locked = A** (on-read composite; D19). This loop adds
ONE new atom INPUT, which forces exactly ONE journal rebuild + ONE IC recalibration (D6 build-once,
D19). Composite refresh is FREE (on-read). Do NOT start the rebuild COMPUTE until Loop C is locked.

## Goal (one sentence)

Add a **daily delivery-% accumulation signal** to the **Flow** lens — delivery-trend vs its own
30/60-day average + up/down-day asymmetry — sourced PIT from `public.de_equity_ohlcv.delivery_pct`,
with thresholds in `atlas_thresholds`; then rebuild the journal once and recalibrate IC once so the
composite (on-read) reflects Flow's (expected) higher IC. Optionally bundle **rs_*_sector** (sector
relative-strength, currently inert/0%) into the SAME rebuild + recalibration to avoid a second cycle.

## Why (D19)

Delivery % = the fraction of traded volume that settles as real delivery (vs intraday churn). Rising
delivery on up-days is an accumulation signature (conviction buying, not day-trading froth). Flow is
today the WEAKEST conviction lens (OOS IC ≈ 0.012); a real accumulation signal is the most plausible
lift, and a higher Flow IC raises Flow's learned weight — all reflected on-read, no re-materialise.

## The falsifiable GATE — your only definition of done (do NOT weaken)

Loop D is done iff, on REAL produced output:
1. `python scripts/foundation/validate_loopC.py --mode full` exits 0 — **C1–C8 stay green** (the
   on-read atom is unbroken), AND the NEW **C9 (delivery)** group passes.
2. `python scripts/foundation/validate_lenses.py --check A` exits 0 (immutable — run SOLO; it has
   full-table aggregates that need the whole 600s/query budget, so never run it next to another
   DB-heavy job — see the Loop-C contention lesson in SUMMARY).
3. `pytest atlas/lenses` green (pure-fn + real-data tests for the new accumulation sub-component).

**C9 — delivery enrichment is real, PIT, and additive (add to `validate_loopC.py`):**
- **C9a populated**: `technical_daily.delivery_pct` is non-null for ≥ (verified coverage − margin)
  of (instrument, date) rows that have a `de_equity_ohlcv.delivery_pct` on the same (instrument_id,
  date). Verify the real coverage in D0 first; assert against THAT number, not a guess.
- **C9b PIT / reconciled**: on ≥20 real (instrument, date) samples, `technical_daily.delivery_pct`
  == `de_equity_ohlcv.delivery_pct` for the SAME date (delivery % is an EOD-published same-day
  observable → no forward shift, but PROVE it reconciles to the raw feed and is never future-dated).
- **C9c None, never 0**: names/dates with no `de_equity_ohlcv` delivery row (or below the liquidity
  floor) have `delivery_pct IS NULL` and the Flow **accumulation** sub-component NULL — never a
  fabricated 0/neutral (RULE #0). Assert ≥1 legitimately-NULL real case and 0 coerced-to-0 cases.
- **C9d Flow wired**: the Flow lens exposes a populated `flow_accumulation` sub-score for a
  meaningful share of names on a recent date (it FIRES), and it is NULL where delivery is NULL.
- **C9e Flow IC uplift (honest)**: Flow's walk-forward OOS IC AFTER the rebuild ≥ Flow's OOS IC
  BEFORE (recorded pre-value in SUMMARY/DECISIONS). If it does NOT lift, that is a real negative
  result — record it, keep the sub-component as transparency-only context, do NOT fake a lift, and do
  NOT raise Flow's weight artificially. The gate asserts "computed + sign-stable", and the uplift is
  reported; an FM decision governs whether a non-lifting signal stays in the composite.

## The model — what "point-in-time" means for delivery

For session D, delivery_pct(D) is knowable on D (published with the EOD bhavcopy). Trailing averages
(`delivery_avg_30d/60d`) and up/down-day asymmetry use ONLY sessions ≤ D. No future session feeds the
signal. Below a liquidity floor the signal is None (illiquid names have noise-dominated delivery %).

## Data (verified 2026-06-22)

- `public.de_equity_ohlcv(instrument_id uuid, date, symbol, delivery_pct numeric)` — the source.
  Prompt says ~79% coverage; **VERIFY the real % in D0** and assert C9a against it. Fresh feed.
- `foundation_staging.ohlcv_stock` — NO delivery column. `foundation_staging.technical_daily` — NO
  delivery column (target of the new columns). technical_daily is the per-(instrument,date) daily
  frame the journal rebuild chunk-preloads, so delivery colocates there (as ATR/BB/vol did in
  d276efe) even though it semantically feeds Flow — the rebuild reads it for free.

## Steps — STRICT order, each validated before the next; LONG steps run in a DURABLE tmux session

> **Execution vehicle = tmux goal-loop (D19).** Run every long job (backfill, rebuild, recalibration)
> inside `tmux new-session -d -s loopD` — survives disconnects, watch via `tmux capture-pane -t loopD
> -p`, NEVER nohup (it hung repeatedly). Keep a resumable state file (e.g. `scripts/loops/.loopD_state`
> / the existing `xbrl_state`-style marker) so a throttle/OOM costs only a restart, never data. ≤6
> workers (shared box). Watch `free -h` / `df -h /` before each parallel stage.

**D0 — verify the source (cheap, read-only).** Real delivery_pct coverage vs the universe + per-name
depth; pick the liquidity-floor metric (e.g. trailing-30d median traded value or volume) and its
threshold; reconcile 2 names' delivery_pct to a known NSE bhavcopy figure. Write the verified
coverage number into C9a. No fabrication.

**D1 — migration (additive, non-destructive).** New nullable columns on
`foundation_staging.technical_daily`: `delivery_pct numeric`, `delivery_avg_30d numeric`,
`delivery_avg_60d numeric`, `delivery_trend numeric` (current vs avg; ratio or z), `delivery_updown_asym
numeric` (avg delivery on up-days − down-days over a trailing window). All NULL on no-source/illiquid.
New `atlas_thresholds` rows for every cutoff (windows, liquidity floor, accumulation tier breakpoints)
— NO hardcoded constants (arch rule #3). Decimal for any money-like value.

**D2 — PIT backfill into technical_daily (tmux, resumable, chunked).** Per instrument, stream its
`de_equity_ohlcv` delivery series ordered by date and compute the rolling/asymmetry signals as-of each
session (only ≤ D). Write in SMALL batches with TCP keepalives + bounded statement_timeout; chunk by
instrument-range; resumable via the state marker. This is a one-time FEED materialisation (legitimate,
like ATR/BB) — NOT the composite (that stays on-read). **VACUUM (ANALYZE) technical_daily after** the
write (GUARDRAILS §5; reclaims dead tuples so later full-table gate scans stay under the 600s/query
cap). Validate a sample reconciles to de_equity_ohlcv before proceeding.

**D3 — Flow accumulation sub-component (pure fn + real-data tests).** In `atlas/lenses/compute/flow.py`
add an `accumulation` sub-score from delivery_trend (vs 30/60d) + up/down-day asymmetry, thresholds
from `atlas_thresholds`; None below the liquidity floor or with no delivery. Re-weight Flow's existing
sub-components (promoter/smart-money) + accumulation so they renormalise over PRESENT dims only (the
existing renorm pattern — never impute). Wire the delivery fields from the technical frame through the
adapter into `score_flow` (the frame already carries the per-(instrument,date) technical row). Tests:
reconcile the sub-score to a hand calc on REAL delivery rows for ≥2 names; assert None where delivery
NULL; assert it fires where delivery present.

**D4 — (optional, bundle) rs_*_sector.** Populate sector relative-strength (`rs_*_sector` = stock ret −
its sector-index ret) in technical_daily from `index_prices` sector indices (29/30 ready). Wire into
score_technical's already-present sector-RS path (currently inert, blends 50/50 with market-RS).
Doing this HERE means one rebuild + one recalibration instead of two. If deferred, say so explicitly.

**D5 — rebuild the journal ONCE (tmux goal-loop, the big compute).** `backfill_lenses.py`
2019-01-01→latest NIFTY-50 session, chunk-preload, resumable, ≤6 workers. Run
`validate_loopC.py --mode progress` between chunks to catch a re-introduced leak early. Stream/batch —
never load all in memory. The composite is NOT written (on-read); only the lens SUB-scores (incl. the
new Flow sub-score) are materialised.

**D6 — recalibrate IC ONCE.** `scripts/foundation/calibrate_loopC.py` — Flow IC changes → new learned
weights to `atlas_thresholds` + `atlas_signal_weights` + `atlas_signal_ic`. Adopt the new weight set
only if it beats the incumbent OOS (drift guardrail, D18). Composite reflects new weights on-read, free.

**D7 — validate + lock.** `validate_loopC.py --mode full` (C1–C9) exits 0 SOLO; `validate_lenses
--check A` exits 0 SOLO; `pytest atlas/lenses` green. Spot-check 2 real names' accumulation sub-score
vs the raw delivery feed with NO lookahead. Update SUMMARY/DECISIONS/HANDOFF. Commit granularly +
push. Lock the atom. ONLY THEN do roll-ups (Loop B+) proceed.

## Constraints (obey — from GUARDRAILS + the Loop-C hard lessons)

- RULE #0: no synthetic/derived data anywhere incl. tests. Missing delivery → None, never 0/neutral.
- Composite/conviction/coverage stay ON-READ (D19) — never re-materialise 3.9M composites.
- No big derived write-loops to Supabase except the one-time FEED backfill (D2), done in small
  batches + durable tmux + VACUUM after. Never nohup.
- Thresholds/weights are `atlas_thresholds` DB variables (frontend-editable) — never hardcoded.
- Run the immutable `validate_lenses --check A` and the heavy `validate_loopC --mode full` SOLO (no
  concurrent DB-heavy job) — concurrent full-table scans contend and trip the per-query timeout.
- ≤6 local workers (shared box). Watch free/df before parallel stages. Resumability over speed.
