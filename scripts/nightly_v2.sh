#!/bin/bash
# Atlas v2 nightly pipeline — state-engine classify + aggregators (sector/fund/ETF).
# Runs Mon-Fri at 21:30 IST (16:00 UTC) after the main nightly at 23:30 IST (18:00 UTC).
# Source: /home/ubuntu/atlas-os-sl (feat/atlas-consolidation branch)
#
# What it does (one invocation covers the whole v2 pipeline):
#   1. Pulls latest code from origin
#   2. Runs m2_daily.py  -> state-engine classify + sector/fund/ETF aggregators
#   3. Generates daily intelligence brief (requires GROQ_API_KEY in .env)
#
# Logs: /home/ubuntu/atlas-v2-nightly.log  (append; tail -100 to monitor)
#
# Usage (manual):
#   bash /home/ubuntu/atlas-os-sl/scripts/nightly_v2.sh
# Cron (add via crontab -e):
#   0 16 * * 1-5 /home/ubuntu/atlas-os-sl/scripts/nightly_v2.sh >> /home/ubuntu/atlas-v2-nightly.log 2>&1

set -euo pipefail

REPO=/home/ubuntu/atlas-os-sl
VENV=/home/ubuntu/atlas-os/.venv
LOG=/home/ubuntu/atlas-v2-nightly.log
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S IST")

echo "" >> "$LOG"
echo "=== Atlas v2 nightly pipeline $TIMESTAMP ===" | tee -a "$LOG"

# Load environment (ATLAS_DB_URL, GROQ_API_KEY, etc.)
ENV_FILE="$REPO/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    ENV_FILE="/home/ubuntu/atlas-os/.env"
fi
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
    echo "[env] Loaded from $ENV_FILE" | tee -a "$LOG"
else
    echo "[env] WARNING: no .env found — ATLAS_DB_URL must already be in environment" | tee -a "$LOG"
fi

if [[ -z "${ATLAS_DB_URL:-}" ]]; then
    echo "FATAL: ATLAS_DB_URL is not set. Aborting." | tee -a "$LOG"
    exit 1
fi

# Activate venv
source "$VENV/bin/activate"
echo "[env] Python: $(which python3)" | tee -a "$LOG"

cd "$REPO"

# Pull latest code (non-fatal — don't abort on network issues)
echo "[git] Pulling latest..." | tee -a "$LOG"
git pull --ff-only origin "$(git branch --show-current)" 2>&1 | tee -a "$LOG" || \
    echo "[git] WARNING: pull failed (continuing with current code)" | tee -a "$LOG"

# Step 1: m2_daily.py — state-engine classify + all 3 aggregators
echo "" | tee -a "$LOG"
echo "[step 1] m2_daily.py (classify + sector + fund + ETF aggregators)..." | tee -a "$LOG"
PYTHONPATH="$REPO" python3 scripts/m2_daily.py 2>&1 | tee -a "$LOG"
M2_EXIT=${PIPESTATUS[0]}
if [[ $M2_EXIT -ne 0 ]]; then
    echo "[step 1] FAILED (exit $M2_EXIT) — continuing to brief step" | tee -a "$LOG"
else
    echo "[step 1] OK" | tee -a "$LOG"
fi

# Step 1b: continuous dwell_days recompute — fixes monthly-chunk degeneracy.
# Runs only when Step 1 (classify) succeeded so dwell reflects today's states.
echo "" | tee -a "$LOG"
echo "[step 1b] dwell_days continuous recompute..." | tee -a "$LOG"
if [[ ${M2_EXIT:-0} -eq 0 ]]; then
    PYTHONPATH="$REPO" python3 -c "
from atlas.db import get_engine
from atlas.intelligence.states.dwell_recompute import recompute_and_persist
n = recompute_and_persist(get_engine())
print(f'dwell recompute updated {n} rows')
" 2>&1 | tee -a "$LOG"
    DWELL_EXIT=${PIPESTATUS[0]}
    if [[ $DWELL_EXIT -ne 0 ]]; then
        echo "[step 1b] FAILED (exit $DWELL_EXIT) — dwell stats will be stale" | tee -a "$LOG"
    else
        echo "[step 1b] OK" | tee -a "$LOG"
    fi
else
    echo "[step 1b] SKIPPED — step 1 failed; dwell recompute requires fresh classify output" | tee -a "$LOG"
fi

# Step 2: daily intelligence brief (requires GROQ_API_KEY)
echo "" | tee -a "$LOG"
echo "[step 2] generate_daily_brief.py --persist..." | tee -a "$LOG"
if [[ -z "${GROQ_API_KEY:-}" ]]; then
    echo "[step 2] SKIPPED — GROQ_API_KEY not set (brief generation requires it)" | tee -a "$LOG"
else
    PYTHONPATH="$REPO" python3 scripts/generate_daily_brief.py --persist 2>&1 | tee -a "$LOG"
    BRIEF_EXIT=${PIPESTATUS[0]}
    if [[ $BRIEF_EXIT -ne 0 ]]; then
        echo "[step 2] FAILED (exit $BRIEF_EXIT) — brief not persisted" | tee -a "$LOG"
    else
        echo "[step 2] OK — brief persisted to atlas_daily_briefs" | tee -a "$LOG"
    fi
fi

# Report final status
echo "" | tee -a "$LOG"
if [[ ${M2_EXIT:-0} -eq 0 ]]; then
    echo "=== Done (all steps OK) $(date) ===" | tee -a "$LOG"
    exit 0
else
    echo "=== Done (partial failure — see log above) $(date) ===" | tee -a "$LOG"
    exit 2
fi
