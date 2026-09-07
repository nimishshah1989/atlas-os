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

# Guard 2: a dirty tree used to mean "skip forever, silently" — one stray file could stop
# every future deploy with nothing surfacing anywhere anyone looks. Stash it instead: that is
# lossless and reversible (`git stash list` on the box), and the deploy proceeds.
if [ -n "$(git status --porcelain)" ]; then
  n=$(git status --porcelain | wc -l | tr -d ' ')
  if git stash push -u -m "auto-deploy: box dirt $(date -u +%FT%TZ)" >>"$LOG" 2>&1; then
    log "ALERT: tree was dirty ($n paths) — stashed and continuing; inspect with 'git stash list'"
  else
    log "ALERT: tree dirty ($n paths) and stash FAILED — deploy blocked, needs a human"
    exit 1
  fi
fi

git fetch origin "$DEPLOY_BRANCH" --quiet 2>>"$LOG" || { log "fetch failed"; exit 0; }
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$DEPLOY_BRANCH")

# Converge on the commit that is actually BUILT, not merely checked out. A build that failed
# after the fast-forward left HEAD == REMOTE with the old .next still serving, and every later
# run exited here — stale production, for as long as nobody noticed. The stamp is written only
# after a build succeeds and pm2 reloads, so a mismatch means "retry".
BUILT_STAMP="$FRONTEND/.next/DEPLOYED_SHA"
BUILT=$(cat "$BUILT_STAMP" 2>/dev/null || echo none)
if [ "$LOCAL" = "$REMOTE" ] && [ "$BUILT" = "$REMOTE" ]; then
  exit 0   # current AND built — nothing to do
fi
if [ "$LOCAL" = "$REMOTE" ] && [ "$BUILT" != "$REMOTE" ]; then
  log "ALERT: $REMOTE is checked out but not built (last built: $BUILT) — rebuilding"
fi

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

# The toolchain must actually be there. A deploy once died on `sh: 1: next: not found`
# because something re-installed node_modules while the build was starting; the build then
# "failed" for a reason that had nothing to do with the code.
if [ ! -x node_modules/.bin/next ]; then
  log "ALERT: node_modules/.bin/next missing — running npm ci before build"
  npm ci >>"$LOG" 2>&1 || { log "ALERT: npm ci failed — deploy aborted"; exit 1; }
fi

[ -d .next ] && cp -r .next ".next.bak.$STAMP"
rm -rf .next/cache/fetch-cache
# flock: shared with atlas_daily.sh and with the Global Atlas board's build
# (scripts/ops/atlas_global_deploy.sh). Two Next builds at once on a 2-vCPU box, each asking for
# 3 GB, OOM and take the live board down. A timeout is a non-zero exit → the rollback branch below.
# NOTE: the copy cron actually runs is /home/ubuntu/atlas-auto-deploy.sh — this edit reaches the
# box only when that copy is refreshed from here (docs/global/deploy-subpath.md §1).
if NEXT_PUBLIC_LENS_V4=1 NODE_OPTIONS='--max-old-space-size=3072' \
   flock -w 2700 "${NEXT_BUILD_LOCK:-/tmp/atlas-next-build.lock}" npm run build >>"$LOG" 2>&1; then
  rm -rf .next/cache/fetch-cache
  pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1
  # Written only here: the stamp means "this commit is built AND serving", which is what the
  # convergence check at the top reads. A rollback restores the old .next and with it the old
  # stamp, so the next run correctly sees the deploy as still outstanding and retries.
  echo "$REMOTE" > .next/DEPLOYED_SHA
  log "OK $REMOTE"
  ls -1dt "$FRONTEND"/.next.bak.* 2>/dev/null | tail -n +4 | xargs -r rm -rf   # keep 3 backups
else
  log "ALERT: BUILD FAILED for $REMOTE — rolling back to previous .next; will retry next run"
  rm -rf .next && mv ".next.bak.$STAMP" .next 2>/dev/null || log "rollback: no backup"
  pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1
  exit 1
fi
