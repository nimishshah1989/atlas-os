# Atlas v6 — Drop Candidates (Awaiting Morning Sign-Off)

**Date:** 2026-05-26
**Status:** AWAITING USER SIGN-OFF (drops not executed per overnight constraint)
**Action when approved:** Execute DROP TABLE for each, update `atlas_alembic_version`

---

## 6 confirmed drop candidates (zero code references)

Verified via `grep -rln <table_name> atlas/ frontend/src/ scripts/ tests/ migrations/`. Zero hits across the entire codebase. Safe to drop.

| Table | Rows | DB comment |
|---|---|---|
| `atlas_governance_daily` | 0 | ATLAS-REVIEW-UNUSED: no code reference - drop candidate pending review (tagged 2026-05-21) |
| `atlas_governance_master` | 0 | Same |
| `atlas_index_membership` | 0 | Same |
| `atlas_v6_exclusions_log` | 0 | Same |
| `atlas_v6_recommendations_daily` | 0 | Same |
| `atlas_v6_strategy_runs` | 16 | Same. 16 rows = old strategy runs from May 2026 internal sprint; no recovery dependency |

---

## 2 tables tagged but ACTUALLY LIVE (mistakenly flagged)

These have `ATLAS-REVIEW-UNUSED` DB comments but ARE referenced by frontend code:

| Table | Rows | Used by | Action |
|---|---|---|---|
| `atlas_portfolio_policy` | 1 | `frontend/src/app/api/policy/route.ts` + `frontend/src/lib/queries/policy.ts` | **DO NOT DROP.** Update DB comment to remove the REVIEW-UNUSED tag. |
| `atlas_portfolio_proposed_change` | 0 | `frontend/src/app/api/portfolio/propose/route.ts` + `frontend/src/lib/queries/proposed-changes.ts` | **DO NOT DROP.** Update DB comment. |

These belong to the Strategy Lab + Setup workstream (active feature). Frontend reads from them; without them the policy editor + propose-change UI break.

---

## SQL to execute when signed off

```sql
-- After explicit user sign-off, in Alembic migration 098_v6_drop_unused.py:
DROP TABLE atlas.atlas_governance_daily;
DROP TABLE atlas.atlas_governance_master;
DROP TABLE atlas.atlas_index_membership;
DROP TABLE atlas.atlas_v6_exclusions_log;
DROP TABLE atlas.atlas_v6_recommendations_daily;
DROP TABLE atlas.atlas_v6_strategy_runs;

-- Update incorrectly-tagged tables (these stay):
COMMENT ON TABLE atlas.atlas_portfolio_policy IS
  'ATLAS-ENGINE: live, used by frontend/src/app/api/policy/route.ts (tagged 2026-05-26)';
COMMENT ON TABLE atlas.atlas_portfolio_proposed_change IS
  'ATLAS-ENGINE: live, used by frontend/src/app/api/portfolio/propose/route.ts (tagged 2026-05-26)';
```

---

## Verification gate (run before applying drops)

For each of the 6 to-be-dropped:

```sql
-- 1. Confirm zero foreign key dependencies
SELECT conname, conrelid::regclass AS dependent_table
FROM pg_constraint
WHERE confrelid = 'atlas.<table_name>'::regclass;
-- expect: 0 rows

-- 2. Confirm zero view dependencies
SELECT dependent_view, source_table
FROM information_schema.view_table_usage
WHERE table_schema = 'atlas' AND table_name = '<table_name>';
-- expect: 0 rows

-- 3. Confirm zero rule dependencies
SELECT rulename FROM pg_rules
WHERE schemaname = 'atlas' AND tablename = '<table_name>';
-- expect: 0 rows
```

---

## Rollback path

If a drop turns out to be wrong:
1. The schema is in `migrations/versions/<old>.py` — can be re-created from there
2. No data is recovered (the 16 rows in `atlas_v6_strategy_runs` are lost) — acceptable per "no recovery dependency" assessment

---

**Action: present this doc to user in morning. Drops execute only on explicit "yes."**
