"""SP04 Stage 3: conviction tables.

Three audit-tracked tables plus a materialized view:

- atlas_signal_weights: currently-active per-tier weight sets, with
  effective_from/effective_to history columns. A partial unique index
  enforces at most one active row per (tier, regime, signal).
- atlas_tier_membership_daily: each instrument's liquidity tier by date,
  ranked on 20-day ADV (top 1000 retained).
- atlas_stock_conviction_daily: computed conviction score per (stock,
  date) with a JSONB per-signal breakdown for audit + UI breakdown panel.
- mv_top_conviction_daily: latest-date top conviction names where
  confidence_label is industry_grade or baseline, refreshed by pg_cron.

Revision ID: 039
Revises: 038
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. atlas_signal_weights — currently-active weights per tier × signal
    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_signal_weights (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tier            VARCHAR(32) NOT NULL,
            regime          VARCHAR(16) NOT NULL DEFAULT 'all',
            signal_name     VARCHAR(64) NOT NULL,
            weight          NUMERIC(8, 6) NOT NULL,
            flipped         BOOLEAN NOT NULL DEFAULT FALSE,
            effective_from  DATE NOT NULL,
            effective_to    DATE,
            train_ic        NUMERIC(8, 6),
            holdout_ic      NUMERIC(8, 6),
            approved_by     VARCHAR(64) NOT NULL DEFAULT 'sp04-stage2-initial',
            approved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_weights_tier CHECK (tier IN (
                'tier_1_megacap','tier_2_largecap','tier_3_uppermid',
                'tier_4_lowermid','tier_5_smallcap'
            )),
            CONSTRAINT chk_weights_regime CHECK (regime IN (
                'Risk-On','Constructive','Cautious','Risk-Off','all'
            )),
            CONSTRAINT chk_weights_value CHECK (weight >= 0 AND weight <= 1)
        )
        """)
    )

    # At most one active (effective_to IS NULL) row per (tier, regime, signal)
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_weights_active
        ON atlas.atlas_signal_weights (tier, regime, signal_name)
        WHERE effective_to IS NULL
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_signal_weights_lookup
        ON atlas.atlas_signal_weights (tier, regime)
        WHERE effective_to IS NULL
        """)
    )

    # 2. atlas_tier_membership_daily — liquidity tier per (instrument, date)
    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_tier_membership_daily (
            instrument_id   UUID NOT NULL,
            date            DATE NOT NULL,
            tier            VARCHAR(32) NOT NULL,
            adv_rank        INTEGER NOT NULL,
            adv_20d         NUMERIC(20, 2),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date),
            CONSTRAINT chk_tier_value CHECK (tier IN (
                'tier_1_megacap','tier_2_largecap','tier_3_uppermid',
                'tier_4_lowermid','tier_5_smallcap','untiered'
            ))
        )
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_tier_membership_date_tier
        ON atlas.atlas_tier_membership_daily (date DESC, tier)
        """)
    )

    # 3. atlas_stock_conviction_daily — computed conviction per (stock, date)
    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_conviction_daily (
            instrument_id        UUID NOT NULL,
            date                 DATE NOT NULL,
            tier                 VARCHAR(32) NOT NULL,
            conviction_score     NUMERIC(6, 4) NOT NULL,
            confidence_label     VARCHAR(32) NOT NULL,
            backing_ic           NUMERIC(8, 6),
            contributing_signals JSONB NOT NULL,
            weight_set_version   VARCHAR(96) NOT NULL,
            computed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date),
            CONSTRAINT chk_conviction_score
                CHECK (conviction_score >= 0 AND conviction_score <= 1),
            CONSTRAINT chk_conviction_label CHECK (confidence_label IN (
                'industry_grade','baseline','descriptive_only'
            ))
        )
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_conviction_date_tier_score
        ON atlas.atlas_stock_conviction_daily (date DESC, tier, conviction_score DESC)
        """)
    )

    # 4. Materialized view: latest-date top conviction names (industry_grade + baseline only)
    op.execute(
        sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_top_conviction_daily AS
        SELECT
            c.instrument_id,
            c.date,
            c.tier,
            c.conviction_score,
            c.confidence_label,
            c.backing_ic,
            c.contributing_signals
        FROM atlas.atlas_stock_conviction_daily c
        WHERE c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
          AND c.confidence_label IN ('industry_grade', 'baseline')
        ORDER BY c.tier, c.conviction_score DESC
        """)
    )
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_top_conviction_instrument
        ON atlas.mv_top_conviction_daily (instrument_id)
        """)
    )

    # 5. pg_cron refresh (skipped if extension missing — handled on EC2 only)
    op.execute(
        sa.text("""
        DO $body$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                PERFORM cron.schedule(
                    'atlas_mv_conviction',
                    '45 14 * * *',
                    'REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_top_conviction_daily'
                );
            ELSE
                RAISE NOTICE 'pg_cron not installed; skipping schedule (apply on EC2)';
            END IF;
        END
        $body$;
        """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
        DO $body$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                PERFORM cron.unschedule('atlas_mv_conviction');
            END IF;
        EXCEPTION WHEN OTHERS THEN NULL;
        END
        $body$;
        """)
    )
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_top_conviction_daily"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_stock_conviction_daily"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_tier_membership_daily"))
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.uq_signal_weights_active"))
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_signal_weights_lookup"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_signal_weights"))
