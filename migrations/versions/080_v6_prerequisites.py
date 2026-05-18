"""v6 data prerequisites — index membership, factor returns, macro daily,
governance master/daily, strategy runs, exclusions log, recommendations.

Revision ID: 080
Revises: 079
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. atlas_index_membership — point-in-time index reconstitution history
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_index_membership (
            index_name TEXT NOT NULL,
            instrument_id UUID NOT NULL,
            valid_from DATE NOT NULL,
            valid_to DATE,
            PRIMARY KEY (index_name, instrument_id, valid_from)
        );
        CREATE INDEX IF NOT EXISTS ix_atlas_index_membership_lookup
            ON atlas.atlas_index_membership (instrument_id, valid_from, valid_to);
    """)

    # 2. atlas_factor_returns_daily — Indian Fama-French + Carhart factor returns
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_factor_returns_daily (
            date DATE PRIMARY KEY,
            mkt_excess NUMERIC(10,6),
            smb        NUMERIC(10,6),
            wml        NUMERIC(10,6),
            hml        NUMERIC(10,6)
        );
    """)

    # 3. atlas_macro_daily — USDINR / DXY / 10Y / T-bill / FII / breadth
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_macro_daily (
            date DATE PRIMARY KEY,
            usdinr                  NUMERIC(10,4),
            dxy                     NUMERIC(10,4),
            india_10y_yield         NUMERIC(8,4),
            risk_free_91d           NUMERIC(8,4),
            fii_cash_equity_flow_cr NUMERIC(14,2),
            breadth_pct_above_200dma NUMERIC(5,2)
        );
    """)

    # 4. atlas_governance_master — auditor + promoter group + audit qualifications
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_governance_master (
            instrument_id            UUID PRIMARY KEY,
            promoter_group           TEXT,
            auditor_name             TEXT,
            auditor_is_top_10        BOOLEAN,
            last_auditor_change_date DATE,
            last_qualified_audit_date DATE,
            updated_at               TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_atlas_governance_master_group
            ON atlas.atlas_governance_master (promoter_group);
    """)

    # 5. atlas_governance_daily — pledge ratio + F&O ban
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_governance_daily (
            instrument_id        UUID NOT NULL,
            date                 DATE NOT NULL,
            pledge_ratio_pct     NUMERIC(6,2),
            in_fno_ban_list      BOOLEAN,
            PRIMARY KEY (instrument_id, date)
        );
        CREATE INDEX IF NOT EXISTS ix_atlas_governance_daily_date
            ON atlas.atlas_governance_daily (date);
    """)

    # 6. atlas_v6_strategy_runs — backtest runs + goal-post evaluations
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_v6_strategy_runs (
            run_id                  UUID PRIMARY KEY,
            strategy_name           TEXT NOT NULL,
            signal_weights          JSONB NOT NULL,
            is_period               TSRANGE NOT NULL,
            oos_period              TSRANGE NOT NULL,
            calmar                  NUMERIC,
            vol_ratio               NUMERIC,
            mdd_ratio               NUMERIC,
            win_rate                NUMERIC,
            alpha_t_stat            NUMERIC,
            oos_ic_retention        NUMERIC,
            capacity_cr             NUMERIC,
            turnover_annual         NUMERIC,
            dd_compliance           NUMERIC,
            passes_all_constraints  BOOLEAN,
            constraint_failures     TEXT[],
            holdout_examined_at     TIMESTAMPTZ,
            created_at              TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 7. atlas_v6_exclusions_log — every governance exclusion + reason
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_v6_exclusions_log (
            instrument_id  UUID NOT NULL,
            date           DATE NOT NULL,
            reason         TEXT NOT NULL,
            weight_before  NUMERIC,
            weight_after   NUMERIC,
            PRIMARY KEY (instrument_id, date, reason)
        );
        CREATE INDEX IF NOT EXISTS ix_atlas_v6_exclusions_log_date
            ON atlas.atlas_v6_exclusions_log (date);
    """)

    # 8. atlas_v6_recommendations_daily — daily live picks
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_v6_recommendations_daily (
            date             DATE NOT NULL,
            instrument_id    UUID NOT NULL,
            composite_score  NUMERIC NOT NULL,
            weight_in_book   NUMERIC NOT NULL,
            rank             INT NOT NULL,
            confidence_band  TEXT NOT NULL,
            PRIMARY KEY (date, instrument_id),
            CONSTRAINT confidence_band_check
                CHECK (confidence_band IN ('HIGH', 'MED', 'LOW'))
        );
        CREATE INDEX IF NOT EXISTS ix_atlas_v6_recs_date_rank
            ON atlas.atlas_v6_recommendations_daily (date, rank);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_v6_recommendations_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_v6_exclusions_log;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_v6_strategy_runs;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_governance_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_governance_master;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_macro_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_factor_returns_daily;")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_index_membership;")
