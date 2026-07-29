# HANDOFF — atlas-os

Current session only. ~50 lines. Evict older into `STATE.md` or a decision record.

---

## 2026-07-29 — laptop resynced; development moves off the box

Not a feature session. The local clone had drifted badly and was being mistaken for the project.

**What was wrong**

The laptop copy sat on `fix/fund-scores-cell-routes-tv-chart` — a branch deleted from origin —
**315 commits behind `main`**, last local commit 2026-06-02 against a remote HEAD of 2026-07-28.
Anything measured against it described a system that no longer exists: it still assumed a
FastAPI backend, the `atlas.*` schema, and alembic 001→124. Current reality is no FastAPI, one
`atlas_foundation` schema, and a single squashed migration baseline.

That stale tree produced two wrong reports elsewhere ("1 commit in 7 days" — real answer 12;
"5/100, worst repo") which were passed upstream as fact. `~/.claude/bin/doctor` now fails any
repo more than 20 commits behind its origin default branch.

**What was done**

- Archived everything local-only to `~/All AI/_archive/atlas-os-local-only-2026-07-29/`:
  the pre-July `STATE/HANDOFF/SPEC/DECISIONS` docs, both CLAUDE.md versions,
  `frontend/.env.local`, uncommitted diffs, and a verified bundle of the 2 unpushed commits.
- `git checkout main && git reset --hard origin/main`. Chose reset over delete-and-clone so
  `frontend/.env.local` survived and the folder path stayed stable — Claude memory is keyed to
  the path and this repo has already lost its memory to moves twice.
- Root `.env` created from `frontend/.env.local` (`ATLAS_DB_URL`); gitignored, confirmed.
- Rewrote `STATE.md` and `HANDOFF.md` from commands actually run, not from the old docs.
- `CLAUDE.md`: canonical path corrected `~/dev/atlas-os` → `~/All AI/atlas-os`, and a
  *Where development happens* section added.

**The pre-July docs were deliberately NOT restored.** They describe the old architecture;
pushing them would inject obsolete facts into a current repo. They stay in the archive as history.

**Verified state**

```
make test                          49 passed, 11 deselected
make lint                          All checks passed
scripts/ci/pyright_ratchet.py      OK — 848/848 baselined
make typecheck                     fails raw (107 in atlas/) — expected, ratchet is the gate
```

**Next**

1. Confirm what SHA is live: `ssh` the box, `git -C /home/ubuntu/atlas-os rev-parse HEAD`,
   `git status`, `git stash list`. Nothing local can answer this.
2. Give backend/cron code the CI deploy the frontend already has.
3. Eval sets for model-generated output — still absent, against the global standard.
