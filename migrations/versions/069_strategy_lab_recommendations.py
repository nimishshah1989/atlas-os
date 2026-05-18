"""Strategy Lab — daily recommendations table.

The persistent recommendation state required by the goal post. Each row is
"genome G recommends action A on stock I as of date D, with conviction C,
position size P, stop S, confidence band B". The Strategy Lab nightly job
(scripts/strategy_lab_today.py) writes here after the incubator runs.

Schema design:
  - Composite PK: (date, genome_id, instrument_id, action). One genome can
    recommend BUY and SELL on different stocks the same day. Two genomes can
    recommend the same stock the same day (different rows).
  - No FK on instrument_id (cross-modulith rule — same as 067 positions table).
  - No FK on genome_id either (it would chain through atlas_strategy_genomes
    which is mutable; we keep recommendations even if a genome is archived).
  - confidence_band is derived at write time from IR + hit_rate + t_stat.

Revision ID: 069
Revises: 068
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.create_table(
        "atlas_strategy_recommendations_daily",
        sa.Column("date", sa.Date, nullable=False),
        sa.Column(
            "genome_id",
            UUID(as_uuid=True),
            # No FK: see file docstring. Recommendations outlive genome archive.
            nullable=False,
            index=True,
        ),
        sa.Column("rank", sa.Integer, nullable=False),  # leaderboard rank at time of write
        sa.Column("instrument_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "action", sa.Text, nullable=False
        ),  # BUY / HOLD / SELL / EXIT_SIGNAL / STOP_HIT
        sa.Column("conviction", sa.Numeric(10, 4), nullable=False),
        sa.Column("position_size_pct", sa.Numeric(10, 4), nullable=False),
        # Nullable: stop_price only meaningful for BUY/HOLD; SELL/EXIT have NULL.
        sa.Column("stop_price", sa.Numeric(20, 4), nullable=True),
        # Source genome's confidence metrics, copied for audit trail. If a genome
        # is archived, we still know what confidence the recommendation was made under.
        sa.Column("genome_alpha_oos", sa.Numeric(10, 4), nullable=False),
        sa.Column("genome_information_ratio", sa.Numeric(10, 4), nullable=False),
        sa.Column("genome_hit_rate", sa.Numeric(10, 4), nullable=False),
        sa.Column("genome_t_stat", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "confidence_band", sa.Text, nullable=False
        ),  # HIGH / MEDIUM / LOW — derived
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("date", "genome_id", "instrument_id", "action"),
        sa.CheckConstraint(
            "action IN ('BUY','HOLD','SELL','EXIT_SIGNAL','STOP_HIT')",
            name="ck_recommendations_action",
        ),
        sa.CheckConstraint(
            "confidence_band IN ('HIGH','MEDIUM','LOW')",
            name="ck_recommendations_confidence_band",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_recommendations_date",
        "atlas_strategy_recommendations_daily",
        ["date"],
        schema=_SCHEMA,
        postgresql_ops={"date": "DESC"},
    )
    op.create_index(
        "ix_recommendations_date_band",
        "atlas_strategy_recommendations_daily",
        ["date", "confidence_band"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendations_date_band",
        table_name="atlas_strategy_recommendations_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_recommendations_date",
        table_name="atlas_strategy_recommendations_daily",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_strategy_recommendations_daily", schema=_SCHEMA)
