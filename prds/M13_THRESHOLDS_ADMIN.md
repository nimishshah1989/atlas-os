# M13 — Threshold Admin (FM-driven)

**Date:** 2026-05-09
**Goal:** Let the Fund Manager change methodology threshold values and trigger
a recompute, with full audit trail. ~5.5 hours of focused work.

---

## What ships

A page at `atlas.jslwealth.in/admin/thresholds` (admin-gated) where FM can:

1. **View** all ~38 rows of `atlas.atlas_thresholds`, grouped by category
   (sector / fund / regime / etf), with: current value, allowed range, default,
   description, last_modified_by, last_modified_at.
2. **Edit** one threshold via a modal — input field + diff preview ("20% → 25%")
   + required "reason for change" textarea + Save.
3. **Audit log per threshold** — last 20 changes from `atlas_threshold_history`.
4. **Re-run** — buttons "Re-run sector states", "Re-run fund decisions",
   "Re-run everything". Triggers the matching `m*_daily.py` on EC2.
5. **Live status** — polls `atlas_pipeline_runs` to show "running 3m / 5m" etc.

What does NOT change: methodology structure (which states exist, which gates
fire). Only threshold *values* are tunable. The audit log is load-bearing for
SEBI compliance.

---

## Architecture decisions (locked)

