# STATE — atlas-os

Pointers only. Each line names **how it was verified**, not what someone claimed.
Reasoning lives in `CLAUDE.md`, `docs/`, and `docs/adr/`.

Verified 2026-07-29 on `main` @ `3aefd9c0` (2026-07-28) from `~/All AI/atlas-os`.

---

## Green — ran it, saw it

| What | Command | Result |
|---|---|---|
| **Pre-PR gate** | **`make gate`** | **exit 0 in ~7s** — lint + tests + ratchet |
| Unit tests | `make test` | **49 passed**, 11 deselected, 11s |
| Lint | `make lint` (ruff) | **All checks passed** |
| Type gate | `python scripts/ci/pyright_ratchet.py` | **OK** — 848 errors, 848 baselined, no per-file regression |
| Local env build | `make setup` via `uv` | 105 packages, venv from scratch in <1s |

**`make typecheck` fails raw, and that is by design.** It reports 107 errors in `atlas/`
(848 tree-wide). The gate is the *ratchet*, not the raw count: `ci/pyright-baseline.json`
grandfathers pre-existing debt and CI fails only when a file's count *rises*. Down from 693
at the 2026-05-31 baseline. Never "fix" this by editing the baseline — burn it down in
focused PRs with `--update`.

## Not verified here — do not assume

- **Frontend build** — not run locally this session.
- **Integration tests** — need the direct non-pooler `ATLAS_DB_URL`; run on the box.
- **What SHA is live** — nothing local can tell you. `ssh` the box and
  `git -C /home/ubuntu/atlas-os rev-parse HEAD`.

## Shape (as of this commit)

- **364 source files.** `atlas/` contexts: `compute`, `desk`, `intraday`, `lenses`, `portfolio`.
- **One schema, `atlas_foundation`.** Migrations squashed to a single baseline
  (`0001_baseline_atlas_foundation.py`); prod DDL managed directly, not by alembic.
- **No FastAPI backend.** The Next.js board reads `atlas_foundation` directly.
  (Any doc claiming a FastAPI layer, `atlas.*` schema, or alembic 001→124 is pre-July and wrong.)
- **Orchestrators** in `scripts/ops/`: `atlas_daily.sh` (19:30 IST), `atlas_intraday.sh`,
  `atlas_weekly.sh`, `atlas_sunday_qa.sh`.
- **13 branches on origin.**

## Deploy — closed loop for the frontend, open for everything else

`frontend/**` merged to `main` → GitHub Actions clones, builds, `pm2 reload atlas-frontend-v3`,
health-checks, and **auto-rolls back** on a non-200. Separately `scripts/ops/atlas-auto-deploy.sh`
fast-forwards the box from `main` on its own.

**Backend and cron code have no CI deploy.** Pushing `atlas/` or `scripts/` to `main` does not
change what runs nightly until the box fast-forwards. Closing that is open work.

**Auto-deploy skips silently when the box's tree is dirty** (`tree dirty on $branch — skip`,
written only to `/home/ubuntu/logs/auto-deploy.log`). One stray edit on the box stops every
future deploy with no visible error. This is the mechanical reason development happens on the
laptop — see `CLAUDE.md` § Where development happens.

## Standing risks

- Box is simultaneously prod and a git checkout. Never `pm2 reload` mid-build — it corrupts
  `.next` and 500s the board (`docs/deploy-hygiene.md`).
- ~200 PMS clients downstream. Treat the DB as production; no casual write paths.
- No eval set for any model-generated output, against the global standard.
