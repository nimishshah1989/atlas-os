# Global Atlas at `atlas.jslwealth.in/global` — the deployment package

> ## ⛔ DO NOT RUN THIS YET — three independent adversarial reviews said so
>
> This document is **blocked**, not draft. Three reviewers (nginx/process, auth/exposure,
> rollback-under-pressure) each tried to break the live India board with it and each succeeded by a
> different route. The nginx design itself is sound and all three said so; what is unsafe is
> everything around it. Fix these first, then delete this banner:
>
> 1. **The build lock has a hole exactly where the traffic is.** India has THREE deployers and the
>    repo contradicts itself about which is live (`docs/deploy.md:16-21` vs
>    `scripts/ops/atlas-src-sync.sh:5-11` vs `STATE.md:44-48`). The GitHub Action
>    `deploy-frontend.yml` builds ON THE BOX and does NOT take the lock added here. One `frontend/**`
>    merge during a global build = two 3 GB builds on 2 vCPU = the live India process OOM-killed.
> 2. **Nothing checks disk.** `df`/`disk`/`space` appear zero times in 460 lines. The second app is
>    548 MB of `node_modules` + 110 MB of `.next` + three `.next.bak.*`. All three India build paths
>    do `cp -r .next .next.bak.$STAMP` with the exit status UNCHECKED and, on failure,
>    `mv` the backup back — so ENOSPC makes India's own rollback install a truncated build.
> 3. **The rollback `sed` can silently do nothing, and poisons India's rollback while it does.**
>    `sed -i` exits 0 whether or not it matched, and on the standard `sites-enabled` symlink layout
>    it replaces the symlink with a regular file — disabling the documented `3004`→`3002` break-glass
>    that `docs/deploy.md:29` promises. Discovered during the next India incident.
> 4. **Port 3002 looks free and is not.** It is India's instant-rollback target; that process is
>    STOPPED, so `ss -ltnp` does not show it, and §0 tells the operator to trust `ss` over the docs.
> 5. **The Supabase cookie is `Path=/`.** `@supabase/ssr` defaults to the whole domain and no
>    `cookieOptions` are passed, so a Global session attaches to every India request including
>    static assets, and can overflow nginx's header buffer into `400 Bad Request` — for the FM and
>    the analysts specifically, i.e. the loudest reporters, on a board that works for everyone else.
> 6. **A session-mode `ATLAS_GLOBAL_DB_URL` in the deploy shell beats the `.env.local` guard**
>    (`@next/env` prefers `process.env`) and takes India's last Postgres session slot; India's
>    `db.ts` is sized at `max: 14` against a hard cap of 15.
> 7. **`git pull` on the box while this lives on a branch** ships untested code to real clients:
>    `atlas_daily.sh` has no branch guard, and `atlas-auto-deploy.sh` `git stash`es a dirty tree and
>    carries on rather than stopping.
>
> Also unresolved and listed here so it is not lost: the fail-open auth path
> (`frontend-global/src/lib/auth.ts`) must be closed before `/global` is reachable from the public
> internet, and the box `.env` is `set -a; source`d by the nightly and then handed to
> `pm2 reload --update-env`, so anything added there lands in the India server process's environment.

Serving the Global Atlas board from the prod box, under the existing domain, beside the live India
board. Written to be run top to bottom by a human on the box. **Nothing here was executed against
the box** — this session had no SSH — so every step that depends on a box fact says so and names
the command that settles it. Do not improvise past a step whose precondition you have not read
with your own eyes.

This reverses a written decision. `docs/global/plan.md` §Frontend + hosting + auth chose Vercel
explicitly *to keep the global app off this box*: "the prod box stays Python-only: its two racing
deploy paths, the 2-vCPU nightly, and pm2 never touch the global app." All three reasons are still
true. What changes them is not that they went away but that the FM wants one domain. §2 and §6
carry what that costs and what has been done about it. Log the reversal in `decisions.jsonl` and
correct `CLAUDE.md`'s "Global: Vercel" line when this lands.

**Read §6 before §1.** Three things are not safe on a public domain today, and one of them
(`/health`) is reachable without a session by design.

---

## §0 — Confirm on the box before touching anything

Not in this repo, not guessable, and each one changes a later step. Run all seven, keep the output.

