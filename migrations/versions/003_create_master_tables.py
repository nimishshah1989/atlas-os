"""create master tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-06 00:00:02.000000

Layer 2 master/mapping tables per ``docs/02_DATABASE_SCHEMA.md`` Section
2.5-2.7.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_sector_master (
            sector_name            VARCHAR(64)     NOT NULL PRIMARY KEY,
            primary_nse_index      VARCHAR(32),
            secondary_nse_indices  TEXT[],
            fallback_benchmark     VARCHAR(32)     NOT NULL DEFAULT 'NIFTY 500',
            notes                  TEXT,
            is_active              BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_benchmark_master (
            benchmark_code         VARCHAR(32)     NOT NULL PRIMARY KEY,
            benchmark_name         VARCHAR(128)    NOT NULL,
            benchmark_type         VARCHAR(32)     NOT NULL,
            source_table           VARCHAR(64)     NOT NULL,
            source_identifier      VARCHAR(64)     NOT NULL,
            description            TEXT,
            is_active              BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_fund_category_benchmark_map (
            category_name          VARCHAR(64)     NOT NULL PRIMARY KEY,
            benchmark_code         VARCHAR(32)     NOT NULL
                REFERENCES atlas.atlas_benchmark_master(benchmark_code),
            notes                  TEXT,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """))


def downgrade() -> None:
    for tbl in (
        "atlas_fund_category_benchmark_map",
        "atlas_benchmark_master",
        "atlas_sector_master",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS atlas.{tbl}"))
