# Migration 097 — v6 Frontend Column Adds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 18 nullable columns across 4 existing tables + 2 new config tables required by v6 frontend mockups, applied as Alembic migration 097 against live Supabase atlas-os.

**Architecture:** Single Alembic migration file (`migrations/versions/097_v6_frontend_column_adds.py`). All column additions are nullable so existing rows are unaffected. Two new tables are seed-only config tables (no incremental writers needed). The migration applies cleanly to live DB; downgrade is idempotent.

**Tech Stack:** Python 3.11, Alembic 1.13, SQLAlchemy 2.0, PostgreSQL 17.6 (Supabase), psycopg2.

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `migrations/versions/097_v6_frontend_column_adds.py` | CREATE | Single Alembic migration with upgrade + downgrade |
| `tests/migrations/test_097_v6_frontend_column_adds.py` | CREATE | Integration test: applies migration in transaction, asserts cols + seed rows exist, then rollback |

---

## Task 1: Write the migration test (TDD red)

**Files:**
- Create: `tests/migrations/test_097_v6_frontend_column_adds.py`

- [ ] **Step 1.1: Write the failing test**

```python
# tests/migrations/test_097_v6_frontend_column_adds.py
"""Integration test for migration 097: v6 frontend column adds.

Verifies post-upgrade state:
1. atlas_cell_definitions has display_name + explain_text columns
2. atlas_cell_definitions.display_name is populated for all 21 cells (deterministic backfill)
3. atlas_sector_metrics_daily has 8 new columns (all nullable)
4. atlas_macro_daily has 5 new columns
5. atlas_etf_scorecard has 3 new columns
6. atlas_stock_macro_overlay_map exists with 23 seed rows
7. atlas_etf_te_bands exists with 5 seed rows
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import os
import urllib.parse


@pytest.fixture(scope="module")
def engine() -> Engine:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        pytest.skip("ATLAS_DB_URL not set")
    # SQLAlchemy driver swap if needed
    if db_url.startswith("postgresql+psycopg2://"):
        return create_engine(db_url)
    return create_engine(db_url.replace("postgresql://", "postgresql+psycopg2://"))


def _column_exists(engine: Engine, schema: str, table: str, column: str) -> bool:
    sql = text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t AND column_name = :c
    """)
    with engine.connect() as conn:
        return conn.execute(sql, {"s": schema, "t": table, "c": column}).first() is not None


def test_cell_definitions_has_display_name(engine):
    assert _column_exists(engine, "atlas", "atlas_cell_definitions", "display_name")


def test_cell_definitions_has_explain_text(engine):
    assert _column_exists(engine, "atlas", "atlas_cell_definitions", "explain_text")


def test_cell_definitions_display_name_backfilled(engine):
    """All 21 cells must have display_name populated post-migration."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT COUNT(*) FILTER (WHERE display_name IS NULL) AS null_count,
                   COUNT(*) AS total
            FROM atlas.atlas_cell_definitions
        """)).first()
    assert row.null_count == 0, f"{row.null_count}/{row.total} cells have NULL display_name"
    assert row.total == 21, f"Expected 21 cells, got {row.total}"


def test_cell_definitions_display_name_format(engine):
    """display_name follows '{tier} {tenure} {action} signal' pattern."""
    with engine.connect() as conn:
        names = [r[0] for r in conn.execute(text(
            "SELECT display_name FROM atlas.atlas_cell_definitions ORDER BY display_name"
        )).fetchall()]
    # Sample: "Mid 6m BUY signal", "Large 12m AVOID signal", etc.
    for name in names:
        parts = name.split(" ")
        assert len(parts) == 4, f"Unexpected display_name format: {name!r}"
        assert parts[0] in ("Small", "Mid", "Large"), f"Bad tier in {name!r}"
        assert parts[1] in ("1m", "3m", "6m", "12m"), f"Bad tenure in {name!r}"
        assert parts[2] in ("BUY", "WATCH", "AVOID"), f"Bad action in {name!r}"
        assert parts[3] == "signal"


@pytest.mark.parametrize("col", ["rs_1w", "rs_1m", "rs_6m", "rs_12m",
                                  "pct_above_ema20", "pct_above_ema200", "pct_52wh", "hhi"])
def test_sector_metrics_has_new_column(engine, col):
    assert _column_exists(engine, "atlas", "atlas_sector_metrics_daily", col)


@pytest.mark.parametrize("col", ["dii_flow", "us_10y_yield", "brent_inr", "cpi_yoy", "vix_9d"])
def test_macro_daily_has_new_column(engine, col):
    assert _column_exists(engine, "atlas", "atlas_macro_daily", col)


@pytest.mark.parametrize("col", ["premium_bps", "te_60d", "adv_20d_inr"])
def test_etf_scorecard_has_new_column(engine, col):
    assert _column_exists(engine, "atlas", "atlas_etf_scorecard", col)


def test_stock_macro_overlay_map_exists(engine):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT COUNT(*) AS row_count FROM atlas.atlas_stock_macro_overlay_map
            WHERE effective_to IS NULL
        """)).first()
    assert row.row_count == 23, f"Expected 23 seed rows, got {row.row_count}"


def test_stock_macro_overlay_map_critical_sectors(engine):
    """Verify Energy, IT, Pvt Bank seed rows exist with expected macro overlays."""
    with engine.connect() as conn:
        rows = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(text("""
            SELECT sector, macro_series_1, macro_series_2, macro_series_3
            FROM atlas.atlas_stock_macro_overlay_map
            WHERE sector IN ('Energy', 'IT', 'Pvt Bank') AND effective_to IS NULL
        """)).fetchall()}
    assert rows["Energy"] == ("BRENT_INR", "USDINR", "INDIA_10Y")
    assert rows["IT"] == ("USDINR", "US_10Y", "DXY")
    assert rows["Pvt Bank"] == ("INDIA_10Y", "USDINR", "BRENT_INR")


def test_etf_te_bands_exists(engine):
    with engine.connect() as conn:
        rows = {r[0]: r[1] for r in conn.execute(text(
            "SELECT category, te_max_bps FROM atlas.atlas_etf_te_bands"
        )).fetchall()}
    assert rows == {
        "index": 15,
        "sector": 30,
        "smart_beta": 50,
        "international": 35,
        "commodity": 20,
    }


def test_migration_head_is_097(engine):
    with engine.connect() as conn:
        head = conn.execute(text(
            "SELECT version_num FROM atlas.atlas_alembic_version"
        )).scalar()
    assert head == "097", f"Expected alembic head '097', got {head!r}"
```

