"""v6 — consolidate pg_cron MV refresh schedule.

Drops per-MV pg_cron jobs (created during chunks 100-108) and replaces them
with ONE ordered chain `mv_refresh_v6_all` that fires at 21:45 UTC = 03:15 IST,
AFTER run_atlas_intelligence_nightly.sh finishes (~02:00 IST), so MVs always
refresh on fresh upstream data.

Why: jobs 14-22 (created earlier this week) fired at 14:30-15:40 UTC, which is
BEFORE the intel chain runs at 20:00 UTC. Result: MVs refreshed on STALE
upstream data.

Untouched: jobs 1-5 (SP02 MVs already inside intel script), jobs 7-8 (intraday
by design), job 11 (top conviction already inside intel script).

Revision ID: 111
Revises: 110
Create Date: 2026-05-28 IST
"""

from __future__ import annotations

from alembic import op

revision = "111"
down_revision = "110"
branch_labels = None
depends_on = None

_DROP_OLD_JOBS = """
DO $$
BEGIN
  PERFORM cron.unschedule(j.jobid)
  FROM cron.job j
  WHERE j.jobname IN (
    'mv_india_pulse_nightly',
    'mv_markets_rs_detail_charts_nightly',
    'mv_sector_cards_nightly',
    'mv_sector_breadth_nightly',
    'mv_sector_rrg_nightly',
    'mv_sector_deepdive_nightly',
    'mv_stock_landscape_nightly',
    'mv_etf_list_v6_nightly',
    'mv_etf_deepdive_nightly'
  );
END $$;
"""

_CREATE_CONSOLIDATED = """
SELECT cron.schedule(
  'mv_refresh_v6_all',
  '45 21 * * *',
  $$
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_india_pulse;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_markets_rs_detail_charts;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_cards;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_breadth;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rrg;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_deepdive;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_landscape;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_etf_list_v6;
  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_etf_deepdive;
  $$
);
"""


def upgrade() -> None:
    op.execute(_DROP_OLD_JOBS)
    op.execute(_CREATE_CONSOLIDATED)


def downgrade() -> None:
    op.execute("SELECT cron.unschedule('mv_refresh_v6_all');")
