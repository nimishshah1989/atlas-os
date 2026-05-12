# SP04 Stage 3 — Conviction Composite Production Deployment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED PRE-FLIGHT:** Before touching code, read `docs/phase2/00-master-plan.html` SP04 section, and the output of the Stage 2 holdout test at `/private/tmp/claude-501/-Users-nimishshah-Documents-GitHub-atlas-os/b03c7f67-fe54-4643-8fc6-c6dce97c8b0f/tasks/bs61oxsuk.output` — that file contains the exact tier-by-tier weights that this plan seeds into production.
>
> **Required review gates per CLAUDE.md:** This plan MUST pass `/plan-eng-review` AND the frontend portion MUST pass `/plan-design-review` BEFORE execution begins. After execution, `/review` runs on the diff and `/qa` validates on production.

**Goal:** Deploy the Stage-2-validated v2 conviction composite to production — tiered weights for top 1000 NSE names by ADV, computed nightly, surfaced on Atlas frontend with tier-honest confidence labels, consumed by SP07 stock-screener agent + Daily Brief.

**Architecture:** Three new audit-tracked Postgres tables (signal weights, daily conviction scores, daily tier membership) populated by a new `atlas.intelligence.conviction` Python module running in the nightly pipeline. Frontend reads via a materialized view refreshed by pg_cron. Tier-conditional UI badges (industry_grade / baseline / descriptive_only) prevent users from over-trusting weak-tier scores.

**Tech Stack:** Python 3.12, Pandas, SQLAlchemy 2.0, FastAPI, Supabase Postgres (pg_cron), Next.js 15 + Tailwind, Recharts.

**Out-of-scope (handled in Stage 4 or later):** Continuous auto-optimization, FM approval workflow, regime-conditioned weight sets, new signal types (fundamentals/flows). Stage 3 ships static weights; Stage 4 makes them adaptive.

---

## File Structure

**Database (new):**
- `migrations/versions/039_create_conviction_tables.py` — 3 tables + 1 materialized view + pg_cron schedule

**Backend (new bounded sub-context `atlas.intelligence.conviction`):**
- `atlas/intelligence/conviction/__init__.py` — public API exports
- `atlas/intelligence/conviction/tier_assignment.py` — assign each stock to a liquidity tier per date
- `atlas/intelligence/conviction/composer.py` — compute conviction score per (stock, date) using tier-active weights
- `atlas/intelligence/conviction/persistence.py` — UPSERT to `atlas_stock_conviction_daily` and `atlas_tier_membership_daily`
- `atlas/intelligence/conviction/weight_loader.py` — load currently-active weight set per tier
- `scripts/compute_conviction.py` — nightly CLI orchestrator
- `scripts/seed_signal_weights.py` — one-shot seeder for the Stage-2 baseline weights

**Backend (modify):**
- `atlas/agents/specialists/stock_screener.py` — switch to conviction-ranked output
- `atlas/agents/tools/atlas_queries.py` — add `get_top_conviction` tool
- `atlas/agents/tools/registry.py` — register the new tool

**Frontend (new):**
- `frontend/src/lib/queries/conviction.ts` — server-only queries against conviction tables
- `frontend/src/components/stocks/ConvictionCell.tsx` — table cell with score + tier badge
- `frontend/src/components/stocks/ConvictionBreakdownPanel.tsx` — deep-dive breakdown chart
- `frontend/src/components/intelligence/TopConvictionSection.tsx` — dashboard section

**Frontend (modify — surgical):**
- `frontend/src/app/stocks/page.tsx` — wire Conviction column into the existing screener table
- `frontend/src/app/stocks/[symbol]/page.tsx` — slot the breakdown panel into the deep dive
- `frontend/src/app/intelligence/page.tsx` — add `TopConvictionSection` to the dashboard

**Tests (new):**
- `tests/intelligence/conviction/test_tier_assignment.py` — 4 tests
- `tests/intelligence/conviction/test_composer.py` — 5 tests
- `tests/intelligence/conviction/test_weight_loader.py` — 3 tests
- `tests/intelligence/conviction/test_persistence.py` — 2 integration tests
- `tests/intelligence/conviction/test_cli_smoke.py` — 1 integration smoke
- `frontend/playwright/conviction.spec.ts` — 3 e2e smoke tests

---

## Stage-2-validated weights to seed (READ THIS — DO NOT INVENT NEW WEIGHTS)

The Stage 2 holdout test produced these weights. They must be seeded verbatim. The full weight set is below.

**T1: 1-50 (NIFTY mega-cap) — Confidence: `industry_grade` (holdout IC 0.0511, t=6.19)**

| signal | weight | flipped |
|---|---|---|
| ma_30w_slope_4w | 0.161 | false |
| ret_6m | 0.145 | false |
| ret_12m_1m | 0.131 | false |
| extension_pct | 0.121 | false |
| vol_ratio_63 | 0.119 | false |
| effort_ratio_63 | 0.095 | false |
| realized_vol_63 | 0.082 | false |
| max_drawdown_252 | 0.067 | false |
| rs_pctile_3m | 0.053 | false |
| ema_10_ratio | 0.019 | false |
| atr_21 | 0.006 | **true** |

**T2: 51-150 (large-cap) — Confidence: `baseline` (holdout IC 0.0068, t=1.12)**

| signal | weight | flipped |
|---|---|---|
| ma_30w_slope_4w | 0.178 | false |
| ret_12m_1m | 0.170 | false |
| ret_6m | 0.146 | false |
| extension_pct | 0.141 | false |
| rs_pctile_3m | 0.115 | false |
| vol_ratio_63 | 0.074 | false |
| effort_ratio_63 | 0.069 | false |
| atr_21 | 0.058 | **true** |
| ema_10_ratio | 0.046 | false |
| realized_vol_63 | 0.003 | false |

**T3: 151-300 (upper mid-cap) — Confidence: `industry_grade` (holdout IC 0.0538, t=8.53)**

| signal | weight | flipped |
|---|---|---|
| ma_30w_slope_4w | 0.252 | false |
| ret_12m_1m | 0.234 | false |
| ret_6m | 0.158 | false |
| extension_pct | 0.152 | false |
| effort_ratio_63 | 0.086 | false |
| atr_21 | 0.078 | **true** |
| rs_pctile_3m | 0.041 | false |

**T4: 301-500 (lower mid-cap) — Confidence: `baseline` (holdout IC 0.0268, t=3.81)**

| signal | weight | flipped |
|---|---|---|
| ma_30w_slope_4w | 0.172 | false |
| max_drawdown_252 | 0.161 | false |
| ret_12m_1m | 0.149 | false |
| atr_21 | 0.120 | **true** |
| effort_ratio_63 | 0.115 | false |
| realized_vol_63 | 0.092 | false |
| extension_pct | 0.076 | false |
| vol_ratio_63 | 0.062 | false |
| ret_6m | 0.053 | false |

**T5: 501-1000 (small-cap) — Confidence: `baseline` (holdout IC 0.0413, t=5.70)**

| signal | weight | flipped |
|---|---|---|
| ret_12m_1m | 0.195 | false |
| ma_30w_slope_4w | 0.185 | false |
| ret_6m | 0.155 | false |
| extension_pct | 0.143 | false |
| rs_pctile_3m | 0.103 | false |
| atr_21 | 0.080 | **true** |
| effort_ratio_63 | 0.069 | false |
| ema_10_ratio | 0.057 | false |
| vol_ratio_63 | 0.013 | false |

**Holdout IC for `backing_ic` column:** T1=0.0511, T2=0.0068, T3=0.0538, T4=0.0268, T5=0.0413.

---

## Task 0: Pre-flight + verify EC2 state

**Files:** none (verification only)

- [ ] **Step 1: Read the Stage 2 output verbatim**

Open `/private/tmp/claude-501/-Users-nimishshah-Documents-GitHub-atlas-os/b03c7f67-fe54-4643-8fc6-c6dce97c8b0f/tasks/bs61oxsuk.output`. Confirm the weights above match the file. If they differ, the file is authoritative.

- [ ] **Step 2: Verify EC2 baseline**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  'cd /home/ubuntu/atlas-os && source .venv/bin/activate && alembic current 2>&1 | tail -2'
```

Expected: `038 (head)`. If different, halt and flag.

- [ ] **Step 3: Confirm signal columns exist in `atlas_stock_metrics_daily`**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  'cd /home/ubuntu/atlas-os && source .venv/bin/activate && python3 -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
needed = [\"rs_pctile_3m\",\"ret_6m\",\"ret_12m_1m\",\"ema_10_ratio\",\"extension_pct\",\"vol_ratio_63\",\"max_drawdown_252\",\"realized_vol_63\",\"atr_21\",\"ma_30w_slope_4w\",\"effort_ratio_63\"]
with e.connect() as c:
    cols = [r[0] for r in c.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_schema=\\'atlas\\' AND table_name=\\'atlas_stock_metrics_daily\\'\")).fetchall()]
    missing = [n for n in needed if n not in cols]
    print(\"Missing:\", missing if missing else \"none\")
"'
```

Expected: `Missing: none`. If any are missing, halt.

---

## Task 1: Migration 039 — three tables + materialized view

