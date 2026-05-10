"""add state_since_date to atlas_stock_states_daily

Revision ID: 026
Revises: 025
Create Date: 2026-05-10

Adds state_since_date DATE to atlas_stock_states_daily.
The nightly pipeline writes this on each state classification run.
getAllStocks() reads CURRENT_DATE - s.state_since_date to compute days_in_state.
NULL means pre-backfill; display as '—' in the frontend.
"""
from alembic import op

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.atlas_stock_states_daily
        ADD COLUMN IF NOT EXISTS state_since_date DATE;
    """)

    # Backfill: for each instrument find the start date of the current
    # contiguous RS state run. One-time cost at migration time on ~500K rows.
    op.execute("""
        WITH ranked AS (
            SELECT
                instrument_id,
                date,
                rs_state,
                LAG(rs_state) OVER (
                    PARTITION BY instrument_id ORDER BY date
                ) AS prev_rs_state
            FROM atlas.atlas_stock_states_daily
        ),
        state_starts AS (
            SELECT instrument_id, date AS start_date, rs_state
            FROM ranked
            WHERE prev_rs_state IS DISTINCT FROM rs_state
        ),
        latest_start AS (
            SELECT DISTINCT ON (s.instrument_id)
                s.instrument_id,
                ss.start_date
            FROM atlas.atlas_stock_states_daily s
            JOIN state_starts ss
                ON ss.instrument_id = s.instrument_id
                AND ss.rs_state = s.rs_state
                AND ss.start_date <= s.date
            ORDER BY s.instrument_id, ss.start_date DESC
        )
        UPDATE atlas.atlas_stock_states_daily dst
        SET state_since_date = ls.start_date
        FROM latest_start ls
        WHERE dst.instrument_id = ls.instrument_id
          AND dst.state_since_date IS NULL;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_states_since_date
        ON atlas.atlas_stock_states_daily (instrument_id, state_since_date);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS atlas.idx_stock_states_since_date;
    """)
    op.execute("""
        ALTER TABLE atlas.atlas_stock_states_daily
        DROP COLUMN IF EXISTS state_since_date;
    """)
