"""State Engine — atlas_component_validation table.

Revision ID: 079
Revises: 078
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_component_validation",
        sa.Column("component_name", sa.String(length=48), nullable=False),
        sa.Column("badge", sa.String(length=32), nullable=False),
        sa.Column("threshold_range", sa.String(length=64), nullable=False),
        sa.Column("implied_action", sa.String(length=48), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("mean_ic", sa.Numeric(10, 6), nullable=True),
        sa.Column("ic_std", sa.Numeric(10, 6), nullable=True),
        sa.Column("ic_t_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("ic_ir", sa.Numeric(10, 4), nullable=True),
        sa.Column("q5_q1_spread", sa.Numeric(10, 6), nullable=True),
        sa.Column("n_observations", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "validated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "component_name", "badge", "horizon_days", "as_of_date"
        ),
        sa.CheckConstraint(
            "status IN ('validated', 'validated_inverse', 'weak', 'decorative')",
            name="ck_component_validation_status",
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("atlas_component_validation", schema=_SCHEMA)
