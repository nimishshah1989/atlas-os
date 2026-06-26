#!/usr/bin/env bash
# ── One-time: point the deploy box at main ───────────────────────────────────
# Run this ONCE on the EC2 box right after the consolidation PR merges into main
# (the box currently tracks a release branch). It switches the working tree to
# main and does one clean build+reload. After this, atlas-auto-deploy.sh keeps
# main live automatically on every future merge — no manual deploys.
#
# Idempotent + safe: aborts if the tree is dirty (won't clobber work).
set -euo pipefail

REPO=/home/ubuntu/atlas-os
FRONTEND="$REPO/frontend"
PM2_APP=atlas-frontend-v3

cd "$REPO"
if [ -n "$(git status --porcelain)" ]; then
  echo "ABORT: working tree is dirty — commit/stash first."
  git status --short
  exit 1
fi

echo "→ fetching + switching to main"
git fetch origin main --quiet
git checkout main
git reset --hard origin/main

echo "→ clean build (LENS_V4 + cache hygiene)"
cd "$FRONTEND"
rm -rf .next/cache/fetch-cache
NEXT_PUBLIC_LENS_V4=1 NODE_OPTIONS='--max-old-space-size=3072' npm run build

echo "→ reload live process"
rm -rf .next/cache/fetch-cache
pm2 reload "$PM2_APP" --update-env
pm2 save

echo "✓ box is now on main at $(git rev-parse --short HEAD). Auto-deploy will keep it current."
