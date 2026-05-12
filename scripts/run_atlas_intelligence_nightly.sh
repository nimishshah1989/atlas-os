#!/usr/bin/env bash
# Stage 4a + 4c + SP02 MVs + Validator A+B unified nightly chain.
#
# Runs after the existing M2-M5 cron at UTC 21:30 (IST 03:00). Each step
# is non-blocking: if one fails we log and continue so partial output
# still lands. Failed steps trigger an email alert via notify_failure.py
# when SMTP_USER + SMTP_PASS are configured in .env.
#
# Install (replace any existing line for this script):
#   crontab -l > /tmp/cron.bak
#   ( crontab -l ; echo "0 22 * * 1-5 cd /home/ubuntu/atlas-os && /home/ubuntu/atlas-os/scripts/run_atlas_intelligence_nightly.sh >> /home/ubuntu/logs/atlas-intelligence.log 2>&1" ) | crontab -

set -u
cd /home/ubuntu/atlas-os
source .venv/bin/activate
export $(grep -E "^(GROQ_API_KEY|ATLAS_DB_URL|SMTP_USER|SMTP_PASS|NOTIFY_EMAIL)" .env | xargs)

LOG_FILE="/home/ubuntu/logs/atlas-intelligence.log"
FAILED_STEPS=()

log() { echo "[$(date -u +%FT%TZ)] $*"; }

run_step() {
  local name="$1"; shift
  log "BEGIN $name"
  if "$@"; then
    log "OK    $name"
  else
    local exit_code=$?
    log "FAIL  $name (exit $exit_code) — continuing chain"
    FAILED_STEPS+=("$name")
    # Fire alert immediately for each failure so they don't get buried.
    python scripts/notify_failure.py "$name" "$LOG_FILE" || true
  fi
}

run_step "compute_conviction"         python scripts/compute_conviction.py --persist
run_step "recompute_signal_ic"        python scripts/recompute_signal_ic.py --persist
run_step "generate_weight_candidates" python scripts/generate_weight_candidates.py --persist
run_step "track_live_ic"              python scripts/track_live_ic.py --persist
run_step "compute_hit_rates"          python scripts/compute_hit_rates.py --persist
# Drift check runs dry by default. Flip to --apply once ≥60 days of live_perf
# data exists for at least one active weight set.
run_step "check_weight_drift"         python scripts/check_weight_drift.py
run_step "validator_sensibility"      python scripts/run_validator.py --scope sensibility
run_step "validator_schema"           python scripts/run_validator.py --scope schema

# Refresh all materialized views after the full pipeline completes.
# SP02 MVs (rs_leaders, breakout_candidates, deterioration_watch,
# sector_rotation_state, current_market_regime) depend on atlas_sector_metrics_daily
# which is written by the M3 cron at ~21:30 UTC. Refreshing here at ~22:xx UTC
# ensures the MVs always reflect today's compute output.
run_step "refresh_mv" python -c "
from atlas.db import get_engine
from sqlalchemy import text

MVS = [
    'atlas.mv_rs_leaders_daily',
    'atlas.mv_breakout_candidates',
    'atlas.mv_deterioration_watch',
    'atlas.mv_sector_rotation_state',
    'atlas.mv_current_market_regime',
    'atlas.mv_top_conviction_daily',
]
e = get_engine()
with e.begin() as c:
    for mv in MVS:
        c.execute(text(f'REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}'))
        print(f'refreshed {mv}')
print(f'refreshed {len(MVS)} materialized views')
"

if [ ${#FAILED_STEPS[@]} -eq 0 ]; then
  log "DONE atlas_intelligence_nightly — all steps OK"
else
  log "DONE atlas_intelligence_nightly — ${#FAILED_STEPS[@]} step(s) failed: ${FAILED_STEPS[*]}"
fi
