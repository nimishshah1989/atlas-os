"""State Engine — swap decorative vol/volume predicates with IC-validated replacements.

IC investigation against 273k rows of 2023-2024 classified state data found:
  - atr_14 / close (Stage 1 vol metric): IR -0.18 at 63d → decorative
  - volume_today / volume_50d_avg (Stage 2A volume req): IR 0.15 at 21d → decorative
  - atr_14 / atr_14_252d_avg (contraction ratio): IR -0.48 at 63d → VALIDATED
  - realized_vol_63 (per-stock realized vol): IR +0.55 at 63d → VALIDATED
  - obv_slope_50d (OBV slope over 50 days): IR -0.43 at 63d → VALIDATED_INVERSE

Four changes:
  1. Deactivate theta_low_vol (stage_1) — replaced by theta_contraction
  2. Deactivate theta_vol_mult (stage_2a) — volume requirement dropped
  3. Insert theta_contraction (stage_1, 0.95) — atr_14/atr_14_252d_avg < 0.95
  4. Insert theta_obv_slope_neg (stage_3, 0.0) — OBV slope < 0 triggers topping

Revision ID: 078
Revises: 077
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Deactivate theta_low_vol (stage_1) — IC-invalid, IR -0.18 at 63d.
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_low_vol'
          AND state_or_gate = 'stage_1'
          AND active = TRUE
    """))

    # 2. Deactivate theta_vol_mult (stage_2a) — IC-invalid, IR 0.15 at 21d.
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_vol_mult'
          AND state_or_gate = 'stage_2a'
          AND active = TRUE
    """))

    # 3. Insert theta_contraction (stage_1, 0.95).
    #    atr_14 / atr_14_252d_avg < 0.95 means ATR is at least 5% below its
    #    252-day average — confirming volatility contraction in a base.
    #    IC-validated: IR -0.48 at 63d (contraction predicts high forward returns).
    op.execute(sa.text("""
        INSERT INTO atlas.atlas_state_thresholds
            (threshold_name, state_or_gate, threshold_value, as_of_date, active)
        VALUES ('theta_contraction', 'stage_1', 0.95, CURRENT_DATE, TRUE)
        ON CONFLICT (threshold_name, state_or_gate, as_of_date) DO NOTHING
    """))

    # 4. Insert theta_obv_slope_neg (stage_3, 0.0).
    #    OBV slope below 0 (i.e., negative) triggers the OBV topping conjunct.
    #    IC-validated: IR -0.43 at 63d for held Stage 2 stocks (inverse — falling
    #    OBV signals distribution; "exit warning").
    op.execute(sa.text("""
        INSERT INTO atlas.atlas_state_thresholds
            (threshold_name, state_or_gate, threshold_value, as_of_date, active)
        VALUES ('theta_obv_slope_neg', 'stage_3', 0.0, CURRENT_DATE, TRUE)
        ON CONFLICT (threshold_name, state_or_gate, as_of_date) DO NOTHING
    """))


def downgrade() -> None:
    # Reverse 4: remove theta_obv_slope_neg (stage_3).
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_obv_slope_neg'
          AND state_or_gate = 'stage_3'
    """))

    # Reverse 3: remove theta_contraction (stage_1).
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_contraction'
          AND state_or_gate = 'stage_1'
    """))

    # Reverse 2: reactivate theta_vol_mult (stage_2a, value=1.5 from migration 076).
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = TRUE
        WHERE threshold_name = 'theta_vol_mult'
          AND state_or_gate = 'stage_2a'
          AND threshold_value = 1.5
    """))

    # Reverse 1: reactivate theta_low_vol (stage_1, value=0.035 from migration 076).
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = TRUE
        WHERE threshold_name = 'theta_low_vol'
          AND state_or_gate = 'stage_1'
          AND threshold_value = 0.035
    """))
