"""create health observability tables

Revision ID: 021
Revises: 020
Create Date: 2026-05-09 00:00:00.000000

M12 — Backend Data Health Observability.
Renumbered from 013 to 021 because parallel M7 work landed migrations
013-020 first.

Three append-only operational tables:
  atlas_pipeline_runs       — every script invocation
  atlas_validator_results   — every validator run
  atlas_health_daily        — long-format metric snapshots with anomaly flags
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- atlas_pipeline_runs -----------------------------------------------
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_pipeline_runs (
            run_id          UUID         PRIMARY KEY,
            script_name     VARCHAR(64)  NOT NULL,
            milestone       VARCHAR(8),
            phase           VARCHAR(32),
            started_at      TIMESTAMPTZ  NOT NULL,
            ended_at        TIMESTAMPTZ,
            status          VARCHAR(16)  NOT NULL,
            rows_written    BIGINT,
            error_message   TEXT,
            host            VARCHAR(64),
            git_sha         VARCHAR(40),

            CONSTRAINT chk_pipeline_runs_status CHECK (
                status IN ('running', 'success', 'failed')
            )
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_pipeline_runs_script_started
            ON atlas.atlas_pipeline_runs (script_name, started_at DESC)
    """))

    # ---- atlas_validator_results -------------------------------------------
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_validator_results (
            run_id            UUID         PRIMARY KEY,
            validator         VARCHAR(16)  NOT NULL,
            ran_at            TIMESTAMPTZ  NOT NULL,
            total_checks      INTEGER      NOT NULL,
            failures          INTEGER      NOT NULL,
            status            VARCHAR(8)   NOT NULL,
            failure_summary   JSONB,
            host              VARCHAR(64),
            git_sha           VARCHAR(40),

            CONSTRAINT chk_validator_results_status CHECK (
                status IN ('PASS', 'FAIL')
            ),
            CONSTRAINT chk_validator_results_validator CHECK (
                validator IN ('M2', 'M3', 'M4', 'M5')
            )
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_validator_results_validator_ran
            ON atlas.atlas_validator_results (validator, ran_at DESC)
    """))

    # ---- atlas_health_daily ------------------------------------------------
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_health_daily (
            data_date         DATE         NOT NULL,
            table_name        VARCHAR(64)  NOT NULL,
            metric_name       VARCHAR(64)  NOT NULL,
            value_today       NUMERIC,
            value_prior_day   NUMERIC,
            rolling_14d_avg   NUMERIC,
            rolling_14d_std   NUMERIC,
            pct_change_dod    NUMERIC,
            z_score           NUMERIC,
            is_anomaly        BOOLEAN      NOT NULL DEFAULT FALSE,
            severity          VARCHAR(8),
            notes             TEXT,
            computed_at       TIMESTAMPTZ  NOT NULL,

            PRIMARY KEY (data_date, table_name, metric_name),
            CONSTRAINT chk_health_severity CHECK (
                severity IS NULL OR severity IN ('info', 'warn', 'critical')
            )
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_health_daily_anomaly
            ON atlas.atlas_health_daily (data_date DESC, is_anomaly)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_health_daily"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_validator_results"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_pipeline_runs"))
