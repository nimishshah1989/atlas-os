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
# PHASE 1: ingest_macro, freshness_guard, the health snapshot and the revalidate publish are
# wired; the remaining Phase 1–3 steps are listed below, commented, in the plan's order.
# Uncomment a step ONLY in the PR that lands its producer WITH its board surface, and register
# the table in scripts/global_market/freshness_guard.py PRODUCERS in the same PR (commented
# steps do not satisfy the registry — check_producers ignores comment lines). A gate is wired
# only once its check exists: a gate known to fail every night trains the FM to ignore the push.
#
#   bash scripts/ops/atlas_global_daily.sh
#   ATLAS_REPO=$PWD ATLAS_LOG_DIR=/tmp/atlas-logs bash scripts/ops/atlas_global_daily.sh   # local dry run (runbook §6)
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
LOG="$LOG_DIR/atlas_global_daily_$(date +%Y%m%d_%H%M%S).log"
EOD=$($PY -c "import _gdb; print(_gdb.eod_cutoff())") || { echo "FATAL: $PY cannot import _gdb" >&2; exit 1; }
echo "=== atlas_global_daily EOD=$EOD  $(date -Is) ===" | tee -a "$LOG"

FAILURES=()
RUNFILE=$(mktemp /tmp/atlas_global_daily_runs.XXXXXX)   # per-step timings → health snapshot
PUBLISH_CFG=                                             # the publish step's curl config (bearer)
trap 'rm -f "$RUNFILE" "$PUBLISH_CFG"' EXIT
step() {  # step "name" cmd...   (non-fatal; records failures + a run row; cmd may set STEP_WHY)
  local name="$1"; shift
  local start; start=$(date -Is)
  echo "--- $name ---" | tee -a "$LOG"
  local st; STEP_WHY=
  if "$@" >>"$LOG" 2>&1; then echo "  ok: $name" | tee -a "$LOG"; st=success
  else echo "  FAIL: $name (${STEP_WHY:-rc=$?})" | tee -a "$LOG"; FAILURES+=("$name"); st=failed; fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$start" "$(date -Is)" "$st" >> "$RUNFILE"
}

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

# 1. INGEST (Phase 1). ingest_prices must abort loudly if SPY has no bar for $EOD — the
#    anchor calendar is membership-by-presence of SPY bars, so a missing anchor means no
#    session to score, not a quiet carry-forward.
step "ingest_prices"           $PY scripts/global_market/ingest_prices.py --eod "$EOD" --report "$LOG_DIR/ingest_prices_$EOD.csv"
step "ingest_macro"            $PY scripts/global_market/ingest_macro.py --eod "$EOD"
# step "ingest_filings_8k"       $PY scripts/global_market/ingest_filings_8k.py
# step "ingest_form4"            $PY scripts/global_market/ingest_form4.py
# step "ingest_issuer_holdings"  $PY scripts/global_market/ingest_issuer_holdings.py

# 2. COMPUTE cascade (EOD-anchored, single schema).
# BASIS runs BEFORE the cascade, not with the output gates: it MEASURES which price series
# ohlcv_daily carries (against FRED's price index) and compute_technicals stamps that basis on
# every metric it writes. A night where the archive's adjustment changed must not be scored
# first and questioned afterwards — a failure here withholds the publish, so the board keeps
# its last-good data rather than advancing on metrics computed against an unverified basis.
gate "validate_global_BASIS" $PY scripts/global_market/validate_global.py --check BASIS

# compute_technicals is INCREMENTAL by default: it recomputes each instrument from its full
# history but writes only the sessions beyond what technical_daily already holds, so a normal
# night is about one upsert per instrument. --scope universe (the default) is the scored set
# plus former index members plus the benchmarks; --redo rewrites all history.
step "compute_technicals"      $PY scripts/global_market/compute_technicals.py --eod "$EOD" --report "$LOG_DIR/compute_technicals_$EOD.csv"
# build_universe_snapshot exits 2 (step FAIL, nothing written) until the FM sets
# liquidity_min_traded_value_usd from the ADV$ table it prints and saves to $LOG_DIR/adv_usd_$EOD.md (runbook §7).
step "build_universe_snapshot" $PY scripts/global_market/build_universe_snapshot.py --eod "$EOD" --report "$LOG_DIR/universe_snapshot_$EOD.csv" --report-dir "$LOG_DIR"
# step "build_exposures"         $PY scripts/global_market/build_exposures.py --changed
# step "score_stocks"            $PY scripts/global_market/score_stocks.py --as-of "$EOD"
# step "score_etfs"              $PY scripts/global_market/score_etfs.py --as-of "$EOD"
# Countries: one tradeable fund per market, read off technical_daily. Uncommented once its
# board surface existed (/countries, #240) and its builder ran (#241) — the rule at the top
# of this file. Without it country_daily stays empty and the page says so honestly, which
# is what it did until now.
step "build_country_views"     $PY scripts/global_market/build_country_views.py --eod "$EOD" --report "$LOG_DIR/country_views_$EOD.csv"
# Rolling signal quality — step, not gate (a lens losing IC is a finding for the FM, not a
# reason to withhold a correct board). Window start computed in Python (no GNU `date -d`).
# IC_START=$($PY -c "import datetime as d, _gdb; print(_gdb.eod_cutoff() - d.timedelta(days=730))")
# step "eval_signal"             $PY scripts/global_market/eval_signal.py --start "$IC_START" --end "$EOD"

