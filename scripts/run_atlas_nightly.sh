#!/bin/bash
# Atlas nightly pipeline: JIP sync → M2 → M3 → M4 → M5 → health check
# Runs Mon-Fri at 21:00 IST (15:30 UTC) after NSE market close + JIP ETL
# Failures trigger email notification via scripts/notify_failure.py.
set -euo pipefail

LOG_DIR=/home/ubuntu/atlas-compute/output
mkdir -p $LOG_DIR
LOG=$LOG_DIR/nightly_$(date +%Y%m%d_%H%M%S).log
VENV=/home/ubuntu/atlas-os/.venv
REPO=/home/ubuntu/atlas-os
TODAY=$(date +%Y-%m-%d)
FAILED_STEP=""

cd $REPO
source $VENV/bin/activate
set -a; source .env; set +a

# Email on any failure and re-raise the exit code.
on_error() {
  local exit_code=$?
  echo "=== FAILED at step: $FAILED_STEP (exit $exit_code) ===" | tee -a $LOG
  python3 scripts/notify_failure.py "$FAILED_STEP" "$LOG" 2>&1 | tee -a $LOG || true
  exit $exit_code
}
trap on_error ERR

echo "=== Atlas nightly pipeline $TODAY ===" | tee -a $LOG

FAILED_STEP="[1] JIP sync"
echo "$FAILED_STEP (yesterday's data)..." | tee -a $LOG
python3 scripts/jip_incremental_sync.py --from-date $(date -d 'yesterday' +%Y-%m-%d) 2>&1 | tee -a $LOG

FAILED_STEP="[1b] AMFI supplemental NAV sync"
echo "$FAILED_STEP (funds JIP does not cover)..." | tee -a $LOG
python3 scripts/amfi_nav_backfill.py --write --stale-days 5 2>&1 | tee -a $LOG

FAILED_STEP="[1c] NSE bhavcopy ETF sync"
echo "$FAILED_STEP (tickers not in JIP)..." | tee -a $LOG
python3 scripts/etf_sector_backfill.py --start $(date -d "yesterday" +%Y-%m-%d) --end $(date +%Y-%m-%d) --force 2>&1 | tee -a $LOG

FAILED_STEP="[1d] Global price refresh (MSCIWORLD/SP500 benchmarks)"
echo "$FAILED_STEP (URTH, ^GSPC last 7 days)..." | tee -a $LOG
python3 scripts/refresh_global_prices.py --days 7 2>&1 | tee -a $LOG

FAILED_STEP="[1e] Stooq daily OHLCV update (US+Global)"
echo "$FAILED_STEP (us_atlas + global_atlas OHLCV)..." | tee -a $LOG
set +e
python3 scripts/stooq_daily_update.py 2>&1 | tee -a $LOG
set -e

FAILED_STEP="[1f] Corporate-action close_adj recompute (idempotent)"
echo "$FAILED_STEP (populates de_equity_ohlcv.close_adj from observed split-day price moves)..." | tee -a $LOG
set +e
python3 scripts/atlas_compute_adjustments.py 2>&1 | tee -a $LOG
set -e

FAILED_STEP="[2] M2 stocks+ETFs"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/m2_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[3] M3 indices+sectors+regime"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/m3_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[4] M4 fund NAV+states"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/m4_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[5] M5 decisions"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/m5_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[5b] US ETF daily compute"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/us_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[5c] Global ETF daily compute"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/global_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[5d] US Stocks daily compute (S&P 500)"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/us_stocks_daily.py 2>&1 | tee -a $LOG

FAILED_STEP="[6] Health check"
echo "$FAILED_STEP..." | tee -a $LOG
python3 scripts/health_check_daily.py 2>&1 | tee -a $LOG

# Frontend validator — non-fatal: Playwright/network issues must not abort the pipeline.
echo "[7] Frontend validator (Phase C route crawler)..." | tee -a $LOG
PYTHONPATH=$REPO python3 scripts/crawl_frontend.py 2>&1 | tee -a $LOG ||   echo "WARNING: frontend validator step failed (non-fatal — check log for details)" | tee -a $LOG

echo "=== Done $(date) ===" | tee -a $LOG