**Files:**
- Create: `migrations/versions/039_create_conviction_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""SP04 Stage 3 — conviction tables: signal_weights, stock_conviction_daily,
tier_membership_daily, plus mv_top_conviction_daily materialized view.

Revision ID: 039
Revises: 038
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. atlas_signal_weights — audit-tracked, currently-active weights per tier × signal
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_signal_weights (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tier            VARCHAR(32) NOT NULL,
            regime          VARCHAR(16) NOT NULL DEFAULT 'all',
            signal_name     VARCHAR(64) NOT NULL,
            weight          NUMERIC(8, 6) NOT NULL,
            flipped         BOOLEAN NOT NULL DEFAULT FALSE,
            effective_from  DATE NOT NULL,
            effective_to    DATE,
            train_ic        NUMERIC(8, 6),
            holdout_ic      NUMERIC(8, 6),
            approved_by     VARCHAR(64) NOT NULL DEFAULT 'sp04-stage2-initial',
            approved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_weights_tier CHECK (tier IN (
                'tier_1_megacap','tier_2_largecap','tier_3_uppermid',
                'tier_4_lowermid','tier_5_smallcap'
            )),
            CONSTRAINT chk_weights_regime CHECK (regime IN (
                'Risk-On','Constructive','Cautious','Risk-Off','all'
            )),
            CONSTRAINT chk_weights_value CHECK (weight >= 0 AND weight <= 1)
        )
    """))

    # At most one active (effective_to IS NULL) row per (tier, regime, signal_name)
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_weights_active
        ON atlas.atlas_signal_weights (tier, regime, signal_name)
        WHERE effective_to IS NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_signal_weights_lookup
        ON atlas.atlas_signal_weights (tier, regime)
        WHERE effective_to IS NULL
    """))

    # 2. atlas_tier_membership_daily — which liquidity tier each instrument occupies
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_tier_membership_daily (
            instrument_id   UUID NOT NULL,
            date            DATE NOT NULL,
            tier            VARCHAR(32) NOT NULL,
            adv_rank        INTEGER NOT NULL,
            adv_20d         NUMERIC(20, 2),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date),
            CONSTRAINT chk_tier_value CHECK (tier IN (
                'tier_1_megacap','tier_2_largecap','tier_3_uppermid',
                'tier_4_lowermid','tier_5_smallcap','untiered'
            ))
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_tier_membership_date_tier
        ON atlas.atlas_tier_membership_daily (date DESC, tier)
    """))

    # 3. atlas_stock_conviction_daily — computed conviction per (stock, date)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_conviction_daily (
            instrument_id        UUID NOT NULL,
            date                 DATE NOT NULL,
            tier                 VARCHAR(32) NOT NULL,
            conviction_score     NUMERIC(6, 4) NOT NULL,
            confidence_label     VARCHAR(32) NOT NULL,
            backing_ic           NUMERIC(8, 6),
            contributing_signals JSONB NOT NULL,
            weight_set_version   VARCHAR(64) NOT NULL,
            computed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date),
            CONSTRAINT chk_conviction_score CHECK (conviction_score >= 0 AND conviction_score <= 1),
            CONSTRAINT chk_conviction_label CHECK (confidence_label IN (
                'industry_grade','baseline','descriptive_only'
            ))
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_conviction_date_tier_score
        ON atlas.atlas_stock_conviction_daily (date DESC, tier, conviction_score DESC)
    """))

    # 4. Materialized view: latest-date top conviction names, only industry_grade + baseline
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_top_conviction_daily AS
        SELECT
            c.instrument_id,
            c.date,
            c.tier,
            c.conviction_score,
            c.confidence_label,
            c.backing_ic,
            c.contributing_signals
        FROM atlas.atlas_stock_conviction_daily c
        WHERE c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
          AND c.confidence_label IN ('industry_grade', 'baseline')
        ORDER BY c.tier, c.conviction_score DESC
    """))
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_top_conviction_instrument
        ON atlas.mv_top_conviction_daily (instrument_id)
    """))

    # 5. pg_cron schedule (guarded — extension may not be available locally)
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                PERFORM cron.schedule(
                    'atlas_mv_conviction',
                    '45 14 * * *',  -- 20:15 IST, after nightly compute
                    $cmd$REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_top_conviction_daily$cmd$
                );
            ELSE
                RAISE NOTICE 'pg_cron not installed — skipping schedule. Apply on EC2.';
            END IF;
        END$$;
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_top_conviction_daily"))
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                PERFORM cron.unschedule('atlas_mv_conviction');
            END IF;
        EXCEPTION WHEN OTHERS THEN NULL;
        END$$;
    """))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_stock_conviction_daily"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_tier_membership_daily"))
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.uq_signal_weights_active"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_signal_weights"))
```

- [ ] **Step 2: Apply migration locally**

Run: `alembic upgrade head 2>&1 | tail -5`
Expected: `Running upgrade 038 -> 039, SP04 Stage 3 — conviction tables...`

- [ ] **Step 3: Verify tables created**

Run: `python3 -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.connect() as c:
    for t in ['atlas_signal_weights','atlas_tier_membership_daily','atlas_stock_conviction_daily']:
        r = c.execute(text(f\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='atlas' AND table_name='{t}'\")).scalar()
        print(t, '=', r)
"`
Expected: all three return 1.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/039_create_conviction_tables.py
git commit -m "feat(sp04-stage3): migration 039 — conviction tables (signal_weights, tier_membership, stock_conviction)"
```

---

## Task 2: Seed Stage-2 weights

**Files:**
- Create: `scripts/seed_signal_weights.py`
- Create: `tests/intelligence/conviction/__init__.py` (empty marker)

- [ ] **Step 1: Write the seeder**

```python
"""One-shot seeder for the Stage 2 validated weights.

Idempotent: safe to re-run. If a weight set already exists for the
(tier, regime, signal, effective_from) combination, INSERT is skipped.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import text

from atlas.db import get_engine

log = structlog.get_logger()

# Holdout IC per tier from Stage 2 (2023-2025 out-of-sample)
TIER_HOLDOUT_IC: dict[str, Decimal] = {
    "tier_1_megacap":  Decimal("0.0511"),
    "tier_2_largecap": Decimal("0.0068"),
    "tier_3_uppermid": Decimal("0.0538"),
    "tier_4_lowermid": Decimal("0.0268"),
    "tier_5_smallcap": Decimal("0.0413"),
}

# (signal_name, weight, flipped) per tier — from Stage 2 holdout-validated output
WEIGHTS: dict[str, list[tuple[str, Decimal, bool]]] = {
    "tier_1_megacap": [
        ("ma_30w_slope_4w",   Decimal("0.161"), False),
        ("ret_6m",            Decimal("0.145"), False),
        ("ret_12m_1m",        Decimal("0.131"), False),
        ("extension_pct",     Decimal("0.121"), False),
        ("vol_ratio_63",      Decimal("0.119"), False),
        ("effort_ratio_63",   Decimal("0.095"), False),
        ("realized_vol_63",   Decimal("0.082"), False),
        ("max_drawdown_252",  Decimal("0.067"), False),
        ("rs_pctile_3m",      Decimal("0.053"), False),
        ("ema_10_ratio",      Decimal("0.019"), False),
        ("atr_21",            Decimal("0.006"), True),
    ],
    "tier_2_largecap": [
        ("ma_30w_slope_4w",   Decimal("0.178"), False),
        ("ret_12m_1m",        Decimal("0.170"), False),
        ("ret_6m",            Decimal("0.146"), False),
        ("extension_pct",     Decimal("0.141"), False),
        ("rs_pctile_3m",      Decimal("0.115"), False),
        ("vol_ratio_63",      Decimal("0.074"), False),
        ("effort_ratio_63",   Decimal("0.069"), False),
        ("atr_21",            Decimal("0.058"), True),
        ("ema_10_ratio",      Decimal("0.046"), False),
        ("realized_vol_63",   Decimal("0.003"), False),
    ],
    "tier_3_uppermid": [
        ("ma_30w_slope_4w",   Decimal("0.252"), False),
        ("ret_12m_1m",        Decimal("0.234"), False),
        ("ret_6m",            Decimal("0.158"), False),
        ("extension_pct",     Decimal("0.152"), False),
        ("effort_ratio_63",   Decimal("0.086"), False),
        ("atr_21",            Decimal("0.078"), True),
        ("rs_pctile_3m",      Decimal("0.041"), False),
    ],
    "tier_4_lowermid": [
        ("ma_30w_slope_4w",   Decimal("0.172"), False),
        ("max_drawdown_252",  Decimal("0.161"), False),
        ("ret_12m_1m",        Decimal("0.149"), False),
        ("atr_21",            Decimal("0.120"), True),
        ("effort_ratio_63",   Decimal("0.115"), False),
        ("realized_vol_63",   Decimal("0.092"), False),
        ("extension_pct",     Decimal("0.076"), False),
        ("vol_ratio_63",      Decimal("0.062"), False),
        ("ret_6m",            Decimal("0.053"), False),
    ],
    "tier_5_smallcap": [
        ("ret_12m_1m",        Decimal("0.195"), False),
        ("ma_30w_slope_4w",   Decimal("0.185"), False),
        ("ret_6m",            Decimal("0.155"), False),
        ("extension_pct",     Decimal("0.143"), False),
        ("rs_pctile_3m",      Decimal("0.103"), False),
        ("atr_21",            Decimal("0.080"), True),
        ("effort_ratio_63",   Decimal("0.069"), False),
        ("ema_10_ratio",      Decimal("0.057"), False),
        ("vol_ratio_63",      Decimal("0.013"), False),
    ],
}

NOTES = (
    "Initial seeding from SP04 Stage 2 holdout test. "
    "Train period 2019-2022, holdout 2023-2025. "
    "See /private/tmp/.../bs61oxsuk.output for full evidence."
)

INSERT_SQL = """
    INSERT INTO atlas.atlas_signal_weights
        (tier, regime, signal_name, weight, flipped,
         effective_from, effective_to, train_ic, holdout_ic,
         approved_by, notes)
    VALUES
        (:tier, 'all', :signal_name, :weight, :flipped,
         :eff_from, NULL, NULL, :holdout_ic,
         'sp04-stage2-initial', :notes)
    ON CONFLICT (tier, regime, signal_name) WHERE effective_to IS NULL
    DO NOTHING
