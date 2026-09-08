# Global Atlas at `global.jslwealth.in` — the deployment

Serving the Global board from the prod box on **its own hostname**, beside the live India board at
`atlas.jslwealth.in`. Run top to bottom on the box.

This supersedes `deploy-subpath.md`, which put the board at `atlas.jslwealth.in/global`. Same box,
same pm2, same everything — one hostname instead of one path prefix. That single change removes
three whole classes of failure rather than guarding them:

| Sub-path had to handle | A subdomain |
|---|---|
| The Supabase session cookie riding on every India request (`Path=/`), overflowing nginx's header buffer into a bare `400` for whoever holds a Global session | **cannot happen.** Cookies are scoped by HOST. A cookie set on `global.jslwealth.in` is never sent to `atlas.jslwealth.in` |
| Editing India's live vhost, and a rollback `sed` that could no-op or replace the `sites-enabled` symlink with a regular file, disabling India's documented break-glass | **India's vhost is never opened.** The new config is its own file; rollback is `rm` the symlink and reload |
| `ATLAS_GLOBAL_BASE_PATH` needed at BUILD time *and* RUN time, identical, or a signed-in reader lands on India's `/etfs` | **unset.** The board serves at the root, which is also how CI builds it |

What a subdomain does **not** separate: **CPU, RAM and disk.** Both apps still build on 2 vCPU and
each build asks 3 GB. That is what the shared build lock and the checked `.next` backup are for
(`scripts/ops/atlas_global_deploy.sh`, `.github/workflows/deploy-frontend.yml`); they stay
load-bearing here. Full physical separation means a second VPS, and is a lift-and-shift from this
setup with no code change — the board is already running at the root.

---

## §0 — Read the box first

Two facts this document cannot know. Get them with your own eyes.

```bash
ss -ltnp | grep -E ':(300[0-9]|8[0-9]{3})'   # pick a free port for ATLAS_GLOBAL_PORT
df -h /home/ubuntu                            # a build + a backup wants a couple of GB
```

**Do not take 3002.** It looks free because that process is STOPPED — it is India's instant-rollback
target (`docs/deploy.md`). **3004 is India live.** Pick something outside that range.

```bash
dig +short atlas.jslwealth.in                 # the IP the new A record must point at
sudo certbot certificates                     # how the existing certificate is issued
ls -l /etc/nginx/sites-enabled/               # symlinks or regular files — do not change the style
```

## §1 — DNS

Add an **A record**: `global` → the IP from §0. Wait for it to resolve before §3; certbot's
HTTP-01 challenge needs the hostname to reach this box.

```bash
dig +short global.jslwealth.in                # must equal the atlas.jslwealth.in IP
```

## §2 — The board's environment

```bash
cd /home/ubuntu/atlas-os/frontend-global
cp .env.example .env.local                      # then edit
chmod 600 .env.local
```

Four values (`frontend-global/.env.example` documents each):

