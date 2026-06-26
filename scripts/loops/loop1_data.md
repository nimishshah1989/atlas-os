ultracode

# AUTONOMOUS LOOP 1 — DATA FEEDS for the six-lens engine

**FIRST read `scripts/loops/GUARDRAILS.md` and obey it absolutely** — review before every
commit, push to `feat/v4-six-lens` frequently for phone review, keep `SUMMARY.md` current.

You are running unattended. GOAL, then STOP. Do not deploy, do not merge to main,
do not switch any production surface. Work only on branch `feat/v4-six-lens`
(create from current HEAD if it doesn't exist). Commit your progress there and stop.

## Read first (the locked plan — do not re-derive)
- docs/atlas-v4-blueprint.md  (the architecture + superset guarantee)
- docs/atlas-six-lens-data-spec.md  (every table + metric per lens)
- CLAUDE.md, CONTEXT.md  (rules: modulith, thresholds-in-DB, Decimal, tz-aware, file-size limits)
- Reuse the proven foundation code in scripts/foundation/ (DB helper `_db`, validators).

## GOAL (definition of done)
Every six-lens DATA feed is ingested into the `foundation_staging` / `atlas` schema and
VALIDATED green for the liquid core (current Nifty 500), with no schema/threshold-rule
violations. Stop when a validation script confirms this.

## Tasks (each gated; idempotent; resumable)
1. **Backend triage → all-green**: in scripts/foundation/validate.py make coverage/gap
   metrics listing-relative and ignore non-positive closes; exempt INDIA VIX + liquid-rate
   ETFs from the jump check; seed `foundation_staging.corp_action_event` with the known
   demergers that surfaced (ABLBL, 360ONE, ABFRL, …). Re-run validate.py → liquid core green.
2. **XBRL financials** (deterministic, ready): run `scripts/foundation/ingest_xbrl.py` for all
   ~2,000 stocks (resumable; it self-refreshes NSE cookies). Confirm `foundation_staging.financials_quarterly`
   covers the liquid core with ≥8y of quarters.
3. **Widen tv_metrics → 2,000 + refresh**: extend atlas/tv/screener.py to target the full
   `instrument_master` stock universe (not just ~750); run it; confirm freshness.
4. **Catalyst feed**: port /home/ubuntu/jip-india/india_alpha/fetchers/nse_filings_fetcher.py
   into atlas (reuse its NSE-session cookie pattern) → `atlas.lens_filings`
   (instrument_id, filing_date, category_bucket{earnings|capital|governance}, signal_priority,
   subject_text, extracted_text, source_url). Ingest recent + as much history as the API gives.
5. **Flow feeds**: port the NSE insider (`corporates-pit`), shareholding, and bulk-deals
   fetchers from /home/ubuntu/jip-india/india_alpha/fetchers/ → `atlas.lens_insider`,
   `atlas.lens_shareholding`, `atlas.lens_bulk_deals`. Ingest for the liquid core.

## GATE (stop condition)
Write/extend a validation script that asserts: financials_quarterly, tv_metrics (2000),
lens_filings, lens_insider, lens_shareholding, lens_bulk_deals are all populated for the
Nifty-500 core. When it passes, commit and STOP. Log a one-screen summary of coverage.

## Rules
- Branch `feat/v4-six-lens` only. No deploy, no main, no production switch.
- Thresholds/weights in `atlas_thresholds`, never hardcoded. Decimal for money. Tz-aware.
- If a feed is genuinely blocked (e.g. NSE hard-block), record it, skip, and continue —
  do not loop forever on one feed. Report blockers in the final summary.
- Be minimal: reuse before writing; least code that works (ponytail discipline).
