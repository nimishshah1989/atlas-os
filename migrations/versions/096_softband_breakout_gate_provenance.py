"""State Engine — Wave 4C soft-band rework: re-affirm theta_base_breakout = 1.000.

Wave 4C history (the load-bearing decision record):
  - Task 2: the `breakout_ratio` *factor* is decorative cross-sectionally (IR 0.11/0.15).
  - Task 3 (commit 6d972c2): REMOVED the breakout gate from classify_stage_2a.
  - Task 5: removal DEGRADED the aggregate Stage-2 state — 63d IR fell from +0.243
    (gate intact) to +0.179 (gate removed), out of the weak band into decorative.
  - Wave 4C soft-band rework: theta_base_breakout was IC-grid-tuned over
    {0.90, 0.92, 0.94, 0.96, 0.98} on the 524,887-row 2023-2026 panel, OLD-topology
    apples-to-apples vs the +0.243 Task 5 baseline. 63d IR is monotone in theta —
    0.90→0.202, 0.92→0.206, 0.94→0.208, 0.96→0.224, 0.98→0.225, 1.00→0.243.
    NO soft-band value in 0.90-0.98 clears the 0.243 SHIP bar.

Decision: the breakout gate is RE-INTRODUCED in classify_stage_2a (it was removed
by Task 3) but kept at theta_base_breakout = 1.000 — the IC-proven value. The gate
works as a binary quality filter precisely because it is a literal 60-day-high
filter; any loosening admits a lower-quality cohort that dilutes the Stage-2 IR.

This migration is intentionally value-neutral: the active atlas_state_thresholds
row for ('theta_base_breakout','stage_2a') is already 1.000 (left active, at 1.000,
by migration 077 — Task 3 stopped *reading* it but did not deactivate it). This
migration re-stamps the row with a current as_of_date so the threshold-history
audit trail records the Wave 4C re-validation as an explicit decision rather than
a stale leftover. See docs/audits/2026-05-stage2-softband-revalidation.md.

Revision ID: 096_softband_breakout_gate_provenance
Revises: 095_seed_hybrid_classifier_thresholds
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "096_softband_breakout_gate_provenance"
down_revision = "095_seed_hybrid_classifier_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deactivate any prior active row (preserving it for history).
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_base_breakout'
          AND state_or_gate = 'stage_2a'
          AND active = TRUE
    """))
    # Re-affirm the IC-proven value (1.000) as active with a Wave 4C as_of_date.
    # ON CONFLICT handles a same-day re-run (idempotent).
    op.execute(sa.text("""
        INSERT INTO atlas.atlas_state_thresholds
            (threshold_name, state_or_gate, threshold_value, as_of_date, active)
        VALUES ('theta_base_breakout', 'stage_2a', 1.000, CURRENT_DATE, TRUE)
        ON CONFLICT (threshold_name, state_or_gate, as_of_date) DO UPDATE SET
            threshold_value = EXCLUDED.threshold_value, active = TRUE
    """))


def downgrade() -> None:
    # Revert: deactivate the Wave 4C row, reactivate the most recent prior row.
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = FALSE
        WHERE threshold_name = 'theta_base_breakout'
          AND state_or_gate = 'stage_2a'
          AND as_of_date = CURRENT_DATE
    """))
    op.execute(sa.text("""
        UPDATE atlas.atlas_state_thresholds
        SET active = TRUE
        WHERE (threshold_name, state_or_gate, as_of_date) = (
            SELECT 'theta_base_breakout', 'stage_2a', MAX(as_of_date)
            FROM atlas.atlas_state_thresholds
            WHERE threshold_name = 'theta_base_breakout'
              AND state_or_gate = 'stage_2a'
              AND as_of_date < CURRENT_DATE
        )
    """))
