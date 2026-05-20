"""Add target_weight to custom portfolios + create atlas_portfolio_proposed_change.

Wave 3 "Act loop" data model:
1. target_weight (Numeric, nullable) added to atlas.strategy_fm_custom_portfolios —
   represents the fund manager's intended total allocation target for a portfolio.
   NULL = no target set yet.

2. atlas_portfolio_proposed_change — one row per proposed (not-yet-executed) trade,
   sized by policy, before compliance sign-off.  Statuses: pending → applied | rejected.

Notes on instrument_id:
  atlas_universe_stocks has a composite PK (instrument_id, effective_from) so it cannot
  serve as a direct FK target.  The same bounded-context decision was made in migration
  067 (atlas_strategy_positions_daily) and atlas_universe_membership_daily.  instrument_id
  is therefore a plain indexed UUID — validated at write time by the Act layer.

Revision ID: 093_portfolio_targets_holdings
Revises: 092_atlas_portfolio_policy
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "093_portfolio_targets_holdings"
down_revision = "092_atlas_portfolio_policy"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"
_TABLE = "atlas_portfolio_proposed_change"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add target_weight to atlas.strategy_fm_custom_portfolios
    # ------------------------------------------------------------------
    # Numeric(7,4): supports 0.0000–999.9999 — covers any percentage target.
    # Nullable: NULL means "no target set yet" — valid state for new portfolios.
    op.add_column(
        "strategy_fm_custom_portfolios",
        sa.Column(
            "target_weight",
            sa.Numeric(7, 4),
            nullable=True,
        ),
        schema=_SCHEMA,
    )

    # ------------------------------------------------------------------
    # 2. Create atlas_portfolio_proposed_change
    # ------------------------------------------------------------------
    op.create_table(
        _TABLE,
        # --- Identity ---
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # --- FK to portfolio ---
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "atlas.strategy_fm_custom_portfolios.id",
                name="fk_proposed_change_portfolio_id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        ),
        # --- Instrument ---
        # Plain indexed UUID — no FK.  Validated at write time by the Act layer.
        # (Universe tables use composite PKs; see module docstring for full rationale.)
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            nullable=False,
            index=True,
        ),
        # --- Proposed allocation ---
        # Numeric(7,4): matches target_weight precision; covers 0.0000–99.9999 % per instrument.
        sa.Column(
            "proposed_weight",
            sa.Numeric(7, 4),
            nullable=False,
        ),
        # --- Lifecycle ---
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # --- Rationale ---
        # Nullable free-text note explaining the proposal (e.g. "gap-bound 2.5%").
        # Used by Task 3.4 Act affordance to surface reasoning alongside the proposed change.
        sa.Column(
            "rationale",
            sa.Text(),
            nullable=True,
        ),
        # --- Audit ---
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # --- CHECK constraints ---
        sa.CheckConstraint(
            "status IN ('pending','applied','rejected')",
            name="ck_proposed_change_status",
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("atlas_portfolio_proposed_change", schema=_SCHEMA)
    op.drop_column("strategy_fm_custom_portfolios", "target_weight", schema=_SCHEMA)
