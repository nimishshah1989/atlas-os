"""SP09: CTS Timing Engine — schema foundation.

Creates:
- atlas_cts_signals_daily: daily PPC/NPC/Contraction/Stage per instrument
- atlas_cts_sector_pivot_daily: sector-level PPC/NPC balance
- atlas_cts_timing_ic: rolling Spearman IC for signal strength
- atlas_cts_hit_rates: binary hit rate + lift ratio per signal type
- atlas_cts_param_proposals: threshold calibration proposals

Revision ID: 043
Revises: 042
Create Date: 2026-05-12
"""

from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE atlas.atlas_cts_signals_daily (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date            DATE NOT NULL,
            instrument_id   UUID NOT NULL,
            stage           SMALLINT,
            is_stage1b      BOOLEAN,
            sma_150         NUMERIC(12, 4),
            sma_150_slope   NUMERIC(8, 6),
            trp             NUMERIC(6, 4),
            avg_trp         NUMERIC(6, 4),
            trp_ratio       NUMERIC(6, 4),
            is_tradeable    BOOLEAN,
            is_ppc          BOOLEAN,
            ppc_strength    NUMERIC(6, 4),
            is_npc          BOOLEAN,
            npc_strength    NUMERIC(6, 4),
            is_contraction  BOOLEAN,
            is_trigger_bar  BOOLEAN,
            trigger_level   NUMERIC(12, 4),
            atr_14          NUMERIC(8, 4),
            atr_slope       NUMERIC(10, 6),
            fwd_ret_5d      NUMERIC(8, 6),
            fwd_ret_10d     NUMERIC(8, 6),
            fwd_ret_20d     NUMERIC(8, 6),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_signals_daily_uq UNIQUE (date, instrument_id)
        )
    """)
    op.execute("CREATE INDEX cts_sig_date_idx   ON atlas.atlas_cts_signals_daily (date)")
    op.execute("CREATE INDEX cts_sig_inst_idx   ON atlas.atlas_cts_signals_daily (instrument_id)")
    op.execute("CREATE INDEX cts_sig_ppc_idx    ON atlas.atlas_cts_signals_daily (date) WHERE is_ppc")
    op.execute("CREATE INDEX cts_sig_stage2_idx ON atlas.atlas_cts_signals_daily (date) WHERE stage = 2")

    op.execute("""
        CREATE TABLE atlas.atlas_cts_sector_pivot_daily (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date            DATE NOT NULL,
            sector          VARCHAR(100) NOT NULL,
            ppc_count       INT NOT NULL DEFAULT 0,
            npc_count       INT NOT NULL DEFAULT 0,
            total_tradeable INT NOT NULL DEFAULT 0,
            pivot_balance   NUMERIC(6, 4),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_sector_pivot_uq UNIQUE (date, sector)
        )
    """)

    op.execute("""
        CREATE TABLE atlas.atlas_cts_timing_ic (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date        DATE NOT NULL,
            signal_name       VARCHAR(50) NOT NULL,
            lookback_window   INT NOT NULL,
            forward_horizon   INT NOT NULL,
            n_observations    INT NOT NULL,
            ic                NUMERIC(8, 6),
            t_stat            NUMERIC(8, 4),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_timing_ic_uq UNIQUE (as_of_date, signal_name, lookback_window, forward_horizon)
        )
    """)

    op.execute("""
        CREATE TABLE atlas.atlas_cts_hit_rates (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date        DATE NOT NULL,
            signal_type       VARCHAR(20) NOT NULL,
            stage_filter      SMALLINT,
            forward_horizon   INT NOT NULL,
            return_threshold  NUMERIC(6, 4) NOT NULL,
            hit_count         INT NOT NULL,
            total_signals     INT NOT NULL,
            hit_rate          NUMERIC(6, 4),
            base_rate         NUMERIC(6, 4),
            lift_ratio        NUMERIC(6, 4),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT atlas_cts_hit_rates_uq UNIQUE (as_of_date, signal_type, stage_filter, forward_horizon, return_threshold)
        )
    """)

    op.execute("""
        CREATE TABLE atlas.atlas_cts_param_proposals (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date          DATE NOT NULL,
            param_key           VARCHAR(100) NOT NULL,
            current_value       NUMERIC(12, 6) NOT NULL,
            proposed_value      NUMERIC(12, 6) NOT NULL,
            smoothed_value      NUMERIC(12, 6) NOT NULL,
            direction           VARCHAR(10) NOT NULL,
            expected_lift_delta NUMERIC(8, 6),
            rationale           TEXT NOT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'pending',
            applied_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Seed CTS thresholds (Jhaveri defaults as prior)
    # category, min_allowed, max_allowed, default_value are all NOT NULL
    op.execute("""
        INSERT INTO atlas.atlas_thresholds (
            threshold_key, threshold_value, category, description,
            min_allowed, max_allowed, default_value,
            last_modified_by, is_active
        )
        VALUES
            ('cts_trp_tradeable_min',         2.0,  'cts', 'Min TRP% for tradeable stock',             0.5,  10.0,  2.0,  'migration_043', true),
            ('cts_ppc_range_multiplier',       1.5,  'cts', 'PPC: TRP ratio threshold',                 1.0,  5.0,   1.5,  'migration_043', true),
            ('cts_ppc_close_pct',              0.60, 'cts', 'PPC: close must be in top X% of range',    0.50, 0.90,  0.60, 'migration_043', true),
            ('cts_ppc_volume_multiplier',      1.5,  'cts', 'PPC: volume vs 20-bar avg',                1.0,  5.0,   1.5,  'migration_043', true),
            ('cts_npc_range_multiplier',       1.5,  'cts', 'NPC: TRP ratio threshold',                 1.0,  5.0,   1.5,  'migration_043', true),
            ('cts_npc_close_pct',              0.40, 'cts', 'NPC: close must be in bottom X% of range', 0.10, 0.50,  0.40, 'migration_043', true),
            ('cts_npc_volume_multiplier',      1.5,  'cts', 'NPC: volume vs 20-bar avg',                1.0,  5.0,   1.5,  'migration_043', true),
            ('cts_contraction_bars',           5,    'cts', 'Contraction narrowing lookback bars',       3,    20,    5,    'migration_043', true),
            ('cts_contraction_resistance_pct', 3.0,  'cts', 'Contraction: max % from highest high',     1.0,  10.0,  3.0,  'migration_043', true),
            ('cts_stage2_sma_period',          150,  'cts', 'Weinstein SMA period (trading days)',       100,  250,   150,  'migration_043', true),
            ('cts_stage2_slope_min_days',      20,   'cts', 'SMA slope lookback days',                  10,   60,    20,   'migration_043', true)
        ON CONFLICT (threshold_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_param_proposals")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_hit_rates")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_timing_ic")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_sector_pivot_daily")
    op.execute("DROP TABLE IF EXISTS atlas.atlas_cts_signals_daily")
    op.execute("""
        DELETE FROM atlas.atlas_thresholds
        WHERE threshold_key LIKE 'cts_%'
    """)
