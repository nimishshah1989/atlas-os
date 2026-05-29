# Atlas Deploy Hygiene Guide

**Date:** 2026-05-30
**Trigger:** The feat/tv-integration deploy (a) had a duplicate alembic
revision in main for 6+ commits, (b) had 16 unapplied migrations on prod
masked by a stale `public.alembic_version` table, (c) shipped against a
dependency API that no longer exists, and (d) emitted Python `str(dict)`
into a JSONB column. Each is fixable individually; together they cost
several hours of unplanned debugging during deploy. This doc captures the
rules that would have prevented every one of them.

This guide is mandatory reading for anyone landing migrations, frontend
work, or dependencies on `main`. Cross-link it from `CLAUDE.md` next time
the file gets touched.

---

## Rule 1 — Migrations are the source of truth for schema. No MCP-applied DDL.

**The pattern that bit us:** Migration files 098, 105-109 had no-op
`upgrade()` bodies (or `IF NOT EXISTS` guards). The actual MV/table
creation happened via the Supabase MCP `execute_sql` tool out-of-band,
sometimes before the migration file was written. Over a month this
created drift between:

- The **migration file** (what the repo says the schema looks like)
- The **production schema** (what Supabase actually has)
- The **alembic_version table** (what alembic *thinks* has run)

By the time we tried to land 117-119, three different views of the world
disagreed. View 115 was created out-of-band with one column set; the
migration tried `CREATE OR REPLACE VIEW` with a different shape; Postgres
rejected it.

**The rule:** every schema change to atlas.* lands as an alembic migration
that *actually does the work*. `op.execute("SELECT 1 AS marker")` no-op
tombstones are banned for new migrations. If you must apply a DDL change
via MCP in the moment (rare, e.g. unblocking a live page during an
incident), within the same session:

1. Write the migration file with the canonical DDL
2. Run `alembic stamp <rev>` to record it
3. Open a PR that ships the file

**Enforcement:** pre-commit hook to reject migration files whose
`upgrade()` body is structurally identical to `op.execute("SELECT 1 ...")`
unless the file name contains `_tombstone` AND has a docstring with the
literal text "RECONCILIATION" or "TOMBSTONE".

---

## Rule 2 — One revision ID per migration file. Renumber before commit.

**The pattern:** `097_v6_frontend_column_adds.py` and
`097_v6_mv_stock_list.py` both declared `revision = "097"`. Alembic logged
"Revision 097 is present more than once" and walked one of them. Which
one? Nobody could tell from the file tree. Production ended up with
artifacts from both (one via alembic, one via MCP).

**The rule:** before committing a migration, run `alembic heads` locally.
If it warns about a duplicate, renumber by:

1. Find the actual current head: `alembic history --indicate-current | tail`
2. Rename your file to `<next_int>_<slug>.py`
3. Update `revision = "<next_int>"` and `down_revision = "<prev_head>"` inside the file

**Enforcement:** pre-commit hook that runs
`alembic check` (or just `alembic heads | wc -l`) and rejects if more than
one head is present or any duplicate-revision warning is emitted.

---

## Rule 3 — Always know what production thinks it is. Single source of truth for `alembic_version`.

**The pattern:** Two `alembic_version`-shaped tables existed:

- `public.alembic_version` — populated by some unknown actor, said "112"
- `atlas.atlas_alembic_version` — what `env.py` actually uses, said "104"

Earlier in the session I asked Supabase MCP `SELECT version_num FROM
alembic_version` and got "112" — but that was the wrong table. The real
production state was 8 migrations further behind.

**The rule:** there is exactly one alembic version table for this project,
and it lives at the path `env.py` configures. Don't query `alembic_version`
without qualifying the schema. The right query is:

```sql
SELECT version_num FROM atlas.atlas_alembic_version;
```

**Enforcement:** drop the stray `public.alembic_version` table in a
follow-up migration. Add a sanity-check job to the nightly cron that runs:

```sql
SELECT 'OK' FROM atlas.atlas_alembic_version
UNION ALL
SELECT 'STRAY: ' || table_schema || '.' || table_name
  FROM information_schema.tables
 WHERE table_name = 'alembic_version'
   AND table_schema <> 'atlas';
```

…and pages on any STRAY row.

---

## Rule 4 — `CREATE OR REPLACE VIEW` cannot drop or rename columns. Use DROP-then-CREATE.

**The pattern:** migrations 115 and 116 both used `CREATE OR REPLACE VIEW`
to redefine `atlas.mv_stock_landscape_trader`. The new column set was a
subset of the existing one (or renamed columns), and Postgres rejected
the replace. This blocked the deploy until each migration was patched.

