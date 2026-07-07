# Disaster recovery — Atlas

The honest DR picture for Atlas, and the checklist to recover from each failure mode.
Atlas runs on **one shared EC2 box** (it also hosts other JSL apps — champion, jhaveri-pm,
clients.jslwealth.in) with the data on **managed Supabase Postgres**. There is **no
automatic failover** — this runbook turns a box loss from a panic into a ~30–60 min
checklist. Standing up real HA (a second box / managed hosting) is a separate, resourced
decision, not covered here.

## What can fail, and the blast radius

| Component | Where | Recoverable from | RPO |
|---|---|---|---|
| **Data** (`atlas_foundation`) | Supabase (managed) | Supabase backups / PITR | your tier's granularity |
| **Frontend** (pm2 `atlas-frontend-v3` :3004) | the box | git — rebuilds itself | ~0 (self-heals) |
| **Cron pipeline** (`scripts/ops/*.sh`) | the box | git + crontab | one nightly run |
| **`.env`** (all creds) | the box only | **nothing but your off-box copy** | — |

**`.env` is the single point of unrecoverable loss.** It holds the Supabase URL, Kite,
Morningstar (`MSTAR_*`), `FRED_API_KEY`, Telegram, and `GH_TOKEN` — none of which are in
git. **Keep an encrypted off-box copy** (password manager / private S3). Everything else on
the box is reproducible from git; `.env` is not.

## What already self-heals (so most incidents need no runbook)

- A crontab watchdog curls `http://localhost:3004/` every 5 min and `pm2 restart`s the
  frontend if it's down — a crashed/hung Next process recovers on its own.
- Frontend deploys are automated (GitHub `deploy-frontend.yml` on push to `main` +
  `atlas-auto-deploy.sh` polling every 5 min), with a build health-check + auto-rollback.
- The nightly orchestrator only deploys if all gates pass, so a broken/stale run keeps the
  last-good board rather than overwriting it.

So the runbook below is for the rare **full box loss / rebuild**, not day-to-day blips.

## 1. Data recovery (Supabase)

The data is on managed Supabase, so a bad write / accidental drop / table loss is recovered
from Supabase, not from the box.

1. **Verify your backup tier now, before you need it** (Supabase dashboard → Database →
   Backups): Pro = **PITR** (restore to any second); Free/other = **daily** backups, ~7-day
   retention. If Atlas is doing capital-relevant work on a free tier, upgrading to PITR is
   the cheapest real resilience win available.
2. Restore via the dashboard (PITR to a timestamp, or the latest daily). Point-in-time is
   the tool for "a bad nightly run corrupted a table" — roll back to just before it.
3. The schema is also reproducible from git: `migrations/baseline/atlas_foundation_schema.sql`
   is a verbatim dump; `uv run alembic upgrade head` rebuilds an empty DB's schema.

## 2. Box rebuild (frontend + crons on a fresh EC2)

Everything here is reproducible from git + your `.env` copy.

```bash
# 0. Prereqs on the new box: git, Node 20, uv, pm2, nginx, postgresql-client-17.
#    NOTE: the current box ships pg_dump 16 — install client 17 to match Supabase PG17:
#      sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
#      wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add - && sudo apt update && sudo apt install -y postgresql-client-17

# 1. Code
git clone git@github.com:nimishshah1989/atlas-os.git /home/ubuntu/atlas-os
cd /home/ubuntu/atlas-os
cp /path/to/your/offbox/.env .env          # the irreplaceable step

# 2. Backend deps + verify DB reachable
uv sync --extra dev
set -a; source .env; set +a
PYTHONPATH=.:scripts/foundation .venv/bin/python scripts/ops/freshness_guard.py   # confirms DB + freshness

# 3. Frontend build + serve
cd frontend && npm ci && NEXT_PUBLIC_LENS_V4=1 npm run build && cd ..
pm2 start npm --name atlas-frontend-v3 -- start   # (or restore from `pm2 resurrect` if you saved a dump)
pm2 save

# 4. Restore the crontab (see the canonical set below) and nginx site
crontab -e                                  # paste the crons from §3
sudo cp <backup>/atlas.jslwealth.in /etc/nginx/sites-available/ && sudo ln -sf ../sites-available/atlas.jslwealth.in /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx

# 5. DNS: point atlas.jslwealth.in A-record at the new box IP.
```

> **nginx `/api/` routing (self-contained board).** The board has no separate backend —
> every `/api/*` route is a Next.js route on :3004. The catch-all `location /api/` MUST
> `proxy_pass http://127.0.0.1:3004`, NOT `return 404` or proxy to the retired FastAPI
> (:8010). A `return 404` there silently kills every non-whitelisted API route (portfolio
> create, add-to-basket, instrument search, thresholds) — pages still render (SSR) so it
> looks fine, but all client-side writes 404. Only `/api/kite/` and `/api/v1/*` fan out to
> other ports; everything else is :3004.

## 3. Canonical crontab (as of 2026-07)

```
20 3 * * 1-5  .venv/bin/python scripts/kite_autologin.py        # Kite token (08:50 IST)
0 14 * * 1-5  scripts/ops/atlas_daily.sh                        # nightly pipeline (19:30 IST)
0 7  * * 6    scripts/ops/atlas_weekly.sh                       # weekly feeds (Sat)
30 4 * * 0    scripts/ops/atlas_sunday_qa.sh                    # Sunday QA
*/5 * * * *   atlas-auto-deploy.sh                              # poll-deploy from main
*/5 * * * *   curl -sf http://localhost:3004/ || pm2 restart atlas-frontend-v3   # frontend watchdog
```
(Times are UTC; prod runs IST = UTC+5:30. Full paths under `/home/ubuntu/`; logs → `/home/ubuntu/logs/`.)

## 4. Capture the box's non-git state — run this periodically

`scripts/ops/backup_box_state.sh` tars the recovery-critical state that is NOT in git
(`.env`, crontab, the nginx site, a pm2 dump) into one archive. Run it after any infra
change and **copy the archive off-box** (it contains secrets — store it encrypted).

## RTO / RPO summary + the honest gap

- **RPO** (data): whatever your Supabase backup tier gives (PITR ≈ seconds; daily ≈ 24h).
- **RTO** (box): ~30–60 min *if* you have the `.env` copy and DNS access; effectively
  unbounded if `.env` is lost.
- **The gap:** single box, no automatic failover. This runbook makes recovery fast and
  repeatable; it does not make it instant. Real HA (a warm standby or managed frontend
  hosting) is the resourced next step if Atlas's uptime needs to be better than "one
  person, one checklist, ~an hour."
