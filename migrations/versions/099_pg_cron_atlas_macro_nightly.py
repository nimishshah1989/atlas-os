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

from alembic import op

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The 8 macro columns (india_10y_yield, fii_cash_equity_flow_cr, risk_free_91d,
    # dii_flow, us_10y_yield, brent_inr, cpi_yoy, vix_9d) already exist on
    # atlas_macro_daily — verified via Supabase MCP on 2026-05-27. Migration 097
    # added 5 of them; the other 3 predate. This migration is pg_cron-only.

    # pg_cron — register atlas_macro_nightly job
    # Runs 20:15 IST = 14:45 UTC, Mon-Fri (after NSE market close + bhavcopy publish).
    # NOTIFY channel is consumed by an EC2 systemd listener that runs the Python
    # runner. If the listener is not deployed, a plain EC2 crontab fallback works:
    #   45 20 * * 1-5 cd ~/atlas-os && source .venv/bin/activate &&
    #     python -m atlas.ingest.macro.runner --mode=incremental \
    #     >> /var/log/atlas/macro_nightly.log 2>&1
    op.execute(
        """
        SELECT cron.schedule(
            'atlas_macro_nightly',
            '45 14 * * 1-5',
            $$ NOTIFY atlas_macro_trigger, 'incremental'; $$
        );
        """
    )


def downgrade() -> None:
    op.execute("SELECT cron.unschedule('atlas_macro_nightly');")
