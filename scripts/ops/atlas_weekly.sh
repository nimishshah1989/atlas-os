#!/bin/bash
# Atlas v4 WEEKLY refresh (Saturday). The slower, weekly-cadence sources: MF holdings +
# fund/ETF masters (Morningstar), fundamentals/ratios (screener), shareholding pattern.
# Daily prices/scoring are handled by atlas_daily.sh. Non-fatal; Telegram-alerts on fail.
set -uo pipefail
REPO=/home/ubuntu/atlas-os
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation"
source "$REPO/.venv/bin/activate"
set -a; source .env; set +a
PY="$REPO/.venv/bin/python"
LOG=/home/ubuntu/logs/atlas_weekly_$(date +%Y%m%d_%H%M%S).log
echo "=== atlas_weekly $(date -Is) ===" | tee -a "$LOG"
FAILURES=()
step() { local n="$1"; shift; echo "--- $n ---" | tee -a "$LOG"
  if "$@" >>"$LOG" 2>&1; then echo "  ok: $n" | tee -a "$LOG"; else echo "  FAIL: $n" | tee -a "$LOG"; FAILURES+=("$n"); fi; }

# Universe membership + sector guard first, so the fund/holdings ingests below key off a
# fresh instrument_master. build_universe refreshes NIFTY-500 membership from live NSE
# (active-stock diff printed; a reconstitution is surfaced, never silent); assign_sectors
# guards the ≤21-sector mapping and loudly reports any un-sectored active name.
step "build_universe"      $PY scripts/foundation/build_universe.py
step "assign_sectors"      $PY scripts/foundation/assign_sectors.py
# populate_etf_isin MUST follow build_universe: build_universe recreates ETF rows with a
# NULL isin, so the Morningstar-holdings bridge has to be re-filled after every rebuild.
step "populate_etf_isin"   $PY scripts/foundation/populate_etf_isin.py
# etf_sector MUST follow build_universe for the same reason — recreated ETF rows come back
# with a NULL sector, which would silently re-break the model-portfolio sector pies (the
# Passive book is 100% ETFs). Idempotent; fails loudly if any active ETF ends up unlabelled.
step "etf_sector"          $PY scripts/foundation/etf_sector.py

step "ingest_fund_master"  $PY scripts/foundation/ingest_fund_master.py
step "ingest_mf_holdings"  $PY scripts/foundation/ingest_mf_holdings.py
# ETF holdings (same Morningstar service, keyed by mstar_id) — had no producer croned and
# froze at 05-04 (59d); feeds the /etfs+/funds lens roll-ups and sector free-float weights.
step "ingest_etf_holdings" $PY scripts/foundation/ingest_etf_holdings.py
step "ingest_screener"     $PY scripts/foundation/ingest_screener.py
step "ingest_shareholding" $PY scripts/foundation/ingest_shareholding.py
# Market cap (screener scrape — slow, weekly cadence is fine) + fundamentals (XBRL filings).
step "fetch_marketcap"     $PY scripts/foundation/fetch_marketcap.py
# v_stock_cap ranks the caps fetched above, so it re-applies right after them. The view
# itself never goes stale (it is a view, not a MV) — this is CREATE OR REPLACE so the
# board's one cap-cohort definition has a producer in the pipeline rather than living
# only wherever it was last typed by hand.
step "cap_cohort"          $PY scripts/foundation/cap_cohort.py
step "ingest_xbrl"         $PY scripts/foundation/ingest_xbrl.py

# System-generated portfolios: the walk-forward expert agent. Weekly cadence (its own
# anti-noise floor is min_days_change); evaluates each system portfolio's policy on an
# out-of-sample window and promotes a challenger only if it clears the bar (excess return
# over NIFTY 500 with max-drawdown below it), journaling the evidence. Reads only fresh
# scored tables, so it runs last. On promotion it re-runs that portfolio's backtest.
step "portfolio_evolve"    $PY scripts/foundation/portfolio_evolve.py
# Desk weekly reflection: updates each desk's lessons from forward outcome stamps
# (confidence earned/decayed), retires dead lessons. Needs the week's desk_journal
# + desk_outcomes rows, both written nightly by desk_run.
# Backtest curves: NOTHING rebuilt these before, so each book's "if this rulebook had run
# for 5 years" chart sat wherever someone last ran it by hand — the FM found 13/34 frozen
# at 21-Jul. Weekly is enough for an 8-year replay across 19 books; nightly is wasteful.
step "portfolio_backtest_rebuild" $PY scripts/foundation/portfolio_run.py backtest --all --years 8
step "desk_reflect"        $PY scripts/foundation/desk_reflect.py
# Desk v2 wave 4: one falsifiable methodology hypothesis + one masked-ticker
# memorization audit per week (rotating desk). Both journal to their tables.
step "desk_hypothesis"     $PY scripts/foundation/desk_hypothesis.py
step "desk_audit_masked"   $PY scripts/foundation/desk_audit_masked.py

if [ ${#FAILURES[@]} -eq 0 ]; then echo "=== atlas_weekly COMPLETE — all green ===" | tee -a "$LOG"
else MSG="atlas_weekly FAILURES: ${FAILURES[*]}"; echo "=== $MSG ===" | tee -a "$LOG"
  : ; fi  # Telegram removed (FM, 2026-07-30) — crossover books only on that channel
