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

### Pillar 2 — CI on every PR  *(highest leverage; ~half a day)* — **landing 2026-05-31**
A GitHub Actions workflow that runs on every PR and blocks merge if red.
- Spin up a `postgres:16` service container (matches the EC2 `pg_dump` 16.x that
  produces the fixture below).
- `uv sync --extra dev`, run `ruff check` + `ruff format --check` + pyright
  ratchet + `pytest tests/unit -m unit` + the pragma finance-critical gate.
- **Apply every migration to the fresh DB** (`alembic upgrade head`) — proves
  migrations work before they ever touch prod. (This alone would have caught the
  30-min refresh and the breadth bugs pre-merge.)
- Turn on **branch protection**: can't merge to `main` while CI is red.
- **Unblocks:** broken code becomes impossible to ship; the coverage hook runs in
  a real environment, so no more `--no-verify`.

**Decisions made while building Pillar 2 (2026-05-31):**

1. **Type checker = pyright only.** The tree had a two-checker split — `make
   typecheck` + `[tool.pyright]` + global CLAUDE.md used pyright, while
   `.pre-commit-config.yaml` used mypy (never in the dev extra, different
   config). mypy removed; pyright is the single standard, enforced by `make
   check` locally and the CI ratchet.
2. **Type debt = baseline + ratchet, not fix-all.** pyright surfaced 693
   pre-existing errors across 113 files (never gated). Fixing all at once is a
   huge, risky diff — many are Decimal/float money coercions where a careless
   cast changes a calculation. Instead `ci/pyright-baseline.json` grandfathers
   the debt and `scripts/ci/pyright_ratchet.py` fails CI only if a file's error
   count *rises* (new/changed files must be clean). Burn the baseline down in
   later focused PRs via `--update`.
3. **External `de_*` tables in CI = captured schema-only dump.** Migrations read
   12 `de_*` tables owned by the DE pipeline but never created by atlas
   migrations, so `alembic upgrade head` on a fresh DB needs their schema first.
   We commit a one-time `pg_dump --schema-only -t 'public.de_*'`, **slimmed to
   parent tables only** by `ci/fixtures/slim_de_dump.py` (the raw prod dump
   carried 66 partition children, RLS policies, FK constraints and sequences —
   most of which would *fail* on a clean DB), giving
   `ci/fixtures/external_de_tables.sql` (25 empty parent tables). Chosen over a
   hand-written stub (would need column-correctness by hand) or a
   create-if-not-exists migration (would make atlas "own" tables it doesn't).
   Real schema, no live-prod access in CI, regenerate only when the DE pipeline
   changes. Prod is PG 17.6, so the CI service + the dump client are both PG 17.

4. **Migration-apply gate is reporting-only (non-blocking) for now.** With the
   `de_*` fixture in place, `alembic upgrade head` on a fresh DB immediately
   surfaced pre-existing migration-chain debt: migration **064** builds
   `idx_tv_signal_dedup` on `date_trunc('hour', triggered_at)` where
   `triggered_at` is `timestamptz` — that expression is only STABLE, never
   IMMUTABLE, so it cannot apply to a clean Postgres. Prod has the table (it's
   at head 122), so the committed chain has **drifted** from what actually ran
   on prod. 106/120 migrations use raw `op.execute` SQL, so the cascade is of
   unknown depth. Decision: mirror the pyright-debt approach — keep the job
   running (it seeds the fixture and reports how far the chain gets) but
   `continue-on-error: true` so it does not block merge, and burn the chain down
   to green in a dedicated follow-up before flipping it to a required check.
   Known immutable fix for 064 when we get there:
   `date_trunc('hour', triggered_at, 'UTC')` (verified on PG 17).

**Sequencing decision (2026-05-31): defer the cleanup, not the gate.** Both the
693 pyright errors and the migration-chain replayability are deferred to a
single **end-of-project hardening pass** (after the v6 M- and F-phases ship),
done as one careful, focused exercise. Rationale: neither blocks building
product — the pyright ratchet guarantees the type debt can't *grow* while we
build (new/changed code must be clean), and new migrations are tested on EC2 by
hand as they are today. The ratchet is precisely what makes deferral safe. The
hardening pass will: drive pyright to ~0, make `alembic upgrade head` replay
cleanly on a fresh DB, and flip the migration-apply job to a required check.

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
