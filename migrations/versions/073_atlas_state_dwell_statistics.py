"""State Engine — per-cohort dwell baselines.

Revision ID: 073
Revises: 072
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_state_dwell_statistics",
        sa.Column("cohort_key", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("mean_dwell_days", sa.Numeric(8, 2), nullable=True),
        sa.Column("median_dwell_days", sa.Integer(), nullable=True),
        sa.Column("p25_dwell_days", sa.Integer(), nullable=True),
        sa.Column("p75_dwell_days", sa.Integer(), nullable=True),
        sa.Column("p95_dwell_days", sa.Integer(), nullable=True),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cohort_key", "state", "as_of_date"),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("atlas_state_dwell_statistics", schema=_SCHEMA)
