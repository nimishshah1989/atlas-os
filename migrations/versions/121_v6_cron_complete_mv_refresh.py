"""v6 — complete the pg_cron MV refresh job + fix mv_stock_list_v6 date anchor.

Resolves two CRITICAL findings from docs/v6/2026-05-30-overnight-audit.md.

1. `mv_refresh_cron_incomplete` / `stale-mv-cascade` (CRIT)
   --------------------------------------------------------
   Migration 111 registered `mv_refresh_v6_all` ('45 21 * * *') with only the
   9 MVs that existed before migration 098. The 7 MVs created in migration 098
   (mv_market_regime_landing, mv_markets_rs_grid, mv_stock_list_v6,
   mv_stock_deepdive, mv_fund_list_v6, mv_fund_deepdive, mv_calls_performance)
   were never added to any refresh job, so the landing page, /stocks,
   /markets-rs, fund + calls pages froze while their source tables stayed
   fresh. This migration unschedules the job and re-registers it with ALL 16
   v6 MVs. Every one has a unique index (verified), so CONCURRENTLY is safe.

2. `mv_stock_list_v6` date-anchor bug (Chunk A, audit §8)
   -----------------------------------------------------
   The MV's `latest` CTE read `max(snapshot_date)` from the DEAD legacy table
   `atlas_conviction_daily` (frozen 2026-05-22). That `latest.d` drove BOTH the
   `as_of_date` label AND the `atlas_scorecard_daily` join, so /stocks showed
   fresh decisions stamped with a 7-day-old date and stale family_* features.
   This migration DROPs + reCREATEs the MV with `latest` repointed to the LIVE
   table `atlas_stock_conviction_daily` (column `date`). The MV has no
   dependents (verified via pg_depend); its 3 indexes are recreated.

NOT addressed here (intentionally):
 * `mv_stock_landscape` freezing was a DATA gap, not a definition bug — its
   anchor `MAX(date) WHERE rs_3m_nifty500 IS NOT NULL` is correct; the
   rs_*_nifty500 columns were simply NULL for the latest day because no daily
   writer populates them. Fixed operationally via
   scripts/ops/backfill_stock_rs_nifty500.py. Permanent wiring is Chunk C.
 * `atlas_fund_scorecard` has no generator (Chunk C).

Apply path: alembic on EC2 (psycopg2 works there). This is the project's
sanctioned write path going forward — NOT MCP out-of-band, which is what
produced the 098/120 marker-migration mess this report flags.

Revision ID: 121
Revises: 120
Create Date: 2026-05-30 IST
"""

from __future__ import annotations

from alembic import op

revision = "121"
down_revision = "120"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# 1. Consolidated cron job — all 16 v6 MVs (sources before dependents).
# ---------------------------------------------------------------------------
_ALL_16_MVS = (
    "mv_market_regime_landing",
    "mv_india_pulse",
    "mv_markets_rs_grid",
    "mv_markets_rs_detail_charts",
    "mv_sector_cards",
    "mv_sector_breadth",
    "mv_sector_rrg",
    "mv_sector_deepdive",
    "mv_stock_landscape",
    "mv_stock_list_v6",
    "mv_stock_deepdive",
    "mv_fund_list_v6",
    "mv_fund_deepdive",
    "mv_etf_list_v6",
    "mv_etf_deepdive",
    "mv_calls_performance",
)

# migration 111's original 9-MV body, for downgrade.
_ORIGINAL_9_MVS = (
    "mv_india_pulse",
    "mv_markets_rs_detail_charts",
    "mv_sector_cards",
    "mv_sector_breadth",
    "mv_sector_rrg",
    "mv_sector_deepdive",
    "mv_stock_landscape",
    "mv_etf_list_v6",
    "mv_etf_deepdive",
)

_UNSCHEDULE = "SELECT cron.unschedule('mv_refresh_v6_all');"


def _schedule_sql(mvs: tuple[str, ...]) -> str:
    body = "\n".join(
        f"  REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.{mv};" for mv in mvs
    )
    return (
        "SELECT cron.schedule(\n"
        "  'mv_refresh_v6_all',\n"
        "  '45 21 * * *',\n"
        "  $$\n"
        f"{body}\n"
        "  $$\n"
        ");"
    )


# ---------------------------------------------------------------------------
# 2. mv_stock_list_v6 — body reproduced verbatim from pg_get_viewdef, with the
#    `latest` CTE source as the ONLY variable. Templating both upgrade and
#    downgrade off one body guarantees they cannot drift apart.
# ---------------------------------------------------------------------------
_LATEST_CTE_LIVE = (
    "         SELECT max(atlas_stock_conviction_daily.date) AS d\n"
    "           FROM atlas.atlas_stock_conviction_daily"
)
_LATEST_CTE_DEAD = (
    "         SELECT max(atlas_conviction_daily.snapshot_date) AS d\n"
    "           FROM atlas.atlas_conviction_daily"
)