```bash
crontab -l                                        # which deploy paths are actually live
ls -la /home/ubuntu/atlas-auto-deploy.sh          # …and whether the auto-deployer still exists
pm2 list; pm2 describe atlas-frontend-v3          # exec mode, cwd, instances, env of the LIVE app
ss -ltnp                                          # which ports are genuinely taken
cat /etc/nginx/sites-enabled/atlas.jslwealth.in   # the vhost — §3 depends on every line of it
free -m; nproc                                    # headroom for a second Next build
grep -o '^[A-Z_]*=' /home/ubuntu/atlas-os/.env    # which global variables are already set
```

What you are looking for:

| Question | Why it decides a step |
|---|---|
| Which of `atlas-auto-deploy.sh` (cron, every 5 min), the GitHub Action `deploy-frontend.yml`, and `atlas_daily.sh` (16:00 IST) actually deploys India | The repo contradicts itself: `docs/deploy.md` says cron, `scripts/ops/atlas-src-sync.sh` says the cron was disabled on 2026-08-04 because it raced the Action, and `scripts/ops/crontab.txt` still lists it. Whichever is live shares the box's memory with the global build — see the lock in §2 |
| A free loopback port | 3004 is live (India). 3002 and 3005 are both claimed as the retired v2 by different files; 8010 was a retired FastAPI; `docs/disaster-recovery.md` admits `/api/kite/` and `/api/v1/*` fan out to ports it does not name. **Pick from `ss -ltnp`, never from a document** |
| Does the vhost hold a **regex** `location ~ ^/api/`? | A regex location would hijack `/global/api/revalidate` to :3004 and the nightly publish would fail every night. The `^~` in §3 is what prevents this — but you must see the vhost to know it was needed |
| Does `proxy_pass` in the India `location /` end in a slash or a URI? | Yours must not (§3). Theirs is not your business, but read it to copy the header set the box already proves works |
| Does port 80 `301` to https? | The Supabase session cookies carry **no `Secure` flag** (§6). Without the redirect a token can cross the wire in clear text |
| `Host` / `X-Forwarded-Host` / `X-Forwarded-Proto` set on the India block? | The magic link's origin is built from those headers (`frontend-global/src/app/login/actions.ts`), and Next 15 validates a Server Action's Origin against them. The India board carries an explicit `serverActions.allowedOrigins` entry for this domain, which is evidence this proxy needs it |
| RAM, and whether swap exists | Each Next build asks for 3 GB (`NODE_OPTIONS=--max-old-space-size=3072`) on 2 vCPU. Two at once OOMs and takes the **live India board** down. §2's lock is the mitigation; the numbers tell you whether one build alone is even comfortable |

---

## §1 — Prerequisites

Serving the board is the **last** step, not the first. With no `atlas_global` schema,
`atlas_global.app_user` does not exist, `requireUser()` throws on every request, and every board
page renders the error boundary while `/global/health` prints the relation name to the public.

### FM only — nobody else can do these

1. **Prod schema.** `docs/global/runbook.md` §2: `apply_ddl.py` (41 tables) then
   `seed_thresholds.py`. Done when `python -m atlas.db` prints `atlas_global_exists True`.
   This has **never been applied to prod**.
2. **Database role.** `runbook.md` §3: `CREATE ROLE atlas_global_app` with the listed grants and
   the `REVOKE ALL ON SCHEMA atlas_foundation`. Done when
   `psql -U atlas_global_app -c "select count(*) from atlas_foundation.instrument_master"` fails
   with *permission denied*. A success there is a bug, not a convenience.
3. **Supabase Auth.** Authentication → enable Email (magic link). Then, in
   **Authentication → URL Configuration** — these two are what make sign-in work at all:
   - **Redirect URLs** must include `https://atlas.jslwealth.in/global/login/callback`
     (or `https://atlas.jslwealth.in/global/**`). Not the Vercel value `runbook.md` §4 describes,
     and not the path without `/global`. On a mismatch Supabase silently falls back to Site URL.
   - **Site URL** = `https://atlas.jslwealth.in/global`. If it is still a Vercel origin, every
     link that fails the allow-list check goes to Vercel and looks like a broken link.
   - **Turn "Allow new users to sign up" OFF** (Authentication → Sign In / Providers → Email).
     The anon key is public by design; with sign-ups on, a stranger can mint a valid session
     against the project. §6 explains why that matters more than it looks.
   - Check **Email Templates** for a hardcoded path instead of `{{ .ConfirmationURL }}`.