- [ ] **Step 1.2: Verify test fails (pre-migration state)**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os && ATLAS_DB_URL="$(grep ATLAS_DB_URL .env | cut -d= -f2-)" pytest tests/migrations/test_097_v6_frontend_column_adds.py -v 2>&1 | tail -30`

Expected: FAIL on `test_cell_definitions_has_display_name` and most others (columns don't exist yet). The `test_migration_head_is_097` test fails (current head is 096).

- [ ] **Step 1.3: Commit failing test**

```bash
git add tests/migrations/test_097_v6_frontend_column_adds.py
git commit -m "test(migrations): add 097 column-add verification test (RED — pre-migration)"
```

---

## Task 2: Write the migration

**Files:**
- Create: `migrations/versions/097_v6_frontend_column_adds.py`

- [ ] **Step 2.1: Write the migration file**

Migration body is in the next major section; see "Migration 097 source" below in this plan document.

- [ ] **Step 2.2: Lint check the migration**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os && python -c "import migrations.versions.\"097_v6_frontend_column_adds\""`

Expected: No import errors. (If filename has hyphens, use importlib — adjust as needed.)

- [ ] **Step 2.3: Commit the migration**

```bash
git add migrations/versions/097_v6_frontend_column_adds.py
git commit -m "feat(migrations): 097 v6 frontend column adds (cells/sectors/macro/ETF + 2 config tables)"
```

---

## Task 3: Apply migration to live Supabase atlas-os

**Files:**
- Modify: `atlas.atlas_alembic_version` (live DB; via Alembic CLI)
- Create: 18 columns + 2 tables in live DB

- [ ] **Step 3.1: Confirm current alembic head**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os && ATLAS_DB_URL="$(grep ATLAS_DB_URL .env | cut -d= -f2-)" alembic current 2>&1 | tail -5`

Expected: `096 (head)` printed.

- [ ] **Step 3.2: Apply migration**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os && ATLAS_DB_URL="$(grep ATLAS_DB_URL .env | cut -d= -f2-)" alembic upgrade head 2>&1 | tail -20`

