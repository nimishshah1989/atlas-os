"""Mock migration fixture: creates atlas_universe_stocks and atlas_stock_metrics_daily.

Used by test_v6_data_availability_audit.py to simulate a migrations/versions/ directory.
"""

import sqlalchemy as sa
from alembic import op

revision = "mock001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "atlas_universe_stocks",
        sa.Column("instrument_id", sa.UUID, primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
    )
    op.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS atlas.atlas_stock_metrics_daily "
            "(instrument_id uuid, date date, ret_1m numeric)"
        )
    )
    op.create_table(
        "atlas_fund_scorecard",
        sa.Column("scheme_code", sa.String(20), primary_key=True),
        sa.Column("top_holdings", sa.JSON, nullable=True),
    )