4. **The allowlist row**, once the schema exists:
   `insert into atlas_global.app_user (email, role, display_name) values ('<lowercase>', 'fm', '<name>');`
5. **The decision.** §6 lists three exposures that are the FM's call, not the operator's.

### Operator

6. `git pull` on the box so `frontend-global/` is at the commit carrying this document.
7. `/home/ubuntu/atlas-os/frontend-global/.env.local` — copy from `frontend-global/.env.example`,
   fill in `ATLAS_GLOBAL_DB_URL` (**:6543**, transaction pooler, role `atlas_global_app`),
   `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `GLOBAL_REVALIDATE_SECRET`.
   Never committed; excluded from every sync, exactly like India's `frontend/.env.local`.
   `atlas_global_deploy.sh` refuses to run if the file is missing, if the DB URL is absent, or if
   it is not on :6543 — India's session pool already holds 14 of its 15 slots, so a session-mode
   URL here would take the India board down, and `db.ts` only warns about it.
8. **Box `.env`**: `GLOBAL_REVALIDATE_URL=http://127.0.0.1:<port>/global/api/revalidate`
   (loopback, so the nightly publish cannot fail on a proxy or TLS problem), and
   `GLOBAL_REVALIDATE_SECRET` matching `.env.local`. **No trailing slash** — Next answers
   `…/revalidate/` with a 308, the publish step does not follow redirects, and the night ends as
   `FAIL: publish (http 308)`. Verified locally: `POST /global/api/revalidate/` → `308`.
9. If `/home/ubuntu/atlas-auto-deploy.sh` is live (§0), refresh it from
   `scripts/ops/atlas-auto-deploy.sh` so it takes the shared build lock. Until it does, the lock
   in §2 has only one party and does nothing.

---

## §2 — The pm2 entry

There is **no ecosystem file in this repo** and never has been — every pm2 process on the box was
created by hand and survives only in `~/.pm2/dump.pm2`. That is the house pattern, so this does not
invent one. What it does add is `scripts/ops/atlas_global_deploy.sh`, which is the India nightly's
build block (`scripts/ops/atlas_daily.sh` §4) applied to `frontend-global`, because that block is
the only place in the repo where CLAUDE.md rule #5 is implemented in full.

```bash
export ATLAS_GLOBAL_PORT=<the free port from §0>      # no default on purpose
bash /home/ubuntu/atlas-os/scripts/ops/atlas_global_deploy.sh
```

Run it again for every subsequent deploy — it starts on the first run and reloads after.

What it does, and why each part is not optional:

- **Rule #5, in order**: back up `.next` → clear `fetch-cache` → build → **assert `.next/BUILD_ID`**
  → clear `fetch-cache` again (the build repopulates it) → **one** `pm2` action. A reload mid-build
  serves a half-written `.next` and 500s the board.
- **`ATLAS_GLOBAL_BASE_PATH=/global` is exported for the build *and* for the process.** It is a
  build-time variable (`next.config.js` bakes the prefix into the routing manifest) *and* a runtime
  one (`src/lib/basePath.ts`, for the two sign-in URLs Next does not prefix). A build with the
  prefix served by a process without it sends a freshly signed-in reader to
  `atlas.jslwealth.in/etfs` — the **India** ETF page, which renders happily. This is why the script
  exports one value for both rather than trusting pm2's stored environment.
- **`PORT` is exported, not prefixed.** `pm2 reload --update-env` re-reads the calling shell's
  environment; a reload from a shell without `PORT` would put the board back on :3000 (the
  `start` script is a bare `next start`) and nginx would proxy `/global` to nothing.
- **Fork mode, one instance. Never `pm2 start -i`.** Nothing here is prerendered; freshness is
  `unstable_cache` + `revalidateTag('eod')`, and one POST to `/api/revalidate` lands in **one**
  process. A second instance would go on serving yesterday's numbers with nothing to show for it.
- **`pm2 save` after the first start**, or the process does not survive a reboot.
- **A shared build lock** (`/tmp/atlas-next-build.lock`, `flock -w 2700`), now also taken by
  `atlas_daily.sh` and `atlas-auto-deploy.sh`. Two 3 GB Next builds on 2 vCPU is the failure that
  ends with the **live India board** down, and the global deploy is ad-hoc while the India nightly
  fires at 10:30 UTC. The script waits; it does not skip. See §1.9 — the lock is only real once
  the box's own copy of the auto-deployer has it too.
