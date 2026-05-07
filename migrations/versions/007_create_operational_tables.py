"""create operational tables

Revision ID: 007
Revises: 006
Create Date: 2026-05-06 00:00:06.000000

Operational tables per ``docs/02_DATABASE_SCHEMA.md`` Section 6:
- ``atlas_run_log`` — one row per nightly run
- ``atlas_validation_results`` — per-tier validation check results
- 4 quarantine tables (stocks, ETFs, indices, sectors, funds)
- ``atlas_benchmark_returns_cache`` — working table, materialized per run
- ``atlas_thresholds`` — 35 tunable thresholds (seeded by M1 universe lock code)
- ``atlas_threshold_history`` — append-only audit of threshold changes
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


_QUARANTINE_TABLES = (
    "atlas_stock_metrics_quarantine",
    "atlas_etf_metrics_quarantine",
    "atlas_index_metrics_quarantine",
    "atlas_sector_metrics_quarantine",
    "atlas_fund_metrics_quarantine",
)


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_run_log (
            compute_run_id         UUID            NOT NULL PRIMARY KEY,
            business_date          DATE            NOT NULL,
            started_at             TIMESTAMPTZ     NOT NULL,
            completed_at           TIMESTAMPTZ,
            status                 VARCHAR(16)     NOT NULL,

            -- Stage timings (seconds)
            stage1_pre_check_sec   INTEGER,
            stage2_reference_sec   INTEGER,
            stage3_stock_etf_sec   INTEGER,
            stage4_index_sec       INTEGER,
            stage5_sector_sec      INTEGER,
            stage6_regime_sec      INTEGER,
            stage7_funds_sec       INTEGER,
            stage8_decisions_sec   INTEGER,
            stage9_validation_sec  INTEGER,

            rows_written_total     INTEGER,
            rows_quarantined_total INTEGER,

            tier1_pass             BOOLEAN,
            tier2_pass             BOOLEAN,
            tier3_pass             BOOLEAN,
            tier4_pass             BOOLEAN,

            failure_stage          VARCHAR(32),
            failure_message        TEXT,

            -- Indicates a reclassify run (threshold change applied) vs a normal nightly run
            reclassify             BOOLEAN         NOT NULL DEFAULT FALSE,

            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

            CONSTRAINT chk_run_log_status CHECK (status IN (
                'RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL'
            ))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_validation_results (
            id                     SERIAL          PRIMARY KEY,
            compute_run_id         UUID            NOT NULL
                REFERENCES atlas.atlas_run_log(compute_run_id),
            business_date          DATE            NOT NULL,
            tier                   SMALLINT        NOT NULL,
            check_name             VARCHAR(128)    NOT NULL,
            instrument_id          UUID,
            expected_value         TEXT,
            actual_value           TEXT,
            passed                 BOOLEAN         NOT NULL,
            deviation_pct          NUMERIC(10,4),
            notes                  TEXT,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

            CONSTRAINT chk_validation_tier CHECK (tier BETWEEN 1 AND 5)
        )
    """))

    # Quarantine tables — same shape, one per scope
    for tbl in _QUARANTINE_TABLES:
        op.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS atlas.{tbl} (
                id                     SERIAL          PRIMARY KEY,
                instrument_id          UUID,
                ticker                 VARCHAR(32),
                mstar_id               VARCHAR(32),
                index_code             VARCHAR(32),
                sector_name            VARCHAR(64),
                date                   DATE,
                error_type             VARCHAR(64)     NOT NULL,
                error_message          TEXT,
                raw_input              JSONB,
                compute_run_id         UUID,
                created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
            )
        """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_benchmark_returns_cache (
            benchmark_code         VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,
            close                  NUMERIC(18,4)   NOT NULL,
            ret_1d                 NUMERIC(10,4),
            ret_1w                 NUMERIC(10,4),
            ret_1m                 NUMERIC(10,4),
            ret_3m                 NUMERIC(10,4),
            ret_6m                 NUMERIC(10,4),
            ret_12m                NUMERIC(10,4),
            ret_12m_1m             NUMERIC(10,4),
            ema_10                 NUMERIC(18,4),
            ema_20                 NUMERIC(18,4),
            realized_vol_63        NUMERIC(10,4),
            PRIMARY KEY (benchmark_code, date)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_thresholds (
            threshold_key          VARCHAR(64)     NOT NULL PRIMARY KEY,
            threshold_value        NUMERIC(18,6)   NOT NULL,
            category               VARCHAR(32)     NOT NULL,
            description            TEXT            NOT NULL,
            methodology_section    VARCHAR(16),
            units                  VARCHAR(16),
            min_allowed            NUMERIC(18,6)   NOT NULL,
            max_allowed            NUMERIC(18,6)   NOT NULL,
            default_value          NUMERIC(18,6)   NOT NULL,
            last_modified_by       VARCHAR(64)     NOT NULL DEFAULT 'system',
            last_modified_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            is_active              BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

            CONSTRAINT chk_threshold_in_range
                CHECK (threshold_value >= min_allowed AND threshold_value <= max_allowed),
            CONSTRAINT chk_threshold_default_in_range
                CHECK (default_value >= min_allowed AND default_value <= max_allowed)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_threshold_history (
            id                     SERIAL          PRIMARY KEY,
            threshold_key          VARCHAR(64)     NOT NULL
                REFERENCES atlas.atlas_thresholds(threshold_key),
            old_value              NUMERIC(18,6),
            new_value              NUMERIC(18,6)   NOT NULL,
            changed_by             VARCHAR(64)     NOT NULL,
            changed_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            change_reason          TEXT,
            triggered_reclassify   BOOLEAN         NOT NULL DEFAULT FALSE,
            reclassify_run_id      UUID,
            user_ip                INET,
            user_agent             TEXT
        )
    """))


def downgrade() -> None:
    drop_order = (
        "atlas_threshold_history",
        "atlas_thresholds",
        "atlas_benchmark_returns_cache",
        *_QUARANTINE_TABLES,
        "atlas_validation_results",
        "atlas_run_log",
    )
    for tbl in drop_order:
        op.execute(sa.text(f"DROP TABLE IF EXISTS atlas.{tbl}"))
