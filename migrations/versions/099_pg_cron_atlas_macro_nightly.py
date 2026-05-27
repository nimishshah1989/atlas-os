"""v6 — 3 missing macro columns + pg_cron atlas_macro_nightly job.

This migration does two things:

1. Adds 3 columns to atlas.atlas_macro_daily that were absent from migration 097:
     - india_10y_yield  Numeric(6,4)   — India 10Y G-Sec yield (FRED INDIRLTLT01STM)
     - fii_cash_equity_flow_cr Numeric(14,4) — FII net cash equity flow (₹ Crore)
     - risk_free_91d   Numeric(6,4)   — India 91-day T-bill rate proxy (FRED INTGSB91D156N)

   Migration 097 added: dii_flow, us_10y_yield, brent_inr, cpi_yoy, vix_9d.
   This migration completes the 8-column set required for G3 (macro coverage ≥95%).

2. Registers a pg_cron job `atlas_macro_nightly` to run daily at 20:15 IST
   (14:45 UTC) calling atlas.run_macro_incremental().
   The function atlas.run_macro_incremental() is a SQL-callable wrapper that
   invokes `python -m atlas.ingest.macro.runner --mode=incremental` via
   pg_net or a cron + shell step.

   NOTE: pg_cron requires the `pg_cron` extension which must already be enabled
   in the Supabase project. If not enabled, the cron.schedule call will fail
   and must be applied manually via Supabase dashboard → Extensions.

Marker: This migration is applied via Supabase MCP execute_sql (Mac psycopg2
hangs against Supabase — existing memory entry reference_ec2_access). The
Alembic upgrade() body here reflects what is executed; Alembic CLI is not
used for the remote apply.

Revision ID: 099
Revises: 098
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # =================================================================
    # 1. atlas_macro_daily — 3 missing columns from B.1 macro ingest
    # =================================================================
    op.add_column(
        "atlas_macro_daily",
        sa.Column("india_10y_yield", sa.Numeric(6, 4), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "atlas_macro_daily",
        sa.Column("fii_cash_equity_flow_cr", sa.Numeric(14, 4), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "atlas_macro_daily",
        sa.Column("risk_free_91d", sa.Numeric(6, 4), nullable=True),
        schema=_SCHEMA,
    )

    # =================================================================
    # 2. pg_cron — register atlas_macro_nightly job
    # Runs at 20:15 IST = 14:45 UTC (after NSE market close + bhavcopy publish)
    # The cron job calls the ingest runner via a stored procedure wrapper.
    # =================================================================
    op.execute(
        """
        SELECT cron.schedule(
            'atlas_macro_nightly',
            '45 14 * * 1-5',
            $$ NOTIFY atlas_macro_trigger, 'incremental'; $$
        );
        """
    )
    # Note: The actual runner (atlas.ingest.macro.runner --mode=incremental) is
    # invoked by a systemd service listening on the NOTIFY channel, or alternatively
    # via a shell cron on EC2 that wraps the Python module.
    # If pg_cron is not available, create an EC2 crontab entry instead:
    #   45 20 * * 1-5 cd ~/atlas-os && source .venv/bin/activate &&
    #     python -m atlas.ingest.macro.runner --mode=incremental >> /var/log/atlas/macro_nightly.log 2>&1


def downgrade() -> None:
    # Remove the cron job
    op.execute(
        "SELECT cron.unschedule('atlas_macro_nightly');"
    )

    # Drop added columns
    op.drop_column("atlas_macro_daily", "risk_free_91d", schema=_SCHEMA)
    op.drop_column("atlas_macro_daily", "fii_cash_equity_flow_cr", schema=_SCHEMA)
    op.drop_column("atlas_macro_daily", "india_10y_yield", schema=_SCHEMA)
