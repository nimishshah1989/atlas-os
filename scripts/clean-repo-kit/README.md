# Clean-repo kit — make cleanliness the default *everywhere*, once

The problem this solves: setting up `.gitignore` / pre-commit / `make clean` **per repo**
means it's forgotten on the next project. This moves the setup **up to the machine level**,
so every repo you create or clone is clean by default — you never wire it up again.

There are exactly two layers, both native to git:

## Layer 1 — machine setup (run ONCE per computer)

```bash
bash setup-machine.sh
```

Sets two global git configs that apply to **every repo on the machine**:
- **`core.excludesfile` → `~/.gitignore_global`** — universal junk (`.DS_Store`, `__pycache__/`,
  `.venv/`, `node_modules/`, `.next/`, caches, `.env`, logs) is ignored in *every* repo with
  **zero per-repo `.gitignore` entries**. This alone kills ~90% of the clutter you were seeing.
- **`init.templateDir` + `pre-commit init-templatedir`** — every `git init`/`git clone` from now
  on **auto-installs the pre-commit hook** (it activates whenever the repo has a
  `.pre-commit-config.yaml`).

Prereq: `pipx install pre-commit` (or `brew install pre-commit`). Idempotent — safe to re-run.
For repos you *already* cloned, run `pre-commit install` once inside each.

## Layer 2 — new projects (per project, one command)

```bash
bash new-project.sh my-app
```

Scaffolds a fresh repo that's clean by construction: `git init` + a portable
`.pre-commit-config.yaml` (the self-contained hygiene pack + gitleaks secret-scan) + a
`.gitignore` + a `make clean` target + `README.md`, then activates hooks and makes the first
commit. (Layer 1's global ignore already covers the junk; this adds the per-repo guardrails +
structure.)

## The result

| | Before | After |
|---|---|---|
| New repo ignores `.DS_Store`/caches/`node_modules` | you add it, every time | automatic, global |
| pre-commit runs on commit | you remember to `pre-commit install` | auto-installed on clone/init |
| junk-sweep command | none | `make clean` in every scaffold |
| secrets blocked from commits | no | gitleaks, in every scaffold |

## Portability

This kit is machine-level tooling, not Atlas-specific — it lives here because this is where it
was built. For long-term reuse, copy `clean-repo-kit/` into your **dotfiles repo** (or its own
repo) and run `setup-machine.sh` on each computer you code on. The one durable rule it can't
enforce for you: **scratch/experiment files go to `/tmp`, never a tracked dir** — that's the
single biggest source of committed junk.
