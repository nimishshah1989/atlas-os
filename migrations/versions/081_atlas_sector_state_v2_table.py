"""atlas_sector_state_v2 table — bottom-up sector aggregate state.

Bottom-up replacement for atlas_sector_states_daily. Populated nightly by
atlas/intelligence/aggregations/sector.py via the persistence writer.

Revision ID: 081
Revises: 080
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_sector_state_v2",
        sa.Column("sector", sa.String(64), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("dominant_state", sa.String(20), nullable=False),
        sa.Column("dominant_share", sa.Numeric(6, 4), nullable=False),
        sa.Column("n_constituents", sa.Integer, nullable=False),
        sa.Column("mean_within_state_rank", sa.Numeric(6, 4), nullable=True),
        sa.Column("pct_stage_2", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_3", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_4", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_stage_1", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_uninvestable", sa.Numeric(6, 4), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("sector", "date"),
        sa.CheckConstraint(
            "dominant_state IN ('uninvestable','stage_1','stage_2a','stage_2b',"
            "'stage_2c','stage_3','stage_4')",
            name="ck_sector_state_v2_dominant_state",
        ),
        schema="atlas",
    )
    op.create_index(
        "ix_sector_state_v2_date",
        "atlas_sector_state_v2",
        ["date"],
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_index("ix_sector_state_v2_date", "atlas_sector_state_v2", schema="atlas")
    op.drop_table("atlas_sector_state_v2", schema="atlas")