- **It refuses rather than guesses**: no `ATLAS_GLOBAL_PORT`, no `.env.local`, a missing or
  session-mode `ATLAS_GLOBAL_DB_URL`, a trailing slash on the base path — each is an exit, not a
  warning. And it ends by asserting `/global/health` answers 200 on the loopback port, because
  every one of those variables is optional to the *build*: a misconfigured board boots, serves
  200s, and is silently wrong.

Also add a watchdog line beside India's, once the port is known — `scripts/ops/crontab.txt`:

```cron
*/5 * * * *   curl -sf http://localhost:<port>/global/health -o /dev/null || (logger -t atlas-global 'global board down — restarting'; pm2 restart atlas-global)
```

`/global/health`, not `/global` — the board root redirects to `/login`, and `curl -sf` treats a
307 as success, so a watchdog on `/global` would never fire.

---

## §3 — The nginx location block

The design goal is that a typo here **cannot** reach the India board. So the new configuration
lives in its own file and the live vhost gains exactly **one** line.

**Step 1 — back up the vhost.** Not optional; it is the rollback.

```bash
sudo cp /etc/nginx/sites-enabled/atlas.jslwealth.in \
        /etc/nginx/sites-enabled/.atlas.jslwealth.in.bak.$(date +%Y%m%d_%H%M%S)
```

**Step 2 — write the snippet.** Substitute the port from §0; nothing else changes.

```nginx
# /etc/nginx/snippets/atlas-global.conf
# Global Atlas (frontend-global, pm2 atlas-global) under /global on the India vhost.
# docs/global/deploy-subpath.md. Remove by commenting the include in the vhost — nothing else.

# The board's front door, exactly. `=` beats every other location, so this can never be
# shadowed. Next answers /global/ with a 308 to /global, which is why both exist.
location = /global {
    proxy_pass http://127.0.0.1:PORT;
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
}

# Everything under it — pages, /global/_next/static, /global/_next/image, /global/api/revalidate.
# Next bakes the /global prefix into the routing manifest and into every asset URL, so the WHOLE
# sub-tree is the app's and must reach the app.
#
#   ^~   once this prefix matches, nginx checks NO regex location. That is deliberate: it is what
#        stops a regex `location ~ ^/api/` in this vhost from hijacking /global/api/revalidate to
#        the India board on :3004 and failing the nightly publish (§0).
#   proxy_pass with NO trailing slash and NO URI — the request URI is passed through UNCHANGED,
#        /global included. `proxy_pass http://127.0.0.1:PORT/;` would strip the prefix and every
#        single route would 404. This is the one line that makes or breaks the deployment.
location ^~ /global/ {
    proxy_pass http://127.0.0.1:PORT;
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
}
```

Notes on the header set: `Host` and `X-Forwarded-Host` are what `requestOrigin()` reads to build
the emailed magic link, and what Next 15 checks a Server Action's `Origin` against — the sign-in
form *is* a Server Action. `X-Forwarded-Proto $scheme` is correct only if TLS terminates at **this**
nginx; if anything sits in front of it, use that layer's value or the link goes out as `http`.
Compare against the India block you read in §0 and prefer whatever that block already proves works
on this box.

**Step 3 — one line into the vhost**, inside the `server { … }` that serves TLS for
`atlas.jslwealth.in`, above the `location / { … }` that proxies to :3004:

```nginx
    include /etc/nginx/snippets/atlas-global.conf;
```

**Step 4 — the gate. `nginx -t` decides whether you reload; it is not advice.**

```bash
sudo nginx -t || { echo "CONFIG BAD — NOT RELOADING"; exit 1; }
sudo systemctl reload nginx
```

If `nginx -t` fails, nginx keeps running the old configuration and the India board never noticed.
Fix the snippet and test again. Do **not** reload on a failed test, and do not `restart` where
`reload` is meant — reload is graceful, restart drops connections.

Longest-prefix matching means `^~ /global/` wins over the vhost's `location /`; the India board's
own routing is untouched, and `/globally`-style paths do not match either location.

---

## §4 — Verification, both boards

**Before you change anything**, capture India:

```bash
for p in / /today /etfs /stocks /health; do
  printf '%-10s ' "$p"; curl -sS -o /dev/null -w '%{http_code}\n' "https://atlas.jslwealth.in$p"
