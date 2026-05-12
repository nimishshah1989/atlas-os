#!/usr/bin/env bash
# Stage 4a + 4c + Validator A+B unified nightly chain.
#
# Runs after the existing M2-M5 cron at UTC 21:30 (IST 03:00). Each step
# is non-blocking: if one fails we log and continue so partial output
# still lands.
#
# Install (replace any existing line for this script):
#   crontab -l > /tmp/cron.bak
#   ( crontab -l ; echo "0 22 * * 1-5 cd /home/ubuntu/atlas-os && /home/ubuntu/atlas-os/scripts/run_atlas_intelligence_nightly.sh >> /home/ubuntu/logs/atlas-intelligence.log 2>&1" ) | crontab -

set -u
cd /home/ubuntu/atlas-os
source .venv/bin/activate
export $(grep -E "^(GROQ_API_KEY|ATLAS_DB_URL)" .env | xargs)

log() { echo "[$(date -u +%FT%TZ)] $*"; }

run_step() {
  local name="$1"; shift
  log "BEGIN $name"
  if "$@"; then
    log "OK    $name"
  else
    log "FAIL  $name (exit $?) — continuing chain"
  fi
}

run_step "compute_conviction"        python scripts/compute_conviction.py --persist
run_step "recompute_signal_ic"       python scripts/recompute_signal_ic.py --persist
run_step "generate_weight_candidates" python scripts/generate_weight_candidates.py --persist
run_step "track_live_ic"             python scripts/track_live_ic.py --persist
run_step "compute_hit_rates"         python scripts/compute_hit_rates.py --persist
# Drift check runs dry by default. Flip to --apply once ≥60 days of live_perf
# data exists for at least one active weight set.
run_step "check_weight_drift"        python scripts/check_weight_drift.py
run_step "validator_sensibility"     python scripts/run_validator.py --scope sensibility
run_step "validator_schema"          python scripts/run_validator.py --scope schema

# Refresh materialized views once everything is persisted.
run_step "refresh_top_conviction_mv" python -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.begin() as c:
    c.execute(text('REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_top_conviction_daily'))
print('refreshed mv_top_conviction_daily')
"

log "DONE atlas_intelligence_nightly"
