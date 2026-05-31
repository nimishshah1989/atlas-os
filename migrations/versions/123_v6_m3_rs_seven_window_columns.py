"""v6 M3 — RS 7-window standardization columns.

Adds the persisted columns required by the M3 RS baseline work (ADR-0001 /
ADR-0002):

* ``atlas_stock_metrics_daily``: new tier-RS windows ``rs_1d_tier`` /
  ``rs_24m_tier``, the 24-month raw return ``ret_24m`` (denominator source for
  sector 24m RS), and the four new direct stock-vs-gold windows
  ``rs_{1d,6m,12m,24m}_tier_gold`` (1w/1m/3m already exist from migration 004).
* ``atlas_index_metrics_daily``: ``ret_24m`` — the Nifty500 24m denominator for
  the sector bottom-up 24m RS surface.
* ``atlas_sector_metrics_daily``: the six new ``bottomup_rs_{1d,1w,1m,6m,12m,24m}
  _nifty500`` windows (3m already exists from migration 004).

All columns are ``NUMERIC(10,4)`` nullable, matching the existing RS/return
columns. Values are backfilled by the M3 EC2 backfill, not by this migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "123"
down_revision = "122"

_NUM = sa.Numeric(precision=10, scale=4)

# (table, column) pairs added by this migration.
_STOCK_COLS = (
    "rs_1d_tier",
    "rs_24m_tier",
    "ret_24m",
    "rs_1d_tier_gold",
    "rs_6m_tier_gold",
    "rs_12m_tier_gold",
    "rs_24m_tier_gold",
)
_INDEX_COLS = ("ret_24m",)
_SECTOR_COLS = (
    "bottomup_rs_1d_nifty500",
    "bottomup_rs_1w_nifty500",
    "bottomup_rs_1m_nifty500",
    "bottomup_rs_6m_nifty500",
    "bottomup_rs_12m_nifty500",
    "bottomup_rs_24m_nifty500",
)

_TABLE_COLS = (
    ("atlas_stock_metrics_daily", _STOCK_COLS),
    ("atlas_index_metrics_daily", _INDEX_COLS),
    ("atlas_sector_metrics_daily", _SECTOR_COLS),
)


def upgrade() -> None:
    for table, cols in _TABLE_COLS:
        for col in cols:
            op.add_column(
                table,
                sa.Column(col, _NUM, nullable=True),
                schema="atlas",
            )


def downgrade() -> None:
    for table, cols in reversed(_TABLE_COLS):
        for col in reversed(cols):
            op.drop_column(table, col, schema="atlas")