done | tee /tmp/india-before.txt
```

**After the reload**, the same loop into `/tmp/india-after.txt`, then `diff` them. **Any difference
is a rollback (§5), not a debugging session.** This is the only check that actually proves the
India board is unharmed; everything else is inference.

Then the global board. Expected values are what a correct build produces — every one of them was
observed locally against a production `next build` with `ATLAS_GLOBAL_BASE_PATH=/global`, served by
`next start`, on this commit:

```bash
B=https://atlas.jslwealth.in
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' $B/global        # 307 -> $B/global/login
curl -sS -o /dev/null -w '%{http_code}\n'                $B/global/login   # 200
curl -sS -o /dev/null -w '%{http_code}\n'                $B/global/health  # 200
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' $B/global/etfs   # 307 -> $B/global/login?next=%2Fetfs
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' $B/global/etfs/SPY  # 307 -> …?next=%2Fetfs%2FSPY
curl -sSI $B/global/health | head -1                                       # http:// → 301 to https
```

`/global/etfs` redirecting to `/global/login` (and **not** to `/login`) is the proof that the
prefix survived nginx. `/login` would be the India board's 404.

Assets — the failure that looks like a working board with no styling:

```bash
curl -sS $B/global/login | grep -o '"/[^"]*_next/[^"]*"' | sort -u | head
# every hit must start "/global/_next/…  — zero bare "/_next/…
curl -sS -o /dev/null -w '%{http_code}\n' "$B$(curl -sS $B/global/login | grep -o '/global/_next/static/[^"]*\.js' | head -1)"   # 200
```

The publish webhook — this is also the test that no regex `location ~ ^/api/` hijacked it:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST $B/global/api/revalidate \
     -H 'Authorization: Bearer wrong' -H 'Content-Type: application/json' -d '{"tag":"eod"}'   # 401
```

`401` is the route answering. A `404`, a `405`, or an India-shaped page means the request reached
:3004 instead. Then the real one, over loopback, exactly as the nightly sends it:

```bash
source /home/ubuntu/atlas-os/.env
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$GLOBAL_REVALIDATE_URL" \
     -H "Authorization: Bearer $GLOBAL_REVALIDATE_SECRET" \
     -H 'Content-Type: application/json' -d '{"tag":"eod"}'   # 200, never 308
```

**`/global/health` must show real rows**, not the "no database configured" panel. That panel means
the process did not get `ATLAS_GLOBAL_DB_URL` — which is also the fail-open state in §6. It is the
one screen that distinguishes a working board from a board that is merely answering.

**Sign-in, end to end.** Nothing above exercises it, and it is where the sub-path bugs lived:

1. `/global/login`, submit the FM's address. A Server Action failure here is the
   `serverActions.allowedOrigins` / proxy-header problem (§3).
2. In the email, **read the link before clicking**. It must contain
   `atlas.jslwealth.in/global/login/callback`. Without `/global` the Supabase redirect allow-list
   or Site URL is still pointing somewhere else (§1.3).
3. Click it. You must land on `/global`, signed in, seeing US names. Landing on Indian equities
   means a prefix was dropped — stop and roll back; that failure is silent by construction,
   because both boards serve `/etfs` and `/stocks`.
4. A non-allowlisted address must get `/global/login?reason=not-invited`.

---

## §5 — Rollback

Back to exactly today's state. **≈2 minutes**, and the first step alone (~20 seconds) is what the
public sees. Nothing below depends on a build, so it is available even when the box is unhappy.

**1. Take `/global` off the domain (~20 s).** Comment out the one line added in §3, step 3:

```bash
sudo sed -i 's|^\(\s*include /etc/nginx/snippets/atlas-global.conf;\)|#\1|' \
     /etc/nginx/sites-enabled/atlas.jslwealth.in
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` is a gate here too. If it fails, restore the backup taken in §3 step 1 and test again:

```bash
sudo cp /etc/nginx/sites-enabled/.atlas.jslwealth.in.bak.<stamp> \
        /etc/nginx/sites-enabled/atlas.jslwealth.in
sudo nginx -t && sudo systemctl reload nginx
```

`https://atlas.jslwealth.in/global` now 404s from the India board, which is exactly its
pre-change behaviour. **The India board was never reconfigured**, so there is nothing to undo on
its side — and note the converse: India's own documented rollback to `:3002` does not take
`/global` down, and this rollback does not touch India.

**2. Stop the process (~10 s).**

