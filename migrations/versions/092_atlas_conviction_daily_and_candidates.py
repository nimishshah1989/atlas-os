"""v6 — atlas_cell_rule_candidates + atlas_conviction_daily.

Two tables that close out the deep-search → daily-tape pipeline:

1. ``atlas_cell_rule_candidates`` — top-K validated rules per cell. The
   primary ``atlas_cell_definitions`` row is the cell's single canonical
   rule (top-1 by friction-adjusted excess, sign-correct per direction).
   The 4 next-best candidates live here as the ensemble runner-ups —
   queryable per cell, ranked 1..5.

2. ``atlas_conviction_daily`` — per-(instrument × tenure) daily verdict
   produced by ``atlas.inference.conviction_tape``. One row per
   ``(snapshot_date, instrument_id, tenure)``, with the best firing rule
   id, verdict (POSITIVE / NEUTRAL / NEGATIVE), ELI5 explanation, and a
   conflict flag when both directions fire on the same instrument.

Revision ID: 092
Revises: 089
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "092"
down_revision = "089"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # -----------------------------------------------------------------
    # atlas_cell_rule_candidates — top-K validated rules per cell
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_cell_rule_candidates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cell_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("rule_dsl", postgresql.JSONB(), nullable=False),
        sa.Column("archetype", sa.String(length=40), nullable=False),
        sa.Column("ic", sa.Numeric(8, 4), nullable=True),
        sa.Column("friction_adjusted_excess", sa.Numeric(10, 4), nullable=True),
        sa.Column("bh_q_value", sa.Numeric(8, 4), nullable=True),
        sa.Column("eli5", sa.Text(), nullable=True),
        sa.Column(
            "validated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "cell_definition_id",
            "rank",
            name="uq_atlas_cell_rule_candidates_cell_rank",
        ),
        sa.CheckConstraint(
            "rank BETWEEN 1 AND 20",
            name="ck_atlas_cell_rule_candidates_rank_range",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_cell_rule_candidates_cell",
        "atlas_cell_rule_candidates",
        ["cell_definition_id"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_conviction_daily — per-instrument × tenure daily verdict
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_conviction_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Tenure stored as VARCHAR(3) for the four allowed values — using
        # the existing atlas_tenure enum here would force a cross-migration
        # enum bind that complicates downgrade.  CHECK below pins the
        # vocabulary.
        sa.Column("tenure", sa.String(length=3), nullable=False),
        # Verdict similarly stored as VARCHAR (POSITIVE/NEUTRAL/NEGATIVE)
        # to stay loose from the atlas_cell_action enum.
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column(
            "best_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_rule_candidates.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "cell_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("ic", sa.Numeric(8, 4), nullable=True),
        sa.Column("friction_adjusted_excess", sa.Numeric(10, 4), nullable=True),
        sa.Column("fired_predicates", postgresql.JSONB(), nullable=True),
        sa.Column("eli5", sa.Text(), nullable=True),
        sa.Column(
            "conflict",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_date",
            "instrument_id",
            "tenure",
            name="uq_atlas_conviction_daily_natural_key",
        ),
        sa.CheckConstraint(
            "tenure IN ('1m','3m','6m','12m')",
            name="ck_atlas_conviction_daily_tenure",
        ),
        sa.CheckConstraint(
            "verdict IN ('POSITIVE','NEUTRAL','NEGATIVE')",
            name="ck_atlas_conviction_daily_verdict",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_conviction_daily_iid_date",
        "atlas_conviction_daily",
        ["instrument_id", "snapshot_date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_conviction_daily_date_verdict",
        "atlas_conviction_daily",
        ["snapshot_date", "verdict"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Drop the two new tables in reverse FK order."""
    op.drop_index(
        "idx_conviction_daily_date_verdict",
        table_name="atlas_conviction_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "idx_conviction_daily_iid_date",
        table_name="atlas_conviction_daily",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_conviction_daily", schema=_SCHEMA)

    op.drop_index(
        "idx_cell_rule_candidates_cell",
        table_name="atlas_cell_rule_candidates",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_cell_rule_candidates", schema=_SCHEMA)
