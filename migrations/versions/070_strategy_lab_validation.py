"""Strategy Lab — backtest validation table.

Per-year backtest results for each top-N genome over the full 12-year
history. Populates the "Proof" tab on /strategies/lab — the goal post's
"proven through portfolios actually beating the benchmark with risks
lower than the benchmark" clause.

One row per (genome_id, year). Strategy Lab validation script computes
this once per leaderboard refresh (heavy compute — ~30 min for 3 genomes
× 12 years on .214).

Revision ID: 070
Revises: 069
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_strategy_validation",
        sa.Column(
            "genome_id",
            UUID(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("strategy_return", sa.Numeric(10, 4), nullable=False),
        sa.Column("benchmark_return", sa.Numeric(10, 4), nullable=False),
        sa.Column("alpha", sa.Numeric(10, 4), nullable=False),
        sa.Column("max_drawdown", sa.Numeric(10, 4), nullable=False),
        sa.Column("benchmark_max_drawdown", sa.Numeric(10, 4), nullable=False),
        sa.Column("sortino", sa.Numeric(10, 4), nullable=False),
        sa.Column("n_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_positions_held", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("genome_id", "year"),
        sa.CheckConstraint("year >= 2010 AND year <= 2100", name="ck_validation_year_range"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_validation_year",
        "atlas_strategy_validation",
        ["year"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_validation_year",
        table_name="atlas_strategy_validation",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_strategy_validation", schema=_SCHEMA)
