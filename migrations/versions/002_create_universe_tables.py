"""create universe tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-06 00:00:01.000000

Layer 2 universe tables per ``docs/02_DATABASE_SCHEMA.md`` Section 2.1-2.4.
Composite PK on ``(identifier, effective_from)`` allows slowly-changing-
dimension Type 2 history when the universe is refreshed quarterly. v0
populates one current row per instrument with ``effective_to IS NULL``.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_universe_stocks (
            instrument_id          UUID            NOT NULL,
            symbol                 VARCHAR(32)     NOT NULL,
            company_name           VARCHAR(256),
            tier                   VARCHAR(8)      NOT NULL,
            sector                 VARCHAR(64)     NOT NULL,
            industry               VARCHAR(128),
            in_nifty_50            BOOLEAN         NOT NULL DEFAULT FALSE,
            in_nifty_100           BOOLEAN         NOT NULL DEFAULT FALSE,
            in_nifty_500           BOOLEAN         NOT NULL DEFAULT FALSE,
            listing_date           DATE,
            effective_from         DATE            NOT NULL,
            effective_to           DATE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, effective_from),
            CONSTRAINT chk_universe_stocks_tier
                CHECK (tier IN ('Large', 'Mid', 'Small', 'Micro'))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_universe_etfs (
            ticker                 VARCHAR(32)     NOT NULL,
            isin                   VARCHAR(16),
            fund_house             VARCHAR(128),
            etf_name               VARCHAR(256),
            theme                  VARCHAR(16)     NOT NULL,
            linked_sector          VARCHAR(64),
            linked_index           VARCHAR(32),
            asset_class            VARCHAR(32),
            inception_date         DATE,
            effective_from         DATE            NOT NULL,
            effective_to           DATE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, effective_from),
            CONSTRAINT chk_universe_etfs_theme
                CHECK (theme IN ('Broad', 'Sectoral', 'Thematic'))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_universe_indices (
            index_code             VARCHAR(32)     NOT NULL,
            index_name             VARCHAR(128)    NOT NULL,
            role                   VARCHAR(16)     NOT NULL,
            linked_sector          VARCHAR(64),
            inception_date         DATE,
            effective_from         DATE            NOT NULL,
            effective_to           DATE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (index_code, effective_from),
            CONSTRAINT chk_universe_indices_role
                CHECK (role IN ('broad', 'sectoral', 'industry', 'factor', 'thematic'))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_universe_funds (
            mstar_id               VARCHAR(32)     NOT NULL,
            scheme_name            VARCHAR(256)    NOT NULL,
            amc                    VARCHAR(128),
            broad_category         VARCHAR(32)     NOT NULL,
            category_name          VARCHAR(64)     NOT NULL,
            plan_type              VARCHAR(16)     NOT NULL DEFAULT 'Regular',
            option_type            VARCHAR(16)     NOT NULL DEFAULT 'Growth',
            benchmark_code         VARCHAR(32),
            inception_date         DATE,
            effective_from         DATE            NOT NULL,
            effective_to           DATE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (mstar_id, effective_from)
        )
    """))


def downgrade() -> None:
    for tbl in (
        "atlas_universe_funds",
        "atlas_universe_indices",
        "atlas_universe_etfs",
        "atlas_universe_stocks",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS atlas.{tbl}"))
