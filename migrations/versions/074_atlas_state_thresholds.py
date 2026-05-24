"""State Engine — learned threshold values with history.

Revision ID: 074
Revises: 073
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_state_thresholds",
        sa.Column("threshold_name", sa.String(length=64), nullable=False),
        sa.Column("state_or_gate", sa.String(length=24), nullable=False),
        sa.Column("threshold_value", sa.Numeric(12, 6), nullable=False),
        sa.Column("ic_at_threshold", sa.Numeric(8, 4), nullable=True),
        sa.Column("ic_ir_at_threshold", sa.Numeric(8, 4), nullable=True),
        sa.Column("q5_q1_spread", sa.Numeric(8, 4), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "tuned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("threshold_name", "state_or_gate", "as_of_date"),
        schema=_SCHEMA,
    )
    # Partial unique index: at most one active row per (threshold_name, state_or_gate).
    # Enables unambiguous WHERE active = TRUE lookups in the state classifier.
    op.execute("""
        CREATE UNIQUE INDEX uq_state_thresholds_active
          ON atlas.atlas_state_thresholds (threshold_name, state_or_gate)
          WHERE active = TRUE
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS atlas.uq_state_thresholds_active")
    op.drop_table("atlas_state_thresholds", schema=_SCHEMA)
