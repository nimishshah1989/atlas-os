#!/usr/bin/env bash
# Atlas v6 frontend deploy — safe, additive, with auto-rollback.
#
# Mirror of .github/workflows/deploy-frontend.yml — use this locally when
# CI is unavailable or you want to deploy a specific commit without pushing.
#
# Lessons baked in (2026-05-28 incident):
#  - rsync NEVER uses --delete (don't wipe sibling files on deploy target)
#  - .next backed up BEFORE build, kept for instant rollback
#  - pm2 reload (not restart) for rolling restart on cluster mode
#  - HTTPS health-check after reload; auto-rollback to backup on non-200
#  - 5 most-recent backups retained, older pruned
#
# Usage (from local Mac):
#   bash scripts/deploy_frontend_v6.sh
#   bash scripts/deploy_frontend_v6.sh --skip-rsync   # rebuild only, don't sync
#
# Requires:
#  - ~/.ssh/jsl-wealth-key.pem
#  - SSH access to ubuntu@13.206.34.214

set -euo pipefail

EC2_HOST="${EC2_HOST:-ubuntu@13.206.34.214}"
EC2_KEY="${EC2_KEY:-$HOME/.ssh/jsl-wealth-key.pem}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="/home/ubuntu/atlas-os"
STAMP="$(date +%Y%m%d_%H%M%S)"
SKIP_RSYNC=0

for arg in "$@"; do
  case "$arg" in
    --skip-rsync) SKIP_RSYNC=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg"; exit 1 ;;
  esac
done

ssh_cmd() {
  ssh -i "$EC2_KEY" -o ConnectTimeout=15 "$EC2_HOST" "$@"
}

echo "[deploy ${STAMP}] backup current .next on EC2"
ssh_cmd "cd ${DEPLOY_DIR} && [ -d .next ] && cp -r .next .next.bak.${STAMP} && echo 'OK backup'"

if [ "$SKIP_RSYNC" -eq 0 ]; then
  echo "[deploy ${STAMP}] rsync frontend/src/ → EC2 (NO --delete)"
  rsync -avz -e "ssh -i ${EC2_KEY}" \
    --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='standalone' --exclude='.env*' \
    "${REPO_ROOT}/frontend/" \
    "${EC2_HOST}:${DEPLOY_DIR}/frontend/"
fi

echo "[deploy ${STAMP}] build on EC2 (PM2 still serves OLD .next during this step)"
ssh_cmd "cd ${DEPLOY_DIR} && NODE_OPTIONS='--max-old-space-size=3072' nohup npm run build > /home/ubuntu/logs/deploy_${STAMP}.log 2>&1 &"
echo "[deploy ${STAMP}] waiting for build to finish (typical: 2-4 min)..."
ssh_cmd "until ! pgrep -f 'next build' > /dev/null; do sleep 15; done"

echo "[deploy ${STAMP}] build done — checking exit status"
if ! ssh_cmd "tail -5 /home/ubuntu/logs/deploy_${STAMP}.log | grep -qE 'Compiled successfully|Build error'"; then
  echo "[deploy ${STAMP}] build log inconclusive — tail:"
  ssh_cmd "tail -30 /home/ubuntu/logs/deploy_${STAMP}.log"
  exit 1
fi

if ssh_cmd "tail -5 /home/ubuntu/logs/deploy_${STAMP}.log | grep -q 'Build error'"; then
  echo "[deploy ${STAMP}] BUILD FAILED — .next untouched, PM2 still serving old. No reload needed."
  exit 2
fi

echo "[deploy ${STAMP}] pm2 reload (rolling, zero-downtime)"
ssh_cmd "pm2 reload atlas-frontend"

sleep 6
echo "[deploy ${STAMP}] health-check https://atlas.jslwealth.in/"
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" https://atlas.jslwealth.in/)
echo "[deploy ${STAMP}] HTTP ${HTTP_CODE}"

if [ "$HTTP_CODE" = "200" ]; then
  echo "[deploy ${STAMP}] ✓ DEPLOY OK"
  # prune old backups (keep last 5)
  ssh_cmd "ls -1dt ${DEPLOY_DIR}/.next.bak.* 2>/dev/null | tail -n +6 | xargs -r rm -rf"
  exit 0
fi

echo "[deploy ${STAMP}] ✗ HEALTH-CHECK FAILED (HTTP ${HTTP_CODE}) — rolling back to .next.bak.${STAMP}"
ssh_cmd "cd ${DEPLOY_DIR} && rm -rf .next && mv .next.bak.${STAMP} .next && pm2 reload atlas-frontend-v2"
sleep 6
HTTP_AFTER=$(curl -sk -o /dev/null -w "%{http_code}" https://atlas.jslwealth.in/)
echo "[deploy ${STAMP}] after rollback: HTTP ${HTTP_AFTER}"
exit 2
