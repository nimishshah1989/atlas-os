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
FAILED_ROUTES=()

h()   { printf '\n== %s ==\n' "$*"; }
kv()  { printf '  %-22s %s\n' "$1" "$2"; }
bad() { VERDICTS+=("✗ $*"); }
ok()  { VERDICTS+=("✓ $*"); }

# ── 1. code: is the checkout on main, and is it current? ────────────────────
h "code on the box"
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  # A fetch, deliberately: "is the box behind main" cannot be answered from the local refs.
  # It touches only origin/main's ref, never the worktree; bounded so an unreachable GitHub
  # cannot hang a status command.
  timeout 20 git -C "$REPO" fetch origin main --quiet 2>/dev/null || kv "fetch" "FAILED (offline?) — comparing against last known origin/main"
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
        port=env.get('PORT') or env.get('env',{}).get('PORT') or '?'
        print(env.get('status','?'), port, f'{h}h', env.get('restart_time','?')); break
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
# THE LIST IS DERIVED, NOT TYPED. It used to be six paths written by hand, and on the day
# /pulse shipped it 500ed in public while this script reported every verdict green — because
# /pulse was not on the list. A status check that cannot see a page cannot tell you it is down.
# So the routes come from the app directory itself: every `src/app/**/page.tsx` without a
# dynamic `[segment]` (a segment needs a real id, which this script has no way to pick).
routes() {
  local dir="$APP/src/app"
  [ -d "$dir" ] || { printf '/\n'; return; }
  find "$dir" -name 'page.tsx' -not -path '*/\[*' -printf '%P\n' 2>/dev/null \
    | sed -e 's#/\?page\.tsx$##' -e 's#^(.*)/##' -e 's#^#/#' -e 's#^/$#/#' \
    | sed -e 's#^//#/#' | sort -u
}
if [ "$PORT" != "?" ]; then
  for path in $(routes); do
    R=$(probe "$path"); CODE=${R%% *}; REST=${R#* }; T=${REST%% *}; LOC=${REST#* }
    kv "$path" "$CODE  ${T}s${LOC:+  → $LOC}"
    case "$path:$CODE" in
      /:200)      ok "/ renders without a session — the board is OPEN";;
      # A redirect is only evidence of AUTH when it points AT the sign-in page. `/` redirects
      # to /countries by design (app/page.tsx), and reading that as "auth is on" sent a reader
      # hunting a session bug that did not exist while the board was open all along.
      /:307|/:302)
        case "$LOC" in
          */login*) bad "/ redirects to sign-in — AUTH IS ON in the serving build (${LOC})";;
          *)        ok "/ redirects to ${LOC##*/} without a session — the board is OPEN";;
        esac;;
      /:000)      bad "/ did not answer in 15s on :$PORT — the process is not serving";;
      /health:000) bad "/health did not answer in 15s (database path or render stall)";;
      *:200|*:30[1278]) : ;;   # a page, or a redirect already shown on its line
      *)          bad "$path answered $CODE on :$PORT — an error page, not the board"; FAILED_ROUTES+=("$path");;
    esac
  done
  # A 5xx is a thrown exception, and its stack is in pm2's error log and nowhere a reader of
  # this output can otherwise reach. Print the tail once, not per route.
  if [ "${#FAILED_ROUTES[@]}" -gt 0 ] && command -v pm2 >/dev/null 2>&1; then
    h "why ${FAILED_ROUTES[*]} failed (pm2 error log, last 40 lines)"
    ERR=$(pm2 jlist 2>/dev/null | python3 -c 'import json,sys
try: print(next(p["pm2_env"]["pm_err_log_path"] for p in json.load(sys.stdin) if p.get("name")=="'"$PM2_APP"'"))
except Exception: print("")' 2>/dev/null || echo "")
    if [ -n "$ERR" ] && [ -f "$ERR" ]; then tail -n 40 "$ERR" | redact | sed 's/^/  /'
    else kv "pm2 error log" "not found"; fi
  fi
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
    *) bad "$scheme://$HOST/ answered $CODE — not a page";;
  esac
