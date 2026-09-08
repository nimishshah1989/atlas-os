#!/usr/bin/env bash
# ── Global Atlas — the whole picture in one command ─────────────────────────
#
#     bash scripts/ops/atlas_global_status.sh        (on the box; safe to run any time)
#
# WHY THIS EXISTS. On 2026-09-08 it took eight round trips through a human to learn things
# that fit on one screen: the box was on the right commit, but the BUILD was seven hours
# stale; the database was fine, but the sign-in button was dead for a reason that leaves no
# log; the merge that should have deployed had deployed nothing. Each fact was fetched one at
# a time, by one command at a time, each command guessed from the previous answer. Every one
# of those facts is printed below, unconditionally, with a verdict.
#
# The discipline it enforces: BEFORE anyone theorises about why the board is wrong, run this,
# and read the VERDICTS at the bottom. "The code is right but it is not what is serving" and
# "it is serving but auth is on" and "the route works on the box but not through nginx" are
# three different problems with three different fixes, and they look identical from a browser.
#
# Every section is independent and none may abort the script: a check that cannot run says so
# and the rest still prints. It writes nothing and changes nothing.
set -uo pipefail

REPO="${ATLAS_REPO:-/home/ubuntu/atlas-os}"
APP="$REPO/frontend-global"
PM2_APP="${PM2_APP:-atlas-global}"
HOST="${ATLAS_GLOBAL_HOST:-global.jslwealth.in}"
LOG_DIR="${ATLAS_LOG_DIR:-/home/ubuntu/logs}"
VERDICTS=()

h()   { printf '\n== %s ==\n' "$*"; }
kv()  { printf '  %-22s %s\n' "$1" "$2"; }
bad() { VERDICTS+=("✗ $*"); }
ok()  { VERDICTS+=("✓ $*"); }

# ── 1. code: is the checkout on main, and is it current? ────────────────────
h "code on the box"
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$REPO" fetch origin main --quiet 2>/dev/null || kv "fetch" "FAILED (offline?) — comparing against last known origin/main"
  BRANCH=$(git -C "$REPO" branch --show-current 2>/dev/null || echo '?')
  HEAD_SHA=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')
  MAIN_SHA=$(git -C "$REPO" rev-parse --short origin/main 2>/dev/null || echo '?')
  BEHIND=$(git -C "$REPO" rev-list --count HEAD..origin/main 2>/dev/null || echo '?')
  kv "branch" "$BRANCH"
  kv "HEAD" "$HEAD_SHA  $(git -C "$REPO" log -1 --format=%s 2>/dev/null | cut -c1-70)"
  kv "origin/main" "$MAIN_SHA"
  kv "commits behind main" "$BEHIND"
  DIRTY=$(git -C "$REPO" status --porcelain 2>/dev/null | grep -vc '^??' || true)
  kv "modified tracked files" "$DIRTY"
  if [ "$BRANCH" != "main" ]; then bad "box is on branch '$BRANCH', not main — the deploy pulls main"; fi
  if [ "$BEHIND" != "0" ] && [ "$BEHIND" != "?" ]; then bad "box is $BEHIND commit(s) BEHIND main — the fix you merged is not here yet"
  elif [ "$BRANCH" = "main" ]; then ok "checkout is main and current"; fi
else
  kv "repo" "$REPO is not a git checkout"; bad "no git checkout at $REPO"
fi

