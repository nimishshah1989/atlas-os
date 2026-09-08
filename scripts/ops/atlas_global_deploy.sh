#!/usr/bin/env bash
# ── Global Atlas — build + serve on the box ──────────────────────────────────
# Builds frontend-global and starts (first run) or reloads (every run after) its pm2 process.
# Run BY HAND, from the box, after `git pull` — there is no cron and no GitHub Action for the
# global board (deploy-frontend.yml is filtered to `frontend/**` and only knows the India app).
# Full procedure, prerequisites and rollback: docs/global/deploy-subpath.md.
#
# Properties, in the order they matter:
#   • CLAUDE.md rule #5 — build FULLY, assert `.next/BUILD_ID`, THEN reload, exactly once. A
#     reload mid-build serves a half-written .next and 500s the board.
#   • Shares $NEXT_BUILD_LOCK with the India build paths (atlas_daily.sh, atlas-auto-deploy.sh).
#     The box is 2 vCPU and each Next build asks for 3 GB; two at once OOMs and takes the LIVE
#     India board down with it. This script waits, it does not skip.
#   • ATLAS_GLOBAL_BASE_PATH is a BUILD-time variable (frontend-global/next.config.js) AND a
#     run-time one (src/lib/basePath.ts). It is exported for both here, from one value.
#   • .next backup + rollback on a failed build: the board keeps serving the last good one.
#   • fork mode, ONE instance. Never `-i`: freshness is unstable_cache + revalidateTag, which
#     lands in one process — a second instance would keep serving yesterday, silently.
#
# Required in the environment (the box .env, or exported):
#   ATLAS_GLOBAL_PORT   the loopback port nginx proxies /global to. No default ON PURPOSE:
#                       pick it from `ss -ltnp` on the box, not from a document.
# Optional: ATLAS_REPO (default /home/ubuntu/atlas-os), ATLAS_LOG_DIR (default /home/ubuntu/logs),
#           PM2_APP (default atlas-global), ATLAS_GLOBAL_BASE_PATH (default /global).
set -uo pipefail

REPO="${ATLAS_REPO:-/home/ubuntu/atlas-os}"
APP_DIR="$REPO/frontend-global"
PM2_APP="${PM2_APP:-atlas-global}"
# Default EMPTY: the board is served at the ROOT of its own host, global.jslwealth.in
# (docs/global/deploy-subdomain.md). The old default was /global, from the superseded sub-path
# deployment — and `:-` treats an EMPTY value as unset, so an operator who set the variable to
# "" in .env.local still got a /global build whose every route 404s at the root. `-` without
# the colon is the difference: unset falls back, empty is respected.
BASE_PATH="${ATLAS_GLOBAL_BASE_PATH-}"
LOG_DIR="${ATLAS_LOG_DIR:-/home/ubuntu/logs}"
LOG="$LOG_DIR/atlas_global_deploy.log"
NEXT_BUILD_LOCK="${NEXT_BUILD_LOCK:-/tmp/atlas-next-build.lock}"
mkdir -p "$LOG_DIR"

say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
die() { say "REFUSED: $*"; exit 1; }

[ -n "${ATLAS_GLOBAL_PORT:-}" ] || die "ATLAS_GLOBAL_PORT is unset — choose a free port from \`ss -ltnp\` (docs/global/deploy-subpath.md §2)"
[ -d "$APP_DIR" ] || die "$APP_DIR does not exist"
case "$BASE_PATH" in */) die "ATLAS_GLOBAL_BASE_PATH must not end in a slash (got '$BASE_PATH')";; esac
command -v pm2 >/dev/null || die "pm2 not on PATH"

# The board reads its own env from .env.local in the serving directory (same mechanism as India's
# frontend/.env.local; both are excluded from every sync). Without ATLAS_GLOBAL_DB_URL the board
# still boots and still serves 200s — with the allowlist check skipped (src/lib/auth.ts:58). That
# must never happen on the public domain, so refuse here rather than discover it later.
[ -f "$APP_DIR/.env.local" ] || die "$APP_DIR/.env.local is missing (see frontend-global/.env.example)"
grep -qE '^ATLAS_GLOBAL_DB_URL=.+' "$APP_DIR/.env.local" \
  || die ".env.local has no ATLAS_GLOBAL_DB_URL — the board would serve with the allowlist disabled"
grep -qE '^ATLAS_GLOBAL_DB_URL=.*:6543/' "$APP_DIR/.env.local" \
  || die "ATLAS_GLOBAL_DB_URL is not the transaction pooler (:6543) — session mode shares India's 15 slots and India already holds 14"