"""


def main() -> int:
    engine = get_engine()
    today = date.today()
    inserted = 0
    skipped = 0
    with engine.begin() as conn:
        for tier, rows in WEIGHTS.items():
            for signal_name, weight, flipped in rows:
                result = conn.execute(
                    text(INSERT_SQL),
                    {
                        "tier": tier,
                        "signal_name": signal_name,
                        "weight": weight,
                        "flipped": flipped,
                        "eff_from": today,
                        "holdout_ic": TIER_HOLDOUT_IC[tier],
                        "notes": NOTES,
                    },
                )
                if result.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
    log.info("seed_signal_weights_complete", inserted=inserted, skipped=skipped)
    print(f"Inserted {inserted} rows; skipped {skipped} (already active)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create test marker files**

```bash
mkdir -p tests/intelligence/conviction
touch tests/intelligence/conviction/__init__.py
```

- [ ] **Step 3: Run seeder locally**

Run: `python scripts/seed_signal_weights.py`
Expected: `Inserted 47 rows; skipped 0 (already active)`
(47 = sum of weights across all 5 tiers: 11 + 10 + 7 + 9 + 9 = 46... wait, recount: T1=11, T2=10, T3=7, T4=9, T5=9 = 46. Adjust expected to 46.)

- [ ] **Step 4: Verify seeded data**

Run: `python3 -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.connect() as c:
    rows = c.execute(text('''
        SELECT tier, COUNT(*) AS n_signals, SUM(weight)::numeric(8,4) AS weight_sum, MAX(holdout_ic) AS ic
        FROM atlas.atlas_signal_weights
        WHERE effective_to IS NULL AND regime = 'all'
        GROUP BY tier ORDER BY tier
    ''')).fetchall()
    for r in rows: print(r)
"`
Expected: weight_sum per tier should be ≈ 1.000 (sums of normalized weights).

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_signal_weights.py tests/intelligence/conviction/__init__.py
git commit -m "feat(sp04-stage3): seed Stage-2 validated weights into atlas_signal_weights"
```

---

## Task 3: `weight_loader.py` (pure function, no I/O abstraction)

**Files:**
- Create: `atlas/intelligence/__init__.py` (verify exists from SP01 — should already)
- Create: `atlas/intelligence/conviction/__init__.py`
- Create: `atlas/intelligence/conviction/weight_loader.py`
- Create: `tests/intelligence/conviction/test_weight_loader.py`

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/conviction/test_weight_loader.py`:

```python
"""Tests for weight_loader — loads currently-active weight sets per tier."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.weight_loader import (
    TierWeightSet,
    load_active_weights,
)


@pytest.mark.integration
class TestLoadActiveWeights:
    def test_returns_one_set_per_tier(self):
        engine = get_engine()
        result = load_active_weights(engine)
        # All 5 tiers seeded
        assert set(result.keys()) == {
            "tier_1_megacap", "tier_2_largecap", "tier_3_uppermid",
            "tier_4_lowermid", "tier_5_smallcap",
        }

    def test_weights_are_decimals(self):
        engine = get_engine()
        result = load_active_weights(engine)
        tier_1 = result["tier_1_megacap"]
        assert isinstance(tier_1, TierWeightSet)
        assert all(isinstance(w, Decimal) for _, w, _ in tier_1.signals)

    def test_atr_21_flipped_for_tier_1(self):
        engine = get_engine()
        result = load_active_weights(engine)
        tier_1 = result["tier_1_megacap"]
        atr_entries = [(s, w, f) for s, w, f in tier_1.signals if s == "atr_21"]
        assert len(atr_entries) == 1
        assert atr_entries[0][2] is True
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/intelligence/conviction/test_weight_loader.py -v -m integration
```
Expected: ImportError.

- [ ] **Step 3: Create package markers**

`atlas/intelligence/conviction/__init__.py`:

```python
"""SP04 Stage 3 — conviction composite production module.

Public surface:

- weight_loader: load currently-active weight sets per tier
- tier_assignment: compute liquidity tier for each instrument per date
- composer: produce conviction_score per (instrument, date)
- persistence: UPSERT to atlas_stock_conviction_daily + atlas_tier_membership_daily

See docs/phase2/plans/2026-05-12-sp04-stage3-conviction-production.md
"""

from atlas.intelligence.conviction.weight_loader import (
    TierWeightSet,
    load_active_weights,
)

__all__ = ["TierWeightSet", "load_active_weights"]
```

- [ ] **Step 4: Implement `weight_loader.py`**

```python
"""Load the currently-active signal weight set per tier from atlas_signal_weights."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

_TIERS: Final[tuple[str, ...]] = (
    "tier_1_megacap",
    "tier_2_largecap",
    "tier_3_uppermid",
    "tier_4_lowermid",
    "tier_5_smallcap",
)


@dataclass(frozen=True)
class TierWeightSet:
    """The active weight set for one (tier, regime) combination."""

    tier: str
    regime: str
    holdout_ic: Decimal | None
    signals: list[tuple[str, Decimal, bool]]  # (signal_name, weight, flipped)
    weight_set_version: str  # used for atlas_stock_conviction_daily.weight_set_version


def load_active_weights(engine: Engine, regime: str = "all") -> dict[str, TierWeightSet]:
    """Load currently-active weight sets per tier for the given regime.

    Returns dict keyed by tier name. Empty dict if no weights are seeded.
    """
    sql = text("""
        SELECT tier, regime, signal_name, weight, flipped, holdout_ic, approved_at
        FROM atlas.atlas_signal_weights
        WHERE effective_to IS NULL
          AND regime = :regime
        ORDER BY tier, weight DESC
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"regime": regime}).fetchall()

    by_tier: dict[str, list] = {}
    holdout_by_tier: dict[str, Decimal | None] = {}
    latest_approval: dict[str, str] = {}
    for r in rows:
        tier = r[0]
        by_tier.setdefault(tier, []).append((r[2], Decimal(str(r[3])), bool(r[4])))
        if r[5] is not None and tier not in holdout_by_tier:
            holdout_by_tier[tier] = Decimal(str(r[5]))
        # Version stamp: tier + ISO approval timestamp
        latest_approval[tier] = f"{tier}@{r[6].isoformat()}"

    result: dict[str, TierWeightSet] = {}
    for tier in _TIERS:
        if tier in by_tier:
            result[tier] = TierWeightSet(
                tier=tier,
                regime=regime,
                holdout_ic=holdout_by_tier.get(tier),
                signals=by_tier[tier],
                weight_set_version=latest_approval[tier],
            )
    log.info("active_weights_loaded", regime=regime, n_tiers=len(result))
    return result
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/intelligence/conviction/test_weight_loader.py -v -m integration
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add atlas/intelligence/conviction/__init__.py \
        atlas/intelligence/conviction/weight_loader.py \
        tests/intelligence/conviction/test_weight_loader.py
git commit -m "feat(sp04-stage3): weight_loader — active per-tier weight sets from atlas_signal_weights"
```

---

## Task 4: `tier_assignment.py`

**Files:**
- Create: `atlas/intelligence/conviction/tier_assignment.py`
- Create: `tests/intelligence/conviction/test_tier_assignment.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for tier_assignment — compute 20-day ADV rank per instrument per date."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.db import get_engine
from atlas.intelligence.conviction.tier_assignment import (
    TIER_BOUNDS,
    assign_tier_from_rank,
    compute_tier_membership,
)


class TestAssignTierFromRank:
    def test_rank_1_is_megacap(self):
        assert assign_tier_from_rank(1) == "tier_1_megacap"

    def test_rank_50_is_megacap(self):
        assert assign_tier_from_rank(50) == "tier_1_megacap"

    def test_rank_51_is_largecap(self):
        assert assign_tier_from_rank(51) == "tier_2_largecap"

    def test_rank_999_is_smallcap(self):
        assert assign_tier_from_rank(999) == "tier_5_smallcap"

    def test_rank_1001_is_untiered(self):
        assert assign_tier_from_rank(1001) == "untiered"


@pytest.mark.integration
class TestComputeTierMembership:
    def test_returns_dataframe_with_required_columns(self):
        engine = get_engine()
        df = compute_tier_membership(engine, as_of=date(2026, 4, 1))
        assert {"instrument_id", "date", "tier", "adv_rank", "adv_20d"} <= set(df.columns)

    def test_top_50_are_tier_1(self):
        engine = get_engine()
        df = compute_tier_membership(engine, as_of=date(2026, 4, 1))
        top_50 = df.nsmallest(50, "adv_rank")
        assert (top_50["tier"] == "tier_1_megacap").all()
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
pytest tests/intelligence/conviction/test_tier_assignment.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `tier_assignment.py`**

