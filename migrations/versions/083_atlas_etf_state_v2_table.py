"""atlas_etf_state_v2 table — bottom-up ETF state aggregate.

Bottom-up replacement for the state-classification portion of atlas_etf_states_daily.
Populated nightly by atlas/intelligence/aggregations/etf.py via the persistence
writer.

Revision ID: 083
Revises: 082
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_etf_state_v2",
        sa.Column("etf_ticker", sa.String(32), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("dominant_state", sa.String(20), nullable=False),
        sa.Column("dominant_share", sa.Numeric(6, 4), nullable=False),
        sa.Column("n_holdings", sa.Integer, nullable=False),
        sa.Column("mean_rs_rank_12m", sa.Numeric(6, 4), nullable=True),
        sa.Column("pct_stage_2", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_3", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_4", sa.Numeric(6, 4), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("etf_ticker", "date"),
        sa.CheckConstraint(
            "dominant_state IN ('uninvestable','stage_1','stage_2a','stage_2b',"
            "'stage_2c','stage_3','stage_4')",
            name="ck_etf_state_v2_dominant_state",
        ),
        schema="atlas",
    )
    op.create_index(
        "ix_etf_state_v2_date",
        "atlas_etf_state_v2",
        ["date"],
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_index("ix_etf_state_v2_date", "atlas_etf_state_v2", schema="atlas")
    op.drop_table("atlas_etf_state_v2", schema="atlas")
