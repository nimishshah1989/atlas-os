# Migration 098 — v6 Seven MVs Marker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline task-by-task execution. Steps use checkbox (`- [ ]`).

**Goal:** Land a no-op Alembic marker migration 098 that bumps `atlas_alembic_version` to 098, documents that 7 v6 MVs were applied directly via Supabase MCP `execute_sql`, and provides idempotent DROP statements in the downgrade path.

**Architecture:** Single Alembic migration file. `upgrade()` is intentionally no-op (the MVs were already created via MCP since Mac psycopg2 hangs against Supabase per existing memory; EC2 is the working Alembic path). `downgrade()` provides DROP MATERIALIZED VIEW IF EXISTS for clean rollback. Full MV SQL bodies live in design spec docs.

**Tech Stack:** Python 3.11, Alembic 1.13, SQLAlchemy 2.0.

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `migrations/versions/098_v6_seven_mvs.py` | CREATE | Marker migration with no-op upgrade + idempotent downgrade DROPs |

---

## Task 1: Write the marker migration

**Files:**
- Create: `migrations/versions/098_v6_seven_mvs.py`

- [ ] **Step 1.1: Write the migration file**

```python
"""v6 — 7 materialized views (Pages 01, 03, 05, 05a, 06, 06a, 08).

Marker migration. The 7 MVs listed below were APPLIED on 2026-05-27 directly
via Supabase MCP execute_sql against live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry), so Alembic CLI
is not usable from local Mac; MCP execute_sql is the working write path.

MVs created (all verified via MCP query, see docs/v6/2026-05-27-mv-buildout-log.md):
- mv_market_regime_landing  (Page 01)  — 1 wide row + JSONB nested sections
- mv_markets_rs_grid        (Page 03)  — 9 baselines × 5 windows
- mv_stock_list_v6          (Page 05)  — 750 stocks
- mv_stock_deepdive         (Page 05a) — 750 stocks with 30d trajectory + macro overlay
- mv_fund_list_v6           (Page 06)  — 587 funds with AMC rollup
- mv_fund_deepdive          (Page 06a) — 587 funds with 12mo NAV + 90d decisions
- mv_calls_performance      (Page 08)  — 363 in-flight signal_calls with realized excess

DEFERRED to migration 099 (need Phase C1.c, C1.d, C2 first):
- Page 04 (Sectors): 5 MVs (depend on atlas_sector_metrics_daily 5y backfill of new cols)
- Page 07 (ETFs): 2 MVs (depend on atlas_etf_scorecard 34→126 expansion)
- Page 02 (India Pulse): 1 MV (depends on macro ingest jobs)

Source-of-truth MV bodies:
- docs/superpowers/specs/2026-05-26-v6-market-regime-mvs-design.md
- docs/superpowers/specs/2026-05-26-v6-markets-rs-mvs-design.md
- docs/superpowers/specs/2026-05-26-v6-stocks-mvs-design.md
- docs/v6/2026-05-26-mv-funds-etfs-calls-plan.md

Refresh strategy (Phase D): pg_cron nightly at 20:00 IST after writer chain.
All 7 MVs have unique indexes for CONCURRENTLY refresh.

Revision ID: 098
Revises: 097
Create Date: 2026-05-27 00:30 IST
"""

from __future__ import annotations

from alembic import op

revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. MVs already exist via MCP execute_sql (see file docstring)."""
    op.execute("SELECT 1 AS marker_migration_098_applied")


def downgrade() -> None:
    """Idempotent rollback: drop all 7 MVs created in this revision."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_calls_performance CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_fund_deepdive CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_fund_list_v6 CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_deepdive CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_list_v6 CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_markets_rs_grid CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_market_regime_landing CASCADE")
```

- [ ] **Step 1.2: Bump atlas_alembic_version to 098 via Supabase MCP**

Run via MCP `execute_sql`:

```sql
UPDATE atlas.atlas_alembic_version SET version_num = '098' WHERE version_num = '097';
SELECT version_num FROM atlas.atlas_alembic_version;
```

Expected: result row shows `098`.

- [ ] **Step 1.3: Commit the migration file**

```bash
git add migrations/versions/098_v6_seven_mvs.py
git commit -m "feat(migrations): 098 marker — 7 v6 MVs applied via MCP (Pages 01,03,05,05a,06,06a,08)"
```

---

## Self-review

**1. Spec coverage:** Plan creates exactly the migration file requested. No other files. ✅

**2. Placeholder scan:** No TODOs, no "fill in details", code blocks complete. ✅

**3. Type consistency:** Single-file migration; no cross-task type concerns. ✅

Plan complete. Inline execution mode (since the MVs already exist; this is just durability via git + bumping the alembic head).
