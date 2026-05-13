"""SP10 multi-index strip: add symbol column to atlas_nifty_intraday.

Changes:
- atlas_nifty_intraday: add symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50'
- Drop single-column primary key on bar_time
- Add composite primary key (symbol, bar_time)
- Add index idx_ani_symbol on (symbol)

This allows all five tracked NSE indices (NIFTY 50, NIFTY BANK, NIFTY MID100,
NIFTY SMLCAP, NIFTY IT) to be stored in a single table, keyed by symbol.
"""

revision = "061"
down_revision = "060"

from alembic import op


def upgrade() -> None:
    op.execute("SET search_path TO atlas")

    # Add symbol column with default so existing rows get 'NIFTY 50'
    op.execute("""
        ALTER TABLE atlas.atlas_nifty_intraday
        ADD COLUMN IF NOT EXISTS symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50'
    """)

    # Drop the old single-column primary key on bar_time
    op.execute("""
        ALTER TABLE atlas.atlas_nifty_intraday
        DROP CONSTRAINT IF EXISTS atlas_nifty_intraday_pkey
    """)

    # Add composite primary key (symbol, bar_time)
    op.execute("""
        ALTER TABLE atlas.atlas_nifty_intraday
        ADD CONSTRAINT atlas_nifty_intraday_pkey PRIMARY KEY (symbol, bar_time)
    """)

    # Index for per-symbol queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ani_symbol
        ON atlas.atlas_nifty_intraday (symbol)
    """)


def downgrade() -> None:
    op.execute("SET search_path TO atlas")

    # Remove non-NIFTY 50 rows (all data beyond the original single-index table)
    op.execute("""
        DELETE FROM atlas.atlas_nifty_intraday
        WHERE symbol != 'NIFTY 50'
    """)

    # Drop composite PK
    op.execute("""
        ALTER TABLE atlas.atlas_nifty_intraday
        DROP CONSTRAINT IF EXISTS atlas_nifty_intraday_pkey
    """)

    # Drop index
    op.execute("DROP INDEX IF EXISTS atlas.idx_ani_symbol")

    # Restore single-column PK on bar_time
    op.execute("""
        ALTER TABLE atlas.atlas_nifty_intraday
        ADD CONSTRAINT atlas_nifty_intraday_pkey PRIMARY KEY (bar_time)
    """)

    # Drop symbol column
    op.execute("""
        ALTER TABLE atlas.atlas_nifty_intraday
        DROP COLUMN IF EXISTS symbol
    """)