```python
"""Compute liquidity-tier membership per instrument per date.

Tiers are defined by 20-day ADV (Average Daily Value = volume × close_adj)
rank within the universe of NSE-listed names. Top 1000 names are placed in
one of five tiers; the rest are 'untiered' and excluded from conviction
scoring.

See docs/phase2/plans/2026-05-12-sp04-stage3-conviction-production.md
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

TIER_BOUNDS: Final[list[tuple[str, int, int]]] = [
    ("tier_1_megacap",  1,    50),
    ("tier_2_largecap", 51,   150),
    ("tier_3_uppermid", 151,  300),
    ("tier_4_lowermid", 301,  500),
    ("tier_5_smallcap", 501,  1000),
]


def assign_tier_from_rank(rank: int) -> str:
    """Return the tier name for a given ADV rank. Ranks > 1000 → 'untiered'."""
    for tier, lo, hi in TIER_BOUNDS:
        if lo <= rank <= hi:
            return tier
    return "untiered"


_ADV_SQL = """
    SELECT instrument_id::text AS instrument_id,
           AVG(volume * close_adj) AS adv_20d
    FROM public.de_equity_ohlcv
    WHERE date BETWEEN :window_start AND :window_end
      AND data_status = 'validated'
      AND volume > 0
      AND close_adj > 0
    GROUP BY instrument_id
    HAVING COUNT(*) >= 15
"""


def compute_tier_membership(engine: Engine, *, as_of: date) -> pd.DataFrame:
    """Compute tier membership for the top 1000 instruments by 20-day ADV ending as_of.

    Returns DataFrame: instrument_id, date, tier, adv_rank, adv_20d.
    Instruments outside the top 1000 are not included in the result.
    """
    window_start = as_of - timedelta(days=35)
    with engine.connect() as conn:
        raw = pd.read_sql(
            text(_ADV_SQL),
            conn,
            params={"window_start": window_start, "window_end": as_of},
        )
    if raw.empty:
        log.warning("tier_membership_empty", as_of=str(as_of))
        return pd.DataFrame(columns=["instrument_id", "date", "tier", "adv_rank", "adv_20d"])

    raw["adv_20d"] = pd.to_numeric(raw["adv_20d"])
    raw = raw.sort_values("adv_20d", ascending=False).reset_index(drop=True)
    raw["adv_rank"] = raw.index + 1
    top_1000 = raw.head(1000).copy()
    top_1000["tier"] = top_1000["adv_rank"].apply(assign_tier_from_rank)
    top_1000["date"] = as_of
    log.info(
        "tier_membership_computed",
        as_of=str(as_of),
        n_top_1000=len(top_1000),
        n_megacap=int((top_1000["tier"] == "tier_1_megacap").sum()),
    )
    return top_1000[["instrument_id", "date", "tier", "adv_rank", "adv_20d"]]
```

- [ ] **Step 4: Re-run tests**

```bash
pytest tests/intelligence/conviction/test_tier_assignment.py -v
```
Expected: 6 passed (4 unit + 2 integration).

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/conviction/tier_assignment.py \
        tests/intelligence/conviction/test_tier_assignment.py
git commit -m "feat(sp04-stage3): tier_assignment — top-1000 ADV ranking + 5-tier bucketing"
```

---

## Task 5: `composer.py`

**Files:**
- Create: `atlas/intelligence/conviction/composer.py`
- Create: `tests/intelligence/conviction/test_composer.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for composer — produce conviction_score per (instrument, date)."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.conviction.composer import (
    CONFIDENCE_LABEL_THRESHOLD,
    assign_confidence_label,
    apply_weights_to_percentile_ranks,
    compute_conviction_scores,
)
from atlas.intelligence.conviction.weight_loader import TierWeightSet


@pytest.fixture
def tier_1_weights() -> TierWeightSet:
    return TierWeightSet(
        tier="tier_1_megacap",
        regime="all",
        holdout_ic=Decimal("0.0511"),
        signals=[
            ("ma_30w_slope_4w", Decimal("0.5"), False),
            ("atr_21",          Decimal("0.5"), True),
        ],
        weight_set_version="tier_1_megacap@2026-05-12T00:00:00",
    )


@pytest.fixture
def sample_raw_with_ranks() -> pd.DataFrame:
    return pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "ma_30w_slope_4w_pct": [0.9, 0.5, 0.1, 0.7],
        "atr_21_pct":          [0.1, 0.5, 0.9, 0.3],
    })


class TestAssignConfidenceLabel:
    def test_holdout_ic_above_threshold_is_industry_grade(self):
        assert assign_confidence_label(Decimal("0.0511")) == "industry_grade"

    def test_holdout_ic_below_threshold_is_baseline(self):
        assert assign_confidence_label(Decimal("0.0268")) == "baseline"

    def test_none_holdout_is_descriptive_only(self):
        assert assign_confidence_label(None) == "descriptive_only"

    def test_threshold_constant(self):
        assert CONFIDENCE_LABEL_THRESHOLD == Decimal("0.05")


class TestApplyWeights:
    def test_perfectly_aligned_signals_give_high_score(self, tier_1_weights, sample_raw_with_ranks):
        scored = apply_weights_to_percentile_ranks(
            sample_raw_with_ranks, tier_1_weights,
        )
        # A has high ma_30w_slope (0.9) but low atr_21 (0.1) — when atr_21 is flipped
        # this becomes 0.9. So A's score: 0.5*0.9 + 0.5*(1-0.1) = 0.9
        a_score = scored.loc[scored["instrument_id"] == "A", "conviction_score"].iloc[0]
        assert a_score == pytest.approx(0.9, abs=0.001)

    def test_score_in_unit_interval(self, tier_1_weights, sample_raw_with_ranks):
        scored = apply_weights_to_percentile_ranks(
            sample_raw_with_ranks, tier_1_weights,
        )
        assert scored["conviction_score"].between(0.0, 1.0).all()

    def test_missing_signal_column_skips_signal(self, tier_1_weights):
        df = pd.DataFrame({
            "instrument_id": ["A"],
            "ma_30w_slope_4w_pct": [0.5],
            # atr_21_pct missing
        })
        scored = apply_weights_to_percentile_ranks(df, tier_1_weights)
        # With atr_21 contribution missing, score = 0.5 * 0.5 / 0.5 (renormalized)
        # = 0.5
        assert scored["conviction_score"].iloc[0] == pytest.approx(0.5, abs=0.001)


@pytest.mark.integration
class TestComputeConvictionScores:
    def test_returns_scores_for_all_tiered_instruments(self):
        from atlas.db import get_engine
        engine = get_engine()
        df = compute_conviction_scores(engine, as_of=date(2026, 4, 1))
        assert "conviction_score" in df.columns
        assert "confidence_label" in df.columns
        assert "contributing_signals" in df.columns
        # Should have rows for all tiered instruments (≤1000)
        assert 1 <= len(df) <= 1000
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
pytest tests/intelligence/conviction/test_composer.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `composer.py`**

