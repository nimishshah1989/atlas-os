"""crossover v2: intraday alert log + decision-trail column

Two additions, both additive and both independently reversible (spec §I.1, §Schema):

  * ``portfolio_trades.composite_at_signal`` — conviction as a real numeric column so
    it can be sorted, filtered and aggregated. The prose lives in the existing
    ``rationale`` column; a number you want to query does not belong inside a sentence.

  * ``crossover_alerts`` — the intraday alerter's dedup + audit log. It writes one row
    per (book, instrument, direction, stage, IST day), which is what stops a 5-minute
    poll firing the same Telegram 78 times. Read-only feed: the nightly mark remains
    the only writer of trades.

No change to the ``run_type`` or ``reason`` CHECKs. The twin books both use
live/backtest, and a death-cross exit and an EMA13 exit are both ``signal`` — which
of the two fired is already implied by the book's own ``exit`` param, so widening a
constraint to restate it would be duplication.

Revision ID: 0002_crossover_v2_decision_trail
Revises: 0001_baseline_atlas_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_crossover_v2_decision_trail"
down_revision: str | None = "0001_baseline_atlas_foundation"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "atlas_foundation"


def upgrade() -> None:
    # Nullable by design: 25,584 historical trades pre-date the trail and stay NULL
    # until their next backtest rebuild repopulates them. Numeric, never float —
    # this is a score that feeds ranking decisions.
    op.add_column(
        "portfolio_trades",
        sa.Column("composite_at_signal", sa.Numeric(20, 4), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "crossover_alerts",
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.portfolio_master.portfolio_id"),
            nullable=False,
        ),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("direction", sa.Text, nullable=False),
        # provisional = breached intraday, not a trade yet.
        # confirmed    = the close (buys) or the 15:15 quote (sells) held it.
        # disarmed     = it recovered before the lock, so no trade. Kept ON PURPOSE:
        #                the near-misses are how the FM judges whether the lock is
        #                earning its keep, and deleting them would hide that.
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column(
            "alert_date",
            sa.Date,
            nullable=False,
            server_default=sa.text("(now() AT TIME ZONE 'Asia/Kolkata')::date"),
        ),
        sa.Column("level", sa.Numeric(20, 4), nullable=False),
        sa.Column("quote", sa.Numeric(20, 4), nullable=False),
        sa.Column("ema_fast", sa.Numeric(20, 4)),
        sa.Column("ema_slow", sa.Numeric(20, 4)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("direction in ('buy','sell')", name="crossover_alerts_direction_check"),
        sa.CheckConstraint(
            "stage in ('provisional','confirmed','disarmed')",
            name="crossover_alerts_stage_check",
        ),
        # The dedup contract: one row per book/instrument/direction/stage/IST day.
        sa.UniqueConstraint(
            "portfolio_id",
            "instrument_id",
            "direction",
            "stage",
            "alert_date",
            name="crossover_alerts_dedup",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_crossover_alerts_portfolio_date",
        "crossover_alerts",
        ["portfolio_id", "alert_date"],
        schema=SCHEMA,
    )
    # every FK column indexed, per the project DB conventions
    op.create_index(
        "ix_crossover_alerts_instrument",
        "crossover_alerts",
        ["instrument_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_crossover_alerts_instrument", "crossover_alerts", schema=SCHEMA)
    op.drop_index("ix_crossover_alerts_portfolio_date", "crossover_alerts", schema=SCHEMA)
    op.drop_table("crossover_alerts", schema=SCHEMA)
    op.drop_column("portfolio_trades", "composite_at_signal", schema=SCHEMA)
