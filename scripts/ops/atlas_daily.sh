#!/bin/bash
# Atlas v4 DAILY orchestrator (Mon–Fri, POST-CLOSE ~16:00 IST). The single canonical
# daily refresh, replacing the JIP/M2-M5/intelligence cron tangle. All writes land in
# ONE schema (atlas_foundation). Calculations anchor to the last COMPLETE EOD (D11).
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
step "ingest_nav (AMFI)"         $PY scripts/foundation/ingest_nav.py
step "ingest_bulk_deals"         $PY scripts/foundation/ingest_bulk_deals.py

# 2. COMPUTE cascade (EOD-anchored, single schema).
step "compute_all (technicals)"  $PY scripts/foundation/compute_all.py
step "build_index_metrics"       $PY -m scripts.foundation.build_index_metrics
step "lens_daily"                $PY scripts/lens_daily.py --as-of "$EOD"
step "rollup_sectors"            $PY scripts/foundation/rollup_sectors.py
step "build_fund_rank_history"   $PY scripts/foundation/build_fund_rank_history.py --latest
step "build_breadth_series"      $PY scripts/foundation/build_breadth_series.py
step "regime"                    $PY -c "from atlas.compute.regime import run_daily_regime; run_daily_regime(schema='atlas_foundation')"

# 3. GATES (assert on REAL produced output — rule #0). Deploy only if ALL pass.
# Run gates DIRECTLY (not via step): step() records a failure but always returns 0,
# so `step ... || GATE_OK=0` never fired — a failed gate could still deploy. And
# validate_lenses requires --check A|B (calling it bare errors rc=2 every run).
GATE_OK=1
for chk in A B; do
  echo "--- validate_lenses ($chk) ---" | tee -a "$LOG"
  if $PY scripts/foundation/validate_lenses.py --check "$chk" >>"$LOG" 2>&1; then
    echo "  ok: validate_lenses $chk" | tee -a "$LOG"
  else
    echo "  FAIL: validate_lenses $chk" | tee -a "$LOG"; FAILURES+=("validate_lenses:$chk"); GATE_OK=0
  fi
done
if $PY scripts/ops/freshness_guard.py --eod "$EOD" >>"$LOG" 2>&1; then
  echo "  ok: freshness_guard" | tee -a "$LOG"
else
  echo "  FAIL: freshness_guard" | tee -a "$LOG"; FAILURES+=("freshness_guard"); GATE_OK=0
fi

# 4. SERVE — REBUILD then reload, with a .next backup + rollback on build failure
#    (mirrors atlas-auto-deploy.sh). The board's home/sectors/stocks pages are static-ISR:
#    they bake the "as of" EOD date at BUILD time, so a bare reload wouldn't advance them —
#    only a rebuild re-prerenders them. Skipped if a gate failed. HYGIENE: reload ONLY after
#    the build completes (never mid-build — that corrupts .next and 500s the whole board).
if [ "$GATE_OK" = "1" ]; then
  echo "--- deploy (rebuild + reload) ---" | tee -a "$LOG"
  cd "$REPO/frontend"
  STAMP=$(date +%Y%m%d_%H%M%S)
  [ -d .next ] && cp -r .next ".next.bak.$STAMP"
  rm -rf .next/cache/fetch-cache
  if NEXT_PUBLIC_LENS_V4=1 NODE_OPTIONS='--max-old-space-size=3072' npm run build >>"$LOG" 2>&1 \
     && [ -f .next/BUILD_ID ]; then
    rm -rf .next/cache/fetch-cache
    pm2 reload atlas-frontend-v3 --update-env >>"$LOG" 2>&1 && echo "  ok: deploy (rebuild + reload)" | tee -a "$LOG"
    ls -1dt "$REPO/frontend"/.next.bak.* 2>/dev/null | tail -n +4 | xargs -r rm -rf  # keep 3 backups
  else
    echo "  FAIL: build — rolling back to previous .next" | tee -a "$LOG"; FAILURES+=("deploy_build")
    rm -rf .next && mv ".next.bak.$STAMP" .next 2>/dev/null
    pm2 reload atlas-frontend-v3 --update-env >>"$LOG" 2>&1
  fi
  cd "$REPO"
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
