#!/bin/bash
# Atlas nightly pipeline: JIP sync → M2 → M3 → M4 → M5 → health check
# Runs Mon-Fri at 18:00 UTC (23:30 IST) after NSE close + JIP ETL.
#
# Failure model (2026-05-29 hardening):
# - Steps DO NOT abort the pipeline. Each step runs in isolation; failures
#   are captured and reported at the end via notify_failure.py.
# - Rationale: breadth (M2+M3) was going NULL because an upstream step
#   (e.g. [1f] close_adj recompute) raised → `set -e + trap ERR` aborted the
#   whole chain → M2/M3 skipped → atlas_market_regime_daily.pct_above_ema_50
#   NULL. The page rendered "BREADTH n/a" for the trader.
# - With this refactor, EVERY step runs to its own completion; M2/M3 always
#   execute as long as the script itself starts. notify_failure still fires
#   at the end with the list of failed steps so we don't lose alerting.

set -uo pipefail
# NOTE: NO `set -e` and NO `trap ERR` — see header.

LOG_DIR=/home/ubuntu/atlas-compute/output
mkdir -p $LOG_DIR
LOG=$LOG_DIR/nightly_$(date +%Y%m%d_%H%M%S).log
VENV=/home/ubuntu/atlas-os/.venv
REPO=/home/ubuntu/atlas-os
TODAY=$(date +%Y-%m-%d)

cd $REPO
source $VENV/bin/activate
set -a; source .env; set +a

# Track failed steps so a single end-of-run notify covers everything.
FAILURES=()

# run_step <step_id> <description> <command...>
# Captures exit code, logs banner + outcome, never aborts the chain.
run_step() {
  local step="$1"; shift
  local descr="$1"; shift
  echo "" | tee -a $LOG
  echo "=== $step $descr ===" | tee -a $LOG
  "$@" 2>&1 | tee -a $LOG
  local rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ]; then
    echo "=== $step EXIT=$rc (continuing chain) ===" | tee -a $LOG
    FAILURES+=("$step (exit $rc)")
  else
    echo "=== $step OK ===" | tee -a $LOG
  fi
  return 0
}

echo "=== Atlas nightly pipeline $TODAY ===" | tee -a $LOG

run_step "[1]"  "JIP sync (yesterday's data)" \
  python3 scripts/jip_incremental_sync.py --from-date "$(date -d 'yesterday' +%Y-%m-%d)"

run_step "[1b]" "AMFI supplemental NAV sync (funds JIP does not cover)" \
  python3 scripts/amfi_nav_backfill.py --write --stale-days 5

run_step "[1c]" "NSE bhavcopy ETF sync (tickers not in JIP)" \
  python3 scripts/etf_sector_backfill.py --start "$(date -d 'yesterday' +%Y-%m-%d)" --end "$(date +%Y-%m-%d)" --force

run_step "[1d]" "Global price refresh (MSCIWORLD/SP500 benchmarks last 7 days)" \
  python3 scripts/refresh_global_prices.py --days 7

run_step "[1e]" "Stooq daily OHLCV update (us_atlas + global_atlas)" \
  python3 scripts/stooq_daily_update.py

run_step "[1f]" "Corporate-action close_adj recompute (idempotent)" \
  python3 scripts/atlas_compute_adjustments.py

run_step "[2]"  "M2 stocks+ETFs (writes atlas_stock_metrics_daily + atlas_stock_states_daily)" \
  python3 scripts/m2_daily.py

run_step "[3]"  "M3 indices+sectors+regime (writes atlas_market_regime_daily incl. breadth)" \
  python3 scripts/m3_daily.py

run_step "[4]"  "M4 fund NAV+states" \
  python3 scripts/m4_daily.py

run_step "[5]"  "M5 decisions" \
  python3 scripts/m5_daily.py

run_step "[5b]" "US ETF daily compute" \
  python3 scripts/us_daily.py

run_step "[5c]" "Global ETF daily compute" \
  python3 scripts/global_daily.py

run_step "[5d]" "US Stocks daily compute (S&P 500)" \
  python3 scripts/us_stocks_daily.py

run_step "[6]"  "Health check" \
  python3 scripts/health_check_daily.py

# Frontend validator — also non-fatal, kept separate because it's a Playwright job.
echo "" | tee -a $LOG
echo "=== [7] Frontend validator (Phase C route crawler) ===" | tee -a $LOG
PYTHONPATH=$REPO python3 scripts/crawl_frontend.py 2>&1 | tee -a $LOG
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then
  echo "=== [7] EXIT=$rc (non-fatal — Playwright/network often flaky) ===" | tee -a $LOG
  FAILURES+=("[7] (exit $rc)")
else
  echo "=== [7] OK ===" | tee -a $LOG
fi

# End-of-run summary + notification
echo "" | tee -a $LOG
echo "=== Pipeline finished $(date) ===" | tee -a $LOG
if [ "${#FAILURES[@]}" -eq 0 ]; then
  echo "=== ALL STEPS OK ===" | tee -a $LOG
  exit 0
else
  echo "=== ${#FAILURES[@]} step(s) failed: ===" | tee -a $LOG
  for f in "${FAILURES[@]}"; do
    echo "  - $f" | tee -a $LOG
  done
  # Notify with the full list of failed steps.
  python3 scripts/notify_failure.py "${FAILURES[*]}" "$LOG" 2>&1 | tee -a $LOG || true
  # Exit non-zero so cron + agent3 see the failure for self-healing.
  exit 1
fi
