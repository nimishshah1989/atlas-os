"""Add per-instrument target_weight_pct to instruments JSONB
+ create atlas_portfolio_proposed_change.

Wave 3 "Act loop" data model — corrected after code review:

1. Per-instrument target_weight_pct backfilled into the instruments JSONB array on
   atlas.strategy_fm_custom_portfolios.  Each element gains a "target_weight_pct" key
   (null = no target set yet — honest default; Task 3.5 renders current vs target per
   holding).  The instruments column was created in migration 020 as JSONB NOT NULL and
   holds an array of objects of the form {instrument_id, instrument_type, weight_pct}.
   A portfolio-level scalar target_weight column was considered and rejected: a single
   scalar cannot express per-instrument targets as required by Task 3.5.

2. atlas_portfolio_proposed_change — one row per proposed (not-yet-executed) trade,
   sized by policy, before compliance sign-off.  Statuses: pending → applied | rejected.
   This table is unchanged from the original design — per-instrument proposed changes are
   naturally row-per-instrument.

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

# ---------------------------------------------------------------------------
# JSONB backfill SQL
# ---------------------------------------------------------------------------
# Adds "target_weight_pct": null to every element of the instruments JSONB
# array that does not already carry that key.  Guards:
#   • WHERE instruments IS NOT NULL         — skip explicit NULLs
#   • AND jsonb_typeof(instruments) = 'array' — skip non-array JSONB
#   • AND jsonb_array_length(instruments) > 0 — skip empty arrays (no-op but
#                                               avoids scanning them)
# The CASE preserves elements that already have the key (idempotent if run
# twice).
_BACKFILL_TARGET_WEIGHT_PCT = """
UPDATE atlas.strategy_fm_custom_portfolios
SET instruments = (
    SELECT jsonb_agg(
        CASE WHEN elem ? 'target_weight_pct' THEN elem
             ELSE elem || '{"target_weight_pct": null}'::jsonb END
    )
    FROM jsonb_array_elements(instruments) AS elem
)
WHERE instruments IS NOT NULL
  AND jsonb_typeof(instruments) = 'array'
  AND jsonb_array_length(instruments) > 0
"""

# Strips the "target_weight_pct" key from every element (downgrade path).
_STRIP_TARGET_WEIGHT_PCT = """
UPDATE atlas.strategy_fm_custom_portfolios
SET instruments = (
    SELECT jsonb_agg(elem - 'target_weight_pct')
    FROM jsonb_array_elements(instruments) AS elem
)
WHERE instruments IS NOT NULL
  AND jsonb_typeof(instruments) = 'array'
  AND jsonb_array_length(instruments) > 0
"""


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Backfill target_weight_pct into every instruments JSONB element
    # ------------------------------------------------------------------
    # instruments is a JSONB NOT NULL column (migration 020) that stores an
    # array of per-holding objects.  We add "target_weight_pct": null to
    # each element that doesn't already carry the key.
    op.execute(sa.text(_BACKFILL_TARGET_WEIGHT_PCT))

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
        # Numeric(7,4): supports 0.0000–99.9999 % per instrument.
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
    op.drop_table(_TABLE, schema=_SCHEMA)
    # Strip target_weight_pct key from all instruments JSONB elements.
    op.execute(sa.text(_STRIP_TARGET_WEIGHT_PCT))
