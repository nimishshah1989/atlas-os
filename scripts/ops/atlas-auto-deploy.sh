#!/usr/bin/env bash
# ── Atlas auto-deploy ────────────────────────────────────────────────────────
# Polls origin/main; on a new commit, fast-forwards the box and redeploys the live
# v4 board. Invoked by cron every 5 min. Designed to be SAFE and idempotent:
#   • Only acts when the working tree is on $DEPLOY_BRANCH and CLEAN — it will never
#     pull onto a different branch or onto uncommitted work (that was the old bug).
#   • Fast-forward only — never creates merge commits/conflicts on the box.
#   • Builds with the production flag (NEXT_PUBLIC_LENS_V4=1) + clears the Next
#     fetch-cache (stale unstable_cache hygiene) every deploy.
#   • Reloads the LIVE pm2 process (atlas-frontend-v3), not the retired one.
#   • Single-flight lock; .next backup + automatic rollback on build failure.
#   • npm ci only when the lockfile actually changed.
# First-time adoption of a deploy branch is a separate, explicit step —
# see scripts/ops/promote_box_to_main.sh.
set -uo pipefail

REPO=/home/ubuntu/atlas-os
FRONTEND="$REPO/frontend"
DEPLOY_BRANCH=main
PM2_APP=atlas-frontend-v3
LOG=/home/ubuntu/logs/auto-deploy.log
LOCK=/tmp/atlas-auto-deploy.lock
mkdir -p /home/ubuntu/logs

log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

# single-flight: bail quietly if a previous run is still going
exec 9>"$LOCK" || exit 0
flock -n 9 || exit 0

cd "$REPO" || { log "repo missing"; exit 1; }

# Guard 1: only deploy from the deploy branch (no-op on feature/release branches)
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
[ "$branch" = "$DEPLOY_BRANCH" ] || exit 0

# Guard 2: never act on a dirty tree (don't clobber WIP; don't pull onto changes)
[ -z "$(git status --porcelain)" ] || { log "tree dirty on $branch — skip"; exit 0; }

git fetch origin "$DEPLOY_BRANCH" --quiet 2>>"$LOG" || { log "fetch failed"; exit 0; }
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$DEPLOY_BRANCH")
[ "$LOCAL" = "$REMOTE" ] && exit 0   # already current — nothing to do

STAMP=$(date +%Y%m%d_%H%M%S)
log "deploy $LOCAL -> $REMOTE"

# Fast-forward only. If history diverged, stop and shout — never auto-merge on the box.
if ! git merge --ff-only "origin/$DEPLOY_BRANCH" >>"$LOG" 2>&1; then
  log "ERROR: $DEPLOY_BRANCH not fast-forwardable — manual intervention needed"
  exit 1
fi

cd "$FRONTEND" || { log "frontend missing"; exit 1; }

# Install deps only when the lockfile changed (keeps normal deploys fast).
if ! git diff --quiet "$LOCAL" "$REMOTE" -- package-lock.json 2>/dev/null; then
  log "lockfile changed — npm ci"
  npm ci >>"$LOG" 2>&1 || { log "npm ci failed"; exit 1; }
fi

[ -d .next ] && cp -r .next ".next.bak.$STAMP"
rm -rf .next/cache/fetch-cache
if NEXT_PUBLIC_LENS_V4=1 NODE_OPTIONS='--max-old-space-size=3072' npm run build >>"$LOG" 2>&1; then
  rm -rf .next/cache/fetch-cache
  pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1
  log "OK $REMOTE"
  ls -1dt "$FRONTEND"/.next.bak.* 2>/dev/null | tail -n +4 | xargs -r rm -rf   # keep 3 backups
else
  log "BUILD FAILED — rolling back to previous .next"
  rm -rf .next && mv ".next.bak.$STAMP" .next 2>/dev/null || log "rollback: no backup"
  pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1
  exit 1
fi
