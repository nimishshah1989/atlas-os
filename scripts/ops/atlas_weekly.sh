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

step "ingest_fund_master"  $PY scripts/foundation/ingest_fund_master.py
step "ingest_mf_holdings"  $PY scripts/foundation/ingest_mf_holdings.py
step "ingest_screener"     $PY scripts/foundation/ingest_screener.py
step "ingest_shareholding" $PY scripts/foundation/ingest_shareholding.py

if [ ${#FAILURES[@]} -eq 0 ]; then echo "=== atlas_weekly COMPLETE — all green ===" | tee -a "$LOG"
else MSG="atlas_weekly FAILURES: ${FAILURES[*]}"; echo "=== $MSG ===" | tee -a "$LOG"
  $PY -c "from atlas.intraday.notify import send_message_sync; send_message_sync('⚠️ $MSG')" >>"$LOG" 2>&1 || true; fi
