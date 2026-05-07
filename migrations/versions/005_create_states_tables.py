"""create states tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-06 00:00:04.000000

Layer 3 state tables per ``docs/02_DATABASE_SCHEMA.md`` Section 4. Stores
categorical state labels per instrument per date. The "what we concluded"
tables.

State sets (per methodology Section 7):
- RS: Leader, Strong, Consolidating, Emerging, Average, Weak, Laggard
- Momentum: Accelerating, Improving, Flat, Deteriorating, Collapsing
- Risk: Low, Normal, Elevated, High, Below Trend
- Volume: Accumulation, Steady-Buying, Neutral, Distribution, Heavy Distribution
Plus three suspended overrides: INSUFFICIENT_HISTORY, ILLIQUID, DISLOCATION_SUSPENDED
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_states_daily (
            instrument_id          UUID            NOT NULL,
            date                   DATE            NOT NULL,

            -- The four primitive states
            rs_state               VARCHAR(32)     NOT NULL,
            momentum_state         VARCHAR(32)     NOT NULL,
            risk_state             VARCHAR(32)     NOT NULL,
            volume_state           VARCHAR(32)     NOT NULL,

            -- Gates and qualifiers
            history_gate_pass      BOOLEAN         NOT NULL,
            liquidity_gate_pass    BOOLEAN         NOT NULL,
            weinstein_gate_pass    BOOLEAN         NOT NULL,
            stage1_base_qualifies  BOOLEAN         NOT NULL,

            -- Sector / tier (denormalized from atlas_universe_stocks for query speed)
            sector                 VARCHAR(64),
            tier                   VARCHAR(8),

            -- Audit
            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date),

            CONSTRAINT chk_stock_states_rs CHECK (rs_state IN (
                'Leader', 'Strong', 'Consolidating', 'Emerging',
                'Average', 'Weak', 'Laggard',
                'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED'
            )),
            CONSTRAINT chk_stock_states_momentum CHECK (momentum_state IN (
                'Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing',
                'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED'
            )),
            CONSTRAINT chk_stock_states_risk CHECK (risk_state IN (
                'Low', 'Normal', 'Elevated', 'High', 'Below Trend',
                'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED'
            )),
            CONSTRAINT chk_stock_states_volume CHECK (volume_state IN (
                'Accumulation', 'Steady-Buying', 'Neutral',
                'Distribution', 'Heavy Distribution',
                'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED'
            ))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_etf_states_daily (
            ticker                 VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,

            rs_state               VARCHAR(32)     NOT NULL,
            momentum_state         VARCHAR(32)     NOT NULL,
            risk_state             VARCHAR(32)     NOT NULL,
            volume_state           VARCHAR(32),    -- informational only for ETFs

            history_gate_pass      BOOLEAN         NOT NULL,
            liquidity_gate_pass    BOOLEAN         NOT NULL,
            weinstein_gate_pass    BOOLEAN         NOT NULL,

            theme                  VARCHAR(16),
            linked_sector          VARCHAR(64),

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_sector_states_daily (
            sector_name            VARCHAR(64)     NOT NULL,
            date                   DATE            NOT NULL,

            sector_state           VARCHAR(16)     NOT NULL,

            bottomup_state         VARCHAR(16),
            topdown_state          VARCHAR(16),
            divergence_flag        BOOLEAN         NOT NULL DEFAULT FALSE,

            -- Reasoning denormalized for UI
            bottomup_rs_state      VARCHAR(16),
            bottomup_momentum_state VARCHAR(16),
            participation_rs_pct   NUMERIC(10,4),

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (sector_name, date),

            CONSTRAINT chk_sector_states_sector CHECK (sector_state IN (
                'Overweight', 'Neutral', 'Underweight', 'Avoid', 'DISLOCATION_SUSPENDED'
            ))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_fund_states_daily (
            mstar_id               VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,

            nav_state              VARCHAR(20)     NOT NULL,
            composition_state      VARCHAR(16)     NOT NULL,
            holdings_state         VARCHAR(20)     NOT NULL,

            -- Refresh dates (Lens 1 daily; Lens 2/3 monthly)
            nav_state_as_of        DATE            NOT NULL,
            composition_as_of      DATE,
            holdings_as_of         DATE,

            category_name          VARCHAR(64),

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (mstar_id, date),

            CONSTRAINT chk_fund_states_nav CHECK (nav_state IN (
                'Leader NAV', 'Strong NAV', 'Emerging NAV',
                'Average NAV', 'Weak NAV', 'Laggard NAV',
                'INSUFFICIENT_HISTORY', 'DISLOCATION_SUSPENDED'
            )),
            CONSTRAINT chk_fund_states_composition CHECK (composition_state IN (
                'Aligned', 'Mixed', 'Misaligned', 'NO_DISCLOSURE', 'DISLOCATION_SUSPENDED'
            )),
            CONSTRAINT chk_fund_states_holdings CHECK (holdings_state IN (
                'Strong-Holdings', 'Decent', 'Weak-Holdings',
                'NO_DISCLOSURE', 'DISLOCATION_SUSPENDED'
            ))
        )
    """))


def downgrade() -> None:
    for tbl in (
        "atlas_fund_states_daily",
        "atlas_sector_states_daily",
        "atlas_etf_states_daily",
        "atlas_stock_states_daily",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS atlas.{tbl}"))
