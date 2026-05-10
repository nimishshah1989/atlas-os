"""add state_since_date to atlas_etf_states_daily

Revision ID: 028
Revises: 027
Create Date: 2026-05-10

Mirrors migration 026 for stocks. Enables days_in_state in getAllETFs().
NULL means pre-backfill; frontend displays as '—'.
"""
from alembic import op

revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.atlas_etf_states_daily
        ADD COLUMN IF NOT EXISTS state_since_date DATE;
    """)

    op.execute("""
        WITH ranked AS (
            SELECT
                ticker,
                date,
                rs_state,
                LAG(rs_state) OVER (
                    PARTITION BY ticker ORDER BY date
                ) AS prev_rs_state
            FROM atlas.atlas_etf_states_daily
        ),
        state_starts AS (
            SELECT ticker, date AS start_date, rs_state
            FROM ranked
            WHERE prev_rs_state IS DISTINCT FROM rs_state
        ),
        latest_start AS (
            SELECT DISTINCT ON (s.ticker)
                s.ticker,
                ss.start_date
            FROM atlas.atlas_etf_states_daily s
            JOIN state_starts ss
                ON ss.ticker = s.ticker
                AND ss.rs_state = s.rs_state
                AND ss.start_date <= s.date
            ORDER BY s.ticker, ss.start_date DESC
        )
        UPDATE atlas.atlas_etf_states_daily dst
        SET state_since_date = ls.start_date
        FROM latest_start ls
        WHERE dst.ticker = ls.ticker
          AND dst.state_since_date IS NULL;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_etf_states_since_date
        ON atlas.atlas_etf_states_daily (ticker, state_since_date);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS atlas.idx_etf_states_since_date;")
    op.execute("""
        ALTER TABLE atlas.atlas_etf_states_daily
        DROP COLUMN IF EXISTS state_since_date;
    """)
