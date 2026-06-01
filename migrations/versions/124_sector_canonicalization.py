"""v6 — sector canonicalization: dissolve junk/theme buckets, reassign to true sectors.

Bubble chart (Page 05, mv_stock_landscape) grouped on atlas_universe_stocks.sector,
which contained junk buckets ("Conglomerate", "Diversified") and theme buckets
("Consumption", "MNC", "Rural", "Services", "Housing") that mis-grouped clearly
single-sector companies (e.g. Bajaj Housing Finance / M&M Financial labelled
"Conglomerate"; Asian Paints / Titan labelled "Consumption"). This distorted the
sector bubble chart.

This migration:
  1. Preserves the raw NSE/BSE label in a new `original_sector` audit column.
  2. Merges the "EV & Auto" theme into "Automobile".
  3. Reassigns each mis-bucketed stock to its true canonical sector (curated).

Scope is deliberately narrow: only the junk/theme buckets are dissolved. Legit
clusters (Digital, Healthcare, Capital Markets, Oil & Gas, Defence, Tourism) are
left untouched — the theme-vs-sector taxonomy debate is tracked separately (H3).

Revision ID: 124
Revises: 123
"""

from alembic import op

revision = "124"
down_revision = "123"
branch_labels = None
depends_on = None


# Curated stock → canonical-sector overrides (by symbol). Canonical sectors are
# drawn from the existing 22-sector set so no new buckets are introduced.
# Rows marked "# judgment" are the genuinely ambiguous ones flagged for review.
_OVERRIDES: dict[str, list[str]] = {
    "Financial Services": [
        "BAJAJHFL", "M&MFIN", "CHOLAHLDNG",        # ex-"Conglomerate" NBFCs
        "PIRAMALFIN", "POONAWALLA", "SUNDARMFIN",  # ex-"Rural" NBFCs
        "CMSINFO",                                  # ex-"Services" — cash-mgmt # judgment
    ],
    "Capital Markets": ["CRISIL"],                  # ex-"MNC" — ratings agency
    "Automobile": ["CEATLTD", "ESCORTS"],           # tyres / tractors
    "IT": ["FSL", "QUESS", "CRIZAC"],               # BPM / staffing / edu-services # judgment
    "Pharma": ["JUBLPHARMA"],
    "FMCG": ["GODREJAGRO", "AWL", "DMART"],         # agri / edible-oil / retail # judgment(DMART)
    "Chemicals": [
        "GODREJIND", "JUBLINGREA", "DCMSHRIRAM",
        "EPL", "JKPAPER", "TIMETECHNO", "SUPREMEIND",  # packaging / paper / plastics # judgment
    ],
    "Capital Goods": ["CARBORUNIV", "3MINDIA", "TIMKEN", "ASTRAL"],  # abrasives/industrials/bearings/pipes # judgment(ASTRAL)
    "Metal": ["MMTC", "MSTCLTD"],                   # metals trading / scrap e-auction # judgment
    "Realty": ["NESCO"],                            # exhibitions + property
    "Consumer Durables": [
        "ALOKINDS",                                  # textiles → nearest # judgment
        "DIXON", "HAVELLS", "TITAN", "TRENT",        # ex-"Consumption"
        "ASIANPAINT", "BERGEPAINT",                  # paints # judgment
        "POLYCAB",                                   # ex-"Housing" — wires & cables
        "KEI",                                       # ex-"EV & Auto" — wires & cables (mirror POLYCAB)
    ],
}


def upgrade() -> None:
    # 1. Preserve the raw label for audit / reversibility.
    op.execute(
        "ALTER TABLE atlas.atlas_universe_stocks "
        "ADD COLUMN IF NOT EXISTS original_sector varchar"
    )
    op.execute(
        "UPDATE atlas.atlas_universe_stocks "
        "SET original_sector = sector WHERE original_sector IS NULL"
    )

    # 2. Theme→sector merge.
    op.execute(
        "UPDATE atlas.atlas_universe_stocks "
        "SET sector = 'Automobile' WHERE sector = 'EV & Auto'"
    )

    # 3. Per-stock reassignment of the dissolved junk/theme buckets.
    for canonical, symbols in _OVERRIDES.items():
        in_list = ", ".join(f"'{s}'" for s in symbols)
        op.execute(
            "UPDATE atlas.atlas_universe_stocks "
            f"SET sector = '{canonical}' WHERE symbol IN ({in_list})"
        )

    # 4. Refresh the serving MV so the bubble chart picks up clean sectors.
    op.execute("REFRESH MATERIALIZED VIEW atlas.mv_stock_landscape")


def downgrade() -> None:
    # Restore the raw classification from the audit column.
    op.execute(
        "UPDATE atlas.atlas_universe_stocks "
        "SET sector = original_sector WHERE original_sector IS NOT NULL"
    )
    op.execute("REFRESH MATERIALIZED VIEW atlas.mv_stock_landscape")
