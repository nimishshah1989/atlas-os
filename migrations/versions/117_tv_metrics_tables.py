"""tv_metrics and tv_portfolio_exports tables

Revision ID: 117
Revises: 116
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa

revision = "117"
down_revision = "116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.tv_metrics (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol          TEXT NOT NULL,
            instrument_id   UUID,
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            tv_recommend_label  TEXT,
            recommend_all   NUMERIC(10,6),
            recommend_ma    NUMERIC(10,6),
            recommend_other NUMERIC(10,6),
            rsi_14          NUMERIC(10,4),
            macd_macd       NUMERIC(10,4),
            ema_20          NUMERIC(16,4),
            ema_50          NUMERIC(16,4),
            ema_200         NUMERIC(16,4),
            atr_14          NUMERIC(16,4),
            volume          BIGINT,
            volume_10d_avg  BIGINT,
            price           NUMERIC(16,4),
            high_52w        NUMERIC(16,4),
            low_52w         NUMERIC(16,4),
            raw_payload     JSONB,
            CONSTRAINT tv_metrics_symbol_unique UNIQUE (symbol)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tv_metrics_instrument_id
            ON atlas.tv_metrics (instrument_id)
            WHERE instrument_id IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS atlas.tv_portfolio_exports (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id    UUID NOT NULL,
            exported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            row_count       INT NOT NULL,
            file_bytes      BYTEA
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tv_portfolio_exports_portfolio_id
            ON atlas.tv_portfolio_exports (portfolio_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS atlas.tv_portfolio_exports")
    op.execute("DROP TABLE IF EXISTS atlas.tv_metrics")
