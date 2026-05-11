"""SP05: create atlas_daily_briefs for Claude-authored daily market narratives.

One row per as_of_date (UNIQUE). UPSERT on (as_of_date) — re-running the
CLI overwrites the prior brief. context_snapshot holds the full input audit
trail required for SEBI compliance review.

Revision ID: 037
Revises: 036
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_daily_briefs (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date            DATE        NOT NULL UNIQUE,
            regime_state          VARCHAR(32) NOT NULL,
            regime_delta          VARCHAR(16) NOT NULL,
            narrative             TEXT        NOT NULL,
            key_themes            JSONB       NOT NULL,
            regime_summary        VARCHAR(16) NOT NULL,
            top_sector_mentions   JSONB       NOT NULL,
            context_snapshot      JSONB       NOT NULL,
            model                 VARCHAR(64) NOT NULL,
            prompt_version        VARCHAR(8)  NOT NULL,
            input_tokens          INTEGER,
            output_tokens         INTEGER,
            generated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT chk_brief_regime_delta CHECK (
                regime_delta IN ('unchanged','upgraded','downgraded')
            ),
            CONSTRAINT chk_brief_summary CHECK (
                regime_summary IN ('bullish','neutral','cautious','defensive')
            )
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_daily_briefs_as_of
        ON atlas.atlas_daily_briefs (as_of_date DESC)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_daily_briefs_as_of"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_daily_briefs"))
