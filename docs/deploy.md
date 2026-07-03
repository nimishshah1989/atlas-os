# Atlas v4 — deploy & CI/CD

The single source of truth is **`main`**. Everything ships through one path; there are
no manual builds on the box once set up.

## The flow

```
feature branch ──PR──► CI ("Lint, types, unit tests") ──merge──► main ──auto-deploy──► live
```

1. **Branch + PR.** Work on a branch, open a PR into `main`.
2. **CI gate.** `main` is a protected branch: the **"Lint, types, unit tests"** GitHub
   check must pass before merge. This is the quality gate — nothing reaches `main` red.
3. **Merge to main.**
4. **Auto-deploy.** The EC2 box runs `~/atlas-auto-deploy.sh` via cron (every 5 min). On a
   new `main` commit it fast-forwards, rebuilds the board (`NEXT_PUBLIC_LENS_V4=1` + clears
   the Next fetch-cache), and reloads the live pm2 process `atlas-frontend-v3`. Logs:
   `~/logs/auto-deploy.log`.

So: **merge to main → live updates within ~5 minutes, automatically.**

## The live process

- **`atlas-frontend-v3`** (pm2, fork mode, port **3004**) — the live board, served from the
  `/home/ubuntu/atlas-os/frontend` working tree (which tracks `main`). nginx →
  `atlas.jslwealth.in` → `127.0.0.1:3004`.
- Rollback (instant): point nginx back to the previous prod on `:3002`
  (`atlas-frontend-v2`): `sudo sed -i 's|3004|3002|g' /etc/nginx/sites-enabled/atlas.jslwealth.in && sudo nginx -t && sudo systemctl reload nginx`.

## atlas-auto-deploy.sh — safety properties

- **Branch-guarded:** only deploys when the tree is on `main`. On any other branch it
  no-ops (this is why it's safe even mid-migration).
- **Dirty-guarded:** never pulls onto uncommitted work.
- **Fast-forward only:** never creates merge commits/conflicts on the box; if history
  diverged it logs an error and stops for a human.
- **Single-flight lock**, `.next` backup + **auto-rollback** on build failure, and
  `npm ci` only when the lockfile changed.

## First-time setup (one time only)

The box may be tracking a release branch when `main` is first adopted. After the PR merges,
run once on the box:

```bash
bash /home/ubuntu/atlas-os/scripts/ops/promote_box_to_main.sh
```

It switches the tree to `main`, does one clean build + reload, and from then on the cron
keeps `main` live automatically.

## Notes

- The retired `atlas-frontend` (pm2 id 2, stopped) and old prod `atlas-frontend-v2` (:3002,
  rollback) are intentionally left alone.
- Backend/nightly compute deploys are separate from the frontend auto-deploy (they run from
  the same tree but are driven by their own cron — see `run_atlas_nightly.sh`).
