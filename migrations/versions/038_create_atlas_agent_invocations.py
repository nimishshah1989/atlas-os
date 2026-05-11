"""SP07: create atlas_agent_invocations for specialist-agent audit trail.

One row per CLI/API invoke() call. Captures the question, narrative,
tool-call trajectory, model id, token counts, and the data_as_of snapshot.
Audit-trail only — no enforcement reads.

Revision ID: 038
Revises: 037
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_agent_invocations (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_name      VARCHAR(64)  NOT NULL,
            question        TEXT         NOT NULL,
            narrative       TEXT         NOT NULL,
            tool_calls      JSONB        NOT NULL DEFAULT '[]'::jsonb,
            model           VARCHAR(64)  NOT NULL,
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            iterations      SMALLINT     NOT NULL,
            data_as_of      DATE,
            caller          VARCHAR(16)  NOT NULL,
            user_id         TEXT,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

            CONSTRAINT chk_agent_caller
                CHECK (caller IN ('cli', 'api', 'test'))
        )
    """)
    )

    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS ix_agent_invocations_agent_created
            ON atlas.atlas_agent_invocations (agent_name, created_at DESC)
    """)
    )

    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS ix_agent_invocations_created
            ON atlas.atlas_agent_invocations (created_at DESC)
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.ix_agent_invocations_created"))
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.ix_agent_invocations_agent_created"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_agent_invocations"))
