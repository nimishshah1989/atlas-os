#!/usr/bin/env bash
# Deploy + run M2 backfill on EC2 (jsl-wealth-server, ap-south-1).
#
# Why EC2 not Mac:
# - Mac venv: psycopg2-binary stalls on Supabase pooler connect (documented
#   in reference_ec2_access memory).
# - EC2 is in the same AWS region as Supabase + JIP RDS — stable network,
#   no NAT traversal issues.
#
# Run from the Mac:
#   bash scripts/m2_ec2_deploy.sh
#
# This script:
# 1. rsyncs atlas/ + scripts/ + pyproject.toml + .env to EC2
# 2. pip installs the bumped pandas-ta + deps
# 3. runs unit tests
# 4. invokes m2_backfill.py with timing capture
#
# Idempotent: re-running just refreshes the code and re-runs.

set -euo pipefail

EC2_HOST="ubuntu@13.206.34.214"
SSH_KEY="${HOME}/.ssh/jsl-wealth-key.pem"
REMOTE_DIR="/home/ubuntu/atlas-os"
SSH_OPTS=(-i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=no)

echo "[1/5] Syncing code to EC2..."
rsync -avz --delete \
  -e "ssh ${SSH_OPTS[*]}" \
  --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  --exclude '*.pyc' --exclude 'output' --exclude 'src' \
  ./atlas ./scripts ./migrations ./pyproject.toml ./alembic.ini ./.env \
  "${EC2_HOST}:${REMOTE_DIR}/"

echo "[2/5] Installing/upgrading deps on EC2..."
ssh "${SSH_OPTS[@]}" "${EC2_HOST}" \
  "cd ${REMOTE_DIR} && python3 -m venv .venv --upgrade-deps 2>/dev/null; \
   .venv/bin/pip install -e '.[dev]' 2>&1 | tail -20"

echo "[3/5] Running unit tests..."
ssh "${SSH_OPTS[@]}" "${EC2_HOST}" \
  "cd ${REMOTE_DIR} && .venv/bin/pytest tests/unit/ -m unit -q --tb=short 2>&1 | tail -30"

echo "[4/5] Smoke test: connect + read universe count..."
ssh "${SSH_OPTS[@]}" "${EC2_HOST}" \
  "cd ${REMOTE_DIR} && .venv/bin/python -c '
from atlas.db import get_engine
from sqlalchemy import text
with get_engine().connect() as c:
    c.execute(text(\"SET statement_timeout = 0\"))
    n = c.execute(text(\"SELECT COUNT(*) FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL\")).scalar()
    print(f\"universe_stocks_active={n}\")
'"

echo "[5/5] M2 backfill (run in background, capture timings)..."
ssh "${SSH_OPTS[@]}" "${EC2_HOST}" \
  "cd ${REMOTE_DIR} && nohup .venv/bin/python scripts/m2_backfill.py \
     > /home/ubuntu/m2_backfill.log 2>&1 &"

echo
echo "Backfill started in background on EC2."
echo "Tail the log:  ssh ${EC2_HOST} 'tail -f /home/ubuntu/m2_backfill.log'"
echo "Or pull when done: scp ${EC2_HOST}:/home/ubuntu/m2_backfill.log ./output/"
