# Atlas v4 six-lens — HANDOFF / STATUS (current state for the next session)

**Branch:** `feat/v4-six-lens` (all work here; nothing on main, flag OFF in prod).
**Read first:** `GUARDRAILS.md`, `DECISIONS.md`, then this file. Loop specs:
`loopA_data_complete.md` (done), `loopC_atom_complete.md` (the atom), `loopB_etf_sector.md` (roll-ups).
**Gate:** `python scripts/foundation/validate_lenses.py --check A` (immutable). Loop C adds a new
independent `validate_loopC.py`.

## Where we are (2026-06-21)

- **Loop A — DONE, pushed, gate green.** Calendar fix (NIFTY 50), journal cleaned to 276 real
  sessions, RULE #0 real-data tests (37 pytest green), feed-gap proofs. Commits 0bdd087..ce4e8e6.
- **Loop C — speced, NOT built.** `loopC_atom_complete.md` + the C1–C8 goalpost. Design pass found
  3 confirmed defects (forward-return leak, technical snapshot subcomponents, wrong session count).
- **Funds, Loop B+ — deferred** (DECISIONS D6/D7).

## The real state of the data (verified — this is the simple truth)

We HAVE deep history for the six lenses on the 750 universe: technical 99% (~15y daily),
fundamental income-stmt 90% (~12y quarterly), catalyst 99% (~20y), flow shareholding 99% (~16y).
**The gap is not missing data — it is (a) the engine stamps TODAY's `tv_metrics` snapshot on history
for fundamental/valuation instead of reading the historical tables, and (b) the XBRL feed is
income-statement-only and stale to 2024.**

## IN FLIGHT / NEXT (fundamentals — COMPLETE ingester DONE, per DECISIONS D10)

- **DONE (committed 3e49519):** `ingest_xbrl.py` now fetches the COMPLETE statement — quarterly
  P&L + disclosed ratios AND the annual balance sheet (`financials_annual`: Equity, Borrowings →
  real ROE/D-E). Verified on RELIANCE (FY24 equity ₹925,788 Cr, ROE 8.6%).
- **RUNNING (background, PID launched 2026-06-21, log `/tmp/xbrl_redo.log`):** full `--redo`
  re-ingest of all 2,093 instruments — populates `financials_annual` for the universe + the new
  quarterly ratio columns. Resumable via `xbrl_state`. **Check it completed** (`grep COMPLETE
  /tmp/xbrl_redo.log`) before relying on balance-sheet coverage.
- **SOURCE REALITY (verified, not a defect):** the NSE XBRL API reachable here returns data through
  **Dec-2024** (130 RELIANCE records, newest 2024-12-31, nothing filtered). There is no 2025-26
  filing to fetch; the same `--redo` auto-captures newer ones whenever the source has them. The
  fundamental lens uses the latest filed quarter as-of each date (carried forward + age-flagged).
- **RUNNING — Screener backfill (`ingest_screener.py`, log `/tmp/screener_backfill.log`):** fills
  the 2025-26 quarters + annual balance sheet (source='SCREENER') into financials_quarterly/annual.
  Parser reused from jip `screener_fetcher`; basis from page CAPTION; overlap reconciliation gate
  (Screener PAT vs XBRL PAT, 2% OR ₹1cr). Verified: RELIANCE/TCS/POLYCAB recent quarters reconcile
  EXACT; `max(period_end)` now 2026-03-31. Quarantine ~0.5% after the small-cap rounding fix.
  **When COMPLETE:** verify recent-quarter coverage (750 + 2,093), review quarantines, then LOCK
  (D11). Resumable via `screener_state` (`--universe all`, no --redo = skip done).
- **NEXT — Loop C proper:** fix the two blockers (D8) → rewire fundamental/valuation/flow/technical
  to the historical tables (now incl. `financials_annual` for ROE/D-E + Screener recent quarters) →
  rebuild journal → calibrate IC → confirm composite consumes the learned weights.

## Data-coverage progress (D12, 2026-06-21)
- **Sector map (item 3): 2,001/2,093 (95.6%) DONE-ish.** Added `instrument_master.sector`; populated
  from atlas_universe_stocks (750 authoritative) + de_instrument.sector clean-22 direct + ISIN recovery
  + a documented industry→nearest-actionable heuristic for ~90 thin-tail SMEs (Packaging→Capital Goods,
  Paper→Consumer Durables, Conglomerates→Financial Services, business-services→Capital Markets, etc. —
  FLAGGED for refinement). All 22 actionable, NO 'Other'. **92 genuine gaps** = no de_instrument source;
  FILL from Screener (it carries sector) in the final coverage pass.
- Items remaining: technical derivations (ATR/BB/volume/52w/sector-RS from OHLCV), P/B from equity,
  insider signal_type classify fix, + the 92 sector gaps from Screener.

## Gotcha (added 2026-06-21)
- `nohup python3 X &` launches a child; `kill <wrapper-pid>` misses the python child. Kill the
  ACTUAL python PID (`ps -eo pid,cmd | grep '[i]ngest_'`), or two runs race + double-load the source.

## Key files
- Lens engine: `atlas/lenses/{pipeline.py, data/adapters.py, compute/*.py, calibration.py}`
- Feeds: `scripts/foundation/ingest_{xbrl,insider,filings,shareholding,bulk_deals}.py`, `refresh_tv_metrics.py`
- Journal rebuild: `scripts/foundation/backfill_lenses.py`
- Gates: `scripts/foundation/validate_lenses.py` (immutable), `validate_loopC.py` (to build)

## Gotchas (hard-won)
- DB access from `scripts/foundation/`: `python3 -c "import _db; ..."`. Postgres `NaN > 0` is TRUE.
- Destructive DB deletes get blocked by the safety classifier — need explicit FM approval each time.
- `financials_quarterly` has NO balance-sheet columns yet (income statement only) — D10 fixes this.
- 6 corrupt insider rows (year 2924) still in `lens_insider` — harmless (excluded by as_of filter),
  optional purge pending; parser already bounded.
