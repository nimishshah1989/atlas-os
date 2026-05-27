"""v6 — atlas_data_health visibility table.

# allow-large: includes seed COMMENT statements

One row per (check_date, schema_name, table_name) describing freshness,
row count, null rate on critical columns, and status (GREEN/YELLOW/RED).

Populated daily at 03:30 IST by scripts/atlas_health_check.py — the LAST
step in the nightly chain after all ingests + compute + MV refreshes.

Frontend (and ops) reads this for at-a-glance backend status. No Slack /
email alerts per user direction (2026-05-27): RED rows ARE the alert.

Revision ID: 109
Revises: 108
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "109"
down_revision = "108"
branch_labels = None
depends_on = None

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS atlas.atlas_data_health (
  check_date            date          NOT NULL,
  schema_name           text          NOT NULL,
  table_name            text          NOT NULL,
  category              text          NOT NULL,         -- 'raw' | 'calculated' | 'mv'
  source                text,                            -- 'NSE bhavcopy' | 'yfinance' | 'AMFI' | 'compute' | 'mv'
  last_data_date        date,
  expected_data_date    date,
  freshness_days_lag    integer,
  row_count             bigint,
  null_rate_critical    numeric(6, 4),
  size_bytes            bigint,
  status                text          NOT NULL,         -- 'GREEN' | 'YELLOW' | 'RED'
  notes                 text,
  checked_at            timestamptz   NOT NULL DEFAULT now(),
  PRIMARY KEY (check_date, schema_name, table_name)
);

CREATE INDEX IF NOT EXISTS ix_atlas_data_health_status_date
  ON atlas.atlas_data_health (check_date DESC, status);

CREATE INDEX IF NOT EXISTS ix_atlas_data_health_table
  ON atlas.atlas_data_health (schema_name, table_name, check_date DESC);

COMMENT ON TABLE atlas.atlas_data_health IS
  'Daily freshness + health snapshot per critical v6 backend table. '
  'Written at 03:30 IST by scripts/atlas_health_check.py. '
  'RED rows are the failure surface (no Slack alerts per user direction).';

COMMENT ON COLUMN atlas.atlas_data_health.status IS
  'GREEN: last_date >= expected AND null_rate < threshold AND row_count > min. '
  'YELLOW: 1d lag or slightly elevated null rate (frontend renders with caveat). '
  'RED: >=2d lag OR row_count = 0 OR null_rate above critical threshold.';

COMMENT ON COLUMN atlas.atlas_data_health.category IS
  'raw: ingested from external source (bhavcopy/Stooq/yfinance/AMFI). '
  'calculated: computed by atlas pipeline (M2-M5, conviction, etc.). '
  'mv: materialized view served to frontend.';
"""

_DROP_TABLE = """
DROP INDEX IF EXISTS atlas.ix_atlas_data_health_table;
DROP INDEX IF EXISTS atlas.ix_atlas_data_health_status_date;
DROP TABLE IF EXISTS atlas.atlas_data_health;
"""


def upgrade() -> None:
    op.execute(_CREATE_TABLE)


def downgrade() -> None:
    op.execute(_DROP_TABLE)
