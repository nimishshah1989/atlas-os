# Repo structure & the clean-repo kit

Two things: where everything lives (so you know where to go), and the portable kit that
keeps this — and any repo you start — clean by construction.

## The map — every top-level dir has one job

```
atlas/         the compute modulith (bounded contexts: compute / lenses / intraday …)
scripts/       ingestion + ops (scripts/foundation = data pulls, scripts/ops = orchestrators)
frontend/      the Next.js board (reads atlas_foundation directly)
migrations/    the single squashed schema baseline (alembic)
tests/         the test suite (tests/unit = fast/no-DB, tests/integration = live-DB)
ci/            CI helper scripts + the pyright baseline
docs/          documentation (this file, deploy, DR, ADRs, agent conventions)
systemd/       service unit files
.github/       CI + deploy workflows
```

Root files are all load-bearing: `CLAUDE.md` / `CONTEXT.md` (agent + domain context),
`README.md`, `Makefile` (dev tasks), `pyproject.toml` + `uv.lock` (Python deps),
`alembic.ini`, `decisions.jsonl` (hash-chained decision log), and the guardrail configs
(`.gitignore`, `.pre-commit-config.yaml`, `.gitleaks.toml`). Nothing else belongs at the root.

## The mental model: junk is *prevented*, not *auto-deleted*

There is no magic that deletes junk during a build. What keeps a repo clean is two layers:

1. **Prevention** — build artifacts and caches never enter git (`.gitignore`), and bad
   commits are rejected before they land (`pre-commit`). A `git clone` only ever sees the
   ~9 clean dirs above; `.venv/`, `node_modules/`, `.next/`, `.ruff_cache/`, `output/` etc.
   sit on your disk locally and are correctly excluded.
2. **On-demand sweep** — the local disk clutter is removed with one command when you want a
   tidy tree: `make clean`.

So "my folder looks messy" is almost always local disk artifacts, not the repo. Confirm with
`git ls-files | wc -l` (what's actually tracked) vs `ls` (what's on disk).

## The portable kit — drop these into every project

| Tool | What it does | Where |
|---|---|---|
| **`.gitignore`** | the front door — artifacts/caches/secrets never enter git | committed |
| **`pre-commit`** | runs on every `git commit`: auto-formats, strips whitespace, blocks big files / secrets / merge-conflict markers / bad commit msgs | `.pre-commit-config.yaml` + `pre-commit install` |
| **CI gates** | block junk from *merging* (types, tests, migrations, file-size) | `.github/workflows/` |
| **`make clean`** | one-command surgical sweep of local disk junk | `Makefile` |
| **scratch discipline** | temp/experiment files go to `/tmp`, never the repo | convention |

The `.pre-commit-config.yaml` here is the reference — its hygiene pack
(`pre-commit/pre-commit-hooks`) is self-contained and portable to any repo.

### Activating pre-commit (the one manual step)

The config exists but only runs once installed:

```bash
pipx install pre-commit            # or: uv tool install pre-commit
pre-commit install                 # activate the git hook
pre-commit install --hook-type commit-msg   # activate commitlint too
pre-commit run --all-files         # optional: sweep the whole repo once now
```

Atlas's config is safe to install as-is: the two hooks that depend on global gates
(`~/.claude/gates`) graceful-skip when absent, and CI remains the source of truth for those.
Heads-up: the `pragma-coverage` hook runs the Python test suite on Python commits — if that
friction bites, move it to `stages: [pre-push]`.

## The scratch discipline (why junk accumulates, and the one rule)

Committed junk almost never comes from the build — it comes from **scratch files written
into the repo** during coding (a `test_thing.py` to try something, a `rough.sql`, an
`output/` dump). The rule: **scratch work lives in `/tmp` (or a git-ignored `scratch/`),
never in a tracked dir.** A real test goes in `tests/`; a real script in `scripts/`;
anything you'd delete tomorrow goes to `/tmp`. `check-added-large-files` + `make clean`
catch the rest.
