# HANDOFF — atlas-os

Current session only. ~50 lines. Evict older into `STATE.md` or a decision record.

---

## 2026-07-29 (night) — Monday confirmations built (branch, not yet merged)

The FM's weekly buy/sell Excel becomes a capability in Atlas: a **Confirmations sub-tab on
/portfolios** (no new nav section), three model books (Alpha / Passive / India XI), and a
printable per-book report.

**Design source.** The flow was reverse-engineered from **niyam** (`nimishshah1989/niyam`,
cloned read-only to scratch). Niyam models the same Monday ritual as a `recommendation_universe`
+ 8-dimension items, then fans it out to ~269 client accounts as consent envelopes. It is NOT in
production (prod DB 31 migrations behind; broker/WhatsApp/Kite are mocks) and has **no document
rendering** — which is precisely the gap Atlas fills. Vocabulary kept niyam-compatible.

**Shipped** — 3 tables in `atlas_foundation` (`mpf_confirmation` / `mpf_call` / `mpf_evidence`,
DDL in `scripts/foundation/mpf_ddl.sql`, **already applied to prod**), 5 API routes, editor +
report pages, print stylesheet. Reasoning in `docs/adr/0003-monday-confirmations-book-state.md`.

**Verified** — `make gate` exit 0 · frontend 212 unit tests · tsc clean · eslint clean ·
`npm run build` clean · **30/30 end-to-end** against the live DB with REAL instruments
(fold semantics, both-sides refusal, oversell refusal, publish freeze, image round-trip,
report render) · Playwright screenshots (pie draws, nav hidden in print, no console errors).
Probe rows dated 1999 were deleted — the three tables are empty and ready for the real seed.

**Bugs found by verification, all fixed:** both-sides returned a raw 500 (now a 409 naming the
instrument); `week_of` rendered as *04-Jan-2001* for a 1999 report (postgres returns DATE as a
Date object — `String().slice(0,10)` mangled it, now `isoDate()`); the editor's "sells free /
buys deploy" showed net figures under gross labels.

**Open before this is usable in anger**
1. **Not merged and not deployed.** Branch `feat/monday-confirmations`. Deploying needs a
   decision from the FM, not from me.
2. **The box needs `client_max_body_size 5m;` in the nginx site block** — the default 1m makes
   every chart upload 413 before Next sees it. Do this BEFORE announcing uploads work.
3. **Seed the three books.** Each book's first published report is buys-only, entered from the
   FM's real current Excel. Zero synthetic rows have been written.
4. Report branding block (logo/disclaimer) still to come from the FM's existing Monday format.

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
