#!/usr/bin/env bash
# Deploys frontend changes from feat/atlas-consolidation to
# /home/ubuntu/atlas-frontend-v2 on EC2. Used during the signal-consolidation
# v2 demo build-out. Production /home/ubuntu/atlas-frontend (port 3001)
# stays untouched.
#
# Usage:  ./scripts/deploy_v2.sh
# Output: prints the demo URL at the end.

set -euo pipefail

BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "feat/atlas-consolidation" ]; then
  echo "Refusing to deploy from branch '$BRANCH' (expected feat/atlas-consolidation)" >&2
  exit 1
fi

echo "[deploy-v2] bundling frontend/src ..."
tar -czf /tmp/atlas-frontend-v2.tgz frontend/src/

echo "[deploy-v2] shipping to EC2 ..."
scp -q /tmp/atlas-frontend-v2.tgz atlas:/tmp/

echo "[deploy-v2] extracting + building + restarting on EC2 ..."
ssh atlas '
  set -e
  cd /home/ubuntu/atlas-frontend-v2/frontend
  tar -xzf /tmp/atlas-frontend-v2.tgz --strip-components=1
  cd /home/ubuntu/atlas-frontend-v2
  npm run build 2>&1 | tail -5
  pm2 restart atlas-frontend-v2
'

echo
echo "[deploy-v2] done."
echo "          internal: http://localhost:3002/  (via ssh -L if port closed)"
echo "          public:   http://13.206.34.214:3002/  (requires sg-0215e4a4161ca4a12 ingress on tcp/3002)"
