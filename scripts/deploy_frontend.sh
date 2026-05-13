#!/usr/bin/env bash
# Deploy frontend to atlas.jslwealth.in
# Usage: bash scripts/deploy_frontend.sh
# Run from local machine (requires SSH alias 'atlas' configured)

set -euo pipefail

REMOTE="atlas"
FRONTEND_DIR="/home/ubuntu/atlas-frontend"
PORT=3001

echo "[deploy] pulling latest main..."
ssh "$REMOTE" "cd $FRONTEND_DIR && git pull origin main"

echo "[deploy] installing dependencies..."
ssh "$REMOTE" "cd $FRONTEND_DIR && npm ci --prefer-offline"

echo "[deploy] building..."
ssh "$REMOTE" "cd $FRONTEND_DIR && npm run build"

echo "[deploy] restarting pm2..."
ssh "$REMOTE" "pm2 restart atlas-frontend 2>/dev/null || pm2 start 'npx next start -p $PORT' --name atlas-frontend --cwd $FRONTEND_DIR && pm2 save"

echo "[deploy] waiting for port $PORT..."
ssh "$REMOTE" "until curl -s -o /dev/null -w '%{http_code}' http://localhost:$PORT/ | grep -qE '^[23]'; do sleep 2; done"

echo "[deploy] done — atlas.jslwealth.in is up"
