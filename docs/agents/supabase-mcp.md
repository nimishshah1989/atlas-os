# Supabase MCP — read freely, gated writes

The Supabase MCP server (`plugin:supabase:supabase`) is wired to query this
project's database directly. Use it for schema introspection, data
spot-checks, and validator work in place of SSH-ing to EC2.

## Tool tiers (enforced globally via `~/.claude/settings.json` + hooks)

- **Auto-allowed (read-only)** — no prompt: `list_tables`, `list_migrations`,
  `list_extensions`, `list_branches`, `list_edge_functions`, `get_logs`,
  `get_advisors`, `generate_typescript_types`, `search_docs`, `get_project*`,
  `get_anon_key`, `list_organizations`, `list_projects`.
- **Hard-denied (no override)**: `apply_migration` (schema changes go through
  Alembic), `deploy_edge_function`, all branch ops
  (`create/delete/merge/reset/rebase_branch`).
- **Gated** — `execute_sql` routes through
  `~/.claude/hooks/pre-supabase-sql-guard.py`, which classifies the SQL after
  stripping string literals + comments.

## Marker protocol for `execute_sql`

Markers live in cwd, one-shot — deleted after the call succeeds.

| SQL kind | Required marker(s) |
|---|---|
| SELECT / WITH / EXPLAIN / SHOW / VALUES / TABLE | none |
| INSERT / UPDATE / UPSERT / MERGE | `.supabase-write-approved` |
| DELETE / DROP / TRUNCATE / ALTER | BOTH `.supabase-delete-approved-1` AND `.supabase-delete-approved-2` |
| anything unclassifiable | denied (fail-safe) |

## Rules for agents

1. Never propose workarounds to the gate. If a write is needed, ask Nimish to
   `touch` the marker(s), then run the SQL. Two-person rule on destructive ops
   is non-negotiable.
2. DDL never goes through MCP — always Alembic (`migrations/versions/`).
3. Every successful `execute_sql` is appended as a one-line audit row to
   `decisions.jsonl`. Don't add separate logging.
4. Prefer MCP for read paths over EC2 SSH — local `psycopg2` is broken, but
   the MCP path works directly from your machine.
