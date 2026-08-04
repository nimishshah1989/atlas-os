#!/usr/bin/env bash
# ── Atlas source sync ────────────────────────────────────────────────────────
# Keeps /home/ubuntu/atlas-os matching origin/main so the NIGHTLY PIPELINE scripts
# (atlas_daily.sh and everything it calls) stay current. It does NOT build and does NOT
# touch pm2 — the frontend is deployed by the GitHub Action (deploy-frontend.yml).
#
# Why this exists: atlas-auto-deploy.sh used to keep this tree current as a side effect of
# deploying. It was disabled on 2026-08-04 because it raced that Action — both built in this
# same directory and tore node_modules apart. Disabling it fixed the race but silently froze
# the backend scripts at whatever commit was last deployed, which is a worse bug than the one
# it solved. This restores the sync without restoring the race.
#
# reset --hard, not merge --ff-only: the Action rsyncs main's frontend/ into this tree on every
# deploy, so it is permanently "dirty" against git and a fast-forward would refuse. Nothing is
# lost — the box is a deploy target, never a workstation (see CLAUDE.md).
set -uo pipefail

REPO=/home/ubuntu/atlas-os
BRANCH=main
LOG=/home/ubuntu/logs/src-sync.log
LOCK=/tmp/atlas-src-sync.lock
mkdir -p /home/ubuntu/logs

exec 9>"$LOCK" || exit 0
flock -n 9 || exit 0

cd "$REPO" || { echo "[$(date -u +%FT%TZ)] repo missing" >> "$LOG"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" = "$BRANCH" ] || exit 0

git fetch origin "$BRANCH" --quiet 2>>"$LOG" || exit 0
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
DIRTY=$(git status --porcelain | wc -l | tr -d ' ')

# Nothing to do only when the commit matches AND the tree is clean.
[ "$LOCAL" = "$REMOTE" ] && [ "$DIRTY" = "0" ] && exit 0

if git reset --hard "$REMOTE" >>"$LOG" 2>&1; then
  [ "$LOCAL" = "$REMOTE" ] \
    && echo "[$(date -u +%FT%TZ)] cleaned $DIRTY rsync-dirtied path(s) at $REMOTE" >> "$LOG" \
    || echo "[$(date -u +%FT%TZ)] synced $LOCAL -> $REMOTE ($DIRTY dirty path(s) discarded)" >> "$LOG"
else
  echo "[$(date -u +%FT%TZ)] ALERT: reset to $REMOTE FAILED — backend scripts are stale" >> "$LOG"
  exit 1
fi