1. **Recompute trigger = HTTP** to a new internal FastAPI on EC2.
   - `POST http://13.206.34.214:8002/internal/recompute/{milestone}` with
     `Authorization: Bearer <ATLAS_INTERNAL_SECRET>`
   - Shared secret in env on both Vercel and EC2.
   - EC2 endpoint exec's `m3_daily.py` / `m4_daily.py` / `m5_daily.py` via
     `subprocess.Popen` (non-blocking), returns `run_id` immediately.
   - **Milestone allowlist**: path param must be in `{m3, m4, m5, all}`.
     Anything else → 400. No string interpolation into the subprocess
     argv beyond the allowlisted milestone → script-name mapping.
   - **Concurrency guard**: before Popen, `SELECT 1 FROM atlas_run_log
     WHERE status='RUNNING' AND business_date=CURRENT_DATE`. If a row
     exists, return 409 with the existing `compute_run_id`. UI surfaces
     "already running" instead of spawning a duplicate process.
   - **Subprocess output**: stdout+stderr redirected to
     `/var/log/atlas/recompute-{milestone}-{run_id}.log` (mkdir -p the
     directory in the systemd unit's `ExecStartPre`). Logfile name is
     grep-able from the run_id surfaced in `atlas_run_log`.
   - **Network exposure**: bind to `0.0.0.0:8002`; bearer secret is the
     auth boundary. Tool is internal-only for now; no SG tightening for
     v0. TODO before any external user gets access: lock SG to Vercel
     egress range or move behind Cloudflare Tunnel.
   - **Response envelope** (matches CLAUDE.md API design rule):
     ```json
     {"data": {"compute_run_id": "...", "milestone": "m3", "status": "running"},
      "meta": {"data_as_of": "2026-05-09T...", "fetched_at": "...", "source": "atlas-internal"}}
     ```
   - **Logging**: structlog with context (`compute_run_id`, `milestone`).
     No `print()`. Per `~/.claude/rules/python-backend.md`.
   - **Sets us up for M6** (full API) — same pattern, scoped down.
   - **Rejected**: SSH-from-Vercel (couples key to deploy). Job queue
     (overkill for 3 users). flock-based lockfile (atlas_run_log check
     is sufficient for v0; flock added if duplicate-run becomes a real
     pattern).

2. **Threshold UPDATE = Server Action**, not API.
   - `frontend/src/app/admin/thresholds/actions.ts` exports
     `updateThreshold(key, value, reason)`.
   - Direct `UPDATE atlas.atlas_thresholds` via the existing Supabase pooler
     (`ATLAS_DB_URL`).
   - **MUST be wrapped in an explicit transaction** (`BEGIN ... COMMIT`).
     `SET LOCAL atlas.change_reason = $1` is a no-op outside a transaction;
     the trigger would then read NULL from `current_setting()` and the audit
     row would have no reason. This is a silent failure mode — covered by
     a critical-path test (see Test Plan).
   - DB trigger writes the audit row (no app-level audit logic).
   - **Identity**: `last_modified_by` = `'fund-manager'` (hardcoded for v0;
     single shared admin cookie). `user_ip` and `user_agent` columns in
     `atlas_threshold_history` capture per-session forensic info if needed.

3. **Auth = HMAC-token cookie** for v0.
   - `ATLAS_ADMIN_PASSWORD` env var on both Vercel (login form check) and
     server (HMAC signing key).
   - `/admin/login` POST: server checks password; if match, sets cookie
     `atlas_admin=<token>` where token = `base64(timestamp || hmac_sha256(secret, timestamp))`.
   - Middleware on `/admin/*`: parses token, verifies HMAC, rejects if
     timestamp older than 7 days. Plain password never leaves the server.
   - TODO comment to upgrade to Supabase Auth role check later.
   - **Rejected**: storing literal password in cookie (visible in dev tools,
     no revocation path, weaker posture).

---

## Schema additions (Migration 023)

```sql
CREATE OR REPLACE FUNCTION atlas.fn_threshold_audit() RETURNS TRIGGER AS $$
DECLARE
  v_reason TEXT;
BEGIN
  IF OLD.threshold_value IS DISTINCT FROM NEW.threshold_value THEN
    -- Reason comes from session GUC set by the Server Action inside the
    -- same transaction. NULL/empty if caller forgot — the test suite
    -- proves the wrapper sets it correctly.
    v_reason := current_setting('atlas.change_reason', true);
    INSERT INTO atlas.atlas_threshold_history (
      threshold_key, old_value, new_value, changed_by, change_reason
    ) VALUES (
      NEW.threshold_key, OLD.threshold_value, NEW.threshold_value,
      NEW.last_modified_by, v_reason
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_threshold_audit
AFTER UPDATE ON atlas.atlas_thresholds
FOR EACH ROW EXECUTE FUNCTION atlas.fn_threshold_audit();
```

Server Action invocation pattern (must use a single transaction; otherwise
`SET LOCAL` is a no-op and `change_reason` lands as NULL):

```ts
await db.transaction(async (tx) => {
  await tx.execute(sql`SET LOCAL atlas.change_reason = ${reason}`);
  await tx.execute(sql`
    UPDATE atlas.atlas_thresholds
    SET threshold_value = ${value}, last_modified_by = 'fund-manager',
        last_modified_at = NOW()
    WHERE threshold_key = ${key}
  `);
});
```

---

## File map

```
migrations/versions/023_threshold_audit_trigger.py    [new]
atlas/api/                                            [new bounded context]
  __init__.py
  internal_recompute.py                               # FastAPI app — POST /internal/recompute/{milestone}
  systemd/atlas-internal-recompute.service            # runs on .214; ExecStartPre creates /var/log/atlas/
tests/unit/api/test_internal_recompute.py             [new]
tests/unit/migrations/test_threshold_audit_trigger.py [new]   # uses pytest-postgresql or live DB
frontend/src/app/admin/                               [new]
  layout.tsx                                          # admin shell (extends regular layout)
  login/page.tsx                                      # password form, posts to login Server Action
  login/actions.ts                                    # validates password, sets HMAC cookie
  thresholds/
    page.tsx                                          # RSC, < 250 LOC: fetch + render <ThresholdsView />
    ThresholdsView.tsx                                # client island holding selection state
    actions.ts                                        # Server Actions: updateThreshold, triggerRecompute
    EditThresholdModal.tsx
    HistoryDrawer.tsx
    RecomputePanel.tsx                                # 3 buttons + 5s polling on atlas_run_log
frontend/src/lib/queries/thresholds.ts                [new]   # SELECT helpers (server-only)
frontend/src/lib/internal-api.ts                      [new]   # fetch wrapper for EC2 endpoint
frontend/src/lib/admin-auth.ts                        [new]   # HMAC sign/verify
frontend/middleware.ts                                [edit]  # gate /admin/* (allow /admin/login)
frontend/src/__tests__/admin/                         [new]
  middleware.test.ts                                  # cookie validation
  actions.test.ts                                     # Server Action branches
  thresholds.e2e.ts                                   # playwright/browse smoke
```

Note: `page.tsx` stays a thin Server Component (data fetch + pass to client
island). All interactive state lives in `ThresholdsView.tsx`. This keeps
the page shell well under the 250-LOC governance limit.

---

## Phasing (~8 hours, post-review)

Boil-the-lake test scope was selected — full coverage of all 22 paths in
the test diagram. Adds ~2.5 hr to the original 5.5 hr estimate.

| # | Chunk | Hours |
|---|---|---|
| 0 | `plan-eng-review` confirms architecture (DONE — this doc was patched) | 0.5 |
| 1 | Migration 023 + trigger test + EC2 recompute endpoint + tests + deploy | 2.5 |
| 2 | Frontend Server Actions + Server Action tests | 1.0 |
| 3 | `/admin/thresholds` page + login + middleware + admin-auth.ts + UI tests + E2E | 3.0 |
| 4 | `verification-before-completion` → `codex` (challenge mode) → `review` → `ship` → `land-and-deploy` | 1.0 |

---

## Skills cadence

| Phase | Skills |
|---|---|
| Phase 0 (plan) | `plan-eng-review` |
| Phase 1-3 (build) | `karpathy-guidelines` (each edit) + `vercel-react-best-practices` (Server Components/Actions) + `frontend-design:frontend-design` (UI) |
| Phase 4 (verify+ship) | `superpowers:verification-before-completion` → `codex review` (challenge mode on shared-secret) → `review` → `ship` → `land-and-deploy` |

---

## Hard rules (already hook-enforced)

- File-size tiers: source 600 / tests 800 / page shells 250
- No cross-context imports (atlas/api can't reach into atlas/compute internals)
- Methodology thresholds in `atlas_thresholds` table (this milestone *uses* them; doesn't add new hardcoded ones)
- Decimal for money, tz-aware datetimes
- No hardcoded credentials → `ATLAS_INTERNAL_SECRET`, `ATLAS_ADMIN_PASSWORD` via env

---

## Success criteria

1. FM logs in at `/admin/thresholds` with admin password (HMAC token cookie set)
2. Sees all thresholds grouped by category, with descriptions
3. Edits `sector_rs_quintile_top_pct` from 80 → 75, reason "tighter Overweight cutoff for current market"
4. Audit row appears in `atlas_threshold_history` with old=80, new=75, reason captured
5. Clicks "Re-run sector states" → sees `atlas_run_log` row appear with status=running, reclassify=TRUE
6. Within 5 min, status flips to success, `atlas_sector_states_daily` reflects new cutoffs
7. Public dashboard at `atlas.jslwealth.in/sectors` shows the recomputed states
8. Concurrency check: clicking "Re-run sector states" again while one is running returns 409 + UI surfaces the existing run_id

---

## Test plan (boil-the-lake)

Full coverage of all 22 code paths + user flows from the eng-review diagram.

### Unit tests

**`tests/unit/migrations/test_threshold_audit_trigger.py`** — DB trigger:
1. UPDATE with different value + GUC set → audit row inserted with reason
2. UPDATE with different value + GUC unset → audit row inserted with NULL reason
3. UPDATE with different value + GUC = '' → audit row with empty-string reason
4. UPDATE with same value (no-op) → no audit row
5. AFTER INSERT not fired (only UPDATE matters)

**`tests/unit/api/test_internal_recompute.py`** — FastAPI endpoint via TestClient + mocked `subprocess.Popen`:
1. POST without bearer → 401
2. POST with wrong bearer → 401
3. POST `/m99` (out of allowlist) → 400
4. POST `/m3` while atlas_run_log has RUNNING row for today → 409 with existing run_id
5. POST `/m3` happy path → 202, run_id returned, Popen called with correct args, log dir created
6. POST `/m3` with Popen raising FileNotFoundError → 500, atlas_run_log row marked FAILED

**`frontend/src/__tests__/admin/middleware.test.ts`** — auth gate:
1. No cookie on /admin/thresholds → redirect /admin/login
2. Cookie with valid HMAC and fresh timestamp → next()
3. Cookie with valid HMAC but timestamp >7 days old → redirect + clear cookie
4. Cookie with tampered HMAC → redirect + clear cookie
5. /admin/login itself is not gated → next()

**`frontend/src/__tests__/admin/actions.test.ts`** — Server Actions (mocked DB pool):
1. `updateThreshold(key, value, '')` → throws (empty reason rejected pre-DB)
2. `updateThreshold(key, out_of_range, 'reason')` → DB CHECK constraint throws → action surfaces error
3. `updateThreshold` happy path → tx.execute called with `SET LOCAL atlas.change_reason = ?` BEFORE the UPDATE inside the same tx (proves wrapper handles GUC) — **CRITICAL**
4. `updateThreshold` happy path → revalidatePath('/admin/thresholds') called
5. `triggerRecompute('m3')` with EC2 200 → returns run_id
6. `triggerRecompute('m3')` with EC2 409 → surfaces existing run_id (not error)
7. `triggerRecompute('m3')` with EC2 401 → throws (secret mismatch — should not happen but)

### E2E tests (browse-based smoke)

**`frontend/src/__tests__/admin/thresholds.e2e.ts`**:
1. Full FM flow: login → /admin/thresholds → click row → edit modal → save with reason → assert audit row in DB
2. Recompute flow: click "Re-run sectors" → poll atlas_run_log → assert status flips to running then success
3. Out-of-range entry → modal surfaces error inline, no DB mutation

---

## What already exists (reused, not rebuilt)

- `atlas.atlas_thresholds` table: 35 rows seeded at M1, schema includes
  `min_allowed`/`max_allowed` CHECK constraints. UI consumes; no DDL changes.
- `atlas.atlas_threshold_history` table: append-only, has `user_ip` + `user_agent`
  columns (forensics) and `reclassify_run_id` (links audit to recompute).
- `atlas_run_log` table: already has a `reclassify BOOLEAN DEFAULT FALSE` column
  (migration 007), so partial-recompute runs can be filtered out of nightly
  status queries by `WHERE reclassify = FALSE`.
- `m3_daily.py` / `m4_daily.py` / `m5_daily.py` exist on `.214` — no
  changes; FastAPI invokes them as-is.
- `ATLAS_DB_URL` Supabase pooler env exists on Vercel. M6 frontend already
  uses it for read queries.
- `frontend/middleware.ts` already exists for non-admin routes; we add the
  `/admin/*` branch.

## NOT in scope (deferred)

- **Per-user identity**: `last_modified_by` is hardcoded to `'fund-manager'`.
  Upgrade to Supabase Auth + role-based admin check is a follow-on.
- **Threshold preview / dry-run**: PRD originally hinted at "diff preview
  before save"; the modal does show old → new visually but does NOT preview
  what state changes would result without committing. Real preview requires
  a parallel-compute scratch run; deferred.
- **Threshold rollback button**: HistoryDrawer shows old values but you
  can't one-click revert. Deferred — for now, FM types the old value back in.
- **Multi-threshold batch edit**: edit-one-at-a-time only. SEBI audit prefers
  it that way (one decision per row).
- **Network-level lockdown of port 8002**: open to 0.0.0.0 with bearer
  secret. SG tightening (Vercel CIDR allowlist or Cloudflare Tunnel) deferred
  until external users access the tool.
- **flock-based concurrency guard**: atlas_run_log soft-check is the v0
  guard. flock on `/var/run/atlas-recompute.lock` is the upgrade if duplicate
  runs become a real problem.
- **Live diff preview of which thresholds are stale vs. the current
  classification run**: would be lovely UX ("you changed this 2 hours ago,
  the latest nightly is from yesterday") but not on the critical path.

## Failure modes (production scenarios)

| Failure | Test? | Error handling? | User experience? |
|---|---|---|---|
| Vercel→.214 network timeout during recompute trigger | ✗ (Server Action throws) | Surface generic error in UI | Toast "couldn't reach compute server" |
| .214 returns 500 (Popen exception) | ✓ test_internal_recompute.py | atlas_run_log marked FAILED with stderr | UI polls, sees FAILED, shows logfile path |
| `SET LOCAL` outside txn → silent NULL change_reason | ✓ test_actions.ts (CRITICAL) | n/a — covered by test | Audit row has NULL reason → SEBI gap |
| HMAC cookie tamper | ✓ test middleware.ts | Redirect + clear cookie | Forced re-login |
| FM clicks Re-run while nightly cron mid-flight | ✓ test_internal_recompute.py | 409 surfaces existing run_id | UI shows "already running, run_id=X" |
| Threshold UPDATE rejected by CHECK constraint | ✓ test_actions.ts | Server Action catches PostgresError | Modal inline error |
| Subprocess output exceeds disk on .214 | ✗ (no test) | logrotate runs nightly via systemd | TODO: add logrotate config |

**Critical gap flagged**: subprocess output disk-fill is the only failure
mode without test + with potentially-silent failure (logfile fills, future
recompute fails to write start log, but atlas_run_log still gets a row).
Mitigation in Phase 1: logrotate config in the systemd unit's deploy script.

## TODOS.md updates

(No `TODOS.md` exists at repo root yet. The deferrals above act as the
TODO surface for now. If/when `TODOS.md` is created, port the "NOT in
scope" list into it.)

Items worth capturing if `TODOS.md` is created:

1. **Upgrade admin auth to Supabase Auth + role check.** Why: per-user
   audit trail; revocation without password rotation. Pros: real identity;
   integrates with existing Supabase user management. Cons: ~2 hr;
   requires login UI, role grant migration, middleware rewrite.
2. **Port 8002 SG lockdown to Vercel CIDR or Cloudflare Tunnel.**
   Why: defense-in-depth before any external user accesses the tool.
3. **logrotate for `/var/log/atlas/recompute-*.log`.** Why: prevent disk
   fill on .214. Trivial — daily rotate, keep 30, gzip.
4. **Threshold rollback button in HistoryDrawer.** Why: 1-click revert.
   FM has to retype old value today.
5. **flock fallback** if duplicate-run becomes a real problem.

## Worktree parallelization

| Step | Modules touched | Depends on |
|---|---|---|
| Migration 023 + trigger test | `migrations/`, `tests/unit/migrations/` | — |
| FastAPI internal_recompute + tests + systemd | `atlas/api/`, `tests/unit/api/` | — |
| HMAC auth lib + login + middleware + tests | `frontend/src/lib/admin-auth.ts`, `frontend/middleware.ts`, `frontend/src/app/admin/login/`, `frontend/src/__tests__/admin/middleware.test.ts` | — |
| Server Actions + tests | `frontend/src/app/admin/thresholds/actions.ts`, `frontend/src/lib/internal-api.ts`, `frontend/src/__tests__/admin/actions.test.ts` | HMAC auth lib (imports) |
| Thresholds page + components + E2E | `frontend/src/app/admin/thresholds/page.tsx` and siblings, queries lib, E2E test | Server Actions, HMAC auth lib |

**Parallel lanes:**
- **Lane A** (backend, isolated): Migration 023 + test → FastAPI + test + systemd. No frontend dep.
- **Lane B** (frontend infra, isolated): HMAC auth lib + login + middleware + middleware test. Independent of Lane A.
- **Lane C** (frontend wiring, depends on B): Server Actions + actions tests. Depends on HMAC lib from B.
- **Lane D** (frontend UI, depends on C): Thresholds page + components + E2E. Depends on actions from C.

**Execution order**: A and B in parallel (worktrees A and B). When B done → C in worktree B. When A merged + C done → D in worktree B (or main). E2E test runs against deployed stack.

**Conflict flags**: Lane A and B touch zero shared module dirs — safe to parallel. Lanes B→C→D are strictly sequential within frontend.

For tonight's autonomous build: run lanes A and B in parallel via `superpowers:dispatching-parallel-agents` (or just two `Agent` invocations with `isolation: "worktree"`). Total wall-clock: max(A, B) + C + D ≈ 2.5 + 1 + 3 = 6.5 hr instead of 8 hr serial. Saves ~1.5 hr.

---

## Completion summary (plan-eng-review)

- Step 0 Scope Challenge: scope accepted as-is (no reduction; 11 files all justified)
- Architecture Review: 4 taste calls answered (auth=HMAC, port=open+bearer, concurrency=run_log soft-check, identity='fund-manager'); 4 trivial fixes patched in spec (NEW.notes bug, milestone allowlist, txn wrapper, atlas_run_log naming)
- Code Quality Review: 1 taste call answered (subprocess logs to date-stamped logfile); 4 trivial fixes patched (envelope shape, page-shell composition, structlog, bounded-context note)
- Test Review: 22-path diagram produced; "boil the lake" scope chosen → all 22 tests added to spec
- Performance Review: no issues; polling cadence pinned to 5s
- NOT in scope: written (7 items)
- What already exists: written (6 items reused)
- TODOS: 5 items captured inline (no TODOS.md yet)
- Failure modes: 7 scenarios mapped; 1 critical gap flagged (subprocess log disk-fill — mitigation: logrotate in deploy script)
- Outside voice: skipped (user pre-scheduled `codex` for Phase 4)
- Parallelization: 4 lanes, 2 parallel (A+B) / 2 sequential (B→C→D); ~1.5 hr saved
- Lake Score: 9/9 (every choice picked the more-complete option)

Unresolved decisions: none.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run (intentional — milestone is operationally locked, not a strategy call) |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | scheduled for Phase 4 (challenge mode on shared-secret model) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 11 issues found, all addressed in spec; 1 critical gap (subprocess log disk-fill) → mitigation: logrotate in deploy |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | not run (admin-only page, internal FM tool, design polish deferred) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | n/a (not a developer-facing product surface) |

**UNRESOLVED:** 0
**VERDICT:** ENG CLEARED — ready to implement. Codex challenge scheduled for Phase 4 per the original plan.