```python
"""Compute conviction scores per (instrument, date) using tier-active weight sets.

Process per stock:
1. Identify the stock's liquidity tier (from tier_assignment).
2. Load the currently-active weight set for that tier.
3. Cross-sectionally rank each signal within the tier (percentile rank).
4. Apply weights: score = sum(weight_i * (rank_i if not flipped else 1 - rank_i)).
5. Normalize by sum of weights actually applied (in case a signal is missing).
6. Build contributing_signals JSONB with per-signal breakdown.
7. Assign confidence label based on tier's measured holdout IC.

See docs/phase2/plans/2026-05-12-sp04-stage3-conviction-production.md
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.tier_assignment import compute_tier_membership
from atlas.intelligence.conviction.weight_loader import TierWeightSet, load_active_weights

log = structlog.get_logger()

CONFIDENCE_LABEL_THRESHOLD: Final[Decimal] = Decimal("0.05")
SIGNAL_COLUMNS: Final[tuple[str, ...]] = (
    "rs_pctile_3m", "ret_6m", "ret_12m_1m",
    "ema_10_ratio", "extension_pct",
    "vol_ratio_63", "max_drawdown_252", "realized_vol_63",
    "atr_21", "ma_30w_slope_4w", "effort_ratio_63",
)


def assign_confidence_label(holdout_ic: Decimal | None) -> str:
    """Map measured holdout IC to a frontend confidence badge."""
    if holdout_ic is None:
        return "descriptive_only"
    if abs(holdout_ic) >= CONFIDENCE_LABEL_THRESHOLD:
        return "industry_grade"
    return "baseline"


def apply_weights_to_percentile_ranks(
    df: pd.DataFrame, weights: TierWeightSet
) -> pd.DataFrame:
    """Given percentile-ranked signal columns, apply weights, return scored df.

    df must have columns `instrument_id` + `<signal>_pct` for each signal in
    weights.signals that's available. Missing signals are skipped and the
    remaining weights are renormalized so score is still in [0,1].
    """
    out = df[["instrument_id"]].copy()
    weighted_sum = pd.Series(0.0, index=df.index)
    weight_applied_total = 0.0
    breakdown_per_row: list[dict] = [{} for _ in range(len(df))]

    for signal_name, weight, flipped in weights.signals:
        col = f"{signal_name}_pct"
        if col not in df.columns:
            continue
        raw_pct = pd.to_numeric(df[col], errors="coerce")
        applied = raw_pct.where(~raw_pct.isna(), 0.5)  # neutral fill
        if flipped:
            applied = 1.0 - applied
        w = float(weight)
        weighted_sum += w * applied
        weight_applied_total += w
        for i, (pct_val, contribution) in enumerate(zip(applied, w * applied, strict=False)):
            breakdown_per_row[i][signal_name] = {
                "weight": w,
                "flipped": flipped,
                "percentile_rank": float(pct_val),
                "contribution": float(contribution),
            }

    if weight_applied_total == 0:
        out["conviction_score"] = 0.5
    else:
        out["conviction_score"] = weighted_sum / weight_applied_total
    out["contributing_signals"] = [json.dumps(b) for b in breakdown_per_row]
    return out


_RAW_SIGNALS_SQL = """
    SELECT s.instrument_id::text AS instrument_id,
           {cols}
    FROM atlas.atlas_stock_states_daily s
    LEFT JOIN atlas.atlas_stock_metrics_daily m
           ON m.instrument_id = s.instrument_id AND m.date = s.date
    WHERE s.date = :as_of
      AND s.instrument_id = ANY(CAST(:uni AS uuid[]))
"""


def _load_raw_signals(engine: Engine, *, as_of: date, instrument_ids: list[str]) -> pd.DataFrame:
    cols = ", ".join(f"m.{c}" for c in SIGNAL_COLUMNS)
    sql = _RAW_SIGNALS_SQL.format(cols=cols)
    with engine.connect() as conn:
        return pd.read_sql(
            text(sql),
            conn,
            params={"as_of": as_of, "uni": instrument_ids},
        )


def compute_conviction_scores(engine: Engine, *, as_of: date) -> pd.DataFrame:
    """Compute conviction scores for every tiered instrument on as_of.

    Returns DataFrame: instrument_id, date, tier, conviction_score,
    confidence_label, backing_ic, contributing_signals (JSON str),
    weight_set_version.
    """
    tier_df = compute_tier_membership(engine, as_of=as_of)
    if tier_df.empty:
        return pd.DataFrame(columns=[
            "instrument_id", "date", "tier", "conviction_score",
            "confidence_label", "backing_ic", "contributing_signals",
            "weight_set_version",
        ])

    weights_by_tier = load_active_weights(engine, regime="all")
    if not weights_by_tier:
        log.error("no_active_weights_seeded")
        raise RuntimeError("No active weight sets in atlas_signal_weights — run seed_signal_weights.py first")

    instruments = tier_df["instrument_id"].tolist()
    raw_signals = _load_raw_signals(engine, as_of=as_of, instrument_ids=instruments)

    out_rows: list[pd.DataFrame] = []
    for tier_name, weight_set in weights_by_tier.items():
        tier_instruments = tier_df.loc[tier_df["tier"] == tier_name, "instrument_id"].tolist()
        if not tier_instruments:
            continue
        tier_raw = raw_signals[raw_signals["instrument_id"].isin(tier_instruments)].copy()
        # Compute cross-sectional percentile rank for each signal within this tier
        for sig in SIGNAL_COLUMNS:
            tier_raw[f"{sig}_pct"] = pd.to_numeric(tier_raw[sig], errors="coerce").rank(pct=True)
        scored = apply_weights_to_percentile_ranks(tier_raw, weight_set)
        scored["tier"] = tier_name
        scored["date"] = as_of
        scored["confidence_label"] = assign_confidence_label(weight_set.holdout_ic)
        scored["backing_ic"] = float(weight_set.holdout_ic) if weight_set.holdout_ic else None
        scored["weight_set_version"] = weight_set.weight_set_version
        out_rows.append(scored)

    if not out_rows:
        return pd.DataFrame()
    final = pd.concat(out_rows, ignore_index=True)
    log.info("conviction_computed", as_of=str(as_of), n_rows=len(final))
    return final[[
        "instrument_id", "date", "tier", "conviction_score",
        "confidence_label", "backing_ic", "contributing_signals",
        "weight_set_version",
    ]]
```

- [ ] **Step 4: Re-run tests**

```bash
pytest tests/intelligence/conviction/test_composer.py -v
```
Expected: 7 passed (6 unit + 1 integration).

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/conviction/composer.py \
        tests/intelligence/conviction/test_composer.py
git commit -m "feat(sp04-stage3): composer — tier-aware conviction with breakdown audit"
```

---

## Task 6: `persistence.py`

**Files:**
- Create: `atlas/intelligence/conviction/persistence.py`
- Create: `tests/intelligence/conviction/test_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
"""Integration tests for persistence — UPSERT conviction rows."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.persistence import (
    persist_conviction_batch,
    persist_tier_membership_batch,
)


@pytest.mark.integration
class TestPersist:
    @pytest.fixture(autouse=True)
    def clean_rows(self):
        eng = get_engine()
        with eng.begin() as c:
            c.execute(text("DELETE FROM atlas.atlas_stock_conviction_daily WHERE date = '1990-01-01'"))
            c.execute(text("DELETE FROM atlas.atlas_tier_membership_daily WHERE date = '1990-01-01'"))
        yield
        with eng.begin() as c:
            c.execute(text("DELETE FROM atlas.atlas_stock_conviction_daily WHERE date = '1990-01-01'"))
            c.execute(text("DELETE FROM atlas.atlas_tier_membership_daily WHERE date = '1990-01-01'"))

    def test_persist_conviction_inserts(self):
        eng = get_engine()
        # Use a real instrument_id (fetch one)
        with eng.connect() as c:
            iid = c.execute(text(
                "SELECT instrument_id::text FROM atlas.atlas_stock_states_daily LIMIT 1"
            )).scalar()
        df = pd.DataFrame([{
            "instrument_id": iid,
            "date": date(1990, 1, 1),  # sentinel date for test
            "tier": "tier_1_megacap",
            "conviction_score": 0.7321,
            "confidence_label": "industry_grade",
            "backing_ic": 0.0511,
            "contributing_signals": '{"ma_30w_slope_4w":{"weight":0.5,"flipped":false,"percentile_rank":0.9,"contribution":0.45}}',
            "weight_set_version": "tier_1_megacap@2026-05-12T00:00:00",
        }])
        n = persist_conviction_batch(eng, df)
        assert n == 1

    def test_persist_tier_membership_inserts(self):
        eng = get_engine()
        with eng.connect() as c:
            iid = c.execute(text(
                "SELECT instrument_id::text FROM atlas.atlas_stock_states_daily LIMIT 1"
            )).scalar()
        df = pd.DataFrame([{
            "instrument_id": iid,
            "date": date(1990, 1, 1),
            "tier": "tier_1_megacap",
            "adv_rank": 1,
            "adv_20d": 123456789.00,
        }])
        n = persist_tier_membership_batch(eng, df)
        assert n == 1
```

- [ ] **Step 2: Run test, confirm failure**

```bash
pytest tests/intelligence/conviction/test_persistence.py -v -m integration
```
Expected: ImportError.

- [ ] **Step 3: Implement `persistence.py`**

```python
"""UPSERT helpers for conviction-score and tier-membership tables."""

from __future__ import annotations

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

_UPSERT_CONVICTION_SQL = """
    INSERT INTO atlas.atlas_stock_conviction_daily
        (instrument_id, date, tier, conviction_score,
         confidence_label, backing_ic, contributing_signals,
         weight_set_version)
    VALUES
        (:instrument_id, :date, :tier, :conviction_score,
         :confidence_label, :backing_ic, CAST(:contributing_signals AS jsonb),
         :weight_set_version)
    ON CONFLICT (instrument_id, date) DO UPDATE SET
        tier = EXCLUDED.tier,
        conviction_score = EXCLUDED.conviction_score,
        confidence_label = EXCLUDED.confidence_label,
        backing_ic = EXCLUDED.backing_ic,
        contributing_signals = EXCLUDED.contributing_signals,
        weight_set_version = EXCLUDED.weight_set_version,
        computed_at = NOW(),
        updated_at = NOW()
"""

_UPSERT_TIER_SQL = """
    INSERT INTO atlas.atlas_tier_membership_daily
        (instrument_id, date, tier, adv_rank, adv_20d)
    VALUES
        (:instrument_id, :date, :tier, :adv_rank, :adv_20d)
    ON CONFLICT (instrument_id, date) DO UPDATE SET
        tier = EXCLUDED.tier,
        adv_rank = EXCLUDED.adv_rank,
        adv_20d = EXCLUDED.adv_20d
"""


def persist_conviction_batch(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a batch of conviction rows. Returns row count."""
    if df.empty:
        return 0
    records = df.to_dict("records")
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_CONVICTION_SQL), records)
    log.info("conviction_batch_persisted", n=len(records))
    return len(records)


def persist_tier_membership_batch(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a batch of tier-membership rows."""
    if df.empty:
        return 0
    records = df.to_dict("records")
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_TIER_SQL), records)
    log.info("tier_membership_batch_persisted", n=len(records))
    return len(records)
```

- [ ] **Step 4: Re-run tests**

```bash
pytest tests/intelligence/conviction/test_persistence.py -v -m integration
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/intelligence/conviction/persistence.py \
        tests/intelligence/conviction/test_persistence.py
git commit -m "feat(sp04-stage3): persistence — UPSERT conviction + tier membership"
```

---

## Task 7: CLI `scripts/compute_conviction.py`

**Files:**
- Create: `scripts/compute_conviction.py`
- Create: `tests/intelligence/conviction/test_cli_smoke.py`

- [ ] **Step 1: Write the smoke test**

```python
"""End-to-end smoke for the conviction CLI."""

import subprocess
import sys

import pytest


@pytest.mark.integration
def test_cli_runs_end_to_end():
    """The CLI should run, write to both tables, and exit 0."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/compute_conviction.py", "--persist"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr[-500:]}"
    assert "conviction_computed" in result.stderr or "persist" in result.stderr.lower()
