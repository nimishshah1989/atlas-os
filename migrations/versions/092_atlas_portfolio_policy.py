"""Add atlas_portfolio_policy table.

Stores the fund manager's trade philosophy as configuration — one row per
portfolio, plus one house-default row (portfolio_id IS NULL, is_house_default
= TRUE). Per-portfolio rows inherit or override the house default at runtime.

A partial unique index on (is_house_default) WHERE is_house_default enforces
at most one house-default row.

Revision ID: 092_atlas_portfolio_policy
Revises: 091_fund_recommendation_enum_fix
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "092_atlas_portfolio_policy"
down_revision = "091_fund_recommendation_enum_fix"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"
_TABLE = "atlas_portfolio_policy"
_IDX = "uix_portfolio_policy_house_default"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        # --- Identity ---
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # FK to atlas.strategy_fm_custom_portfolios; NULL = house-default row
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "atlas.strategy_fm_custom_portfolios.id",
                name="fk_portfolio_policy_portfolio_id",
                ondelete="CASCADE",
            ),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "is_house_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        # --- Deployment ---
        sa.Column("cash_floor_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("respect_regime_cap", sa.Boolean(), nullable=True),
        # --- Concentration ---
        sa.Column("max_per_stock_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("max_per_sector_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("max_small_cap_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("min_holdings", sa.Integer(), nullable=True),
        sa.Column("max_positions", sa.Integer(), nullable=True),
        # --- Entry ---
        # buy_states: list of state strings, e.g. ['stage_2a', 'stage_2b']
        sa.Column("buy_states", ARRAY(sa.Text()), nullable=True),
        sa.Column("min_within_state_rank", sa.Numeric(5, 4), nullable=True),
        sa.Column("min_rs_rank", sa.Numeric(5, 4), nullable=True),
        # --- Exit ---
        sa.Column("hard_stop_pct", sa.Numeric(6, 4), nullable=True),
        # state_exit_trim: stage that triggers a position trim (e.g. 'stage_3')
        sa.Column("state_exit_trim", sa.Text(), nullable=True),
        # state_exit_full: stage that triggers a full exit (e.g. 'stage_4')
        sa.Column("state_exit_full", sa.Text(), nullable=True),
        sa.Column("trailing_stop_pct", sa.Numeric(6, 4), nullable=True),
        # --- Instrument ---
        sa.Column("instrument_universe", sa.Text(), nullable=True),
        # --- Benchmark ---
        sa.Column("benchmark", sa.Text(), nullable=True),
        # --- Cadence ---
        sa.Column("rebalance_cadence", sa.Text(), nullable=True),
        # --- Audit ---
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # --- CHECK constraints ---
        sa.CheckConstraint(
            "instrument_universe IN ('direct_equity','etf','mutual_fund','mixed')",
            name="ck_portfolio_policy_instrument_universe",
        ),
        sa.CheckConstraint(
            "rebalance_cadence IN ('daily','weekly','monthly')",
            name="ck_portfolio_policy_rebalance_cadence",
        ),
        schema=_SCHEMA,
    )

    # Partial unique index: at most one house-default row
    op.create_index(
        _IDX,
        _TABLE,
        ["is_house_default"],
        unique=True,
        schema=_SCHEMA,
        postgresql_where=sa.text("is_house_default"),
    )


def downgrade() -> None:
    # Drop partial unique index first (implicit with table drop, but explicit is cleaner)
    op.drop_index(_IDX, table_name=_TABLE, schema=_SCHEMA)
    op.drop_table(_TABLE, schema=_SCHEMA)
