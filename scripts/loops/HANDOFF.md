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

## IN FLIGHT / NEXT (the fundamentals fix — COMPLETE, per DECISIONS D10)

1. **Extend the XBRL parser to the balance sheet** (`ingest_xbrl.py` `_TAGS` + columns + context).
   Verify the real balance-sheet tag local-names + contextRef against an actual NSE filing first.
2. **Full `--redo` re-ingest** — all quarters through latest (2025–26), all ~2,093 instruments,
   full statement. Long-running, resumable via `xbrl_state`; run in background.
3. Then Loop C proper: fix the two blockers (D8) → rewire fundamental/valuation/flow/technical to
   the historical tables → rebuild journal 2019→2026 → calibrate IC → confirm composite consumes
   the learned weights.

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