- `ATLAS_GLOBAL_DB_URL` — the **transaction** pooler, port **6543**, as `atlas_global_app`
  (runbook §3 creates the role). The app now **refuses to start** on `:5432`: India's session pool
  holds 14 of the cluster's 15 slots and taking the last one stops the live India board.
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` — from Supabase → Settings → API.
- `GLOBAL_REVALIDATE_SECRET` — `openssl rand -hex 32`. The same value goes in the box `.env`.

**Leave `ATLAS_GLOBAL_BASE_PATH` unset.** That is what makes this the root deployment.

⚠️ Never put `ATLAS_GLOBAL_DB_URL` in the box `.env`. The nightly does `set -a; source .env` and
hands that environment to `pm2 reload --update-env`, and `@next/env` prefers a real process
variable over `.env.local` — so a value there silently wins over the file you just wrote.

## §3 — pm2

```bash
export ATLAS_GLOBAL_PORT=<the port from §0>
bash /home/ubuntu/atlas-os/scripts/ops/atlas_global_deploy.sh
```

The script backs up `.next` (refusing to build if the backup fails), waits on `$NEXT_BUILD_LOCK`
so it can never build while India is building, asserts `.next/BUILD_ID` before it reloads pm2, and
smoke-tests `/health` on the loopback port. It is the only command you run to deploy, now and on
every future update.

## §4 — nginx, in its own file

India's vhost is **not opened**. Substitute the port; nothing else changes.

```nginx
# /etc/nginx/sites-available/global.jslwealth.in
server {
    listen 80;
    listen [::]:80;
    server_name global.jslwealth.in;
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name global.jslwealth.in;

    # certbot fills in ssl_certificate / ssl_certificate_key in §5. Until then this server
    # block will not load — run §5 before `nginx -t`.

    location / {
        proxy_pass http://127.0.0.1:PORT;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    }
}
```

`Host` and `X-Forwarded-Host` are what the app reads to build the emailed magic link, and what
Next 15 checks a Server Action's `Origin` against — the sign-in form **is** a Server Action.
`X-Forwarded-Proto $scheme` is right only if TLS terminates at *this* nginx; if anything sits in
front, use that layer's value or the magic link goes out as `http`. Copy whatever the India block
already proves works on this box.

## §5 — TLS, then enable

```bash
sudo ln -s /etc/nginx/sites-available/global.jslwealth.in /etc/nginx/sites-enabled/
sudo certbot --nginx -d global.jslwealth.in     # match §0's issuance method
sudo nginx -t || { echo "CONFIG BAD — NOT RELOADING"; exit 1; }
sudo systemctl reload nginx
```

`nginx -t` is the gate, not advice: on a failure nginx keeps running the old configuration and the
India board never noticed. Fix and re-test. `reload`, never `restart` — reload is graceful.

## §6 — Supabase Auth

1. Authentication → Providers → **Email**, magic link on.
2. URL Configuration → Site URL `https://global.jslwealth.in`; Redirect URLs add
   `https://global.jslwealth.in/login/callback`.
3. Disable public sign-ups if offered — the real allowlist is `atlas_global.app_user`.

## §7 — Verify, both boards

```bash
# The Global board
for p in /health /login /; do
  printf '%-10s ' "$p"; curl -sS -o /dev/null -m 15 -w '%{http_code}\n' "https://global.jslwealth.in$p"
done
# /health 200, /login 200, / 307 to /login

# The India board — unchanged, which is the point
curl -sS -o /dev/null -m 15 -w 'india %{http_code} %{size_download}\n' https://atlas.jslwealth.in/
```

Then sign in with a magic link and confirm it lands on `global.jslwealth.in`, not on India.

Point the nightly publish at the new origin, in the box `.env`:

```
GLOBAL_REVALIDATE_URL=http://127.0.0.1:<port>/api/revalidate
```

Loopback, so the publish cannot fail on the proxy or TLS. **No trailing slash** — Next answers
`/api/revalidate/` with a 308, the publish step does not follow redirects, and the night ends as
`FAIL: publish (http 308)`. Note there is no `/global` in the path any more.

## §8 — Rollback

```bash
sudo rm /etc/nginx/sites-enabled/global.jslwealth.in
sudo nginx -t && sudo systemctl reload nginx
pm2 stop atlas-global && pm2 save
```

`global.jslwealth.in` stops resolving to anything served; India is untouched because nothing in its
configuration was ever changed. That is the whole rollback.

## §9 — One thing that is public by design

Three prefixes answer **without a session** (`src/lib/supabase/paths.ts`): `/login` and its
callback, `/api/revalidate` — which is the orchestrator's publish webhook and carries its own
bearer secret, so a session would be the wrong guard — and `/health`.

`/health` is the ops page the nightly gates report to. It shows table names, row counts and run
timestamps; no client data, no positions, no keys. That is a decision, not an oversight. Say so if
you want it behind auth, and it moves out of that list.
