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

# `npm ci` on EVERY deploy, exactly as India's deploy-frontend.yml does. The old rule ran it
# only when node_modules/.bin/next was missing, which leaves a stale node_modules in place the
# moment package-lock.json moves — and a build that is green in CI (fresh install) then fails
# on the box (old install) for a reason that never appears in the diff. --prefer-offline keeps
# it to seconds when nothing changed.
#
# BUT NOT ON A LIVE TREE FOR NOTHING. `npm ci` deletes node_modules and rebuilds it while pm2
# is still serving from this directory, and a route chunk that requires a module in that
# window fails the request. So the install runs when it can change something — the lockfile
# differs from the one the current node_modules was installed from, or node_modules is gone —
# and is skipped otherwise. The marker lives INSIDE node_modules, so a wiped tree reinstalls
# by construction. FORCE_NPM_CI=1 forces it.
LOCK_SHA=$(sha256sum package-lock.json | cut -c1-64)
if [ "${FORCE_NPM_CI:-0}" != "1" ] && [ -d node_modules ] && [ "$(cat node_modules/.atlas-lock-sha 2>/dev/null)" = "$LOCK_SHA" ]; then
  say "npm ci skipped — package-lock.json unchanged since the last install (FORCE_NPM_CI=1 overrides)"
else
  say "npm ci --prefer-offline"
  npm ci --prefer-offline >>"$LOG" 2>&1 || { say "npm ci FAILED — last 40 lines of $LOG:"; tail -n 40 "$LOG" | sed 's/^/    /'; die "npm ci failed"; }
  printf '%s' "$LOCK_SHA" > node_modules/.atlas-lock-sha || say "warning: could not write node_modules/.atlas-lock-sha — the next deploy installs again"
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
# WHAT IS BEING BUILT, named before a line of it is compiled. On 2026-09-08 the board served a
# build seven hours stale — every deploy since had died on the old /health smoke — while four
# fixes were merged, deployed in nobody's mind but mine, and debugged as if they were running.
# The question "is the code I am debugging the code that is serving?" has to be answerable from
# the log, not from memory.
say "building $(git -C "$REPO" log --oneline -1 2>/dev/null || echo '(not a git checkout)')"
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
  BUILD_RC=$?
  say "FAIL: build (exit $BUILD_RC; 137 = killed, usually OOM) — rolling back to the previous .next; the board keeps serving it"
  # The reason, on stdout, where the Actions log can see it. Without this the only copy of the
  # compiler's complaint is a file on the box, and the deploy reads as "it failed" with no why.
  say "last 60 lines of $LOG:"
  tail -n 60 "$LOG" | sed 's/^/    /'
  # Never `rm -rf .next` first: with no backup that turns a failed deploy into an outage.
  if [ -n "$BACKUP" ]; then
    rm -rf .next && mv "$BACKUP" .next && say "rollback: restored $(cat .next/BUILD_ID)"
  else
    say "rollback: no backup (first deploy) — .next left as the build left it"
  fi
  pm2 describe "$PM2_APP" >/dev/null 2>&1 && pm2 reload "$PM2_APP" --update-env >>"$LOG" 2>&1
  exit 1
fi

# ── smoke ────────────────────────────────────────────────────────────────────
# Assert on behaviour, never on the build having "probably" picked the variable up.
#
# THE SMOKE ROUTE IS /login, NOT /health, and the difference is the whole point. This gate used
# to curl /health, which is the ONE route that queries the database on an unauthenticated
# request — so when the database path stalled, a perfectly good build was rolled back. That is
# backwards twice over: the rollback cannot fix a database, and the build it restores has the
# identical problem, so the only thing the gate achieved was to block the deploy that carried
# the fix. It kept the board off the air for hours over a dependency it does not control.
#
# /login proves what a smoke test is FOR: the port is bound, Next resolves a route at
# ${BASE_PATH}, and the board returns HTML to a stranger. It is also the first page any human
# sees, so if it is broken nothing else matters. Rendering it runs no query, which is what makes
# it a liveness check rather than a dependency check.
#
# It does NOT prove sign-in works, and the log line below must not be read as if it did: the
# sign-in Server Action calls isInvited() (src/app/login/actions.ts -> src/lib/auth.ts:34),
# which reads atlas_global.app_user. So a stalled database would serve this page in full and
# then hang when the button is pressed. That is a MECHANISM to know about, not a diagnosis:
# scripts/db-probe.mjs measured the real path on 2026-09-08 and every step answered in under
# 0.1s, so a dead sign-in button is far more likely to be a Server Action rejected for its
# Origin (next.config.js allowedOrigins), which fails silently — no page error, no log line.
# Measure before concluding; that is what the probe is for.
#
# WAIT for the port, do not race it. `pm2 start` returns as soon as it has forked; Next then
# compiles its manifest and binds, which takes a second or two on this box. Curling once
# immediately answered `000 — Couldn't connect after 0 ms` and killed a deploy that had in
# fact worked. Twenty attempts, half a second apart: a board that has not answered in ten
# seconds is not slow, it is broken.
code=000
for _ in $(seq 20); do
  code=$(curl -sS -m 5 -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$ATLAS_GLOBAL_PORT${BASE_PATH}/login" 2>/dev/null || echo 000)
  [ "$code" = "200" ] && break
  sleep 0.5
done
if [ "$code" != "200" ]; then
  # The board's OWN log is the only thing that says why. Printing it here is the difference
  # between "smoke failed" and a diagnosis, on a deploy the operator is watching right now.
  say "smoke FAILED — last 30 lines of the board's pm2 log:"
  pm2 logs "$PM2_APP" --lines 30 --nostream 2>&1 | tee -a "$LOG" || true
  die "smoke: ${BASE_PATH}/login answered $code on :$ATLAS_GLOBAL_PORT (expected 200)"
fi
say "ok: smoke ${BASE_PATH}/login 200 on :$ATLAS_GLOBAL_PORT"
# The line to grep for when someone says "the fix isn't working". If this commit is not the one
# they merged, the board is not running their code and nothing else in the log matters.
say "NOW SERVING $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?') build=$(cat .next/BUILD_ID) built=$(date -u -r .next/BUILD_ID +%FT%TZ 2>/dev/null || echo '?')"

# The database path, REPORTED and never fatal. /health is worth knowing about on every deploy —
# it is the operator page and the only unauthenticated route that queries — but it depends on
# Supabase being reachable, which is not something this deploy did or can undo. So it is a line
# in the log, not a veto. A short timeout because the failure mode being watched for IS a hang:
# 20s of curl, then say so and carry on.
health=$(curl -sS -m 20 -o /dev/null -w '%{http_code}' \
  "http://127.0.0.1:$ATLAS_GLOBAL_PORT${BASE_PATH}/health" 2>/dev/null || echo 000)
if [ "$health" = "200" ]; then
  say "ok: ${BASE_PATH}/health 200 — the database path is healthy too"
else
  say "NOTE: ${BASE_PATH}/health answered $health (000 = no answer in 20s). The board is UP —"
  say "      the smoke on ${BASE_PATH}/login passed — and this line is about the operator page only."
  say "      A stalled query does NOT produce this: the page bounds each query and renders the"
  say "      stall as its own section, with HTTP 200. A non-200 here is the page failing to"
  say "      render at all: read \`pm2 logs $PM2_APP --lines 100\` and curl ${BASE_PATH}/health again."
fi
