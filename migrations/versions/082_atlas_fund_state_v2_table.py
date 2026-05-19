"""atlas_fund_state_v2 table — bottom-up fund composition + holdings aggregate.

Bottom-up replacement for the state-classification portion of atlas_fund_states_daily.
nav_state is NOT stored here — it remains computed separately by lens_nav.py
and lives in atlas_fund_states_daily. The fund_signal_unified view joins both.

Revision ID: 082
Revises: 081
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_fund_state_v2",
        sa.Column("mstar_id", sa.String(32), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("composition_state", sa.String(24), nullable=False),
        sa.Column("holdings_state", sa.String(24), nullable=False),
        sa.Column("pct_holdings_stage_2", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_holdings_stage_3", sa.Numeric(6, 4), nullable=False),
        sa.Column("pct_holdings_stage_4", sa.Numeric(6, 4), nullable=False),
        sa.Column("mean_within_state_rank", sa.Numeric(6, 4), nullable=True),
        sa.Column("n_holdings", sa.Integer, nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("mstar_id", "date"),
        sa.CheckConstraint(
            "composition_state IN ('Aligned','Deteriorating','Mixed')",
            name="ck_fund_state_v2_composition",
        ),
        sa.CheckConstraint(
            "holdings_state IN ('Strong-Holdings','Weak-Holdings','Mixed-Holdings','Unknown')",
            name="ck_fund_state_v2_holdings",
        ),
        schema="atlas",
    )
    op.create_index(
        "ix_fund_state_v2_date",
        "atlas_fund_state_v2",
        ["date"],
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_index("ix_fund_state_v2_date", "atlas_fund_state_v2", schema="atlas")
    op.drop_table("atlas_fund_state_v2", schema="atlas")
