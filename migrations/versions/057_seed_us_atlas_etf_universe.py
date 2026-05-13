"""Seed us_atlas.atlas_universe_etfs with curated ~60 US-listed ETFs.

Mirrors the ticker list in scripts/stooq_backfill_us.py (ALL_ETFS).
Categories map to etf_category; sector ETFs carry linked_sector for
benchmark resolution in a future RS-vs-sector enhancement.
"""

from alembic import op

revision = "057"
down_revision = "056"


def upgrade() -> None:
    op.execute("""
        INSERT INTO us_atlas.atlas_universe_etfs
            (ticker, etf_category, linked_sector, is_benchmark, is_active)
        VALUES
            -- Sector ETFs (SPDR Select Sectors — 11 GICS sectors)
            ('xlk',  'Sector ETF', 'Information Technology', FALSE, TRUE),
            ('xlf',  'Sector ETF', 'Financials',             FALSE, TRUE),
            ('xle',  'Sector ETF', 'Energy',                 FALSE, TRUE),
            ('xlv',  'Sector ETF', 'Health Care',            FALSE, TRUE),
            ('xli',  'Sector ETF', 'Industrials',            FALSE, TRUE),
            ('xly',  'Sector ETF', 'Consumer Discretionary', FALSE, TRUE),
            ('xlp',  'Sector ETF', 'Consumer Staples',       FALSE, TRUE),
            ('xlb',  'Sector ETF', 'Materials',              FALSE, TRUE),
            ('xlre', 'Sector ETF', 'Real Estate',            FALSE, TRUE),
            ('xlu',  'Sector ETF', 'Utilities',              FALSE, TRUE),
            ('xlc',  'Sector ETF', 'Communication Services', FALSE, TRUE),

            -- Broad Market ETFs
            ('qqq',  'Broad ETF',   NULL, FALSE, TRUE),
            ('iwm',  'Broad ETF',   NULL, FALSE, TRUE),
            ('dia',  'Broad ETF',   NULL, FALSE, TRUE),
            ('voo',  'Broad ETF',   NULL, FALSE, TRUE),
            ('ivv',  'Broad ETF',   NULL, FALSE, TRUE),
            ('vxf',  'Broad ETF',   NULL, FALSE, TRUE),

            -- Factor ETFs
            ('mtum', 'Factor ETF',  NULL, FALSE, TRUE),
            ('qual', 'Factor ETF',  NULL, FALSE, TRUE),
            ('vlue', 'Factor ETF',  NULL, FALSE, TRUE),
            ('usmv', 'Factor ETF',  NULL, FALSE, TRUE),

            -- Precious Metals ETFs
            ('slv',  'Commodity ETF', NULL, FALSE, TRUE),
            ('sil',  'Commodity ETF', NULL, FALSE, TRUE),
            ('gdx',  'Commodity ETF', NULL, FALSE, TRUE),
            ('gdxj', 'Commodity ETF', NULL, FALSE, TRUE),
            ('iau',  'Commodity ETF', NULL, FALSE, TRUE),
            ('sgol', 'Commodity ETF', NULL, FALSE, TRUE),
            ('pplt', 'Commodity ETF', NULL, FALSE, TRUE),
            ('pall', 'Commodity ETF', NULL, FALSE, TRUE),

            -- Energy Commodity ETFs
            ('uso',  'Commodity ETF', NULL, FALSE, TRUE),
            ('dbo',  'Commodity ETF', NULL, FALSE, TRUE),
            ('ung',  'Commodity ETF', NULL, FALSE, TRUE),
            ('amlp', 'Commodity ETF', NULL, FALSE, TRUE),

            -- Broad Commodity ETFs
            ('dba',  'Commodity ETF', NULL, FALSE, TRUE),
            ('dbb',  'Commodity ETF', NULL, FALSE, TRUE),
            ('copx', 'Commodity ETF', NULL, FALSE, TRUE),
            ('xme',  'Commodity ETF', NULL, FALSE, TRUE),
            ('pdbc', 'Commodity ETF', NULL, FALSE, TRUE),
            ('dbc',  'Commodity ETF', NULL, FALSE, TRUE),
            ('gsg',  'Commodity ETF', NULL, FALSE, TRUE),
            ('remx', 'Commodity ETF', NULL, FALSE, TRUE),
            ('lit',  'Commodity ETF', NULL, FALSE, TRUE),

            -- Thematic ETFs
            ('arkk', 'Thematic ETF', NULL, FALSE, TRUE),
            ('botz', 'Thematic ETF', NULL, FALSE, TRUE),
            ('soxx', 'Thematic ETF', NULL, FALSE, TRUE),
            ('smh',  'Thematic ETF', NULL, FALSE, TRUE),
            ('hack', 'Thematic ETF', NULL, FALSE, TRUE)
        ON CONFLICT (ticker) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM us_atlas.atlas_universe_etfs")