cd "$APP_DIR" || die "cannot cd $APP_DIR"
# Exported, not just prefixed: `pm2 reload --update-env` re-reads THIS shell's environment, so
# both variables must be in it on every run. A reload from a shell without PORT would put the
# board back on :3000 and nginx would proxy /global to nothing.
export ATLAS_GLOBAL_BASE_PATH="$BASE_PATH"
export PORT="$ATLAS_GLOBAL_PORT"

# A deploy once died on `sh: 1: next: not found` (atlas-auto-deploy.sh's lesson). Run `npm ci` by
# hand as well whenever the lockfile has moved — this only catches the missing-toolchain case.
if [ ! -x node_modules/.bin/next ]; then
  say "node_modules/.bin/next missing — npm ci"
  npm ci >>"$LOG" 2>&1 || die "npm ci failed"
fi

# `|| die`, because an UNCHECKED cp is how a full disk turns a failed build into a broken
# board: it leaves a partial .next.bak that the rollback below would then install.
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP=""
if [ -d .next ]; then
  cp -r .next ".next.bak.$STAMP" || die "backup of .next failed (disk?) — not building"
  BACKUP=".next.bak.$STAMP"
fi
rm -rf .next/cache/fetch-cache            # before: stale unstable_cache entries
say "build (basePath=${BASE_PATH:-<root>}) port=$ATLAS_GLOBAL_PORT — waiting on $NEXT_BUILD_LOCK if India is building"

if NODE_OPTIONS='--max-old-space-size=3072' \
   flock -w 2700 "$NEXT_BUILD_LOCK" npm run build >>"$LOG" 2>&1 \
   && [ -f .next/BUILD_ID ]; then
  rm -rf .next/cache/fetch-cache          # after: the build repopulates it
  # start on the first run, reload after — one pm2 action either way, after the build is whole.
  if pm2 describe "$PM2_APP" >/dev/null 2>&1; then
    pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1 || die "pm2 reload failed"
    say "ok: reload $PM2_APP ($(cat .next/BUILD_ID))"
  else
    # Fork mode, one instance, port passed through the environment — `npm start` is a bare
    # `next start`, which would otherwise take :3000. `pm2 save` so it survives a reboot.
    pm2 start npm --name "$PM2_APP" --cwd "$APP_DIR" -- start >>"$LOG" 2>&1 \
      || die "pm2 start failed"
    pm2 save >>"$LOG" 2>&1
    say "ok: started $PM2_APP on :$ATLAS_GLOBAL_PORT ($(cat .next/BUILD_ID)) — pm2 save done"
  fi
  ls -1dt "$APP_DIR"/.next.bak.* 2>/dev/null | tail -n +4 | xargs -r rm -rf   # keep 3 backups
else
  say "FAIL: build — rolling back to the previous .next; the board keeps serving it"
  # Never `rm -rf .next` first: with no backup that turns a failed deploy into an outage.
  if [ -n "$BACKUP" ]; then
    rm -rf .next && mv "$BACKUP" .next && say "rollback: restored $(cat .next/BUILD_ID)"
  else
    say "rollback: no backup (first deploy) — .next left as the build left it"
  fi
  pm2 describe "$PM2_APP" >/dev/null 2>&1 && pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1
  exit 1
fi

# Assert on behaviour, never on the build having "probably" picked the variable up. /health is the
# one page that renders without a session (src/lib/supabase/paths.ts).
# WAIT for the port, do not race it. `pm2 start` returns as soon as it has forked; Next then
# compiles its manifest and binds, which takes a second or two on this box. Curling once
# immediately answered `000 — Couldn't connect after 0 ms` and killed a deploy that had in
# fact worked. Twenty attempts, half a second apart: a board that has not answered in ten
# seconds is not slow, it is broken.
code=000
for _ in $(seq 20); do
  code=$(curl -sS -m 5 -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$ATLAS_GLOBAL_PORT${BASE_PATH}/health" 2>/dev/null || echo 000)
  [ "$code" = "200" ] && break
  sleep 0.5
done
if [ "$code" != "200" ]; then
  # The board's OWN log is the only thing that says why. Printing it here is the difference
  # between "smoke failed" and a diagnosis, on a deploy the operator is watching right now.
  say "smoke FAILED — last 30 lines of the board's pm2 log:"
  pm2 logs "$PM2_APP" --lines 30 --nostream 2>&1 | tee -a "$LOG" || true
  die "smoke: ${BASE_PATH}/health answered $code on :$ATLAS_GLOBAL_PORT (expected 200)"
fi
say "ok: smoke ${BASE_PATH}/health 200 on :$ATLAS_GLOBAL_PORT"