# ── 2. build: is what pm2 serves built from the code that is here? ───────────
h "build that is SERVING"
if [ -f "$APP/.next/BUILD_ID" ]; then
  BUILD_ID=$(cat "$APP/.next/BUILD_ID")
  BUILD_AT=$(date -u -r "$APP/.next/BUILD_ID" +%FT%TZ 2>/dev/null || echo '?')
  BUILD_EPOCH=$(stat -c %Y "$APP/.next/BUILD_ID" 2>/dev/null || echo 0)
  # The newest commit that could change a served byte. A build older than it is stale by
  # definition, whatever the checkout says — this is the check that would have ended the day
  # in its first minute.
  LAST_UI_EPOCH=$(git -C "$REPO" log -1 --format=%ct -- frontend-global scripts/ops/atlas_global_deploy.sh 2>/dev/null || echo 0)
  LAST_UI_SHA=$(git -C "$REPO" log -1 --format=%h -- frontend-global scripts/ops/atlas_global_deploy.sh 2>/dev/null || echo '?')
  kv "BUILD_ID" "$BUILD_ID"
  kv "built at" "$BUILD_AT"
  kv "newest UI commit" "$LAST_UI_SHA  $(date -u -d @"$LAST_UI_EPOCH" +%FT%TZ 2>/dev/null || echo '?')"
  if [ "$BUILD_EPOCH" -lt "$LAST_UI_EPOCH" ]; then
    AGE_H=$(( (LAST_UI_EPOCH - BUILD_EPOCH) / 3600 ))
    bad "BUILD IS STALE — built before the newest UI commit (by ~${AGE_H}h). Nothing merged since is being served. Run the deploy."
  else
    ok "build is newer than the newest UI commit"
  fi
  # The deploy log's own claim, if it has one — the NOW SERVING line names the commit it built.
  SERVING_LINE=$(grep -h 'NOW SERVING' "$LOG_DIR/atlas_global_deploy.log" 2>/dev/null | tail -1 || true)
  kv "deploy log says" "${SERVING_LINE:-(no NOW SERVING line yet — deploy predates #244)}"
else
  kv ".next/BUILD_ID" "MISSING — never built here"; bad "no build in $APP/.next"
fi

# ── 3. process ───────────────────────────────────────────────────────────────
h "pm2 process $PM2_APP"
if command -v pm2 >/dev/null 2>&1; then
  PM2_JSON=$(pm2 jlist 2>/dev/null || echo '[]')
  read -r P_STATUS P_PORT P_UPTIME P_RESTARTS <<<"$(printf '%s' "$PM2_JSON" | python3 -c "
import json,sys,time
try: procs=json.load(sys.stdin)
except Exception: procs=[]
for p in procs:
    if p.get('name')=='$PM2_APP':
        env=p.get('pm2_env',{}); up=env.get('pm_uptime',0)
        h=int((time.time()*1000-up)/3600000) if up else 0
        print(env.get('status','?'), env.get('PORT','?'), f'{h}h', env.get('restart_time','?')); break
else: print('ABSENT ? ? ?')
" 2>/dev/null || echo '? ? ? ?')"
  kv "status" "$P_STATUS"; kv "PORT" "$P_PORT"; kv "uptime" "$P_UPTIME"; kv "restarts" "$P_RESTARTS"
  if [ "$P_STATUS" = "online" ]; then ok "pm2 $PM2_APP online on :$P_PORT"; else bad "pm2 $PM2_APP is $P_STATUS"; fi
else
  kv "pm2" "not on PATH"; bad "pm2 not found"; P_PORT="?"
fi
PORT="${ATLAS_GLOBAL_PORT:-$P_PORT}"

# ── 4. routes on the loopback: what the Next process itself answers ──────────
h "routes on 127.0.0.1:$PORT (the process, before nginx)"
probe() {  # probe PATH → "CODE  SECONDS  [→ Location]"
  local out; out=$(curl -sS -o /dev/null -m 15 -w '%{http_code} %{time_total} %{redirect_url}' "http://127.0.0.1:$PORT$1" 2>/dev/null || echo "000 - -")
  printf '%s' "$out"
}
if [ "$PORT" != "?" ]; then
  for path in / /countries /etfs /stocks /login /health; do
    R=$(probe "$path"); CODE=${R%% *}; REST=${R#* }; T=${REST%% *}; LOC=${REST#* }
    kv "$path" "$CODE  ${T}s${LOC:+  → $LOC}"
    case "$path:$CODE" in
      /:200)      ok "/ renders without a session — the board is OPEN";;
      /:307|/:302) bad "/ redirects to sign-in — AUTH IS ON in the serving build (${LOC})";;
      /:000)      bad "/ did not answer in 15s on :$PORT — the process is not serving";;
      /health:000) bad "/health did not answer in 15s (database path or render stall)";;
    esac
  done