def _mv_stock_list_create(latest_cte: str) -> str:
    return f"""
CREATE MATERIALIZED VIEW atlas.mv_stock_list_v6 AS
 WITH latest AS (
{latest_cte}
        ), tape AS (
         SELECT sc.instrument_id,
            max(
                CASE
                    WHEN cd.tenure::text = '1m'::text AND sc.exit_date IS NULL THEN cd.action::text
                    ELSE NULL::text
                END) AS tape_1m,
            max(
                CASE
                    WHEN cd.tenure::text = '3m'::text AND sc.exit_date IS NULL THEN cd.action::text
                    ELSE NULL::text
                END) AS tape_3m,
            max(
                CASE
                    WHEN cd.tenure::text = '6m'::text AND sc.exit_date IS NULL THEN cd.action::text
                    ELSE NULL::text
                END) AS tape_6m,
            max(
                CASE
                    WHEN cd.tenure::text = '12m'::text AND sc.exit_date IS NULL THEN cd.action::text
                    ELSE NULL::text
                END) AS tape_12m
           FROM atlas.atlas_signal_calls sc
             JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = sc.cell_id
          GROUP BY sc.instrument_id
        ), xcell AS (
         SELECT sc.instrument_id,
            count(DISTINCT ROW(sc.cap_tier_at_trigger, sc.tenure, sc.action)) AS cross_cell_depth
           FROM atlas.atlas_signal_calls sc
          WHERE sc.exit_date IS NULL
          GROUP BY sc.instrument_id
        ), best_call AS (
         SELECT DISTINCT ON (sc.instrument_id) sc.instrument_id,
            sc.cell_id,
            sc.confidence_unconditional,
            sc.predicted_excess,
            sc.action,
            cd.display_name AS best_cell_name
           FROM atlas.atlas_signal_calls sc
             JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = sc.cell_id
          WHERE sc.exit_date IS NULL
          ORDER BY sc.instrument_id, sc.confidence_unconditional DESC
        )
 SELECT u.instrument_id,
    u.symbol,
    u.company_name,
    u.sector,
    u.tier,
    u.in_nifty_50,
    u.in_nifty_100,
    u.in_nifty_500,
    round((stc.conviction_score - 0.5) * 20::numeric, 2) AS composite_score,
        CASE stc.confidence_label
            WHEN 'industry_grade'::text THEN 'HIGH'::text
            WHEN 'baseline'::text THEN 'MED'::text
            WHEN 'descriptive_only'::text THEN 'LOW'::text
            ELSE 'LOW'::text
        END AS confidence_band,
    stc.backing_ic,
        CASE
            WHEN bc.action::text = 'POSITIVE'::text THEN 'BUY'::text
            WHEN bc.action::text = 'NEGATIVE'::text THEN 'AVOID'::text
            ELSE 'WATCH'::text
        END AS action,
    bc.best_cell_name,
    bc.predicted_excess,
    COALESCE(xc.cross_cell_depth, 0::bigint) AS cross_cell_depth,
    COALESCE(tp.tape_1m, 'dormant'::text) AS tape_1m,
    COALESCE(tp.tape_3m, 'dormant'::text) AS tape_3m,
    COALESCE(tp.tape_6m, 'dormant'::text) AS tape_6m,
    COALESCE(tp.tape_12m, 'dormant'::text) AS tape_12m,
    sm.ret_1m,
    sm.ret_3m,
    sm.ret_6m,
    sm.ret_12m,
    sm.rs_1m_nifty500,
    sm.rs_3m_nifty500,
    sm.rs_pctile_3m,
    sm.realized_vol_63,
    sm.max_drawdown_252,
    sd.family_trend::text AS family_trend,
    sd.family_volatility::text AS family_volatility,
    sd.family_volume::text AS family_volume,
    sd.family_path::text AS family_path,
    sd.family_sector::text AS family_sector,
    ( SELECT latest.d
           FROM latest) AS as_of_date,
    now() AS refreshed_at
   FROM atlas.atlas_universe_stocks u
     LEFT JOIN atlas.atlas_stock_conviction_daily stc ON stc.instrument_id = u.instrument_id AND stc.date = (( SELECT max(atlas_stock_conviction_daily.date) AS max
           FROM atlas.atlas_stock_conviction_daily
          WHERE atlas_stock_conviction_daily.instrument_id = u.instrument_id))
     LEFT JOIN atlas.atlas_scorecard_daily sd ON sd.instrument_id = u.instrument_id AND sd.date = (( SELECT latest.d
           FROM latest))
     LEFT JOIN atlas.atlas_stock_metrics_daily sm ON sm.instrument_id = u.instrument_id AND sm.date = (( SELECT max(atlas_stock_metrics_daily.date) AS max
           FROM atlas.atlas_stock_metrics_daily
          WHERE atlas_stock_metrics_daily.instrument_id = u.instrument_id))
     LEFT JOIN tape tp ON tp.instrument_id = u.instrument_id
     LEFT JOIN xcell xc ON xc.instrument_id = u.instrument_id
     LEFT JOIN best_call bc ON bc.instrument_id = u.instrument_id
  WHERE u.effective_to IS NULL;
"""


_MV_INDEXES = (
    "CREATE UNIQUE INDEX ix_mv_stock_list_v6_iid ON atlas.mv_stock_list_v6 USING btree (instrument_id);",
    "CREATE INDEX ix_mv_stock_list_v6_action ON atlas.mv_stock_list_v6 USING btree (action);",
    "CREATE INDEX ix_mv_stock_list_v6_tier ON atlas.mv_stock_list_v6 USING btree (tier);",
)

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_list_v6 CASCADE;"


def upgrade() -> None:
    # 1. Re-register the cron job with all 16 v6 MVs.
    op.execute(_UNSCHEDULE)
    op.execute(_schedule_sql(_ALL_16_MVS))

    # 2. Repoint mv_stock_list_v6's date anchor to the live conviction table.
    op.execute(_DROP_MV)
    op.execute(_mv_stock_list_create(_LATEST_CTE_LIVE))
    for idx in _MV_INDEXES:
        op.execute(idx)


def downgrade() -> None:
    # Restore migration 111's 9-MV cron body.
    op.execute(_UNSCHEDULE)
    op.execute(_schedule_sql(_ORIGINAL_9_MVS))

    # Restore the original (dead-table) anchor.
    op.execute(_DROP_MV)
    op.execute(_mv_stock_list_create(_LATEST_CTE_DEAD))
    for idx in _MV_INDEXES:
        op.execute(idx)
