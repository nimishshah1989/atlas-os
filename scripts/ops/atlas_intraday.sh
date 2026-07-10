#!/usr/bin/env bash
# Atlas intraday sector-RS — one tick of the live sector-index ÷ NIFTY 50 path.
# Called every 5 min during market hours by cron (see scripts/ops/crontab.txt).
# Reuses the daily orchestrator's env setup (single .env, both import paths).
set -euo pipefail
REPO="/home/ubuntu/atlas-os"
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation"   # covers atlas.* and _db imports
set -a; source .env; set +a
exec "$REPO/.venv/bin/python" scripts/foundation/build_sector_rs_intraday.py