else
  kv "routes" "skipped — no port known"
fi

# ── 5. through nginx and the public name: what a browser actually gets ───────
h "public: $HOST"
for scheme in http https; do
  R=$(curl -sS -o /dev/null -m 15 -w '%{http_code} %{time_total} %{redirect_url}' "$scheme://$HOST/" 2>/dev/null || echo "000 - -")
  CODE=${R%% *}; REST=${R#* }; T=${REST%% *}; LOC=${REST#* }
  kv "$scheme://$HOST/" "$CODE  ${T}s${LOC:+  → $LOC}"
  case "$scheme:$CODE" in
    http:200|http:301|http:302|http:307) ok "$scheme://$HOST answers ($CODE)";;
    https:200|https:307) ok "https works — TLS is issued";;
    https:000) bad "https does not answer — no certificate yet (Cloudflare grey-cloud, then certbot)";;
    http:000)  bad "http://$HOST does not answer — DNS or nginx";;
    http:502|http:504) bad "nginx answers but cannot reach the process — port mismatch? nginx proxies to a different port than pm2 serves";;
  esac
done

# ── 6. database and data ─────────────────────────────────────────────────────
h "database (scripts/db-probe.mjs, ≤15s per step)"
if [ -f "$APP/scripts/db-probe.mjs" ] && [ -f "$APP/.env.local" ]; then
  # Run ONCE, keep the output, print it: a second run would double the wall clock and hit the
  # database twice for the same answer.
  PROBE_OUT=$(cd "$APP" && timeout 120 node scripts/db-probe.mjs 2>&1 || echo "  (probe did not complete)")
  printf '%s\n' "$PROBE_OUT" | sed 's/^/  /'
  if printf '%s' "$PROBE_OUT" | grep -q 'HUNG\|FAIL\|did not complete'; then bad "database path has a HUNG or FAIL step above"; else ok "database path healthy"; fi
  ROWS=$(printf '%s' "$PROBE_OUT" | grep -oE '[0-9]+ country_daily row' | grep -oE '^[0-9]+' || echo '?')
  if [ "$ROWS" = "0" ]; then bad "country_daily is EMPTY — /countries will say so until build_country_views.py runs (nightly, or by hand)"; fi
else
  kv "probe" "skipped — $APP/scripts/db-probe.mjs or .env.local missing"
fi

# ── 7. the nightly ───────────────────────────────────────────────────────────
h "nightly (atlas_global_daily.sh)"
LAST_NIGHTLY=$(ls -1t "$LOG_DIR"/atlas_global_daily*.log 2>/dev/null | head -1 || true)
if [ -n "$LAST_NIGHTLY" ]; then
  kv "last log" "$LAST_NIGHTLY  ($(date -u -r "$LAST_NIGHTLY" +%FT%TZ 2>/dev/null))"
  kv "last lines" ""; tail -3 "$LAST_NIGHTLY" 2>/dev/null | sed 's/^/    /'
else
  kv "last log" "none under $LOG_DIR"
fi
kv "cron" "$(crontab -l 2>/dev/null | grep -c atlas_global_daily || true) entry/entries for atlas_global_daily"

# ── verdicts ─────────────────────────────────────────────────────────────────
h "VERDICTS — read these first"
if [ "${#VERDICTS[@]}" -eq 0 ]; then printf '  (no verdicts — every section was skipped; is this the box?)\n'; fi
for v in "${VERDICTS[@]+"${VERDICTS[@]}"}"; do printf '  %s\n' "$v"; done
printf '\n  A ✗ on BUILD or "behind main" means: the code is right and it is NOT what is serving.\n'
printf '  Fix that before reading anything else — every other symptom may be a consequence.\n'
