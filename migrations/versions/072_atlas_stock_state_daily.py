"""State Engine — per-stock daily state classification.

Revision ID: 072
Revises: 071
Create Date: 2026-05-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_stock_state_daily",
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("prior_state", sa.String(length=24), nullable=True),
        sa.Column("state_since_date", sa.Date(), nullable=False),
        sa.Column("dwell_days", sa.Integer(), nullable=False),
        sa.Column("dwell_percentile", sa.Numeric(5, 4), nullable=True),
        sa.Column("urgency_score", sa.String(length=12), nullable=False),
        sa.Column("within_state_rank", sa.Numeric(5, 4), nullable=True),
        sa.Column("rs_rank_12m", sa.Numeric(5, 4), nullable=True),
        sa.Column("close_vs_sma_50", sa.Numeric(8, 4), nullable=True),
        sa.Column("close_vs_sma_150", sa.Numeric(8, 4), nullable=True),
        sa.Column("close_vs_sma_200", sa.Numeric(8, 4), nullable=True),
        sa.Column("sma_200_slope", sa.Numeric(8, 6), nullable=True),
        sa.Column("volume_ratio_50d", sa.Numeric(6, 3), nullable=True),
        sa.Column("distribution_days", sa.Integer(), nullable=True),
        sa.Column("classifier_version", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("instrument_id", "date"),
        sa.CheckConstraint(
            "state IN ("
            "'uninvestable','stage_1','stage_2a','stage_2b',"
            "'stage_2c','stage_3','stage_4')",
            name="ck_state_value",
        ),
        sa.CheckConstraint(
            "urgency_score IN ('urgent','normal','late','n/a')",
            name="ck_urgency_value",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_stock_state_daily_date",
        "atlas_stock_state_daily",
        ["date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_stock_state_daily_date_state",
        "atlas_stock_state_daily",
        ["date", "state"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_atlas_stock_state_daily_date_state",
        table_name="atlas_stock_state_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_stock_state_daily_date",
        table_name="atlas_stock_state_daily",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_stock_state_daily", schema=_SCHEMA)
