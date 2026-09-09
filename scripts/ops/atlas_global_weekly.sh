#!/bin/bash
# Global Atlas WEEKLY refresh — Sat 01:30 UTC, after the daily (India's weekly is 07:00 UTC, its daily 10:30
# UTC — no CPU overlap on the 2-vCPU box). The slower, weekly-cadence sources: identity
# (Nasdaq directory / SEC tickers / Alpaca assets), index membership, N-PORT holdings + AUM,
# XBRL financials, 13F, FINRA short interest, then the classification delta and a weekly
# ETF-score backfill. Writes ONLY atlas_global. Same step()/gate()/runfile/Telegram
# scaffolding as scripts/ops/atlas_daily.sh.
#
# PHASE 1: identity, benchmarks, index membership, freshness_guard and the health snapshot are
# wired; the remaining Phase 1–3 steps are listed below, commented, in the plan's order.
# Uncomment a step ONLY in the PR that lands its producer WITH its board surface, and register
# the table in scripts/global_market/freshness_guard.py PRODUCERS in the same PR (commented
# steps do not satisfy the registry — check_producers ignores comment lines).
#
#   bash scripts/ops/atlas_global_weekly.sh
#   ATLAS_REPO=$PWD ATLAS_LOG_DIR=/tmp/atlas-logs bash scripts/ops/atlas_global_weekly.sh   # local dry run (runbook §6)
set -uo pipefail
REPO="${ATLAS_REPO:-/home/ubuntu/atlas-os}"
cd "$REPO" || exit 1
export PYTHONPATH="$REPO:$REPO/scripts/global_market:$REPO/scripts/foundation"   # global before foundation: same-named India scripts must not shadow ours
if [ -n "${ATLAS_REPO:-}" ]; then
  # DRY RUN (runbook §6): the checkout's venv and the caller's environment — .env is never sourced,
  # ATLAS_DB_URL must be exported, and its host must be localhost unless ATLAS_ALLOW_REMOTE_DB=1,
  # so a laptop run can never reach prod by accident.
  PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
  [ -n "${ATLAS_DB_URL:-}" ] || { echo "FATAL: dry-run mode: export ATLAS_DB_URL pointing at a scratch database" >&2; exit 1; }
  DB_HOST="${ATLAS_DB_URL##*@}"; DB_HOST="${DB_HOST%%/*}"; DB_HOST="${DB_HOST%%:*}"
  if [ "${ATLAS_ALLOW_REMOTE_DB:-}" != "1" ] && [ "$DB_HOST" != "localhost" ] && [ "$DB_HOST" != "127.0.0.1" ]; then
    echo "FATAL: dry-run mode: ATLAS_DB_URL host is '$DB_HOST', not localhost (ATLAS_ALLOW_REMOTE_DB=1 overrides)" >&2; exit 1
  fi
else
  # THE BOX: .venv and .env are mandatory.
  [ -x "$REPO/.venv/bin/python" ] || { echo "FATAL: $REPO/.venv is missing" >&2; exit 1; }
  [ -f "$REPO/.env" ] || { echo "FATAL: $REPO/.env is missing" >&2; exit 1; }
  source "$REPO/.venv/bin/activate"; PY="$REPO/.venv/bin/python"
  set -a; source "$REPO/.env"; set +a
fi
LOG_DIR="${ATLAS_LOG_DIR:-/home/ubuntu/logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/atlas_global_weekly_$(date +%Y%m%d_%H%M%S).log"
EOD=$($PY -c "import _gdb; print(_gdb.eod_cutoff())") || { echo "FATAL: $PY cannot import _gdb" >&2; exit 1; }
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
#    The directories are fetched and saved under $LOG_DIR/identity/<EOD>; a saved snapshot
#    replays offline with ATLAS_IDENTITY_SNAPSHOT=<dir> (a local dry run, or the SEC's ten-minute
#    rate-limit window) — the box always fetches.
IDENTITY_SRC=(--snapshot-dir "$LOG_DIR/identity/$EOD")
[ -n "${ATLAS_IDENTITY_SNAPSHOT:-}" ] && IDENTITY_SRC=(--from-snapshot "$ATLAS_IDENTITY_SNAPSHOT")
step "build_identity"           $PY scripts/global_market/build_identity.py "${IDENTITY_SRC[@]}" ${STOOQ_ARG[@]+"${STOOQ_ARG[@]}"}
step "seed_benchmarks"          $PY scripts/global_market/seed_benchmarks.py
step "ingest_index_membership"  $PY scripts/global_market/ingest_index_membership.py --eod "$EOD" --report "$LOG_DIR/index_membership_$EOD.csv"
# 2. SLOW FEEDS (EDGAR / FINRA).
# N-PORT: one small index request per fund, and the document only when the accession changed —
# so a steady week is cheap and a quarter-end week is not. The FIRST run has no watermarks and
# fetches every document (hours, ~1.4 GB streamed, nothing kept); docs/global/runbook.md says to
# seed it in batches with --limit before this step is left to the cron.
# BOUNDED, and the bound is the point. Unlimited, this step walks the whole ~5,600-fund ETF
# universe in one pass: on 2026-09-09 it held /tmp/atlas_global.lock for over two hours and
# every nightly, every weekly and every dispatched run was refused for as long as it ran. The
# feed is watermarked and resumable, so a bounded batch each week loses nothing and finishes.
# ATLAS_NPORT_WEEKLY_LIMIT raises it for a deliberate catch-up run.
step "ingest_nport"             $PY scripts/global_market/ingest_nport.py --limit "${ATLAS_NPORT_WEEKLY_LIMIT:-400}" --report "$LOG_DIR/nport_$EOD.csv"
# step "ingest_financials"        $PY scripts/global_market/ingest_financials.py        # companyfacts, changed filers (Phase 3)
# step "ingest_13f"               $PY scripts/global_market/ingest_13f.py               # Phase 3
# step "ingest_short_interest"    $PY scripts/global_market/ingest_short_interest.py    # Phase 3
# 3. CLASSIFY + RE-SCORE.
# step "classify_etfs"            $PY scripts/global_market/classify_etfs.py --delta    # rules + LLM for new/changed only (Phase 2)
# Exposures are a pure function of a holdings snapshot, so only the NEW snapshots are
# computed — no --all, which is for a change to the exposure arithmetic itself.
step "build_exposures"          $PY scripts/global_market/build_exposures.py --report "$LOG_DIR/exposures_$EOD.csv"
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

# 4b. OBSERVABILITY — the health snapshot (runs, validators, freshness in SPY sessions) for /health: runs even when a gate failed; non-fatal; idempotent.
$PY scripts/global_market/write_health_snapshot.py --runfile "$RUNFILE" --eod "$EOD" --milestone weekly >>"$LOG" 2>&1 \
  && echo "  ok: write_health_snapshot" | tee -a "$LOG" \
  || { echo "  FAIL: write_health_snapshot" | tee -a "$LOG"; FAILURES+=("write_health_snapshot"); }

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
