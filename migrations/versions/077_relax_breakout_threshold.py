"""State Engine — relax theta_base_breakout 1.02 -> 1.00.

Phase 1 smoke (2026-05-18) revealed that with theta_base_breakout=1.02 and
max_close_60d computed inclusive of today, the Stage 2A breakout rule was
trivially unsatisfiable for quiet-grinder uptrends (today == max →
close >= 1.02 × close is always false).

Two fixes shipped together:
  1. CLI _compute_features_for_stock now shifts the 60d-max by one day so
     today is excluded.
  2. This migration relaxes theta_base_breakout from 1.02 to 1.00 so that
     simply printing a new high qualifies (1.02 was always going to be too
     strict combined with the shifted-max; Phase 2 IC tuning will refine).

Marks the 1.02 row inactive (preserving history) and inserts the 1.00 row
as active.

Revision ID: 077
Revises: 076
Create Date: 2026-05-18
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deactivate the prior row (preserving it for history)
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_base_breakout'
          AND state_or_gate = 'stage_2a'
          AND active = TRUE
    """))
    # Insert the new row as active
    op.execute(sa.text("""
        INSERT INTO atlas.atlas_state_thresholds
            (threshold_name, state_or_gate, threshold_value, as_of_date, active)
        VALUES ('theta_base_breakout', 'stage_2a', 1.00, CURRENT_DATE, TRUE)
        ON CONFLICT (threshold_name, state_or_gate, as_of_date) DO UPDATE SET
            threshold_value = EXCLUDED.threshold_value, active = TRUE
    """))


def downgrade() -> None:
    # Revert: deactivate the 1.00 row, reactivate the original 1.02 row
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_base_breakout'
          AND state_or_gate = 'stage_2a'
          AND threshold_value = 1.00
    """))
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = TRUE
        WHERE threshold_name = 'theta_base_breakout'
          AND state_or_gate = 'stage_2a'
          AND threshold_value = 1.02
    """))
