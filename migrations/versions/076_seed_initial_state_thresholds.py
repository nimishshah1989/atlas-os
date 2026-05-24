"""State Engine — seed defensible default thresholds.

These are hand-set defaults for Phase 1 of the State Engine. Phase 2 will
sweep and tune them via IC validation against forward returns.

Revision ID: 076
Revises: 075
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


_SEED: list[tuple[str, str, float]] = [
    # (threshold_name, state_or_gate, value)
    # Uninvestable filter
    ("theta_liq", "uninvestable", 100_000.0),       # min 50d avg ₹ volume
    ("theta_gap", "uninvestable", 20),               # max missing trading days in 252d
    ("theta_min_price", "uninvestable", 10.0),       # min close price (₹)
    # Stage 1 — Base
    ("theta_base_tightness", "stage_1", 0.10),
    ("theta_low_vol", "stage_1", 0.035),
    ("theta_min_recovery_days", "stage_1", 30),
    # Stage 2A — Fresh Breakout
    ("theta_slope_days", "stage_2a", 30),
    ("theta_base_breakout", "stage_2a", 1.02),
    ("theta_vol_mult", "stage_2a", 1.5),
    ("theta_rs", "stage_2a", 70.0),
    ("theta_fresh_days", "stage_2a", 21),
    # Stage 2B — Confirmed
    ("theta_confirmed_days", "stage_2b", 126),
    # Stage 2C — Mature
    ("theta_extension", "stage_2c", 1.10),
    ("theta_atr_expansion", "stage_2c", 1.40),
    # Stage 3 — Top
    ("theta_distribution", "stage_3", 5),
    # Stage 4 — Decline
    ("theta_decline_floor", "stage_4", 0.90),
    # Risk gates
    ("theta_dd_halt", "risk_gate", 15.0),            # halt entries when portfolio DD >= 15%
    ("theta_sector_cap", "risk_gate", 5),            # max stocks per sector
]


def upgrade() -> None:
    insert_sql = sa.text("""
        INSERT INTO atlas.atlas_state_thresholds
            (threshold_name, state_or_gate, threshold_value, as_of_date, active)
        VALUES (:tn, :sg, :v, CURRENT_DATE, TRUE)
        ON CONFLICT (threshold_name, state_or_gate, as_of_date) DO NOTHING
    """)
    bind = op.get_bind()
    for tn, sg, val in _SEED:
        bind.execute(insert_sql, {"tn": tn, "sg": sg, "v": val})


def downgrade() -> None:
    delete_sql = sa.text("""
        DELETE FROM atlas.atlas_state_thresholds
        WHERE active = TRUE
          AND threshold_name = :tn
          AND state_or_gate = :sg
    """)
    bind = op.get_bind()
    for tn, sg, _val in _SEED:
        bind.execute(delete_sql, {"tn": tn, "sg": sg})
