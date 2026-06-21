# Atlas v4 six-lens — DECISION LOG (durable, append-only; newest on top)

The single source of truth for locked decisions. Every non-obvious call lands here
with a date and a why. Do not re-litigate a decision recorded here without adding a
new dated entry that supersedes it.

---

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