```

- [ ] **Step 2: Implement the CLI**

```python
"""Nightly CLI: compute conviction scores for the latest available date.

Usage:
    python scripts/compute_conviction.py [--as-of YYYY-MM-DD] [--persist]

Without --persist, runs end-to-end and prints summary but does not write.
With --persist, UPSERTs both atlas_stock_conviction_daily and
atlas_tier_membership_daily.

Exit codes:
    0  — success
    2  — bad arguments
    3  — no data available for as-of date
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.composer import compute_conviction_scores
from atlas.intelligence.conviction.persistence import (
    persist_conviction_batch,
    persist_tier_membership_batch,
)
from atlas.intelligence.conviction.tier_assignment import compute_tier_membership

log = structlog.get_logger()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", help="YYYY-MM-DD; default = latest atlas_stock_states_daily")
    p.add_argument("--persist", action="store_true", help="Write results to DB")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = get_engine()

    if args.as_of:
        as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    else:
        with engine.connect() as c:
            as_of = c.execute(
                text("SELECT MAX(date) FROM atlas.atlas_stock_states_daily")
            ).scalar()
        if not as_of:
            log.error("no_stock_states_data")
            return 3

    log.info("conviction_cli_start", as_of=str(as_of), persist=args.persist)

    tier_df = compute_tier_membership(engine, as_of=as_of)
    if tier_df.empty:
        log.error("no_tier_data", as_of=str(as_of))
        return 3

    conviction_df = compute_conviction_scores(engine, as_of=as_of)
    if conviction_df.empty:
        log.error("no_conviction_data", as_of=str(as_of))
        return 3

    summary = (
        conviction_df.groupby(["tier", "confidence_label"])
        .agg(n=("conviction_score", "size"), mean_score=("conviction_score", "mean"))
        .reset_index()
    )
    print(summary.to_string(index=False))

    if args.persist:
        n_tier = persist_tier_membership_batch(engine, tier_df)
        n_conv = persist_conviction_batch(engine, conviction_df)
        log.info("conviction_persisted", n_tier=n_tier, n_conviction=n_conv)
        print(f"\nPersisted: {n_tier} tier rows, {n_conv} conviction rows")
    else:
        print("\n(dry run — use --persist to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Manual smoke test locally**

```bash
python scripts/compute_conviction.py 2>&1 | tail -10
```
Expected: prints tier/label summary, exits 0.

- [ ] **Step 4: Run automated smoke test**

```bash
pytest tests/intelligence/conviction/test_cli_smoke.py -v -m integration
```
Expected: 1 passed.

- [ ] **Step 5: Run with --persist**

```bash
python scripts/compute_conviction.py --persist 2>&1 | tail -10
```
Expected: `Persisted: ~1000 tier rows, ~1000 conviction rows`.

- [ ] **Step 6: Verify DB**

```bash
python3 -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.connect() as c:
    rows = c.execute(text('''
        SELECT confidence_label, COUNT(*), ROUND(AVG(conviction_score)::numeric, 4) AS mean_score
        FROM atlas.atlas_stock_conviction_daily
        WHERE date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
        GROUP BY confidence_label ORDER BY confidence_label
    ''')).fetchall()
    for r in rows: print(r)
"
```
Expected: `industry_grade` count ≈ 200, `baseline` count ≈ 800.

- [ ] **Step 7: Commit**

```bash
git add scripts/compute_conviction.py \
        tests/intelligence/conviction/test_cli_smoke.py
git commit -m "feat(sp04-stage3): compute_conviction CLI — nightly orchestrator"
```

---

## Task 8: SP07 agent integration

**Files:**
- Modify: `atlas/agents/tools/atlas_queries.py` — add `get_top_conviction` function
- Modify: `atlas/agents/tools/registry.py` — register new tool
- Modify: `atlas/agents/specialists/stock_screener.py` — use new tool + reference conviction in prompt

- [ ] **Step 1: Read current files**

```bash
grep -n "def get_top_rs_stocks\|TOOL_REGISTRY\|tool_names" \
  atlas/agents/tools/atlas_queries.py \
  atlas/agents/tools/registry.py \
  atlas/agents/specialists/stock_screener.py
```

- [ ] **Step 2: Add `get_top_conviction` to `atlas_queries.py`**

Append this function:

```python
def get_top_conviction(
    engine: Engine,
    *,
    n: int = 10,
    tier: str | None = None,
    confidence_label: str | None = None,
) -> list[dict[str, object]]:
    """Top conviction names from atlas_stock_conviction_daily.

    Args:
        n: top N (1..50)
        tier: optional tier filter ('tier_1_megacap', ...)
        confidence_label: optional ('industry_grade', 'baseline')

    Returns up to n rows, sorted by conviction_score DESC.
    Each row: instrument_id, symbol, sector, tier, conviction_score (0-100),
    confidence_label, backing_ic.
    """
    n = max(1, min(int(n), 50))
    filters = ["c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)"]
    params: dict = {"n": n}
    if tier:
        filters.append("c.tier = :tier")
        params["tier"] = tier
    if confidence_label:
        filters.append("c.confidence_label = :cl")
        params["cl"] = confidence_label
    where_sql = " AND ".join(filters)

    sql = text(f"""
        SELECT
            c.instrument_id::text AS instrument_id,
            u.symbol,
            u.sector,
            c.tier,
            ROUND((c.conviction_score * 100)::numeric, 1) AS conviction_score,
            c.confidence_label,
            c.backing_ic
        FROM atlas.atlas_stock_conviction_daily c
        LEFT JOIN atlas.atlas_universe_stocks u
               ON u.instrument_id = c.instrument_id
        WHERE {where_sql}
        ORDER BY c.conviction_score DESC
        LIMIT :n
    """)  # noqa: S608 — filters are constant identifiers, not user input
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, params).fetchall()]
```

- [ ] **Step 3: Register in `registry.py`**

Inside `build_registry()`, add:

```python
"get_top_conviction": Tool(
    name="get_top_conviction",
    description=(
        "Return the top N stocks by conviction_score from the production "
        "conviction composite. Optionally filter by tier or by confidence_label "
        "(use 'industry_grade' for high-confidence picks only). "
        "Conviction is the IC-weighted composite of RS, momentum, trend, "
        "drawdown, and volatility signals — measured on out-of-sample data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "n": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            "tier": {
                "type": "string",
                "enum": ["tier_1_megacap", "tier_2_largecap", "tier_3_uppermid",
                         "tier_4_lowermid", "tier_5_smallcap"],
            },
            "confidence_label": {
                "type": "string",
                "enum": ["industry_grade", "baseline"],
            },
        },
    },
    fn=lambda **kwargs: aq.get_top_conviction(engine, **kwargs),
),
```

- [ ] **Step 4: Update stock_screener.py**

In the `tool_names` tuple, add `"get_top_conviction"`. In the system prompt, add this sentence near the existing tool description: "When users ask 'show me top stocks' or 'high-conviction names', prefer get_top_conviction with confidence_label='industry_grade' over get_top_rs_stocks. Reference conviction scores as 'Conviction 87' format."

- [ ] **Step 5: Update tests**

Add a test in `tests/agents/tools/test_atlas_queries.py`:

```python
@pytest.mark.integration
def test_get_top_conviction_returns_rows():
    from atlas.agents.tools.atlas_queries import get_top_conviction
    from atlas.db import get_engine
    rows = get_top_conviction(get_engine(), n=5)
    assert len(rows) <= 5
    for r in rows:
        assert "conviction_score" in r
        assert 0 <= r["conviction_score"] <= 100
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/agents/ -v -m integration
```

- [ ] **Step 7: Commit**

```bash
git add atlas/agents/tools/atlas_queries.py atlas/agents/tools/registry.py \
        atlas/agents/specialists/stock_screener.py \
        tests/agents/tools/test_atlas_queries.py
git commit -m "feat(sp04-stage3): SP07 stock_screener + get_top_conviction tool"
```

---

## Task 9: Frontend — `conviction.ts` query file

**Files:**
- Create: `frontend/src/lib/queries/conviction.ts`

- [ ] **Step 1: Implement**

```typescript
// frontend/src/lib/queries/conviction.ts
import 'server-only'
import sql from '@/lib/db'

export type ConfidenceLabel = 'industry_grade' | 'baseline' | 'descriptive_only'

export type ConvictionRow = {
  instrument_id: string
  symbol: string | null
  sector: string | null
  tier: string
  conviction_score: string   // NUMERIC from postgres → string at JS boundary
  confidence_label: ConfidenceLabel
  backing_ic: string | null
  computed_at: Date
}

export type ConvictionBreakdown = {
  weight: number
  flipped: boolean
  percentile_rank: number
  contribution: number
}

export async function getStockConviction(
  instrumentId: string,
): Promise<ConvictionRow | null> {
  const rows = await sql<ConvictionRow[]>`
    SELECT
      c.instrument_id::text  AS instrument_id,
      u.symbol,
      u.sector,
      c.tier,
      c.conviction_score::text  AS conviction_score,
      c.confidence_label,
      c.backing_ic::text        AS backing_ic,
      c.computed_at
    FROM atlas.atlas_stock_conviction_daily c
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = c.instrument_id
    WHERE c.instrument_id = ${instrumentId}::uuid
      AND c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
  `
  return rows[0] ?? null
}

export async function getConvictionBreakdown(
  instrumentId: string,
): Promise<Record<string, ConvictionBreakdown> | null> {
  const rows = await sql<{ contributing_signals: Record<string, ConvictionBreakdown> }[]>`
    SELECT contributing_signals
    FROM atlas.atlas_stock_conviction_daily
    WHERE instrument_id = ${instrumentId}::uuid
      AND date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
  `
  return rows[0]?.contributing_signals ?? null
}

export type ConvictionMapRow = {
  instrument_id: string
  conviction_score: string
  confidence_label: ConfidenceLabel
  tier: string
  backing_ic: string | null
}

export async function getConvictionMap(): Promise<Map<string, ConvictionMapRow>> {
  const rows = await sql<ConvictionMapRow[]>`
    SELECT
      instrument_id::text       AS instrument_id,
      conviction_score::text    AS conviction_score,
      confidence_label,
      tier,
      backing_ic::text          AS backing_ic
    FROM atlas.mv_top_conviction_daily
  `
  const map = new Map<string, ConvictionMapRow>()
  for (const r of rows) map.set(r.instrument_id, r)
  return map
}

export async function getTopConvictionByTier(
  tier: string,
  n: number = 10,
): Promise<ConvictionRow[]> {
  return await sql<ConvictionRow[]>`
    SELECT
      c.instrument_id::text  AS instrument_id,
      u.symbol,
      u.sector,
      c.tier,
      c.conviction_score::text AS conviction_score,
      c.confidence_label,
      c.backing_ic::text     AS backing_ic,
      c.computed_at
    FROM atlas.mv_top_conviction_daily c
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = c.instrument_id
    WHERE c.tier = ${tier}
    ORDER BY c.conviction_score DESC
    LIMIT ${n}
  `
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/queries/conviction.ts
git commit -m "feat(sp04-stage3-fe): conviction query layer for stocks/intelligence pages"
```

---

## Task 10: Frontend — `ConvictionCell` + integrate into `/stocks` table

**Files:**
- Create: `frontend/src/components/stocks/ConvictionCell.tsx`
- Modify: `frontend/src/app/stocks/page.tsx` (surgical: add column to existing table)
- Modify: `frontend/src/components/stocks/StocksClientShell.tsx` (surgical: pass conviction map into table component)

- [ ] **Step 1: Implement `ConvictionCell.tsx`**

```tsx
// frontend/src/components/stocks/ConvictionCell.tsx
'use client'

import type { ConvictionMapRow } from '@/lib/queries/conviction'

type Props = {
  row: ConvictionMapRow | undefined
}

const TIER_NAMES: Record<string, string> = {
  tier_1_megacap: 'Mega',
  tier_2_largecap: 'Large',
  tier_3_uppermid: 'Mid',
  tier_4_lowermid: 'LowerMid',
  tier_5_smallcap: 'Small',
}

const CONFIDENCE_BADGES: Record<string, { label: string; cls: string }> = {
  industry_grade: { label: '★ Industry-Grade', cls: 'bg-teal/10 text-teal border-teal/30' },
  baseline:       { label: 'Baseline · Tuning', cls: 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30' },
  descriptive_only: { label: '—', cls: 'text-ink-tertiary' },
}

export function ConvictionCell({ row }: Props) {
  if (!row) {
    return (
      <span className="font-mono text-xs text-ink-tertiary">—</span>
    )
  }
  const score = Math.round(Number(row.conviction_score) * 100)
  const badge = CONFIDENCE_BADGES[row.confidence_label] ?? CONFIDENCE_BADGES.descriptive_only
  const tierLabel = TIER_NAMES[row.tier] ?? row.tier

  // Conviction bar background — teal intensity scales with score
  const barWidth = `${Math.max(score, 6)}%`
  const barColor = row.confidence_label === 'industry_grade' ? 'bg-teal' : 'bg-ink-tertiary'

  return (
    <div className="flex flex-col gap-0.5 min-w-[120px]">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full`}
            style={{ width: barWidth }}
          />
        </div>
        <span className="font-mono text-xs font-semibold text-ink-primary tabular-nums w-8 text-right">
          {score}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${badge.cls}`}>
          {badge.label}
        </span>
        <span className="font-sans text-[10px] text-ink-tertiary">{tierLabel}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```
Expected: no TypeScript errors.

- [ ] **Step 3: Read current `frontend/src/app/stocks/page.tsx`**

Identify where the screener data is loaded and passed to client component. Use `Read` tool.

- [ ] **Step 4: Add conviction map to the page**

In `stocks/page.tsx`:

```tsx
import { getConvictionMap } from '@/lib/queries/conviction'

// Inside the async server component, parallel-fetch:
const [stocks, regime, convictionMap] = await Promise.all([
  getAllStocks(),
  getCurrentRegime(),
  getConvictionMap(),
])

// Pass to the client shell:
<StocksClientShell
  stocks={stocks}
  regimeState={regime?.regime_state ?? 'Unknown'}
  deploymentMultiplier={Number(regime?.deployment_multiplier ?? '0')}
  convictionMap={Object.fromEntries(convictionMap)}
/>
```

(Pass as a plain object because Map can't cross the server→client boundary directly.)

- [ ] **Step 5: Update `StocksClientShell.tsx`**

Accept `convictionMap: Record<string, ConvictionMapRow>` prop. Pass it down to the screener table component. In the screener table, add a `Conviction` column after the existing columns, rendering `<ConvictionCell row={convictionMap[stock.instrument_id]} />`.

- [ ] **Step 6: Verify build + visual check locally**

```bash
cd frontend && npm run build && npm run dev
```
Open `http://localhost:3000/stocks` — see new Conviction column.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/stocks/ConvictionCell.tsx \
        frontend/src/app/stocks/page.tsx \
        frontend/src/components/stocks/StocksClientShell.tsx
git commit -m "feat(sp04-stage3-fe): Conviction column in /stocks screener with tier badge"
```

---

## Task 11: Frontend — Conviction Breakdown panel on deep-dive

**Files:**
- Create: `frontend/src/components/stocks/ConvictionBreakdownPanel.tsx`
- Modify: `frontend/src/app/stocks/[symbol]/page.tsx` (surgical addition)

- [ ] **Step 1: Implement breakdown panel**

```tsx
// frontend/src/components/stocks/ConvictionBreakdownPanel.tsx
import type { ConvictionBreakdown } from '@/lib/queries/conviction'

type Props = {
  conviction: { conviction_score: string; tier: string; confidence_label: string; backing_ic: string | null } | null
  breakdown: Record<string, ConvictionBreakdown> | null
}

const SIGNAL_LABELS: Record<string, string> = {
  ma_30w_slope_4w: '30-week MA slope (trend)',
  ret_6m: '6-month return',
  ret_12m_1m: '12-1m momentum factor',
  extension_pct: 'Distance from MA',
  vol_ratio_63: '63-day vol ratio',
  effort_ratio_63: 'Effort ratio (vol/range)',
  realized_vol_63: '63-day realized volatility',
  max_drawdown_252: '1-year max drawdown',
  rs_pctile_3m: '3-month RS percentile',
  ema_10_ratio: '10-day EMA ratio',
  atr_21: '21-day ATR (penalty)',
}

export function ConvictionBreakdownPanel({ conviction, breakdown }: Props) {
  if (!conviction || !breakdown) {
    return (
      <section className="border-t border-paper-rule pt-6 mt-6">
        <h3 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-3">
          Conviction Breakdown
        </h3>
        <p className="font-sans text-sm text-ink-tertiary">
          No conviction score available for this stock today.
        </p>
      </section>
    )
  }
  const score = Math.round(Number(conviction.conviction_score) * 100)
  const ic = conviction.backing_ic ? Number(conviction.backing_ic) : null
  const entries = Object.entries(breakdown).sort(
    (a, b) => (b[1].contribution) - (a[1].contribution),
  )
  const maxAbsContrib = Math.max(...entries.map(([, b]) => Math.abs(b.contribution)), 0.001)

  return (
    <section className="border-t border-paper-rule pt-6 mt-6">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">
          Conviction Breakdown
        </h3>
        <div className="font-sans text-[11px] text-ink-tertiary">
          Score <span className="font-mono text-ink-primary tabular-nums">{score}</span>
          {' · '}
          {ic !== null && (
            <>Backing IC <span className="font-mono text-ink-primary tabular-nums">{ic.toFixed(4)}</span></>
          )}
        </div>
      </div>
      <div className="space-y-1.5">
        {entries.map(([signal, info]) => {
          const widthPct = (Math.abs(info.contribution) / maxAbsContrib) * 100
          const label = SIGNAL_LABELS[signal] ?? signal
          const flipped = info.flipped
          return (
            <div key={signal} className="grid grid-cols-[180px_1fr_80px] gap-3 items-center text-xs">
              <span className="font-sans text-ink-primary truncate" title={signal}>
                {label}
                {flipped && <span className="ml-1 text-[10px] text-ink-tertiary">(flipped)</span>}
              </span>
              <div className="relative h-1.5 bg-paper-rule rounded-full overflow-hidden">
                <div
                  className="h-full bg-teal/70 rounded-full"
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <span className="font-mono text-ink-secondary text-right tabular-nums">
                {(info.contribution * 100).toFixed(2)}
              </span>
            </div>
          )
        })}
      </div>
      <p className="font-sans text-[10px] text-ink-tertiary mt-4">
        Bar length = contribution to composite score (signal weight × percentile rank, post-flip).
        Composite is IC-weighted from {conviction.tier.replace('tier_', 'Tier ')} training period 2019-2022.
      </p>
    </section>
  )
}
```

- [ ] **Step 2: Wire into deep-dive page**

In `frontend/src/app/stocks/[symbol]/page.tsx`, parallel-fetch `getStockConviction` and `getConvictionBreakdown` alongside existing queries. Render `<ConvictionBreakdownPanel conviction={...} breakdown={...} />` in the page body.

- [ ] **Step 3: Build verify**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stocks/ConvictionBreakdownPanel.tsx \
        frontend/src/app/stocks/[symbol]/page.tsx
git commit -m "feat(sp04-stage3-fe): conviction breakdown panel on stock deep-dive"
```

---

## Task 12: Frontend — `/intelligence` "Top Conviction Today" section

**Files:**
- Create: `frontend/src/components/intelligence/TopConvictionSection.tsx`
- Modify: `frontend/src/app/intelligence/page.tsx` (surgical addition)

- [ ] **Step 1: Implement the section component**

```tsx
// frontend/src/components/intelligence/TopConvictionSection.tsx
import type { ConvictionRow } from '@/lib/queries/conviction'

type Props = {
  byTier: Record<string, ConvictionRow[]>
}

const TIER_DISPLAY: Array<{ key: string; label: string }> = [
  { key: 'tier_1_megacap', label: 'Mega-cap (industry-grade)' },
  { key: 'tier_3_uppermid', label: 'Upper mid-cap (industry-grade)' },
  { key: 'tier_2_largecap', label: 'Large-cap (baseline)' },
]

export function TopConvictionSection({ byTier }: Props) {
  return (
    <section className="border-t border-paper-rule pt-6 mt-6">
      <h2 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-3">
        Top Conviction Today
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {TIER_DISPLAY.map(({ key, label }) => {
          const rows = byTier[key] ?? []
          if (rows.length === 0) return null
          return (
            <div key={key}>
              <h3 className="font-sans text-xs font-semibold text-ink-primary mb-2">{label}</h3>
              <ul className="space-y-1">
                {rows.slice(0, 5).map((r) => {
                  const score = Math.round(Number(r.conviction_score) * 100)
                  return (
                    <li
                      key={r.instrument_id}
                      className="flex items-center justify-between text-xs py-1 border-b border-paper-rule/40"
                    >
                      <span className="font-sans text-ink-primary">
                        {r.symbol ?? r.instrument_id.slice(0, 8)}
                        <span className="text-ink-tertiary ml-1.5 text-[10px]">{r.sector}</span>
                      </span>
                      <span className="font-mono text-ink-primary tabular-nums">{score}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Wire into `/intelligence/page.tsx`**

Add parallel fetches: `getTopConvictionByTier('tier_1_megacap', 5)`, `tier_3_uppermid`, `tier_2_largecap`. Pass `byTier={{ tier_1_megacap: ..., tier_3_uppermid: ..., tier_2_largecap: ... }}` to the section.

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/intelligence/TopConvictionSection.tsx \
        frontend/src/app/intelligence/page.tsx
git commit -m "feat(sp04-stage3-fe): Top Conviction section on /intelligence dashboard"
```

---

## Task 13: Playwright smoke tests + EC2 deploy

**Files:**
- Create: `frontend/playwright/conviction.spec.ts`
- (No new backend file; just runtime verification)

- [ ] **Step 1: Implement Playwright smoke**

```typescript
// frontend/playwright/conviction.spec.ts
import { test, expect } from '@playwright/test'

const PASSWORD = process.env.ATLAS_PASSWORD ?? 'test123'

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
})

test('stocks page renders Conviction column', async ({ page }) => {
  await page.goto('/stocks')
  await expect(page.getByText('Conviction', { exact: false })).toBeVisible({ timeout: 10000 })
})

test('intelligence page renders Top Conviction section', async ({ page }) => {
  await page.goto('/intelligence')
  await expect(page.getByText('Top Conviction Today', { exact: false })).toBeVisible({ timeout: 10000 })
})

test('stocks deep-dive renders breakdown panel', async ({ page }) => {
  await page.goto('/stocks')
  // Click the first row link
  const firstLink = page.locator('a[href^="/stocks/"]').first()
  if (await firstLink.count() > 0) {
    await firstLink.click()
    await expect(page.getByText('Conviction Breakdown', { exact: false })).toBeVisible({ timeout: 10000 })
  }
})
```

- [ ] **Step 2: Run Playwright locally with dev server**

```bash
cd frontend && ATLAS_PASSWORD=<your-dev-password> npx playwright test conviction.spec.ts
```
Expected: 3 passed.

- [ ] **Step 3: Push to remote**

```bash
git push origin main
```

- [ ] **Step 4: EC2 deploy**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  'cd /home/ubuntu/atlas-os && git pull origin main && source .venv/bin/activate && \
   alembic upgrade head && python scripts/seed_signal_weights.py && \
   python scripts/compute_conviction.py --persist'
```

Expected:
- Migration 039 applies
- 46 weight rows seeded
- ~1000 conviction rows + ~1000 tier rows persisted

- [ ] **Step 5: Refresh materialized view**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 'cd /home/ubuntu/atlas-os && source .venv/bin/activate && python3 -c "
from atlas.db import get_engine
from sqlalchemy import text
e = get_engine()
with e.begin() as c:
    c.execute(text(\"REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_top_conviction_daily\"))
print(\"refreshed\")
"'
```

- [ ] **Step 6: Verify frontend deploy auto-rebuilt**

Wait for the existing auto-deploy script to detect the push and rebuild. Then:

```bash
curl -s -o /dev/null -w "/stocks: %{http_code}\n" https://atlas.jslwealth.in/stocks
curl -s -o /dev/null -w "/intelligence: %{http_code}\n" https://atlas.jslwealth.in/intelligence
```

Expected: both 200.

- [ ] **Step 7: Visual smoke on production**

```bash
curl -s -L https://atlas.jslwealth.in/stocks | grep -c "Conviction"
```
Expected: ≥ 1 (column header is present in HTML).

- [ ] **Step 8: Commit smoke test**

```bash
git add frontend/playwright/conviction.spec.ts
git commit -m "test(sp04-stage3-fe): playwright smoke for conviction column/section/panel"
git push origin main
```

---

## Task 14: Memory file + master plan badge update

**Files:**
- Create: `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp04_stage3_state.md`
- Modify: `docs/phase2/00-master-plan.html` (SP04 badge → ✓ Shipped)

- [ ] **Step 1: Write memory file**

```markdown
---
name: SP04 Stage 3 — Conviction Composite shipped to production
description: v2 composite live on EC2 + atlas.jslwealth.in. T1+T3 industry-grade (IC 0.05+), T2/T4/T5 baseline pending Stage 4 auto-optimization.
type: project
---

[Full text per the project memory pattern — see project_sp02_state.md, project_sp07_state.md as templates.]

Key facts:
- 8 commits, migration 039 applied on local + EC2
- Tables: atlas_signal_weights (audit-tracked), atlas_stock_conviction_daily, atlas_tier_membership_daily
- 46 weight rows seeded, ~1000 conviction rows computed
- 5 tiers, 11 unique signals
- Backing IC per tier: T1 0.051, T2 0.007, T3 0.054, T4 0.027, T5 0.041
- Frontend: /stocks Conviction column, /intelligence Top Conviction section, /stocks/[symbol] breakdown panel
- SP07 stock_screener now consumes get_top_conviction
- Open items for Stage 4: auto-optimization loop, regime-conditioned weights, FM approval UI
```

- [ ] **Step 2: Update master plan badge**

In `docs/phase2/00-master-plan.html` SP04 section, change badge from "⏸ HALTED" to "✓ Stage 3 Shipped 2026-05-12" with notes "Tiered conviction live; Stage 4 auto-optimization next."

- [ ] **Step 3: Commit + push**

```bash
git add ~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp04_stage3_state.md \
        docs/phase2/00-master-plan.html
git commit -m "docs(sp04-stage3): mark Stage 3 shipped, document state for future sessions"
git push origin main
```

---

## Final verification checklist

Before marking SP04 Stage 3 complete:

- [ ] All 14 tasks committed
- [ ] `pytest tests/intelligence/conviction/ -v` shows green (~16 tests)
- [ ] `pyright atlas/intelligence/conviction/` clean
- [ ] `ruff check atlas/intelligence/conviction/` clean
- [ ] Migration 039 applied on EC2
- [ ] `atlas_stock_conviction_daily` populated with ~1000 rows for latest date
- [ ] `mv_top_conviction_daily` refreshed and serves
- [ ] `https://atlas.jslwealth.in/stocks` shows Conviction column with values
- [ ] `https://atlas.jslwealth.in/intelligence` shows Top Conviction section
- [ ] `https://atlas.jslwealth.in/stocks/<any-symbol>` shows breakdown panel
- [ ] SP07 agent call `python scripts/run_agent.py --agent stock_screener --question "top high-conviction names today"` references conviction scores
- [ ] Playwright spec passes against production
- [ ] Memory file written
- [ ] Master plan badge updated

---

## What Stage 4 (next sub-project) builds on top of this

- Continuous nightly IC recomputation per tier
- Candidate weight-set generator (search variants, cross-validate)
- Admin route `/admin/composite-proposals` with approve/reject/snooze
- Bayesian smoothing on approval (15% blend)
- Auto-revert if live IC drops below 50% of backtest IC for 60 days
- Per-regime weight conditioning (5 tiers × 4 regimes = 20 weight sets)
- Hit-rate visibility per stock alongside conviction score
