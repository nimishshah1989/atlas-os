"""v6 — frontend-driven column adds + 2 config tables.

Adds the schema scaffolding that v6 mockup pages 01-08 require:
- atlas_cell_definitions: display_name + explain_text (Page 01 cell cards, Page 05 conviction tape)
- atlas_sector_metrics_daily: rs_{1w,1m,6m,12m} + pct_above_ema20/200 + pct_52wh + hhi
  (Page 04 sector cards + heatmap + deep-dive)
- atlas_macro_daily: dii_flow + us_10y_yield + brent_inr + cpi_yoy + vix_9d
  (Page 02 macro grid — columns are nullable; will populate via Phase C2-C6 ingest)
- atlas_etf_scorecard: premium_bps + te_60d + adv_20d_inr (Page 07 ETF detail)
- atlas_stock_macro_overlay_map (Page 05a macro strip per stock; seeded with 23 sectors)
- atlas_etf_te_bands (Page 07 TE band config; seeded with 5 category bands per CONTEXT.md)

All columns nullable so existing rows are unaffected. Writers populate via Phase C.

Deferred to migration 098 (next session — needs writers built first):
- atlas_etf_ter_components (quarterly AMC SAI disclosure ingest)
- atlas_etf_physical_disclosure (monthly AMC disclosure)
- atlas_stock_fundamentals_quarterly (NSE XBRL parser)
- de_fno_bhavcopy_daily + de_fno_oi_daily + de_fno_participant_oi_daily (NSE F&O scraper)
- atlas_stock_fno_metrics_daily (depends on F&O ingest)

Revision ID: 097
Revises: 096
Create Date: 2026-05-26 22:30 IST
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # =================================================================
    # 1. atlas_cell_definitions — display_name + explain_text
    # =================================================================
    op.add_column(
        "atlas_cell_definitions",
        sa.Column("display_name", sa.String(length=64), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "atlas_cell_definitions",
        sa.Column("explain_text", sa.Text(), nullable=True),
        schema=_SCHEMA,
    )
    # Backfill display_name deterministically from cell_id components per CONTEXT.md
    # convention: "{cap_tier} {tenure} {action_label} signal" where action_label is
    # POSITIVE→BUY, NEUTRAL→WATCH, NEGATIVE→AVOID
    op.execute("""
        UPDATE atlas.atlas_cell_definitions
        SET display_name = cap_tier::text || ' ' || tenure::text || ' ' ||
            CASE action::text
                WHEN 'POSITIVE' THEN 'BUY'
                WHEN 'NEUTRAL'  THEN 'WATCH'
                WHEN 'NEGATIVE' THEN 'AVOID'
            END || ' signal'
        WHERE display_name IS NULL
    """)
    # explain_text stays NULL — backfilled separately via Phase C1.a (manual seed for 21 cells)

    # =================================================================
    # 2. atlas_sector_metrics_daily — RS windows + breadth + concentration
    # =================================================================
    for col_name in ["rs_1w", "rs_1m", "rs_6m", "rs_12m"]:
        op.add_column(
            "atlas_sector_metrics_daily",
            sa.Column(col_name, sa.Numeric(10, 4), nullable=True),
            schema=_SCHEMA,
        )
    for col_name in ["pct_above_ema20", "pct_above_ema200", "pct_52wh"]:
        op.add_column(
            "atlas_sector_metrics_daily",
            sa.Column(col_name, sa.Numeric(5, 2), nullable=True),
            schema=_SCHEMA,
        )
    op.add_column(
        "atlas_sector_metrics_daily",
        sa.Column("hhi", sa.Numeric(8, 2), nullable=True),
        schema=_SCHEMA,
    )

    # =================================================================
    # 3. atlas_macro_daily — 5 new nullable columns
    # =================================================================
    op.add_column("atlas_macro_daily", sa.Column("dii_flow", sa.Numeric(12, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("us_10y_yield", sa.Numeric(6, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("brent_inr", sa.Numeric(12, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("cpi_yoy", sa.Numeric(6, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_macro_daily", sa.Column("vix_9d", sa.Numeric(8, 4), nullable=True), schema=_SCHEMA)

    # =================================================================
    # 4. atlas_etf_scorecard — premium / TE / ADV
    # =================================================================
    op.add_column("atlas_etf_scorecard", sa.Column("premium_bps", sa.Numeric(8, 2), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_etf_scorecard", sa.Column("te_60d", sa.Numeric(8, 4), nullable=True), schema=_SCHEMA)
    op.add_column("atlas_etf_scorecard", sa.Column("adv_20d_inr", sa.Numeric(18, 2), nullable=True), schema=_SCHEMA)

    # =================================================================
    # 5. NEW TABLE: atlas_stock_macro_overlay_map
    # =================================================================
    op.create_table(
        "atlas_stock_macro_overlay_map",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sector", sa.String(length=64), nullable=False),
        sa.Column("business_mix_tag", sa.String(length=64), nullable=True),
        sa.Column("macro_series_1", sa.String(length=32), nullable=False),
        sa.Column("macro_series_2", sa.String(length=32), nullable=False),
        sa.Column("macro_series_3", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("sector", "business_mix_tag", "effective_from", name="uq_stock_macro_overlay_sector_tag"),
        schema=_SCHEMA,
    )
    op.execute("""
        INSERT INTO atlas.atlas_stock_macro_overlay_map (sector, business_mix_tag, macro_series_1, macro_series_2, macro_series_3, rationale) VALUES
        ('Energy', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Oil & gas exposure to Brent, refining margins to USD/INR, capex cost to G-sec'),
        ('Materials', NULL, 'BRENT_INR', 'USDINR', 'DXY', 'Commodity producers sensitive to crude + INR + global metal cycle (DXY proxy)'),
        ('IT', NULL, 'USDINR', 'US_10Y', 'DXY', 'USD revenue + US bond yield (client demand proxy) + dollar strength'),
        ('Pvt Bank', NULL, 'INDIA_10Y', 'USDINR', 'BRENT_INR', 'NIM sensitivity to yields, FX to corporate book, oil to inflation/CAD'),
        ('PSU Bank', NULL, 'INDIA_10Y', 'BRENT_INR', 'USDINR', 'Same as Pvt Bank but stronger PSU yield sensitivity'),
        ('Financials', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'NBFC funding cost + cross-border flows'),
        ('Insurance', NULL, 'INDIA_10Y', 'USDINR', 'NIFTY_VIX', 'Long-duration asset + investment income + claim volatility'),
        ('Auto', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Input cost (steel via INR proxy) + EXIM + consumer financing'),
        ('Pharma', NULL, 'USDINR', 'US_10Y', 'DXY', 'Export exposure + US regulatory cycle (yield proxy) + dollar'),
        ('Healthcare', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'Domestic-heavy; some export'),
        ('FMCG', NULL, 'INDIA_10Y', 'BRENT_INR', 'USDINR', 'Domestic demand + input costs (palm oil/crude proxy)'),
        ('Cons Disc', NULL, 'INDIA_10Y', 'BRENT_INR', 'USDINR', 'Consumer financing + fuel/discretionary spend'),
        ('Cons Staples', NULL, 'BRENT_INR', 'INDIA_10Y', 'USDINR', 'Input cost + rural demand cycle'),
        ('Telecom', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'Capex financing + dollar capex'),
        ('Utilities', NULL, 'BRENT_INR', 'INDIA_10Y', 'USDINR', 'Fuel cost + tariff regulation lag'),
        ('Industrials', NULL, 'INDIA_10Y', 'USDINR', 'BRENT_INR', 'Order book + import inputs + project finance'),
        ('Capital Mkts', NULL, 'NIFTY_VIX', 'INDIA_10Y', 'USDINR', 'Volatility + rate sensitivity + FII flow'),
        ('Real Estate', NULL, 'INDIA_10Y', 'USDINR', 'BRENT_INR', 'Mortgage rate + materials cost + dollar carry'),
        ('Defence', NULL, 'USDINR', 'INDIA_10Y', 'BRENT_INR', 'Defence imports + budget cycle'),
        ('Construction', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Cement/steel cost + project finance'),
        ('Logistics', NULL, 'BRENT_INR', 'USDINR', 'INDIA_10Y', 'Fuel + trade flow + working capital cost'),
        ('Chemicals', NULL, 'BRENT_INR', 'USDINR', 'DXY', 'Petrochemical inputs + global pricing power'),
        ('Communication', NULL, 'INDIA_10Y', 'USDINR', 'DXY', 'Capex financing + dollar capex')
    """)
    op.create_index(
        "ix_atlas_stock_macro_overlay_map_active",
        "atlas_stock_macro_overlay_map",
        ["sector"],
        unique=False,
        postgresql_where=sa.text("effective_to IS NULL"),
        schema=_SCHEMA,
    )

    # =================================================================
    # 6. NEW TABLE: atlas_etf_te_bands (per CONTEXT.md ETF vocabulary)
    # =================================================================
    op.create_table(
        "atlas_etf_te_bands",
        sa.Column("category", sa.String(length=32), primary_key=True),
        sa.Column("te_max_bps", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        schema=_SCHEMA,
    )
    op.execute("""
        INSERT INTO atlas.atlas_etf_te_bands (category, te_max_bps, notes) VALUES
        ('index', 15, 'Plain-vanilla index trackers (NIFTYBEES, NIFTY50, etc.)'),
        ('sector', 30, 'Sector ETFs (BANKBEES, PSUBNKBEES, etc.)'),
        ('smart_beta', 50, 'Smart-beta / factor ETFs (LOWVOL, MOMENTUM, etc.)'),
        ('international', 35, 'International equity exposure (HANG SENG, NASDAQ, etc.)'),
        ('commodity', 20, 'Commodity ETFs (GOLDBEES, SILVERBEES, etc.)')
    """)


def downgrade() -> None:
    op.drop_table("atlas_etf_te_bands", schema=_SCHEMA)
    op.drop_index(
        "ix_atlas_stock_macro_overlay_map_active",
        table_name="atlas_stock_macro_overlay_map",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_stock_macro_overlay_map", schema=_SCHEMA)

    for col_name in ["premium_bps", "te_60d", "adv_20d_inr"]:
        op.drop_column("atlas_etf_scorecard", col_name, schema=_SCHEMA)

    for col_name in ["dii_flow", "us_10y_yield", "brent_inr", "cpi_yoy", "vix_9d"]:
        op.drop_column("atlas_macro_daily", col_name, schema=_SCHEMA)

    for col_name in ["hhi", "pct_52wh", "pct_above_ema200", "pct_above_ema20", "rs_12m", "rs_6m", "rs_1m", "rs_1w"]:
        op.drop_column("atlas_sector_metrics_daily", col_name, schema=_SCHEMA)

    op.drop_column("atlas_cell_definitions", "explain_text", schema=_SCHEMA)
    op.drop_column("atlas_cell_definitions", "display_name", schema=_SCHEMA)