```bash
pm2 delete atlas-global && pm2 save        # `pm2 stop` alone leaves it in the dump
```

**3. Un-point the nightly (~10 s).** In `/home/ubuntu/atlas-os/.env`, comment out
`GLOBAL_REVALIDATE_URL`. Unset, the publish step skips itself and says so in the log
(`SKIP publish — GLOBAL_REVALIDATE_URL / GLOBAL_REVALIDATE_SECRET unset`); left pointing at a dead
port it fails every night instead.

**4. Optional, only if you are also reverting the repo.** `scripts/ops/atlas_daily.sh` and
`scripts/ops/atlas-auto-deploy.sh` gained a `flock` around their build. It is harmless on its own
— with no second builder the lock is always free — so leave it unless you are reverting the whole
change. If you do revert it, refresh `/home/ubuntu/atlas-auto-deploy.sh` from the repo copy again.

**5. Remove the watchdog cron line** if §2's was installed.

Not part of rollback: the schema, the role and the Supabase settings. They are prerequisites for
the board existing at all, not for it being served here, and dropping them destroys real data.

**If sign-in was tested before rollback**, tell the testers to clear cookies for
`atlas.jslwealth.in` once. The Supabase cookies are written at `Path=/` (§6) and outlive the
deployment — they will otherwise ride along on every India request for up to 400 days.

---

## §6 — Not yet safe to expose

An obscure Vercel URL and the firm's public prod domain are different threat models. These moved
from "acceptable" to "the FM decides", and none of them is fixed by this change.

**1. `requireUser()` fails OPEN when `ATLAS_GLOBAL_DB_URL` is missing.**
`src/lib/auth.ts:58` returns a user with `allowlist_checked: false` whenever `dbAvailable` is
false — and `dbAvailable` (`src/lib/db.ts:19`) is `Boolean(url)` evaluated **once at module load**.
It is a configuration flag, not a liveness probe. A *down* database therefore fails closed (the
query throws). What fails **open** is a *missing variable*: then anyone who completes a Supabase
magic link is a user, and `BOARD_ROLES` is never consulted.

On Vercel that was unlikely — env is injected into every invocation. On this box it is an ordinary
operator slip: a `pm2 restart` without `--update-env`, a botched `.env.local` edit, a process whose
cwd is wrong. Silent, persistent, does not self-heal. Today the blast radius is small — every page
still calls `requireUser()` first and then renders the empty "no database" shell, so a stranger
sees the nav rail and a panel naming the role and the pooler port, and zero market rows. But the
**access control** bypass is total, and `requireUser()` is the single gate every future page will
trust: the first page that reads from anything other than that variable turns line 58 into a full
bypass with no code change.

*Mitigated here:* `atlas_global_deploy.sh` refuses to deploy without the variable, and the smoke
asserts `/global/health`. *Not fixed:* the code still fails open. The one-line fix is
`if (!dbAvailable) redirect('/login?reason=unavailable')` — fail closed, which is the right posture
on a public domain. It is deliberately not in this change, because flipping an auth default is the
FM's call, not a deployment detail. **Until it lands, turning Supabase public sign-ups OFF (§1.3)
is what keeps this a shell rather than a bypass.**

**2. `/health` is public, and it renders raw Postgres error text.** `src/lib/supabase/paths.ts:7`
lists `/health` in `PUBLIC_PREFIXES` on purpose — "the operator surface must stay visible when
auth is broken" — and the page never calls `requireUser()`. On
`atlas.jslwealth.in/global/health` that publishes, to anyone who guesses the path: the box's
hostname, the deployed git sha, every nightly step and its failure history, validator scorecards,
freshness lag per table, and per-provider API call volumes. Worse, every query is wrapped in
`attempt()` and a failure is rendered verbatim by `Section.tsx`'s `QueryFailed` — so a bad night
prints strings like `password authentication failed for user "atlas_global_app"` or
`getaddrinfo ENOTFOUND aws-1-…pooler.supabase.com` into the page. Unlike a thrown Server Component
error, Next does not replace this with an opaque digest: it was caught server-side and passed as a
prop. **I rate this above item 1** — it needs no outage and no session.

Choices, in increasing cost: gate `/health` behind nginx basic-auth or an IP allow (config only,
does not touch the app); stop rendering the raw error string; or drop `/health` from
`PUBLIC_PREFIXES` and accept that it goes dark exactly when auth breaks.

