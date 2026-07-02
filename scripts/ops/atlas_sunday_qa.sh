#!/bin/bash
# Atlas v4 SUNDAY QA (no ingestion) — the weekly health audit the FM asked for:
# freshness + coverage/silent-zero + outlier-jump scan → Telegram digest. Exit code
# reflects PASS/FAIL so the cron log makes it obvious.
set -uo pipefail
REPO=/home/ubuntu/atlas-os
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation"
source "$REPO/.venv/bin/activate"
set -a; source .env; set +a
LOG=/home/ubuntu/logs/atlas_sunday_qa_$(date +%Y%m%d_%H%M%S).log
echo "=== atlas_sunday_qa $(date -Is) ===" | tee -a "$LOG"
"$REPO/.venv/bin/python" scripts/ops/qa_weekly.py 2>&1 | tee -a "$LOG"
