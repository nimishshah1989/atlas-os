# AUTONOMOUS BUILD — GUARDRAILS (obey absolutely; non-negotiable)

Every loop reads this first and obeys it without exception. If a rule here conflicts
with anything else, this file wins.

## 0. ⛔ NO SYNTHETIC / DERIVED DATA — ZERO TOLERANCE (CLAUDE.md rule #0)
NEVER use synthetic, mocked, fabricated, placeholder, stubbed, or made-up data anywhere —
including unit tests. Every number traces to a REAL source (DB / real feed / real instrument).
**Tests must run against REAL records pulled from the data layer, not invented inputs** —
rewrite any synthetic-fixture test to use real data. No stub/neutral score may stand in for
a real computation. The definition-of-done is the REAL-data gate
(`scripts/foundation/validate_lenses.py --check {A|B}` exits 0), NOT unit tests on fake data.
This rule exists because synthetic test data hid the catalyst bug. Violating it fails the build.

## 1. Isolation — never violate
- Work ONLY on branch `feat/v4-six-lens` (create from current HEAD if it doesn't exist).
- NEVER: merge to `main`, open-and-merge, deploy, run pm2/systemd/nginx, restart services,
  switch any production surface, or mutate live `de_*` / `atlas_*` data in place (staging only).
- All new frontend ships behind a feature flag, OFF by default → with the flag off, the
  production UI is byte-identical. The FM must see zero change until a human flips it.

## 2. Review before EVERY commit — the bar is "exceptional"
1. **Tests**: write tests alongside the code; they must pass. No commit on red.
2. **Adversarial self-review**: run `/code-review` on the diff (or spawn 2–3 independent
   reviewer agents) to hunt bugs, edge cases, and over-engineering. Default to skepticism;
   FIX every real finding before committing. Do not rationalise findings away.
3. **Accuracy check against ground truth** (this is a capital system):
   - a scorer's output must match Theta's `compute_*` on the same input where ported;
   - a parsed financial value must reconcile to a known figure (spot-check ≥2 names);
   - the harness / validation must be green for the touched scope.
   Adversarially verify any "it works" claim — never assert green you haven't proven.
4. Commit ONLY when: tests green + review clean + accuracy verified. Commit granularly
   (one logical unit per commit) with a clear message.

## 3. Push for mobile review — so it can be reviewed from a phone
- After each milestone (a scorer, a feed, the composite, a roll-up, a surface):
  `git add -A && git commit -m "..."` then `git push origin feat/v4-six-lens`.
- Keep `scripts/loops/SUMMARY.md` current — the phone digest. Per milestone append:
  what was built, test results, the accuracy spot-checks performed, coverage numbers,
  and any blockers/open issues. This is what the reviewer reads on the road.
- Push FREQUENTLY (not one giant end-commit) so progress is visible incrementally on GitHub.

## 4. Quality
- Modulith bounded contexts. Thresholds/weights in `atlas_thresholds` — NO hardcoded constants.
- Decimal for money. Tz-aware datetimes. File-size limits. Reuse before writing; least code
  that works (ponytail discipline). Strict SUPERSET of current Atlas — lose nothing (blueprint §5).

## 5. Resource limits (box = t3.2xlarge: 8 vCPU / 32 GB, burstable — SHARED)
- The box is SHARED with the RIA-platform build and live Atlas services (next-server + uvicorn
  APIs that must keep serving). So **cap local parallel workers at ≤6** (leave ≥2 cores).
  Use `--shard k/6` for the compute, and ≤6 concurrent agents for local-CPU work.
- Chunk large compute — never load all ~2,000 instruments × 25y into memory at once; stream/batch.
- Watch `free -h` and `df -h /` before big parallel stages; back off if memory/disk tightens.
  Resumability means a throttle or OOM costs only a restart, never data — prefer many small
  resumable steps over one giant in-memory pass. Be a good neighbour to the other build.

## 6. Stop condition
- The loop stops when its GATE is green (tests + coverage + accuracy verified). Do NOT loop
  forever. If a sub-task is genuinely blocked, record it in SUMMARY.md, skip it, continue,
  and stop at the gate with the blocker clearly noted. NEVER fabricate or overstate green.
