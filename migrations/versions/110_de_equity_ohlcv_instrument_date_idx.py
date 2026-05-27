"""Add (instrument_id, date) index on de_equity_ohlcv — unblocks atlas_compute_adjustments.

# allow-large: pg propagates parent-table index to 35 partitions

Root cause of the silent 4-day pipeline gap (2026-05-22 -> 2026-05-27):
  scripts/atlas_compute_adjustments.py iterates ~216 instruments running:

    SELECT close::float FROM public.de_equity_ohlcv
    WHERE instrument_id = :iid AND date < :d
    ORDER BY date DESC LIMIT 1

  The PK (date, instrument_id) has the wrong leading column. Only the
  standalone (instrument_id) index is usable, returning ~6000 rows per
  instrument which then sort in-memory. Combined with Supabase 2-min
  statement_timeout, the query times out. Nightly ERR trap fires, M2-M5
  never runs.

Fix: composite (instrument_id, date). PG handles `ORDER BY date DESC LIMIT 1`
via backward index scan. Postgres-12+ propagates parent indexes to all
current and future partitions automatically.

Revision ID: 110
Revises: 109
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "110"
down_revision = "109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_de_equity_ohlcv_instrument_date "
        "ON public.de_equity_ohlcv (instrument_id, date);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.ix_de_equity_ohlcv_instrument_date;")