# 3. GATES (assert on REAL produced output — rule #0). Publish only if ALL pass.
# Run gates DIRECTLY (not via step): step() always returns 0, so a failed gate could
# otherwise still publish. Gate outcomes are recorded into the runfile too. gate() is defined
# beside step() above, because BASIS has to run before the compute cascade it guards.
gate "freshness_guard"   $PY scripts/global_market/freshness_guard.py --eod "$EOD"
# Gate A asserts over the SCORED universe, so it runs AFTER build_universe_snapshot; on a
# night where that step exits 2 (the floor unset) the universe is empty and gate A says so
# rather than passing on nothing.
gate "validate_global_A" $PY scripts/global_market/validate_global.py --check A --eod "$EOD"
# gate "validate_global_B" $PY scripts/global_market/validate_global.py --check B   # Phase 3
# gate "validate_global_C" $PY scripts/global_market/validate_global.py --check C   # Phase 3
# gate "validate_global_D" $PY scripts/global_market/validate_global.py --check D   # Phase 3

# 4. PUBLISH — the board advances by ISR revalidation, never a rebuild here: ONE POST to the board's
#    /api/revalidate (frontend-global/src/app/api/revalidate/route.ts) with the shared bearer and tag
#    'eod', only when every gate passed and both env vars are set; through step(), so the outcome is a
#    run row on /health. The bearer travels in a 0600 curl config file (never argv, so never in ps, and
#    never in the log); only HTTP 200 is success — a 3xx is a misconfigured URL, and -L would follow it
#    blind, so a redirect surfaces as "FAIL: publish (http 308)".
publish() {
  PUBLISH_CFG=$(mktemp /tmp/atlas_global_publish.XXXXXX) || return 1   # mktemp creates it 0600
  printf 'header = "Authorization: Bearer %s"\n' "$GLOBAL_REVALIDATE_SECRET" > "$PUBLISH_CFG"
  local code
  code=$(curl -sS -m 15 -K "$PUBLISH_CFG" -X POST "$GLOBAL_REVALIDATE_URL" \
         -H 'Content-Type: application/json' -d '{"tag":"eod"}' -o /dev/null -w '%{http_code}')
  rm -f "$PUBLISH_CFG"; PUBLISH_CFG=
  [ "$code" = "200" ] && return 0
  STEP_WHY="http $code"; return 1
}
skip() { echo "--- $1 ---" | tee -a "$LOG"; echo "  SKIP $1 — $2" | tee -a "$LOG"; }
if [ "$GATE_OK" != "1" ]; then
  skip publish "a gate failed; the board keeps its last-good data"
elif [ -z "${GLOBAL_REVALIDATE_URL:-}" ] || [ -z "${GLOBAL_REVALIDATE_SECRET:-}" ]; then
  skip publish "GLOBAL_REVALIDATE_URL / GLOBAL_REVALIDATE_SECRET unset (box .env)"
else
  step "publish" publish
fi

# 4b. OBSERVABILITY — the health snapshot (runs, validators, freshness in SPY sessions) for /health: runs even when a gate failed; non-fatal; idempotent.
$PY scripts/global_market/write_health_snapshot.py --runfile "$RUNFILE" --eod "$EOD" --milestone daily >>"$LOG" 2>&1 \
  && echo "  ok: write_health_snapshot" | tee -a "$LOG" \
  || { echo "  FAIL: write_health_snapshot" | tee -a "$LOG"; FAILURES+=("write_health_snapshot"); }

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
