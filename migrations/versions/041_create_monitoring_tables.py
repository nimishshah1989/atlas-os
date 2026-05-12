"""SP04 Stage 4c: live performance tracking, hit rate, revert audit.

- atlas_signal_weights_live_perf: per (weight_set_version, as_of_date) the
  realized IC of the composite over the most recent 21-day forward window,
  alongside the predicted IC from the seed metadata. ic_ratio surfaces
  realized/predicted so the drift detector can scan a single column.
- atlas_stock_hit_rate_daily: per (instrument_id, date, lookback_window)
  the hit-rate of past high-conviction days for this stock. n_high counts
  windows in which conviction was at or above tier-median; n_pos counts
  those windows where realized forward return beat tier-median forward
  return.
- atlas_weight_revert_log: audit row per auto-revert. Captures the
  reverted-from and restored-to versions, the trigger reason, and the
  days-below-threshold count.

Revision ID: 041
Revises: 040
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_signal_weights_live_perf (
            weight_set_version  VARCHAR(96) NOT NULL,
            as_of_date          DATE NOT NULL,
            tier                VARCHAR(32) NOT NULL,
            regime              VARCHAR(16) NOT NULL DEFAULT 'all',
            predicted_holdout_ic NUMERIC(8, 6),
            realized_ic         NUMERIC(8, 6),
            ic_ratio            NUMERIC(8, 4),
            n_observations      INTEGER NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (weight_set_version, as_of_date),
            CONSTRAINT chk_live_perf_tier CHECK (tier IN (
                'tier_1_megacap','tier_2_largecap','tier_3_uppermid',
                'tier_4_lowermid','tier_5_smallcap'
            ))
        )
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_live_perf_tier_date
        ON atlas.atlas_signal_weights_live_perf (tier, as_of_date DESC)
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_live_perf_ratio
        ON atlas.atlas_signal_weights_live_perf (tier, ic_ratio)
        WHERE ic_ratio IS NOT NULL
        """)
    )

    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_hit_rate_daily (
            instrument_id           UUID NOT NULL,
            date                    DATE NOT NULL,
            lookback_window         INTEGER NOT NULL DEFAULT 20,
            n_high_conviction_days  INTEGER NOT NULL DEFAULT 0,
            n_positive_outcomes     INTEGER NOT NULL DEFAULT 0,
            hit_rate                NUMERIC(6, 4),
            tier_at_as_of           VARCHAR(32),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date, lookback_window),
            CONSTRAINT chk_hit_rate_range
                CHECK (hit_rate IS NULL OR (hit_rate >= 0 AND hit_rate <= 1)),
            CONSTRAINT chk_hit_rate_counts
                CHECK (n_positive_outcomes <= n_high_conviction_days)
        )
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_hit_rate_recent
        ON atlas.atlas_stock_hit_rate_daily (instrument_id, date DESC)
        """)
    )

    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_weight_revert_log (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tier                    VARCHAR(32) NOT NULL,
            regime                  VARCHAR(16) NOT NULL DEFAULT 'all',
            reverted_from_version   VARCHAR(96) NOT NULL,
            restored_to_version     VARCHAR(96),
            days_below_threshold    INTEGER NOT NULL,
            realized_ic_avg         NUMERIC(8, 6),
            predicted_holdout_ic    NUMERIC(8, 6),
            ratio_threshold         NUMERIC(6, 4) NOT NULL DEFAULT 0.5,
            triggered_by            VARCHAR(32) NOT NULL,
            notes                   TEXT,
            applied_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_revert_tier CHECK (tier IN (
                'tier_1_megacap','tier_2_largecap','tier_3_uppermid',
                'tier_4_lowermid','tier_5_smallcap'
            )),
            CONSTRAINT chk_revert_trigger
                CHECK (triggered_by IN ('auto-detector', 'manual-admin'))
        )
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_revert_log_applied
        ON atlas.atlas_weight_revert_log (applied_at DESC)
        """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_weight_revert_log"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_stock_hit_rate_daily"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_signal_weights_live_perf"))
