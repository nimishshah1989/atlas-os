"""Create atlas_validator_runs and atlas_validator_findings tables.

These tables back the Phase A Data Integrity Validator agent.

- atlas_validator_runs: one row per validator execution (scope, status, timing)
- atlas_validator_findings: one row per detected data-integrity issue

Deduplication is enforced by a UNIQUE(finding_class, surface, identifier) on
atlas_validator_findings. Upsert semantics: re-detected findings update
last_seen rather than creating duplicates.

Revision ID: 032
Revises: 031
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- atlas_validator_runs ---
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_validator_runs (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at    TIMESTAMPTZ NOT NULL,
            completed_at  TIMESTAMPTZ,
            status        VARCHAR(16) NOT NULL
                          CONSTRAINT chk_validator_run_status
                          CHECK (status IN ('running', 'success', 'failed')),
            scope         VARCHAR(32),
            n_findings    INT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # --- atlas_validator_findings ---
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_validator_findings (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id          UUID        NOT NULL
                            REFERENCES atlas.atlas_validator_runs(id),
            finding_class   VARCHAR(32) NOT NULL
                            CONSTRAINT chk_finding_class
                            CHECK (finding_class IN (
                                'data_gap',
                                'inconsistency',
                                'calc_error',
                                'accuracy_error',
                                'insensible_value',
                                'incomplete_data'
                            )),
            severity        VARCHAR(8)  NOT NULL
                            CONSTRAINT chk_finding_severity
                            CHECK (severity IN ('P0', 'P1', 'P2', 'P3')),
            route           TEXT,
            surface         TEXT        NOT NULL,
            identifier      TEXT        NOT NULL,
            expected_value  TEXT,
            actual_value    TEXT,
            delta_abs       NUMERIC,
            delta_pct       NUMERIC,
            evidence        JSONB,
            remediation     TEXT,
            first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at     TIMESTAMPTZ,
            resolved_by     TEXT,
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_finding_identity
                UNIQUE (finding_class, surface, identifier)
        )
    """))

    # Index for fast lookup by run
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_validator_findings_run_id
            ON atlas.atlas_validator_findings (run_id)
    """))

    # Index for severity filtering (dashboard queries)
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_validator_findings_severity
            ON atlas.atlas_validator_findings (severity)
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DROP TABLE IF EXISTS atlas.atlas_validator_findings
    """))
    op.execute(sa.text("""
        DROP TABLE IF EXISTS atlas.atlas_validator_runs
    """))