done

# ── 6. database and data ─────────────────────────────────────────────────────
h "database (scripts/db-probe.mjs, ≤15s per step)"
if [ -f "$APP/scripts/db-probe.mjs" ] && [ -f "$APP/.env.local" ]; then
  # Run ONCE, keep the output, print it: a second run would double the wall clock and hit the
  # database twice for the same answer.
  PROBE_OUT=$(cd "$APP" && timeout 120 node scripts/db-probe.mjs 2>&1 || echo "  (probe did not complete)")
  printf '%s\n' "$PROBE_OUT" | sed 's/^/  /'
  if printf '%s' "$PROBE_OUT" | grep -q 'HUNG\|FAIL\|did not complete'; then bad "the BOARD's database path has a HUNG or FAIL step above"; else ok "the BOARD's database path is healthy (the pipeline's is checked separately, below)"; fi
  ROWS=$(printf '%s' "$PROBE_OUT" | grep -oE '[0-9]+ country_daily row' | grep -oE '^[0-9]+' || echo '?')
  if [ "$ROWS" = "0" ]; then bad "country_daily is EMPTY — /countries will say so until build_country_views.py runs (nightly, or by hand)"; fi
else
  kv "probe" "skipped — $APP/scripts/db-probe.mjs or .env.local missing"
fi

# ── 6b. the database path the PIPELINE uses — NOT the board's ───────────────
# The probe above reads frontend-global/.env.local: the BOARD's url, the TRANSACTION pooler on
# :6543, role atlas_global_app. The nightly never touches it. It reads the repo .env and reaches
# Postgres through scripts/global_market/_gdb.py, on a different port with a different role — and
# on 2026-09-10 that path was refused outright ("(ECIRCUITBREAKER) too many authentication
# failures, new connections are temporarily blocked") for a whole run while the section above
# printed "database path healthy", because the board's path genuinely was. Two paths, two
# credentials, two ports: a status command that probes one and reports on "the database" is a
# status command that misleads, and it cost an afternoon of theorising to notice.
#
# One connection, one `select 1`, in a subshell so the pipeline's environment cannot leak into
# the rest of this script. It writes nothing.
h "database — the PIPELINE's own path (repo .env → _gdb, what the nightly uses)"
if [ -f "$REPO/.env" ] && [ -x "$REPO/.venv/bin/python" ]; then
  PIPE_DB=$(
    set -a; . "$REPO/.env" 2>/dev/null; set +a
    cd "$REPO" 2>/dev/null && timeout 60 "$REPO/.venv/bin/python" - <<'PYPROBE' 2>&1
import re, sys, time, urllib.parse

POOLERS = {
    6543: "TRANSACTION (:6543) — no backend is pinned to a connection",
    5432: "SESSION (:5432) — one backend pinned per connection, and the cluster has 15",
}


def say_failure(exc: BaseException) -> None:
    """One line, never a traceback — and never a credential.

    psycopg2 puts the whole DSN into an OperationalError, so the only text that escapes here
    has had anything shaped like `//user:pass@` cut out of it first. The host and role printed
    above come from the PARSED url, which carries no password to begin with.
    """
    line = (str(exc).strip().splitlines() or [exc.__class__.__name__])[0]
    print(f"PIPELINE_DB_FAIL       {exc.__class__.__name__}: "
          f"{re.sub(r'//[^/@ ]*@', '//***@', line)[:240]}")


try:
    sys.path.insert(0, "scripts/global_market")
    import _gdb  # noqa: E402 - the path insert above is what makes it importable

    url = urllib.parse.urlsplit(_gdb.psycopg2_url())
    print(f"host                   {url.hostname or '?'}:{url.port or '?'}")
    print(f"pooler                 {POOLERS.get(url.port or 0, 'direct, or a port this does not know')}")
    # The role NAME carries the Supabase project ref (`postgres.<ref>`), and this output lands
    # in a public Actions log. What a reader needs is WHICH role — the cluster superuser or the
    # board's scoped one — so the part before the dot is printed and the ref is not.
    role = (url.username or "?").split(".", 1)[0]
    print(f"role                   {role}{'.***' if '.' in (url.username or '') else ''}"
          f"{'  (the CLUSTER SUPERUSER, not a scoped role)' if role == 'postgres' else ''}")
except BaseException as exc:  # noqa: BLE001 - a status check reports its failure, never raises it
    say_failure(exc)
    raise SystemExit(0) from None

started = time.monotonic()
try:
    print(f"select 1               {_gdb.scalar('select 1')} in {time.monotonic() - started:.2f}s")
    print("PIPELINE_DB_OK")
except BaseException as exc:  # noqa: BLE001 - same: the status command must still print verdicts
    say_failure(exc)
PYPROBE
  ) || true
  printf '%s\n' "${PIPE_DB:-  (the probe produced no output)}" | sed 's/^/  /'
  case "$PIPE_DB" in
    *PIPELINE_DB_OK*)   ok "the pipeline's database path answers" ;;
    *PIPELINE_DB_FAIL*) bad "the PIPELINE cannot reach the database — the board may still be fine; read the line above" ;;
    *)                  bad "the pipeline database probe did not finish (timeout, or no venv/_gdb on this box)" ;;
  esac
