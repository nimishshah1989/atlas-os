#!/bin/bash
# Atlas v4 DAILY orchestrator (Mon–Fri, POST-CLOSE ~19:30 IST (after NSE bhavcopy publishes)). The single canonical
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
RUNFILE=$(mktemp /tmp/atlas_daily_runs.XXXXXX)   # per-step timings → health snapshot
trap 'rm -f "$RUNFILE"' EXIT
step() {  # step "name" cmd...   (non-fatal; records failures + a run row)
  local name="$1"; shift
  local start; start=$(date -Is)
  echo "--- $name ---" | tee -a "$LOG"
  local st
  if "$@" >>"$LOG" 2>&1; then echo "  ok: $name" | tee -a "$LOG"; st=success
  else echo "  FAIL: $name (rc=$?)" | tee -a "$LOG"; FAILURES+=("$name"); st=failed; fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$start" "$(date -Is)" "$st" >> "$RUNFILE"
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
# Sector relative-strength (rs_{1m,3m,6m,12m}_sector) for the latest date — depends on
# compute_all's ret_W and the sector index prices. --latest keeps it fast (one date);
# score_technical does NOT consume these (display-only), so this never shifts composites.
step "backfill_sector_rs"        $PY scripts/foundation/backfill_sector_rs.py --latest
step "build_index_metrics"       $PY -m scripts.foundation.build_index_metrics
# Macro overlay (FRED FX/rates/brent + carry-forward of the lagging India-10Y/CPI/FII/DII)
# for the market-pulse strip — its old 5-source runner was purged; froze at 06-25. Needs
# technical_daily (the trading calendar) fresh, so runs after compute_all.
step "ingest_macro"              $PY scripts/foundation/ingest_macro.py
step "lens_daily"                $PY scripts/lens_daily.py --as-of "$EOD"
step "rollup_sectors"            $PY scripts/foundation/rollup_sectors.py
# Sector RRG (relative-rotation quadrants) for the sectors page — index-derived, cheap;
# was frozen at 06-25 (no producer croned). Refresh after the sector roll-up.
step "build_sector_rrg"          $PY scripts/foundation/build_sector_rrg.py
# Sector cards / breadth / deepdive — the three derived board tables the /sectors +
# stock-detail pages render. Their old builder (atlas/compute/sectors.py) was purged in
# the consolidation and they silently froze at 06-24/25; this lean rebuild reads only fresh
# tables (index metrics + technical_daily + lens journal). Must run after build_index_metrics.
step "build_sector_cards"        $PY scripts/foundation/build_sector_cards.py
step "build_fund_rank_history"   $PY scripts/foundation/build_fund_rank_history.py --latest
step "build_breadth_series"      $PY scripts/foundation/build_breadth_series.py
step "regime"                    $PY -c "from atlas.compute.regime import run_daily_regime; run_daily_regime(schema='atlas_foundation')"

# 3. GATES (assert on REAL produced output — rule #0). Deploy only if ALL pass.
# Run gates DIRECTLY (not via step): step() records a failure but always returns 0,
# so `step ... || GATE_OK=0` never fired — a failed gate could still deploy. And
# validate_lenses requires --check A|B (calling it bare errors rc=2 every run).
# Gate steps are recorded into the runfile too (as pipeline_runs rows), so /health shows
# each night's real gate outcome. gate() mirrors step() but drives GATE_OK on a real fail.
GATE_OK=1
gate() {  # gate "name" cmd...
  local name="$1"; shift
  local start; start=$(date -Is)
  echo "--- $name ---" | tee -a "$LOG"
  local st
  if "$@" >>"$LOG" 2>&1; then echo "  ok: $name" | tee -a "$LOG"; st=success
  else echo "  FAIL: $name" | tee -a "$LOG"; FAILURES+=("$name"); GATE_OK=0; st=failed; fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$start" "$(date -Is)" "$st" >> "$RUNFILE"
}
gate "validate_lenses_A" $PY scripts/foundation/validate_lenses.py --check A
gate "validate_lenses_B" $PY scripts/foundation/validate_lenses.py --check B
gate "validate_lenses_C" $PY scripts/foundation/validate_lenses.py --check C
gate "freshness_guard"   $PY scripts/ops/freshness_guard.py --eod "$EOD"

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

# 4b. OBSERVABILITY — write the nightly health snapshot (per-step runs + validator
#     outcomes + live freshness) so /health and /admin/data-status show THIS run, not a
#     frozen clone. Non-fatal; all rows are real produced output (rule #0).
$PY scripts/ops/write_health_snapshot.py --runfile "$RUNFILE" --eod "$EOD" >>"$LOG" 2>&1 \
  && echo "  ok: write_health_snapshot" | tee -a "$LOG" \
  || { echo "  FAIL: write_health_snapshot" | tee -a "$LOG"; FAILURES+=("write_health_snapshot"); }

# 5. REPORT (Telegram alert on any failure).
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "=== atlas_daily COMPLETE — all green (EOD=$EOD) ===" | tee -a "$LOG"
else
  MSG="atlas_daily $EOD FAILURES: ${FAILURES[*]}"
  echo "=== $MSG ===" | tee -a "$LOG"
  $PY -c "from atlas.intraday.notify import send_message_sync; send_message_sync('⚠️ $MSG')" >>"$LOG" 2>&1 || true
fi
