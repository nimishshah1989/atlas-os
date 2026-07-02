#!/bin/bash
# Atlas v4 DAILY orchestrator (Mon–Fri, POST-CLOSE ~16:00 IST). The single canonical
# daily refresh, replacing the JIP/M2-M5/intelligence cron tangle. All writes land in
# ONE schema (foundation_staging). Calculations anchor to the last COMPLETE EOD (D11).
# Prices are Kite-only via the batched quote() path (no historical-burst throttle).
#
# Non-fatal step model: a failed step never aborts the chain; failures are collected
# and alerted once at the end. The frontend is deployed ONLY if both gates pass, so a
# stale/broken run can never overwrite the last-good board.
#
#   bash scripts/ops/atlas_daily.sh
set -uo pipefail
REPO=/home/ubuntu/atlas-os
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation"   # covers both import styles
source "$REPO/.venv/bin/activate"
set -a; source .env; set +a
PY="$REPO/.venv/bin/python"
LOG=/home/ubuntu/logs/atlas_daily_$(date +%Y%m%d_%H%M%S).log
mkdir -p /home/ubuntu/logs
EOD=$($PY -c "import _db; print(_db.eod_cutoff())")
echo "=== atlas_daily EOD=$EOD  $(date -Is) ===" | tee -a "$LOG"

FAILURES=()
step() {  # step "name" cmd...   (non-fatal; records failures)
  local name="$1"; shift
  echo "--- $name ---" | tee -a "$LOG"
  if "$@" >>"$LOG" 2>&1; then echo "  ok: $name" | tee -a "$LOG"
  else echo "  FAIL: $name (rc=$?)" | tee -a "$LOG"; FAILURES+=("$name"); fi
}

# 0. Ensure a Kite token (the 08:50 cron normally has it; re-try once if missing).
$PY -c "import _db; from atlas.intraday.auth import get_valid_access_token; get_valid_access_token(conn_str=_db.db_url())" >>"$LOG" 2>&1 \
  || step "kite_autologin" $PY scripts/kite_autologin.py

# 1. INGEST (Kite single source, batched quote() — no throttle) + input feeds.
step "ingest_eod (kite quote)"   $PY scripts/foundation/ingest_kite.py --eod
step "ingest_bhavcopy (indices)" $PY scripts/foundation/ingest_bhavcopy.py --date "$EOD"
step "fetch_delivery"            $PY scripts/foundation/fetch_delivery.py
step "backfill_delivery"         $PY scripts/foundation/backfill_delivery.py
step "ingest_filings"            $PY scripts/foundation/ingest_filings.py
step "ingest_insider"            $PY scripts/foundation/ingest_insider.py

# 2. COMPUTE cascade (EOD-anchored, single schema).
step "compute_all (technicals)"  $PY scripts/foundation/compute_all.py
step "build_index_metrics"       $PY -m scripts.foundation.build_index_metrics
step "lens_daily"                $PY scripts/lens_daily.py --as-of "$EOD"
step "rollup_sectors"            $PY scripts/foundation/rollup_sectors.py
step "build_fund_rank_history"   $PY scripts/foundation/build_fund_rank_history.py --latest
step "build_breadth_series"      $PY scripts/foundation/build_breadth_series.py
step "regime"                    $PY -c "from atlas.compute.regime import run_daily_regime; run_daily_regime(schema='foundation_staging')"

# 3. GATES (assert on REAL produced output — rule #0). Deploy only if BOTH pass.
GATE_OK=1
step "validate_lenses"  $PY scripts/foundation/validate_lenses.py || GATE_OK=0
if $PY scripts/ops/freshness_guard.py --eod "$EOD" >>"$LOG" 2>&1; then
  echo "  ok: freshness_guard" | tee -a "$LOG"
else
  echo "  FAIL: freshness_guard" | tee -a "$LOG"; FAILURES+=("freshness_guard"); GATE_OK=0
fi

# 4. SERVE — flush the Next fetch-cache + reload so the board re-reads the fresh EOD.
#    Skipped if a gate failed (don't publish a stale/broken board).
if [ "$GATE_OK" = "1" ]; then
  rm -rf "$REPO/frontend/.next/cache/fetch-cache"
  step "deploy (pm2 reload)" pm2 reload atlas-frontend-v3
else
  echo "  SKIP deploy — a gate failed; keeping last-good board" | tee -a "$LOG"
fi

# 5. REPORT (Telegram alert on any failure).
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "=== atlas_daily COMPLETE — all green (EOD=$EOD) ===" | tee -a "$LOG"
else
  MSG="atlas_daily $EOD FAILURES: ${FAILURES[*]}"
  echo "=== $MSG ===" | tee -a "$LOG"
  $PY -c "from atlas.intraday.notify import send_message_sync; send_message_sync('⚠️ $MSG')" >>"$LOG" 2>&1 || true
fi