else
  kv "pipeline probe" "skipped — $REPO/.env or $REPO/.venv/bin/python missing"
fi

# ── 7. the nightly ───────────────────────────────────────────────────────────
h "nightly (atlas_global_daily.sh)"
# Timestamped run logs only: the cron line in the runbook appends to atlas_global_daily_cron.log,
# which a bare atlas_global_daily*.log would match and report as "the last run".
LAST_NIGHTLY=$(ls -1t "$LOG_DIR"/atlas_global_daily_[0-9]*.log 2>/dev/null | head -1 || true)
if [ -n "$LAST_NIGHTLY" ]; then
  kv "last log" "$LAST_NIGHTLY  ($(date -u -r "$LAST_NIGHTLY" +%FT%TZ 2>/dev/null))"
  kv "last lines" ""; tail -3 "$LAST_NIGHTLY" 2>/dev/null | sed 's/^/    /'
  # The last three lines are the FAILURES roll-call and not one word about WHY. Every step
  # writes `  FAIL: <name> (<the reason it recorded>)` as it happens, and only the FIRST one is
  # a cause: on 2026-09-10 thirteen steps failed and twelve of them failed because the first had
  # already lost the database. Printing the roll-call alone made a one-line cause look like a
  # thirteen-step collapse.
  N_FAIL=$(grep -c '^  FAIL: ' "$LAST_NIGHTLY" 2>/dev/null || true)
  if [ "${N_FAIL:-0}" -gt 0 ]; then
    kv "steps that failed" "$N_FAIL — every one after the first may be a consequence of it"
    kv "FIRST failure" ""
    grep -m1 '^  FAIL: ' "$LAST_NIGHTLY" 2>/dev/null | cut -c1-320 | sed 's/^  /    /'
    bad "the last nightly failed $N_FAIL step(s) — read the FIRST failure above, not the roll-call"
  else
    ok "the last nightly recorded no failed step"
  fi
else
  kv "last log" "none under $LOG_DIR"
fi
kv "cron" "$(crontab -l 2>/dev/null | grep -c atlas_global_daily || true) entry/entries for atlas_global_daily"

