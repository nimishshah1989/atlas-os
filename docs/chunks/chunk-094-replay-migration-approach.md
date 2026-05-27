# Chunk 094: Replay migration 082-088 onto Supabase atlas-os

## Problem
Live Supabase `atlas-os` DB is stamped `alembic_version = 093` but tables from
migrations 082-088 never ran there. Seven migrations (brief_cache, ledger,
paper_portfolio, user_lots, ETF/MF tables, macro overlay, provenance_log,
drift_event_log) are missing.

## Approach
Single consolidated migration `094_v6_replay_missing_tables_082_088.py` using
raw SQL `op.execute()` with `CREATE TABLE IF NOT EXISTS` semantics throughout.
This is idempotent and survives double-runs.

## DDL mapping
| Source | Tables created | New enums |
|--------|---------------|-----------|
| 082 | atlas_brief_cache | none |
| 083 | atlas_ledger + atlas_ledger_public view | none |
| 084 | atlas_paper_portfolio, atlas_user_lots + RLS | none |
| 085 | atlas_etf_signal_calls, atlas_mf_recommendation_daily, atlas_mf_switch_rules | atlas_etf_sub_category, atlas_mf_quartile, atlas_mf_recommendation |
| 086 | atlas_macro_features_daily, atlas_macro_recommendation_daily | none |
| 087 | atlas_provenance_log + write-once trigger + retro FKs | none |
| 088 | atlas_drift_event_log + write-once trigger | atlas_drift_action |

## Idempotency patterns used
- Tables: `CREATE TABLE IF NOT EXISTS atlas.<name> (...)`
- Enums: `DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='...' AND typnamespace = 'atlas'::regnamespace) THEN CREATE TYPE atlas.xxx AS ENUM (...); END IF; END $$;`
- Indexes: `CREATE [UNIQUE] INDEX IF NOT EXISTS`
- View: `CREATE OR REPLACE VIEW`
- RLS policies: wrapped in `DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_policies ...) THEN CREATE POLICY...; END IF; END $$;`
- Triggers: `CREATE OR REPLACE FUNCTION` + drop-if-exists before creating trigger
- Retro FKs: wrapped to skip if FK already exists in pg_constraint

## Existing code reused
- Exact column types, constraints, FK clauses, and index WHERE clauses copied
  verbatim from source migrations 082-088.

## Edge cases
- 085 enums created idempotently (pg_type check) so no duplicate-type error
- 087 retro FKs wrapped in DO $$ to skip if already present
- 088 write-once trigger uses CREATE OR REPLACE FUNCTION (idempotent) and
  drops old trigger before recreating
- RLS policies checked via pg_policies before CREATE POLICY
- Conditional GRANT for atlas_agent_readonly (copied from 083)

## Out of scope
- 089 v5-deprecation ALTER TABLE statements
- Seed data for atlas_mf_switch_rules (migration 095)

## Expected runtime on t3.large
< 5 seconds (pure DDL, no data transforms)
