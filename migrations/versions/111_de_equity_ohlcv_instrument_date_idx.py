"""v6 — index for (instrument_id, date DESC) on de_equity_ohlcv.

Fixes the 2-minute statement_timeout that crashes step [1f]
`atlas_compute_adjustments.py` in run_atlas_nightly.sh. That script runs
per-instrument lookups of the form:

    SELECT close FROM public.de_equity_ohlcv
    WHERE instrument_id = X AND date < Y
    ORDER BY date DESC LIMIT 1;

Existing indexes on each partition:
  - PK on (date, instrument_id)          → wrong leading column for this query
  - separate index on (instrument_id)    → returns ~6000 rows for the stock,
                                            then sort-by-date for LIMIT 1
Both result in a sort over thousands of rows × 216 instruments ×
33 partitions = guaranteed 2-min timeout.

The (instrument_id, date DESC) composite gives index-only access:
seek to first matching (instrument_id, date), return one row.

PG12+ partitioned-index syntax — CREATE INDEX on the parent declares an
index template; PG attaches it to every partition automatically (current
+ future).

Revision ID: 111
Revises: 110
Create Date: 2026-05-28 IST
"""

from __future__ import annotations

from alembic import op

revision = "111"
down_revision = "110"
branch_labels = None
depends_on = None

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS de_equity_ohlcv_instrument_date_desc_idx
ON public.de_equity_ohlcv (instrument_id, date DESC);
"""

_DROP_INDEX = """
DROP INDEX IF EXISTS public.de_equity_ohlcv_instrument_date_desc_idx;
"""


def upgrade() -> None:
    op.execute(_CREATE_INDEX)


def downgrade() -> None:
    op.execute(_DROP_INDEX)