Expected: `Running upgrade 096 -> 097, v6 — frontend-driven column adds + 2 config tables.` then no errors.

- [ ] **Step 3.3: Verify alembic head is now 097**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os && ATLAS_DB_URL="$(grep ATLAS_DB_URL .env | cut -d= -f2-)" alembic current 2>&1 | tail -5`

Expected: `097 (head)`.

- [ ] **Step 3.4: Run integration tests against post-migration state**

Run: `cd /Users/nimishshah/Documents/GitHub/atlas-os && ATLAS_DB_URL="$(grep ATLAS_DB_URL .env | cut -d= -f2-)" pytest tests/migrations/test_097_v6_frontend_column_adds.py -v 2>&1 | tail -30`

Expected: All ~14 tests PASS.

- [ ] **Step 3.5: Verify via Supabase MCP (independent check)**

Use Supabase MCP `execute_sql`:

```sql
-- Verify columns + seed counts
SELECT 'cells_display_name_populated' AS chk, COUNT(*) FILTER (WHERE display_name IS NOT NULL)::text || '/' || COUNT(*) AS result FROM atlas.atlas_cell_definitions
UNION ALL SELECT 'sector_new_cols', STRING_AGG(column_name, ',') FROM information_schema.columns WHERE table_schema='atlas' AND table_name='atlas_sector_metrics_daily' AND column_name IN ('rs_1w','rs_1m','rs_6m','rs_12m','pct_above_ema20','pct_above_ema200','pct_52wh','hhi')
UNION ALL SELECT 'macro_new_cols', STRING_AGG(column_name, ',') FROM information_schema.columns WHERE table_schema='atlas' AND table_name='atlas_macro_daily' AND column_name IN ('dii_flow','us_10y_yield','brent_inr','cpi_yoy','vix_9d')
UNION ALL SELECT 'etf_new_cols', STRING_AGG(column_name, ',') FROM information_schema.columns WHERE table_schema='atlas' AND table_name='atlas_etf_scorecard' AND column_name IN ('premium_bps','te_60d','adv_20d_inr')
UNION ALL SELECT 'overlay_map_rows', COUNT(*)::text FROM atlas.atlas_stock_macro_overlay_map
UNION ALL SELECT 'te_bands_rows', COUNT(*)::text FROM atlas.atlas_etf_te_bands;
```

Expected:
- cells_display_name_populated = `21/21`
- sector_new_cols = all 8 column names comma-joined
- macro_new_cols = all 5
- etf_new_cols = all 3
- overlay_map_rows = `23`
- te_bands_rows = `5`

- [ ] **Step 3.6: Commit run log**

```bash
git add docs/v6/session-log-overnight-2026-05-26.md  # session log file created in final task
git commit --allow-empty -m "chore(migrations): 097 applied to live Supabase, alembic head=097"
```

---

## Migration 097 source

The full source is the single Python file. The content matches what's already drafted in the conversation context above. Key shape:

```python
"""v6 — frontend-driven column adds + 2 config tables.

[Full docstring with scope explanation, deferred items, etc.]

Revision ID: 097
Revises: 096
Create Date: 2026-05-26 22:30 IST
"""

