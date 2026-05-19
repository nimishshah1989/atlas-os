"""v6 clean OHLCV view — excludes corrupt rows (ret_1d > 25% on volume < 1000).

Corrupt rows signature: big price move on suspiciously low volume, caused by
futures/index prices being inserted into equity ticker rows.

Revision ID: 088
Revises: 087
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op

revision = "091"
down_revision = "090_legacy_validation_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_v6_clean_ohlcv AS
        WITH with_prev AS (
          SELECT
            symbol, date, open, high, low, close, volume,
            LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close
          FROM public.de_equity_ohlcv
        )
        SELECT symbol, date, open, high, low, close, volume
          FROM with_prev
         WHERE prev_close IS NULL
            OR ABS(close / NULLIF(prev_close, 0) - 1) <= 0.25
            OR volume >= 1000;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS atlas.atlas_v6_clean_ohlcv;")
