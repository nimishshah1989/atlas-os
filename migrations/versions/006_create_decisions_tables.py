"""create decisions tables

Revision ID: 006
Revises: 005
Create Date: 2026-05-06 00:00:05.000000

Layer 3 decisions tables per ``docs/02_DATABASE_SCHEMA.md`` Section 5.
Investability + entry triggers + exit triggers + position sizing per
methodology Section 13.

Six exit-trigger columns (stocks): market-riskoff, sector-avoid, RS-weaken,
momentum-collapse, volume-distribution, ATR stop. Five for ETFs (no volume
distribution). Funds use a four-recommendation scheme plus four lens-level
exit triggers and four recommendation-transition triggers.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_decisions_daily (
            instrument_id          UUID            NOT NULL,
            date                   DATE            NOT NULL,

            -- Investability
            is_investable          BOOLEAN         NOT NULL,

            -- Gate breakdown (six per methodology 13.2)
            strength_gate          BOOLEAN         NOT NULL,
            direction_gate         BOOLEAN         NOT NULL,
            risk_gate              BOOLEAN         NOT NULL,
            volume_gate            BOOLEAN         NOT NULL,
            sector_gate            BOOLEAN         NOT NULL,
            market_gate            BOOLEAN         NOT NULL,

            -- Entry triggers (only meaningful when is_investable = TRUE)
            transition_trigger     BOOLEAN         NOT NULL DEFAULT FALSE,
            breakout_trigger       BOOLEAN         NOT NULL DEFAULT FALSE,
            proximity_pass         BOOLEAN,

            -- Position sizing
            position_size_pct      NUMERIC(10,4),
            market_multiplier      NUMERIC(10,4),
            risk_multiplier        NUMERIC(10,4),

            -- Six exit triggers per methodology 13.4
            exit_market_riskoff    BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_sector_avoid      BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_rs_deteriorate    BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_momentum_collapse BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_volume_distrib    BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_stop_loss         BOOLEAN         NOT NULL DEFAULT FALSE,

            -- Audit
            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_etf_decisions_daily (
            ticker                 VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,

            is_investable          BOOLEAN         NOT NULL,

            -- Five gates (no volume gate per methodology 13.5)
            strength_gate          BOOLEAN         NOT NULL,
            direction_gate         BOOLEAN         NOT NULL,
            risk_gate              BOOLEAN         NOT NULL,
            sector_gate            BOOLEAN         NOT NULL,
            market_gate            BOOLEAN         NOT NULL,

            transition_trigger     BOOLEAN         NOT NULL DEFAULT FALSE,
            breakout_trigger       BOOLEAN         NOT NULL DEFAULT FALSE,
            proximity_pass         BOOLEAN,

            position_size_pct      NUMERIC(10,4),
            market_multiplier      NUMERIC(10,4),
            risk_multiplier        NUMERIC(10,4),

            -- Five exit triggers (no volume distribution per methodology 13.5)
            exit_market_riskoff    BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_sector_avoid      BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_rs_deteriorate    BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_momentum_collapse BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_stop_loss         BOOLEAN         NOT NULL DEFAULT FALSE,

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_fund_decisions_daily (
            mstar_id               VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,

            recommendation         VARCHAR(32)     NOT NULL,

            is_investable          BOOLEAN         NOT NULL,

            -- Gate breakdown
            performance_gate       BOOLEAN         NOT NULL,
            sectors_gate           BOOLEAN         NOT NULL,
            stocks_gate            BOOLEAN         NOT NULL,
            market_gate            BOOLEAN         NOT NULL,

            -- Lens-level exit triggers (4)
            exit_market_riskoff    BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_composition_misaligned BOOLEAN    NOT NULL DEFAULT FALSE,
            exit_holdings_weak     BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_nav_deteriorate   BOOLEAN         NOT NULL DEFAULT FALSE,

            -- Recommendation-level transition triggers (4)
            entry_trigger          BOOLEAN         NOT NULL DEFAULT FALSE,
            exit_trigger           BOOLEAN         NOT NULL DEFAULT FALSE,
            reduce_trigger         BOOLEAN         NOT NULL DEFAULT FALSE,
            add_trigger            BOOLEAN         NOT NULL DEFAULT FALSE,

            -- Transition tracking
            last_week_recommendation VARCHAR(32),
            weeks_in_current_state INTEGER,

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (mstar_id, date),

            CONSTRAINT chk_fund_decisions_recommendation CHECK (recommendation IN (
                'Recommended', 'Hold', 'Reduce', 'Exit', 'DISLOCATION_SUSPENDED'
            ))
        )
    """))


def downgrade() -> None:
    for tbl in (
        "atlas_fund_decisions_daily",
        "atlas_etf_decisions_daily",
        "atlas_stock_decisions_daily",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS atlas.{tbl}"))