**3. The auth cookies are scoped to the whole origin, and JavaScript can read them.**
`@supabase/ssr` is constructed without `cookieOptions` in all three places, so its defaults stand:
`path: '/'`, `httpOnly: false`, `sameSite: 'lax'`, `maxAge` 400 days, and **no `Secure`**. Serving
under `/global` does not change this — `basePath` is routing, it never reaches the cookie writer.

So `sb-<project-ref>-auth-token` (chunked `.0`/`.1` when large, plus a `-code-verifier` during
sign-in) is now attached to **every** India board request, including every static asset, and is
readable by `document.cookie` from any script running on any India page. Neither app sets a CSP.
The India board has 14 route handlers, several of them mutating. It sets no cookies of its own, so
nothing collides — but the exposure is real: an XSS or a stray third-party tag on the India board
lifts a 400-day refresh token for Global Atlas.

The fix is `cookieOptions: { path: '/global', secure: true }`, identical in
`src/lib/supabase/{client,server,middleware}.ts` — they must match exactly or the middleware writes
a cookie the server client cannot read. It is not in this change because it cannot be tested
without a real Supabase project, and because it needs a rollout note: browsers that signed in
beforehand keep a stale `Path=/` cookie that shadows the new one and produces sign-in behaviour
that looks like a server bug. Clear cookies for the domain once after it lands.
`SameSite=Lax` is correct as it stands and must **not** be relaxed to `None`.

**4. Anonymous traffic now costs database connections.** `layout.tsx` renders `<FreshnessStamp/>`
for every route including the public `/login` and `/health`, and it queries. The pool is `max: 5`.
Behind an obscure URL that was nothing; on a public domain it is a small, cheap denial-of-service
surface, and it sits next to a session pool India has already nearly exhausted.

**5. `robots.txt` belongs to the India board.** Global pages set `robots: noindex, nofollow` as a
meta tag, but the origin-root `robots.txt` is India's and now governs crawler behaviour for
`/global` too. Read it; a permissive one plus a public `/health` is how item 2 gets indexed.

---

## Appendix — what landed in the repo with this document

| Change | Why |
|---|---|
| `frontend-global/src/lib/basePath.ts` | One runtime read of `ATLAS_GLOBAL_BASE_PATH`, for the URLs Next does not prefix |
| `frontend-global/src/lib/supabase/paths.ts` — `magicLinkRedirect`, `postLoginPath` | **Bug fix.** The callback built `new URL(next, url.origin)`, which drops `basePath`: a signed-in reader landed on the **India** `/etfs`. Proven before the fix — `curl /global/login/callback` returned `location: …/login?error=link`; after, `…/global/login?error=link`. The emailed link had the same flaw via `emailRedirectTo`, so nobody could sign in at all |
| `frontend-global/src/lib/__tests__/paths.test.ts` | Both URLs asserted under the prefix — nothing in the suite exercised the sub-path, so this would have regressed on the next touch of the login flow |
| `frontend-global/next.config.js` — `serverActions.allowedOrigins` | The sign-in form is a Server Action; the India board carries the identical entry for this domain |
| `frontend-global/src/middleware.ts` — `'/'` added to the matcher | The catch-all's path group is mandatory, so bare `/global` never reached the gate and its session cookie was never refreshed. Confirmed in the compiled `middleware-manifest.json` and live |
| `frontend-global/.env.example` | `ATLAS_GLOBAL_BASE_PATH`, and where `GLOBAL_REVALIDATE_URL` lives now |
| `scripts/ops/atlas_global_deploy.sh` | §2 |
| `scripts/ops/atlas_daily.sh`, `scripts/ops/atlas-auto-deploy.sh` | The shared build lock (§2) |
| Pointers in `docs/deploy.md`, `docs/global/runbook.md` | So this document is findable from where people already look |

Still to write, and out of scope here: a deploy path. `deploy-frontend.yml` is filtered to
`frontend/**` and knows only the India app, so **every global deploy is a hand-run of §2** until
someone writes a sibling workflow on `frontend-global/**`. That is the state that produced the
2026-06-02 silently-broken-deploy incident recorded in that workflow's own header.

Also noticed while writing this, unrelated but in the documents an operator reads on the way here:
`CLAUDE.md` names Alpaca as the global price provider, while `runbook.md` §1 and `fm-setup.md` say
Tiingo and record it as settled. One of them is wrong; both are currently half-believed.