**The rule:** when a view migration changes the column SET (drops, renames,
or adds NOT NULL columns in a way that requires REPLACE-style atomicity to
break), use:

```python
op.execute("DROP VIEW IF EXISTS atlas.<view> CASCADE")
op.execute(_CREATE_VIEW)
```

For views with downstream dependencies (other views, MVs, rules), use a
single transaction:

```python
with op.get_context().connection.begin():
    op.execute("DROP VIEW ... CASCADE")
    op.execute(_CREATE_DEPENDENTS_FIRST)
    op.execute(_CREATE_VIEW)
```

`CASCADE` drops dependents, the transaction recreates them. If anything
fails, the rollback restores the prior view shape exactly.

**Enforcement:** none yet. Adding a check is hard because `CREATE OR
REPLACE VIEW` is sometimes legitimately the right call (when only the
SELECT body changes, not the column shape). Best we can do is reviewer
discipline + a CI step that applies the migration against a fresh DB and
fails if it errors.

---

## Rule 5 — Pin third-party APIs that have a habit of breaking. Test against the pin.

**The pattern:** `pyproject.toml` had `tradingview-screener>=0.14.0` (no
upper bound). v3.x dropped the `Scanner.get_scanner_data` static method
that atlas/tv/screener.py imports. Tests mocked the whole module so they
passed. Production blew up the moment we ran the screener.

**The rule:**

- For dependencies that move fast and break compatibility (TV, OpenAI SDK,
  Anthropic SDK, langchain, etc.) — pin upper bound: `>=X.Y,<NEXT_MAJOR`.
- For dependencies that follow strict semver — `>=X.Y` is fine.
- At least one test per third-party integration MUST hit the real API in
  a marked-as-slow / opt-in test (`pytest -m external`), exercised in CI
  weekly. If it ever fails, you find out before users do.

**Enforcement:**

- Pre-commit hook on `pyproject.toml`: reject any external dep without an
  upper bound unless explicitly listed as `# allow-unbounded` with a
  one-line reason.
- CI job that runs `pytest -m external` on Saturdays + alerts if any fail.

---

## Rule 6 — JSONB columns get `json.dumps(...)`. Never `str(dict)`.

**The pattern:** `atlas/tv/screener.py` wrote `"raw_payload": str(rec)`
which emits Python repr (single quotes, NaN, datetime literals).
Postgres' JSONB parser is strict — it rejected everything.

**The rule:** any value bound to a `jsonb` column goes through
`json.dumps()`. NaN/inf get coerced to `null`. Datetime objects use
`isoformat()`. Decimal/UUID stringify.

A helper exists at `atlas.tv.screener._json_dumps`. Steal it into a
shared `atlas.primitives.jsonb` module the next time another writer
needs it.

**Enforcement:** ruff rule (custom) that flags `str(...)` whose result is
passed to a bind param that the SQL casts to `jsonb`. Hard to write
perfectly; reviewer discipline backstops.

---

## Rule 7 — SQLAlchemy `text()` cannot have `:name::cast`. Use `CAST(:name AS type)`.

**The pattern:** `tournament.py` had
`INSERT ... VALUES (:rank, :genome_id::uuid, ...)`. SQLAlchemy's
bind-param tokenizer saw `:genome_id` followed by `::uuid` and the
dialect compiler punted the `::` to the wire. Postgres choked on the bare
`:` character.

**The rule:** any time you need a PostgreSQL cast in a `text()` query,
use the SQL-standard `CAST(<expr> AS <type>)` form, not the `::` shorthand:

```python
# BAD
text("INSERT ... VALUES (:genome_id::uuid, ...)")
# GOOD
text("INSERT ... VALUES (CAST(:genome_id AS uuid), ...)")
```

`::cast` on column references is safe (`SELECT instrument_id::text` etc)
— only `::cast` directly adjacent to a bind param breaks.

**Enforcement:** ruff plugin or pre-commit grep:

```bash
grep -rn ':[a-z_][a-z_0-9]*::' atlas/ --include='*.py' | grep 'text('
```

…and reject any non-empty match.

---

## Rule 8 — Branches that touch shared files (decisions.jsonl, *.spec.html) need rebase before merge.

**The pattern:** feat/tv-integration was branched off main 8 days before
its merge. Main accumulated 50+ commits in the interim; the branch
accumulated 40+. Both touched `decisions.jsonl` (Ruflo hash chain) and
the TV integration spec. The merge required manual conflict resolution
in the page.tsx + careful chain reconciliation in `decisions.jsonl`.

