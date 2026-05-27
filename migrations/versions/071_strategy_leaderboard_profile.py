"""Strategy Lab — profile column on leaderboard.

Adds a tunable `profile` column to atlas.atlas_strategy_leaderboard so the
fund-manager view can group strategies into Aggressive / Conservative /
Income buckets without parsing strategy_name strings.

Backfill rule:
  - strategy_name LIKE '%aggressive%'  -> 'aggressive'
  - strategy_name LIKE '%conservative%' -> 'conservative'
  - strategy_name LIKE '%income%'      -> 'income'
  - else                                -> 'aggressive' (safe default for V5
                                          plain + legacy V1-SEED rows)

The column is NULLABLE in this migration so the frontend can land an update
that tolerates pre-migration NULLs first. A follow-up migration (072) will
make it NOT NULL once the frontend ships.

Revision ID: 071
Revises: 070
Create Date: 2026-05-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    op.add_column(
        "atlas_strategy_leaderboard",
        sa.Column("profile", sa.String(length=32), nullable=True),
        schema=_SCHEMA,
    )

    # Backfill from strategy_name pattern. Same defaults the frontend will use.
    op.execute(f"""
        UPDATE {_SCHEMA}.atlas_strategy_leaderboard
        SET profile = CASE
            WHEN strategy_name ILIKE '%conservative%' THEN 'conservative'
            WHEN strategy_name ILIKE '%income%' THEN 'income'
            WHEN strategy_name ILIKE '%defensive%' THEN 'conservative'
            ELSE 'aggressive'
        END
    """)  # noqa: S608  -- _SCHEMA is a module constant, not user input

    # Constrain values once backfilled — keeps future inserts within the
    # known profile vocabulary. NULL still allowed for migration-window
    # tolerance; tightened to NOT NULL in 073.
    op.create_check_constraint(
        "ck_strategy_leaderboard_profile",
        "atlas_strategy_leaderboard",
        "profile IS NULL OR profile IN ('aggressive', 'conservative', 'income')",
        schema=_SCHEMA,
    )

    # Index for the frontend "filter by profile" query pattern.
    op.create_index(
        "ix_strategy_leaderboard_profile",
        "atlas_strategy_leaderboard",
        ["profile"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_leaderboard_profile",
        table_name="atlas_strategy_leaderboard",
        schema=_SCHEMA,
    )
    op.drop_constraint(
        "ck_strategy_leaderboard_profile",
        "atlas_strategy_leaderboard",
        schema=_SCHEMA,
        type_="check",
    )
    op.drop_column("atlas_strategy_leaderboard", "profile", schema=_SCHEMA)
