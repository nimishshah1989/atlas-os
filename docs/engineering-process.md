# Atlas Engineering Process — target workflow & adoption plan

**Status:** plan (2026-05-31). Owner: Nimish. Companion to
`docs/v6/2026-05-30-deploy-hygiene-guide.md` (which lists the *rules*; this lists
the *machinery* that enforces them automatically).

## Why this exists

Today atlas-os ships by hand: code is written, `rsync`'d to EC2 from a branch,
migrations are run manually against the **live** Supabase DB, and the local Mac
can't run the test/lint toolchain at all. That workflow caused, in one session:
a 30-min lock + outage on the live page, a wrong-directory `rsync` that ran stale
code on prod, and a pre-commit hook bypass because it can't execute locally.

None of that is a skill problem. It's missing infrastructure. This plan installs
the four things every professional team has, in the order that gives value
fastest.

## The target loop (what "good" looks like)

```
branch  →  code + tests  →  open PR  →  CI runs automatically (tests + migrations on a fresh DB)
   →  review (AI + self-checklist)  →  merge to main  →  auto-deploy to STAGING  →  verify
   →  promote to PRODUCTION
```

Rule that anchors everything: **`main` is always deployable and always equals
production. Deploys come from `main`, never from a branch by hand.**

## Current state (honest baseline)

| Capability | Today | Gap |
|---|---|---|
| Local dev env | ❌ `uv`/venv won't resolve (`pandas-ta` pins py≥3.12 via `crawler` extra); psycopg2 stalls on Supabase pooler | Can't run alembic / pytest / pre-commit hooks locally |
| Automated tests on PR (CI) | ❌ none | Broken code can merge; coverage hook only runs ad hoc |
| Migration safety | ⚠️ run by hand on prod | No proof a migration applies cleanly before prod |
| Deploy | ⚠️ manual `rsync` + ssh + detached alembic + manual MV refresh | Error-prone, not repeatable by anyone else |
| Staging | ❌ none | Migrations/backfills tested on the live DB |
| Code review | ⚠️ ad hoc | OK for solo if AI-review + checklist is consistent |
| Migrations = source of truth | ✅ rule exists (alembic) | Keep it |
| Pre-commit hooks | ✅ exist | Can't run on the Mac → bypassed |

## The four pillars (adoption order)

### Pillar 1 — Working local dev environment  *(do first; ~1 afternoon)*
Nothing else is pleasant until `pytest`, `ruff`, `pyright`, and `alembic` run on
your Mac in seconds.
- Set `requires-python = ">=3.12"` **or** move `pandas-ta` out of the default
  install into the `crawler` extra so the core dev env resolves.
- Add a `make dev-setup` that creates `.venv` and `pip install -e ".[dev]"`.
- Use a **direct** Postgres connection (port 5432) for local, not the pooler, so
  psycopg2 doesn't stall. Keep the EC2 path for heavy backfills.
- **Unblocks:** running the full pre-commit suite + tests locally; far fewer SSH
  round-trips.

### Pillar 2 — CI on every PR  *(highest leverage; ~half a day)*
A GitHub Actions workflow that runs on every PR and blocks merge if red.
- Spin up a `postgres:17` service container.
- `pip install -e ".[dev]"`, run `ruff` + `pyright` + `pytest`.
- **Apply every migration to the fresh DB** (`alembic upgrade head`) — proves
  migrations work before they ever touch prod. (This alone would have caught the
  30-min refresh and the breadth bugs pre-merge.)
- Turn on **branch protection**: can't merge to `main` while CI is red.
- **Unblocks:** broken code becomes impossible to ship; the coverage hook runs in
  a real environment, so no more `--no-verify`.

### Pillar 3 — One-command deploy from `main`  *(~half a day)*
Replace hand `rsync`/ssh with a single, idempotent path.
- `make deploy` (or a GitHub Action that fires on merge to `main`) that runs the
  canonical sequence: sync code → `alembic upgrade head` → backfills → MV refresh
  → `pm2 restart atlas-frontend`, in order, with `statement_timeout=0`.
- Deploy **only from `main`**. Never `rsync` a branch to prod again.
- Add `make backup` (the Docker `pg_dump` from the deploy-hygiene guide) as a
  hard precondition.
- **Unblocks:** repeatable deploys; the wrong-directory `rsync` class of error
  disappears.

### Pillar 4 — Staging database  *(highest safety; ~1 day)*
A full pre-prod copy to test against.
- Use a **Supabase branch/preview** (or a second project) as staging.
- CI/CD applies migrations + backfills to staging first; you watch refresh time
  and the page there before prod.
- **Unblocks:** the live outage class of problem — you'd see "30-min refresh" on
  staging and fix it before users.

## Solo-adapted practices (you don't have a team)

- **Code review** = AI reviewers on the PR (`/review`, CodeRabbit) + a short
  self-checklist. That's a legitimate substitute for a second human.
- **Trunk-based**: short-lived branches, merge to `main` daily-ish, never let a
  branch live 8 days (that caused the earlier `decisions.jsonl` conflict mess).
- Keep the existing **Four Laws** and **deploy-hygiene rules** — CI/CD enforces
  them instead of relying on discipline.

## Sequencing & milestones

1. **Pillar 1** (local env) → you can run checks locally. *Immediate.*
2. **Pillar 2** (CI) → broken code can't merge. *This week.*
3. **Pillar 3** (one-command deploy) → no hand deploys. *This week.*
4. **Pillar 4** (staging) → no testing on prod. *When the above are stable.*

Each step is independently useful; you don't do all four at once.

## Immediate follow-ups (carried from the Phase 1 session)

- **Backfill process exit-hang** — `scripts/backfill_breadth_ema_4wh.py` finishes
  its work but the process doesn't terminate (engine pool not disposed). Add
  `get_engine().dispose()` / clean exit before wiring it into the nightly cron.
- **Stray `public.alembic_version`** table — drop in a follow-up migration
  (deploy-hygiene Rule 3).

---
*Living document. Update as pillars land.*
