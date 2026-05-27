# Atlas v6 — RLS Decision

**Date:** 2026-05-26
**Status:** Triage complete; awaiting user decision before public launch
**Source:** Supabase advisor flagged 117 atlas tables with RLS disabled. Anon key can read/modify all of them.

---

## The risk (per Supabase advisor)

> "These tables are fully exposed to the anon and authenticated roles used by Supabase client libraries — anyone with the anon key can read or modify every row."

Severity per advisor: **CRITICAL**.

Real-world severity depends on whether the anon key is publicly exposed. For internal-tool v6.0:
- Frontend reaches Supabase via a server-side route (service-role) → anon key is not in browser bundles
- Public launch path needs RLS, but internal/family-office phase can defer

---

## Three policy classes for the 117 tables

### Class A — User-scoped (2 tables, RLS already ENABLED with policies)

| Table | Existing policy |
|---|---|
| `atlas_paper_portfolio` | `paper_portfolio_user_isolation` — PERMISSIVE, ALL, `user_id = jwt.sub` |
| `atlas_user_lots` | `user_lots_user_isolation` — same pattern |

**Advisor note:** both have `auth_rls_initplan` warning (re-evaluates `current_setting` per row). Fix is one-line wrap in `(SELECT ...)`. Non-blocking at v6.0 scale; queue for post-launch.

### Class B — Engine output (115 tables, RLS disabled)

Everything else in `atlas.*`: scorecards, signal_calls, regime, sectors, etc.

**Three policy options:**

#### Option B1 — Enable RLS, allow service-role-only reads (RECOMMENDED for public launch)

```sql
ALTER TABLE atlas.<table> ENABLE ROW LEVEL SECURITY;
-- No policies = no anon/authenticated access; only service_role (used by Atlas backend) reads.
```

Effect:
- Frontend MUST go through server-side route (Next.js Server Component or API route) — direct anon-key access blocked
- Existing frontend already uses server-side queries via `lib/queries/v6/*.ts` (Server Components), so no breakage
- 100% airtight against anon-key leak

#### Option B2 — Enable RLS with `SELECT TO authenticated USING (true)` policies

```sql
ALTER TABLE atlas.<table> ENABLE ROW LEVEL SECURITY;
CREATE POLICY <name>_select ON atlas.<table> FOR SELECT TO authenticated USING (true);
```

Effect:
- Anon role still blocked; authenticated users can read
- Use this if the frontend needs to query via Supabase client lib from browser code (currently it does NOT — all queries are server-side)

#### Option B3 — Defer (current state)

Leave RLS disabled until public launch. Internal-tool phase accepts the risk.

**My recommendation:** **B1 for v6.0 launch.** It's airtight, doesn't break the existing server-side query pattern, and satisfies the advisor. The one-line ALTER per table can be in a migration.

---

## SQL to apply Option B1 (when approved)

The advisor already produced the full remediation SQL — 115 ALTER statements. Apply via Alembic migration `099_v6_enable_rls.py`:

```python
def upgrade():
    tables = [...]  # list of 115 atlas tables to enable RLS
    for t in tables:
        op.execute(f"ALTER TABLE atlas.{t} ENABLE ROW LEVEL SECURITY;")

def downgrade():
    tables = [...]
    for t in tables:
        op.execute(f"ALTER TABLE atlas.{t} DISABLE ROW LEVEL SECURITY;")
```

After this:
- Anon key can't read atlas tables
- Service role (used by Atlas backend) reads all atlas tables (RLS-bypass for service_role is built into Postgres)
- Frontend Server Components continue to work (they use service-role via env var)

---

## Class C — Public/JIP tables (`public.de_*`)

Outside Atlas's RLS scope. JIP data engine owns these. Leave as-is.

---

## Function-level findings (per advisor)

- 7 functions with mutable search_path: `fn_threshold_audit`, `fn_decision_policy_audit`, `fn_strategy_audit`, `guard_walkforward_run_mutation`, `deny_update_delete_provenance`, `deny_update_delete_drift_event`, `guard_friction_params_mutation`. Fix: add `SET search_path = atlas, public, pg_catalog` to body. Non-blocking; queue for cleanup PR.
- 2 functions callable by anon + authenticated: `public.rls_auto_enable()`. **Fix before launch**: `REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon, authenticated;`

---

## Action for morning

User decides:
- **(a)** Apply RLS now via migration 099 (recommended)
- **(b)** Defer until public launch (current state continues)
- **(c)** Different policy class for some subset of tables

Either way, the `REVOKE EXECUTE` on `rls_auto_enable` should be in tonight's migration sequence as a free win.

---

## Why this isn't a tonight-blocking item

The frontend page wiring (Phase G) uses server-side queries via `lib/queries/v6/*.ts`. RLS state doesn't affect server-side rendering. So Phase A-F backend buildout proceeds regardless of the RLS decision; the decision affects launch readiness, not buildout.
