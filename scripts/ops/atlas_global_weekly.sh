#!/bin/bash
# Global Atlas WEEKLY refresh — Sat 01:00 UTC (India's weekly is 07:00 UTC, its daily 10:30
# UTC — no CPU overlap on the 2-vCPU box). The slower, weekly-cadence sources: identity
# (Nasdaq directory / SEC tickers / Alpaca assets), index membership, N-PORT holdings + AUM,
# XBRL financials, 13F, FINRA short interest, then the classification delta and a weekly
# ETF-score backfill. Writes ONLY atlas_global. Same step()/gate()/runfile/Telegram
# scaffolding as scripts/ops/atlas_daily.sh.
#
# PHASE 0 SKELETON: only freshness_guard is wired (registry contract; tables empty-but-valid).
# Every Phase 1–3 step is listed below, commented, in the plan's order. Uncomment a step
# ONLY in the PR that lands its producer WITH its board surface, and register the table in
# scripts/global_market/freshness_guard.py PRODUCERS in the same PR (commented steps do
# not satisfy the registry — check_producers ignores comment lines).
#
#   bash scripts/ops/atlas_global_weekly.sh
set -uo pipefail
REPO=/home/ubuntu/atlas-os
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/global_market:$REPO/scripts/foundation"   # global before foundation: same-named India scripts must not shadow ours
source "$REPO/.venv/bin/activate"
set -a; source .env; set +a
PY="$REPO/.venv/bin/python"
LOG=/home/ubuntu/logs/atlas_global_weekly_$(date +%Y%m%d_%H%M%S).log
mkdir -p /home/ubuntu/logs
EOD=$($PY -c "import _gdb; print(_gdb.eod_cutoff())")
echo "=== atlas_global_weekly EOD=$EOD  $(date -Is) ===" | tee -a "$LOG"

FAILURES=()
RUNFILE=$(mktemp /tmp/atlas_global_weekly_runs.XXXXXX)   # per-step timings → health snapshot
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

# 1. IDENTITY first — build_identity is instrument_master's ONLY writer; everything below
#    keys off a fresh master (renames become symbol_alias rows, never a second instrument).
#    The Stooq archive (hand-downloaded; docs/global/data-sources.md) supplies the delisted
#    names — passed only when it is on the box, never invented.
STOOQ_ZIP="${STOOQ_ARCHIVE:-/home/ubuntu/data/stooq/d_us_txt.zip}"
STOOQ_ARG=(); [ -f "$STOOQ_ZIP" ] && STOOQ_ARG=(--stooq-zip "$STOOQ_ZIP")
step "build_identity"           $PY scripts/global_market/build_identity.py --snapshot-dir "/home/ubuntu/logs/identity/$EOD" "${STOOQ_ARG[@]}"
step "seed_benchmarks"          $PY scripts/global_market/seed_benchmarks.py
step "ingest_index_membership"  $PY scripts/global_market/ingest_index_membership.py --eod "$EOD"
# 2. SLOW FEEDS (EDGAR / FINRA).
# step "ingest_nport"             $PY scripts/global_market/ingest_nport.py             # long tail + AUM (Phase 2)
# step "ingest_financials"        $PY scripts/global_market/ingest_financials.py        # companyfacts, changed filers (Phase 3)
# step "ingest_13f"               $PY scripts/global_market/ingest_13f.py               # Phase 3
# step "ingest_short_interest"    $PY scripts/global_market/ingest_short_interest.py    # Phase 3
# 3. CLASSIFY + RE-SCORE.
# step "classify_etfs"            $PY scripts/global_market/classify_etfs.py --delta    # rules + LLM for new/changed only (Phase 2)
# step "build_exposures"          $PY scripts/global_market/build_exposures.py --all    # Phase 2
# step "score_etfs_backfill"      $PY scripts/global_market/score_etfs.py --backfill-week   # Phase 3

# 4. GATES (assert on REAL produced output — rule #0). Run directly, never via step().
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
# gate "validate_global_E" $PY scripts/global_market/validate_global.py --check E   # classification coverage (Phase 2)

# 5. REPORT. Gate failures push (the FM would otherwise only find out on /health).
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "=== atlas_global_weekly COMPLETE — all green (EOD=$EOD) ===" | tee -a "$LOG"
else
  MSG="atlas_global_weekly $EOD FAILURES: ${FAILURES[*]}"
  echo "=== $MSG ===" | tee -a "$LOG"
  if [ "$GATE_OK" != "1" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -sf -m 10 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
      --data-urlencode "text=GLOBAL BOARD NOT UPDATED — atlas_global_weekly $EOD gate failed. Failed: ${FAILURES[*]}" \
      -o /dev/null || echo "  (gate alert send failed — check /health)" | tee -a "$LOG"
  fi
fi
