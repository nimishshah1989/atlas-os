#!/bin/bash
# Global Atlas DAILY orchestrator — 01:00 UTC Tue–Sat (= 21:00 ET the previous evening, after
# extended hours; 06:30 IST, before India's 16:00 IST run). Writes ONLY atlas_global; every
# calculation anchors to the last COMPLETE US session (EOD = _gdb.eod_cutoff(), 17:00 ET).
#
# Same non-fatal step model as scripts/ops/atlas_daily.sh: a failed step never aborts the
# chain; failures are collected and reported once. Nothing deploys from this box — the
# global board is Vercel + ISR, so "publish" is ONE revalidate webhook, fired only when
# every gate passes. Gate failures push to Telegram; step failures pull (/health).
#
# PHASE 0 SKELETON: only freshness_guard is wired (registry contract; tables empty-but-valid).
# Every Phase 1 step and gate is listed below, commented, in the plan's order. Uncomment a
# step ONLY in the PR that lands its producer WITH its board surface, and register the table
# in scripts/global_market/freshness_guard.py PRODUCERS in the same PR (commented steps do
# not satisfy the registry — check_producers ignores comment lines). A gate is wired only
# once its check exists: a gate known to fail every night trains the FM to ignore the push.
#
#   bash scripts/ops/atlas_global_daily.sh
set -uo pipefail
REPO=/home/ubuntu/atlas-os
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation:$REPO/scripts/global_market"
source "$REPO/.venv/bin/activate"
set -a; source .env; set +a
PY="$REPO/.venv/bin/python"
LOG=/home/ubuntu/logs/atlas_global_daily_$(date +%Y%m%d_%H%M%S).log
mkdir -p /home/ubuntu/logs
EOD=$($PY -c "import _gdb; print(_gdb.eod_cutoff())")
echo "=== atlas_global_daily EOD=$EOD  $(date -Is) ===" | tee -a "$LOG"

FAILURES=()
RUNFILE=$(mktemp /tmp/atlas_global_daily_runs.XXXXXX)   # per-step timings → health snapshot
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

# 1. INGEST (Phase 1). ingest_prices must abort loudly if SPY has no bar for $EOD — the
#    anchor calendar is membership-by-presence of SPY bars, so a missing anchor means no
#    session to score, not a quiet carry-forward.
# step "ingest_prices"           $PY scripts/global_market/ingest_prices.py --eod "$EOD"
# step "ingest_macro"            $PY scripts/global_market/ingest_macro.py
# step "ingest_filings_8k"       $PY scripts/global_market/ingest_filings_8k.py
# step "ingest_form4"            $PY scripts/global_market/ingest_form4.py
# step "ingest_issuer_holdings"  $PY scripts/global_market/ingest_issuer_holdings.py

# 2. COMPUTE cascade (EOD-anchored, single schema).
# step "compute_technicals"      $PY scripts/global_market/compute_technicals.py
# step "build_exposures"         $PY scripts/global_market/build_exposures.py --changed
# step "score_stocks"            $PY scripts/global_market/score_stocks.py --as-of "$EOD"
# step "score_etfs"              $PY scripts/global_market/score_etfs.py --as-of "$EOD"
# step "build_country_views"     $PY scripts/global_market/build_country_views.py
# step "build_universe_snapshot" $PY scripts/global_market/build_universe_snapshot.py
# Rolling signal quality — step, not gate (a lens losing IC is a finding for the FM, not a
# reason to withhold a correct board). Window start computed in Python (no GNU `date -d`).
# IC_START=$($PY -c "import datetime as d, _gdb; print(_gdb.eod_cutoff() - d.timedelta(days=730))")
# step "eval_signal"             $PY scripts/global_market/eval_signal.py --start "$IC_START" --end "$EOD"

# 3. GATES (assert on REAL produced output — rule #0). Publish only if ALL pass.
# Run gates DIRECTLY (not via step): step() always returns 0, so a failed gate could
# otherwise still publish. Gate outcomes are recorded into the runfile too.
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
gate "freshness_guard"   $PY scripts/global_market/freshness_guard.py --eod "$EOD"
# gate "validate_global_A" $PY scripts/global_market/validate_global.py --check A   # Phase 1
# gate "validate_global_B" $PY scripts/global_market/validate_global.py --check B   # Phase 3
# gate "validate_global_C" $PY scripts/global_market/validate_global.py --check C   # Phase 3
# gate "validate_global_D" $PY scripts/global_market/validate_global.py --check D   # Phase 3

# 4. PUBLISH — the board advances by ISR revalidation, never a rebuild here. Phase 1 wires
#    the Vercel on-demand revalidate route (tag 'eod'); until then this only logs.
if [ "$GATE_OK" = "1" ]; then
  echo "--- publish (revalidate tag 'eod') ---" | tee -a "$LOG"
  # curl -sf -m 15 -X POST "${GLOBAL_REVALIDATE_URL}" \
  #   -H "Authorization: Bearer ${GLOBAL_REVALIDATE_SECRET}" \
  #   -H 'Content-Type: application/json' -d '{"tag":"eod"}' -o /dev/null \
  #   && echo "  ok: publish" | tee -a "$LOG" \
  #   || { echo "  FAIL: publish" | tee -a "$LOG"; FAILURES+=("publish"); }
  echo "  SKIP publish — Phase 0: no revalidate webhook wired yet" | tee -a "$LOG"
else
  echo "  SKIP publish — a gate failed; the board keeps its last-good data" | tee -a "$LOG"
fi

# 4b. OBSERVABILITY (Phase 1): the nightly health snapshot — per-step runs + validator
#     outcomes + live freshness — a 1:1 copy of scripts/ops/write_health_snapshot.py over
#     atlas_global, read by the global /health route. Non-fatal.
# $PY scripts/global_market/write_health_snapshot.py --runfile "$RUNFILE" --eod "$EOD" >>"$LOG" 2>&1 \
#   && echo "  ok: write_health_snapshot" | tee -a "$LOG" \
#   || { echo "  FAIL: write_health_snapshot" | tee -a "$LOG"; FAILURES+=("write_health_snapshot"); }

# 5. REPORT. Gate failures PUSH (the board did not update and nothing else would say so —
#    India's 2026-08-19 four-silent-days lesson); step failures pull via /health.
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "=== atlas_global_daily COMPLETE — all green (EOD=$EOD) ===" | tee -a "$LOG"
else
  MSG="atlas_global_daily $EOD FAILURES: ${FAILURES[*]}"
  echo "=== $MSG ===" | tee -a "$LOG"
  if [ "$GATE_OK" != "1" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -sf -m 10 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
      --data-urlencode "text=GLOBAL BOARD NOT UPDATED — atlas_global_daily $EOD gate failed, board keeps last-good data. Failed: ${FAILURES[*]}" \
      -o /dev/null || echo "  (gate alert send failed — check /health)" | tee -a "$LOG"
  fi
fi