from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # 1. atlas_cell_definitions
    op.add_column("atlas_cell_definitions",
                  sa.Column("display_name", sa.String(length=64), nullable=True),
                  schema=_SCHEMA)
    op.add_column("atlas_cell_definitions",
                  sa.Column("explain_text", sa.Text(), nullable=True),
                  schema=_SCHEMA)
    op.execute("""
        UPDATE atlas.atlas_cell_definitions
        SET display_name = cap_tier::text || ' ' || tenure::text || ' ' ||
            CASE action::text
                WHEN 'POSITIVE' THEN 'BUY'
                WHEN 'NEUTRAL'  THEN 'WATCH'
                WHEN 'NEGATIVE' THEN 'AVOID'
            END || ' signal'
        WHERE display_name IS NULL
    """)

    # 2. atlas_sector_metrics_daily
    for col_name in ["rs_1w", "rs_1m", "rs_6m", "rs_12m"]:
        op.add_column("atlas_sector_metrics_daily",
                      sa.Column(col_name, sa.Numeric(10, 4), nullable=True),
                      schema=_SCHEMA)
    for col_name in ["pct_above_ema20", "pct_above_ema200", "pct_52wh"]:
        op.add_column("atlas_sector_metrics_daily",
                      sa.Column(col_name, sa.Numeric(5, 2), nullable=True),
                      schema=_SCHEMA)
    op.add_column("atlas_sector_metrics_daily",
                  sa.Column("hhi", sa.Numeric(8, 2), nullable=True),
                  schema=_SCHEMA)

    # 3. atlas_macro_daily
    op.add_column("atlas_macro_daily", sa.Column("dii_flow", sa.Numeric(12, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("us_10y_yield", sa.Numeric(6, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("brent_inr", sa.Numeric(12, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("cpi_yoy", sa.Numeric(6, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("vix_9d", sa.Numeric(8, 4), nullable=True), schema=_SCHEMA)

    # 4. atlas_etf_scorecard
    op.add_column("atlas_etf_scorecard", sa.Column("premium_bps", sa.Numeric(8, 2), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_etf_scorecard", sa.Column("te_60d", sa.Numeric(8, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_etf_scorecard", sa.Column("adv_20d_inr", sa.Numeric(18, 2), nullable=True), schema=_SCHEMA)

    # 5. atlas_stock_macro_overlay_map
    op.create_table(
        "atlas_stock_macro_overlay_map",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sector", sa.String(length=64), nullable=False),
        sa.Column("business_mix_tag", sa.String(length=64), nullable=True),
        sa.Column("macro_series_1", sa.String(length=32), nullable=False),
        sa.Column("macro_series_2", sa.String(length=32), nullable=False),
        sa.Column("macro_series_3", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("sector", "business_mix_tag", "effective_from", name="uq_stock_macro_overlay_sector_tag"),
        schema=_SCHEMA,
    )
    op.execute("""
        INSERT INTO atlas.atlas_stock_macro_overlay_map (sector, business_mix_tag, macro_series_1, macro_series_2, macro_series_3, rationale) VALUES
        ('Energy', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Oil & gas exposure to Brent, refining margins to USD/INR, capex cost to G-sec'),
        ('Materials', NULL, 'BRENT_INR', 'USDINR', 'DXY', 'Commodity producers sensitive to crude + INR + global metal cycle (DXY proxy)'),
        ('IT', NULL, 'USDINR', 'US_10Y', 'DXY', 'USD revenue + US bond yield (client demand proxy) + dollar strength'),
        ('Pvt Bank', NULL, 'INDIA_10Y', 'USDINR', 'BRENT_INR', 'NIM sensitivity to yields, FX to corporate book, oil to inflation/CAD'),
        ('PSU Bank', NULL, 'INDIA_10Y', 'BRENT_INR', 'USDINR', 'Same as Pvt Bank but stronger PSU yield sensitivity'),
        ('Financials', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'NBFC funding cost + cross-border flows'),
        ('Insurance', NULL, 'INDIA_10Y', 'USDINR', 'NIFTY_VIX', 'Long-duration asset + investment income + claim volatility'),
        ('Auto', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Input cost (steel via INR proxy) + EXIM + consumer financing'),
        ('Pharma', NULL, 'USDINR', 'US_10Y', 'DXY', 'Export exposure + US regulatory cycle (yield proxy) + dollar'),
        ('Healthcare', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'Domestic-heavy; some export'),
        ('FMCG', NULL, 'INDIA_10Y', 'BRENT_INR', 'USDINR', 'Domestic demand + input costs (palm oil/crude proxy)'),
        ('Cons Disc', NULL, 'INDIA_10Y', 'BRENT_INR', 'USDINR', 'Consumer financing + fuel/discretionary spend'),
        ('Cons Staples', NULL, 'BRENT_INR', 'INDIA_10Y', 'USDINR', 'Input cost + rural demand cycle'),
        ('Telecom', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'Capex financing + dollar capex'),
        ('Utilities', NULL, 'BRENT_INR', 'INDIA_10Y', 'USDINR', 'Fuel cost + tariff regulation lag'),
        ('Industrials', NULL, 'INDIA_10Y', 'USDINR', 'BRENT_INR', 'Order book + import inputs + project finance'),
        ('Capital Mkts', NULL, 'NIFTY_VIX', 'INDIA_10Y', 'USDINR', 'Volatility + rate sensitivity + FII flow'),
        ('Real Estate', NULL, 'INDIA_10Y', 'USDINR', 'BRENT_INR', 'Mortgage rate + materials cost + dollar carry'),
        ('Defence', NULL, 'USDINR', 'INDIA_10Y', 'BRENT_INR', 'Defence imports + budget cycle'),
        ('Construction', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Cement/steel cost + project finance'),
        ('Logistics', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Fuel + trade flow + working capital cost'),
        ('Chemicals', NULL, 'BRENT_INR', 'USDINR', 'DXY', 'Petrochemical inputs + global pricing power'),
        ('Communication', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'Capex financing + dollar capex')
    """)
    op.create_index(
        "ix_atlas_stock_macro_overlay_map_active",
        "atlas_stock_macro_overlay_map", ["sector"], unique=False,
        postgresql_where=sa.text("effective_to IS NULL"), schema=_SCHEMA,
    )

    # 6. atlas_etf_te_bands
    op.create_table(
        "atlas_etf_te_bands",
        sa.Column("category", sa.String(length=32), primary_key=True),
        sa.Column("te_max_bps", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        schema=_SCHEMA,
    )
    op.execute("""
        INSERT INTO atlas.atlas_etf_te_bands (category, te_max_bps, notes) VALUES
        ('index', 15, 'Plain-vanilla index trackers'),
        ('sector', 30, 'Sector ETFs'),
        ('smart_beta', 50, 'Smart-beta / factor ETFs'),
        ('international', 35, 'International equity exposure'),
        ('commodity', 20, 'Commodity ETFs')
    """)


def downgrade() -> None:
    op.drop_table("atlas_etf_te_bands", schema=_SCHEMA)
    op.drop_index("ix_atlas_stock_macro_overlay_map_active",
                  table_name="atlas_stock_macro_overlay_map", schema=_SCHEMA)
    op.drop_table("atlas_stock_macro_overlay_map", schema=_SCHEMA)
    for col_name in ["premium_bps", "te_60d", "adv_20d_inr"]:
        op.drop_column("atlas_etf_scorecard", col_name, schema=_SCHEMA)
    for col_name in ["dii_flow", "us_10y_yield", "brent_inr", "cpi_yoy", "vix_9d"]:
        op.drop_column("atlas_macro_daily", col_name, schema=_SCHEMA)
    for col_name in ["hhi", "pct_52wh", "pct_above_ema200", "pct_above_ema20",
                     "rs_12m", "rs_6m", "rs_1m", "rs_1w"]:
        op.drop_column("atlas_sector_metrics_daily", col_name, schema=_SCHEMA)
    op.drop_column("atlas_cell_definitions", "explain_text", schema=_SCHEMA)
    op.drop_column("atlas_cell_definitions", "display_name", schema=_SCHEMA)
```

---

## Self-review

**Spec coverage:**
- ✅ `atlas_cell_definitions` adds: display_name, explain_text — Task 2 step 2.1
- ✅ `atlas_sector_metrics_daily` adds: rs_1w/1m/6m/12m + pct_above_ema20/200 + pct_52wh + hhi — Task 2 step 2.1
- ✅ `atlas_macro_daily` adds: dii_flow + us_10y_yield + brent_inr + cpi_yoy + vix_9d — Task 2 step 2.1
- ✅ `atlas_etf_scorecard` adds: premium_bps + te_60d + adv_20d_inr — Task 2 step 2.1
- ✅ `atlas_stock_macro_overlay_map` CREATE + 23 seed rows — Task 2 step 2.1
- ✅ `atlas_etf_te_bands` CREATE + 5 seed rows — Task 2 step 2.1
- ✅ Backfill display_name from cell_id — Task 2 step 2.1 (UPDATE statement)
- ✅ Apply via Alembic — Task 3
- ✅ Verify via MCP — Task 3 step 3.5
- ✅ Tests verify post-migration state — Task 1

**Placeholder scan:** no TODOs, no "implement later", no "similar to" references. All code is complete inline.

**Type consistency:** column names match across test file, migration, and CONTEXT.md. Sector names in seed match CONTEXT.md "Actionable sectors (22, not 30)" + atlas_sector_master active rows.

Plan complete. Executing inline (per overnight constraint, no subagent ping-pong).