# The WEEKLY writes its own log and none of the above would ever show it. Its N-PORT step is
# the long one, so "nothing is happening" and "the weekly is two hours into a fetch" look the
# same from here without this line.
LAST_WEEKLY=$(ls -1t "$LOG_DIR"/atlas_global_weekly_[0-9]*.log 2>/dev/null | head -1 || true)
if [ -n "$LAST_WEEKLY" ]; then
  kv "last weekly log" "$LAST_WEEKLY  ($(date -u -r "$LAST_WEEKLY" +%FT%TZ 2>/dev/null))"
  kv "last lines" ""; tail -3 "$LAST_WEEKLY" 2>/dev/null | sed 's/^/    /'
fi

# ── 7b. WHO HOLDS THE PIPELINE LOCK ─────────────────────────────────────────
# Both orchestrators serialise on /tmp/atlas_global.lock, and a run refused for want of it
# printed "a scheduled nightly is running now" and nothing else — no pid, no command, no
# elapsed time. A job three minutes in and a job wedged since yesterday were indistinguishable,
# and the only way to tell them apart was an SSH session, which is what this file exists to
# avoid. `flock` holds the lock on an open descriptor, so the holder is whichever process has
# the file open — fuser when it is installed, else /proc, which needs no package.
h "pipeline lock (/tmp/atlas_global.lock)"
LOCK=/tmp/atlas_global.lock
if [ ! -e "$LOCK" ]; then
  kv "lock file" "does not exist — no run has taken it since the last reboot"
else
  HOLDERS=$(fuser "$LOCK" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)
  if [ -z "$HOLDERS" ]; then
    HOLDERS=$(for d in /proc/[0-9]*; do for fd in "$d"/fd/*; do [ "$(readlink "$fd" 2>/dev/null)" = "$LOCK" ] && basename "$d" && break; done; done 2>/dev/null || true)
  fi
  if [ -z "$HOLDERS" ]; then
    kv "held by" "nobody — the lock is FREE (the file itself is never deleted)"
    ok "pipeline lock is free"
  else
    for pid in $HOLDERS; do
      kv "held by pid $pid" "$(ps -o etime=,args= -p "$pid" 2>/dev/null | sed 's/^ *//' | cut -c1-120 || echo 'gone')"
      CHILD=$(pgrep -P "$pid" 2>/dev/null | head -3 || true)
      for c in $CHILD; do kv "  running" "$(ps -o etime=,args= -p "$c" 2>/dev/null | sed 's/^ *//' | cut -c1-120 || true)"; done
    done
    bad "pipeline lock is HELD — a 'run'/'weekly' dispatch will be refused until it clears"
  fi
fi

# ── 7c. the cross-section the fundamental bands are set from ────────────────
# score_stocks prints the S&P 500 fundamental distribution on EVERY run, because the 37 US
# bands are the FM's to set and India's numbers are wrong for this market. It was printed into
# a log file on the box that nobody off the box could read, so the decision it exists to
# inform could not be made from anywhere else. Public market data at seven percentiles: no
# positions, no client data, and it goes through the same redaction as everything else.
h "S&P 500 fundamental cross-section (newest run that printed one)"
XSEC_LOG=$(grep -l 'fundamental cross-section' $(ls -1t "$LOG_DIR"/atlas_global_daily_[0-9]*.log 2>/dev/null | head -5) 2>/dev/null | head -1 || true)
if [ -n "$XSEC_LOG" ]; then
  kv "from" "$XSEC_LOG"
  awk '/fundamental cross-section/{n=1} n && n++<16' "$XSEC_LOG" | sed 's/^/  /'
else
  kv "cross-section" "no recent nightly log printed one — has score_stocks run?"
fi

# ── verdicts ─────────────────────────────────────────────────────────────────
h "VERDICTS — read these first"
if [ "${#VERDICTS[@]}" -eq 0 ]; then printf '  (no verdicts — every section was skipped; is this the box?)\n'; fi
for v in "${VERDICTS[@]+"${VERDICTS[@]}"}"; do printf '  %s\n' "$v"; done
printf '\n  A ✗ on BUILD or "behind main" means: the code is right and it is NOT what is serving.\n'
printf '  Fix that before reading anything else — every other symptom may be a consequence.\n'
