# Atlas v4 six-lens — DECISION LOG (durable, append-only; newest on top)

The single source of truth for locked decisions. Every non-obvious call lands here
with a date and a why. Do not re-litigate a decision recorded here without adding a
new dated entry that supersedes it.

---

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