**The rule:** for any branch that touches `decisions.jsonl`, ADRs, CEO
plans, or any "append-only" file:

1. Rebase on main at least once per day
2. Before merge, rebase on main one more time
3. Verify the SHA-256 chain of decisions.jsonl is intact after rebase
   (`python -m atlas.tools.verify_chain decisions.jsonl`)

**Enforcement:** GitHub branch protection rule — require branch to be up
to date with main before merge. Plus pre-merge CI step that runs the
chain verify against `decisions.jsonl`.

---

## Rule 9 — pg_dump version must match the server. Use Docker if locals lag.

**The pattern:** EC2's Postgres client was v16. Supabase server is v17.
`pg_dump` aborts on version mismatch by default.

**The rule:** before any deploy:

```bash
docker run --rm postgres:17-alpine pg_dump "$PGURL" --schema=atlas --no-owner --no-acl | gzip > "$BACKUP"
```

Use a Docker image whose major version matches the server. Don't fight
your distro's apt to stay current — the image is 100MB and starts in 2s.

**Enforcement:** bake the pg_dump-via-docker step into a `make backup`
target in the repo root. Make it a hard precondition of `make deploy`.

---

## Rule 10 — Code review covers more than the diff. Run the build, run the screener, hit the page.

**The pattern:** the feat/tv-integration code review marked APPROVE_WITH_FIXES.
The fixes were applied. But the reviewer never:

- Ran `pip install -e .` against the locked pyproject — would have caught
  Rule 5 (Scanner removal).
- Ran `python -c "from atlas.tv.screener import fetch_and_upsert_all; fetch_and_upsert_all()"`
  — would have caught Rule 6 (JSON bug).
- Hit `/stocks/RELIANCE` in a browser — would have caught Rule 5+6 both.

**The rule:** for any branch touching a third-party data path or a new
schema column:

- Reviewer runs the full screener (not just the unit tests)
- Reviewer hits the user-facing page in a real browser, observes the data

The summary doc from the review session said "the user-visible pages
render with stubbed mockup data" — this is exactly the smell. If you're
shipping a data-path change but reviewing against stubs, you're not
actually reviewing the change.

**Enforcement:** CI job that runs the screener against a sandbox TV API
and asserts at least 1 row is upserted. Reviewer checklist (in PR
template) with explicit "ran the data path end-to-end against staging"
checkbox.

---

## Rule 11 — Decisions.jsonl is the audit log. Never commit it via bypass-the-hook.

**The pattern:** during this session the pre-commit hook stashed
`decisions.jsonl` repeatedly to let other files commit. Each stash-unstash
cycle was a risk to the hash chain. We were lucky none of them clobbered
state.

**The rule:** if `decisions.jsonl` has unstaged changes when you want to
commit, ALWAYS stage and commit `decisions.jsonl` FIRST as its own
commit. Never let the pre-commit hook stash it.

The hook is doing its job; it's signaling that this file is sacred.
Honor it.

**Enforcement:** the existing pre-commit hook already does SHA-256 chain
integrity check on `decisions.jsonl`. Augment it: if `decisions.jsonl` is
modified but not staged, FAIL with a message "stage and commit
decisions.jsonl as its own commit before staging other files".

---

## What "commercially scalable" means in code terms

Atlas can't move to product if any of these patterns recur:

- **Schema drift between repo and prod.** Investors and B2B customers
  audit our migration history. A clean linear chain is table stakes.
- **Silent third-party breakage.** Production going down because an
  upstream dropped a method is a "do you have anyone watching this?"
  question we don't want to answer.
- **Manual deploy steps that the runbook didn't warn you about.** Every
  deploy that needs an in-flight code fix is a deploy that can't be
  done by someone other than the original author.
- **Test suites that pass while the feature is broken.** Mocked tests are
  signal, not proof.

The fix in every case is the same: codify the rule into a hook or a CI
step. The cost is small (one afternoon per rule). The savings compound:
a rule that catches a bug in pre-commit saves a session-length debug
later.

---

## Action items for next session

1. Add the pre-commit hooks listed under "Enforcement" above (Rules 2, 5, 6, 7).
2. Drop the stray `public.alembic_version` table via a new migration.
3. Cut the existing tombstone migrations (098, 120) into a `RECONCILIATION`
   marker pattern with a docstring template the new hook will accept.
4. Backfill the prevention checklist into `.github/PULL_REQUEST_TEMPLATE.md`.
5. Add `make backup` and `make deploy` targets that codify the dump +
   apply sequence so it's runnable by anyone.

— end —
