"""Change access_token_enc from TEXT to BYTEA.

pgp_sym_encrypt() returns bytea. Migration 042 declared the column as TEXT,
which required a ::bytea cast every time pgp_sym_decrypt() was called. Storing
ciphertext in a BYTEA column is the correct approach — no cast needed, and
psycopg2 returns the value as bytes rather than a string, which is accurate.

The USING clause converts existing stored values: the hex-escaped text
representation that Postgres stores when you write bytea into a text column
is the same bytes, so the cast round-trips cleanly.

Revision ID: 045
Revises: 044
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        ALTER TABLE atlas.atlas_kite_session
            ALTER COLUMN access_token_enc TYPE BYTEA
            USING access_token_enc::bytea
        """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
        ALTER TABLE atlas.atlas_kite_session
            ALTER COLUMN access_token_enc TYPE TEXT
            USING encode(access_token_enc, 'escape')
        """)
    )
