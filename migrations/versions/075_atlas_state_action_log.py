"""State Engine — state-transition action audit log.

Revision ID: 075
Revises: 074
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_state_action_log",
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("transition", sa.String(length=48), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("suppressed_by", sa.String(length=32), nullable=True),
        sa.Column("position_size", sa.Numeric(8, 4), nullable=True),
        sa.Column("within_state_rank", sa.Numeric(5, 4), nullable=True),
        sa.Column("urgency_score", sa.String(length=12), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("instrument_id", "date", "transition"),
        sa.CheckConstraint(
            "action IN ('BUY','HOLD','TRIM','EXIT','WATCH','FORCE_EXIT')",
            name="ck_action_value",
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("atlas_state_action_log", schema=_SCHEMA)
