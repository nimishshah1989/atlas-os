"""SP09 Phase 2: CTS conviction scoring + enhanced sector pivot.

Adds cts_conviction_score, cts_action_confidence to atlas_cts_signals_daily.
Adds stage2_count, stage2_pct, avg_ppc_conviction, action_alert_count to atlas_cts_sector_pivot_daily.
Seeds 6 new quality-filter thresholds.

Revision ID: 044
Revises: 043
Create Date: 2026-05-13
"""

from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.atlas_cts_signals_daily
          ADD COLUMN IF NOT EXISTS cts_conviction_score NUMERIC(6, 2),
          ADD COLUMN IF NOT EXISTS cts_action_confidence BOOLEAN DEFAULT FALSE
    """)

    op.execute("""
        ALTER TABLE atlas.atlas_cts_sector_pivot_daily
          ADD COLUMN IF NOT EXISTS stage2_count INT NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS stage2_pct NUMERIC(6, 4),
          ADD COLUMN IF NOT EXISTS avg_ppc_conviction NUMERIC(6, 2),
          ADD COLUMN IF NOT EXISTS action_alert_count INT NOT NULL DEFAULT 0
    """)

    op.execute("""
        INSERT INTO atlas.atlas_thresholds (
            threshold_key, threshold_value, category, description,
            min_allowed, max_allowed, default_value, last_modified_by, is_active
        )
        VALUES
            ('cts_ppc_stage_min',          2,    'cts', 'PPC: min Weinstein stage (2=advancing)',           1,    4,    2,    'migration_044', true),
            ('cts_npc_stage_max',          3,    'cts', 'NPC: min stage to fire (3=topping, 4=declining)',  1,    4,    3,    'migration_044', true),
            ('cts_ppc_rs_min',             0.60, 'cts', 'PPC: min RS cross-sector percentile',             0.40, 0.90, 0.60, 'migration_044', true),
            ('cts_npc_rs_max',             0.40, 'cts', 'NPC: max RS cross-sector percentile',             0.10, 0.60, 0.40, 'migration_044', true),
            ('cts_ppc_pp_vol_window',      10,   'cts', 'Morales: lookback bars for down-day volume max',  5,    20,   10,   'migration_044', true),
            ('cts_ppc_high_proximity_pct', 15.0, 'cts', 'PPC: max % below 52-bar high to qualify',        5.0,  30.0, 15.0, 'migration_044', true)
        ON CONFLICT (threshold_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.atlas_cts_signals_daily
          DROP COLUMN IF EXISTS cts_conviction_score,
          DROP COLUMN IF EXISTS cts_action_confidence
    """)
    op.execute("""
        ALTER TABLE atlas.atlas_cts_sector_pivot_daily
          DROP COLUMN IF EXISTS stage2_count,
          DROP COLUMN IF EXISTS stage2_pct,
          DROP COLUMN IF EXISTS avg_ppc_conviction,
          DROP COLUMN IF EXISTS action_alert_count
    """)
    op.execute("""
        DELETE FROM atlas.atlas_thresholds
        WHERE threshold_key IN (
            'cts_ppc_stage_min', 'cts_npc_stage_max', 'cts_ppc_rs_min',
            'cts_npc_rs_max', 'cts_ppc_pp_vol_window', 'cts_ppc_high_proximity_pct'
        )
    """)
