"""v6 — Macro overlay tables (Phase 9).

Adds the Phase 9 schema for the macro / asset-allocation overlay:

- ``atlas_macro_features_daily`` — daily cross-asset macro features
  (equity-vs-debt spread, gold trend, INR/USD trend, cross-asset
  dispersion, VIX, 10Y G-Sec yield, Brent crude in INR). These feed the
  allocation rule engine that emits the asset-class % bands.

- ``atlas_macro_recommendation_daily`` — daily asset-class % band
  recommendations (equity / debt / gold / cash). Per /grill Q11 D10
  (Phase 9 sizing bands deferred) this layer emits *ranges only* — no
  per-instrument sizing. Per-instrument sizing is intentionally pushed
  to v7.

Enum references
---------------
Reuses ``atlas_regime_state`` created by migration 080 (referenced with
``create_type=False`` — do NOT re-create, do NOT drop on downgrade).

This migration owns no new enum types — the entire schema reuses 080.

FK relationships
----------------
- ``atlas_macro_recommendation_daily.macro_features_id`` →
  ``atlas.atlas_macro_features_daily(id)`` ON DELETE SET NULL.
  Recommendations should survive (with the FK nulled) if the feature row
  that produced them is later corrected / replaced, so downstream
  audit trails keep working.
- ``provenance_log_id`` on the features table is intentionally a plain
  UUID with no FK — the provenance log table lands in a later
  migration; we keep the column nullable now so the FK can be added in
  place later without an ALTER on a populated NOT NULL column.

CHECK constraints
-----------------
Per spec the recommendation table enforces, for each of equity / debt /
gold / cash:

- ``low <= high`` (4 paired checks)
- ``0 <= low <= 100`` and ``0 <= high <= 100`` (8 range checks)

These are CHECK constraints rather than triggers — they're cheap, catch
bad upstream computes deterministically, and don't add per-row latency.

Migration chain
---------------
    080 (foundation) -> 082 (brief_cache)
                     -> 083 (ledger)
                     -> 084 (paper_portfolio + user_lots)
                     -> 085 (ETF + MF)
                     -> 086 (macro overlay — this migration)

081 (atlas_cell_walkforward_runs) is tracked separately and may land
out of order. 086 does NOT depend on 081.

Revision ID: 086
Revises: 085
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # Reference the existing atlas_regime_state enum from migration 080.
    # create_type=False — 086 does NOT own this enum.
    regime_state_enum = postgresql.ENUM(
        name="atlas_regime_state", schema=_SCHEMA, create_type=False
    )

    # -----------------------------------------------------------------
    # atlas_macro_features_daily — daily cross-asset macro features.
    # One row per date.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_macro_features_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("regime_state", regime_state_enum, nullable=False),
        sa.Column("equity_vs_debt_spread", sa.Numeric(10, 6), nullable=True),
        sa.Column("gold_trend", sa.Numeric(10, 6), nullable=True),
        sa.Column("inr_usd_trend", sa.Numeric(10, 6), nullable=True),
        sa.Column("cross_asset_dispersion", sa.Numeric(10, 6), nullable=True),
        sa.Column("vix_level", sa.Numeric(8, 4), nullable=True),
        sa.Column("g_sec_10y_yield", sa.Numeric(6, 4), nullable=True),
        sa.Column("crude_brent_inr", sa.Numeric(12, 4), nullable=True),
        # FK target table (provenance log) lands in a later migration.
        # Keep the column nullable + un-FK'd now so we can ALTER ADD
        # CONSTRAINT later without rewriting NOT NULL semantics.
        sa.Column("provenance_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "date", name="uq_atlas_macro_features_daily_date"
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_macro_features_daily_date_desc",
        "atlas_macro_features_daily",
        [sa.text("date DESC")],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_macro_recommendation_daily — asset-class % band emissions.
    # Per /grill Q11 D10: ranges only, no per-instrument sizing.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_macro_recommendation_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("regime_state", regime_state_enum, nullable=False),
        sa.Column("equity_pct_low", sa.Numeric(5, 2), nullable=False),
        sa.Column("equity_pct_high", sa.Numeric(5, 2), nullable=False),
        sa.Column("debt_pct_low", sa.Numeric(5, 2), nullable=False),
        sa.Column("debt_pct_high", sa.Numeric(5, 2), nullable=False),
        sa.Column("gold_pct_low", sa.Numeric(5, 2), nullable=False),
        sa.Column("gold_pct_high", sa.Numeric(5, 2), nullable=False),
        sa.Column("cash_pct_low", sa.Numeric(5, 2), nullable=False),
        sa.Column("cash_pct_high", sa.Numeric(5, 2), nullable=False),
        # JSONB attribution map — which features drove the bands.
        sa.Column("drivers", postgresql.JSONB(), nullable=True),
        sa.Column("methodology_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "macro_features_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_macro_features_daily.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # low <= high per asset class.
        sa.CheckConstraint(
            "equity_pct_low <= equity_pct_high",
            name="ck_atlas_macro_reco_equity_low_le_high",
        ),
        sa.CheckConstraint(
            "debt_pct_low <= debt_pct_high",
            name="ck_atlas_macro_reco_debt_low_le_high",
        ),
        sa.CheckConstraint(
            "gold_pct_low <= gold_pct_high",
            name="ck_atlas_macro_reco_gold_low_le_high",
        ),
        sa.CheckConstraint(
            "cash_pct_low <= cash_pct_high",
            name="ck_atlas_macro_reco_cash_low_le_high",
        ),
        # Each low / high in [0, 100].
        sa.CheckConstraint(
            "equity_pct_low >= 0 AND equity_pct_low <= 100",
            name="ck_atlas_macro_reco_equity_low_range",
        ),
        sa.CheckConstraint(
            "equity_pct_high >= 0 AND equity_pct_high <= 100",
            name="ck_atlas_macro_reco_equity_high_range",
        ),
        sa.CheckConstraint(
            "debt_pct_low >= 0 AND debt_pct_low <= 100",
            name="ck_atlas_macro_reco_debt_low_range",
        ),
        sa.CheckConstraint(
            "debt_pct_high >= 0 AND debt_pct_high <= 100",
            name="ck_atlas_macro_reco_debt_high_range",
        ),
        sa.CheckConstraint(
            "gold_pct_low >= 0 AND gold_pct_low <= 100",
            name="ck_atlas_macro_reco_gold_low_range",
        ),
        sa.CheckConstraint(
            "gold_pct_high >= 0 AND gold_pct_high <= 100",
            name="ck_atlas_macro_reco_gold_high_range",
        ),
        sa.CheckConstraint(
            "cash_pct_low >= 0 AND cash_pct_low <= 100",
            name="ck_atlas_macro_reco_cash_low_range",
        ),
        sa.CheckConstraint(
            "cash_pct_high >= 0 AND cash_pct_high <= 100",
            name="ck_atlas_macro_reco_cash_high_range",
        ),
        sa.UniqueConstraint(
            "date", name="uq_atlas_macro_recommendation_daily_date"
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_macro_recommendation_daily_date_desc",
        "atlas_macro_recommendation_daily",
        [sa.text("date DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_macro_recommendation_daily_regime_state",
        "atlas_macro_recommendation_daily",
        ["regime_state"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Reverse upgrade. Drop order:

    1. Named indexes via op.drop_index.
    2. Tables in FK-dependency order — atlas_macro_recommendation_daily
       FKs to atlas_macro_features_daily, so the recommendation table
       MUST be dropped first.
    3. NO enum drops — atlas_regime_state is owned by migration 080.
    """
    # 1. Drop indexes — recommendation table first (FK source).
    op.drop_index(
        "ix_atlas_macro_recommendation_daily_regime_state",
        "atlas_macro_recommendation_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_macro_recommendation_daily_date_desc",
        "atlas_macro_recommendation_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_macro_features_daily_date_desc",
        "atlas_macro_features_daily",
        schema=_SCHEMA,
    )

    # 2. Drop tables — recommendation BEFORE features (FK dependency).
    op.drop_table("atlas_macro_recommendation_daily", schema=_SCHEMA)
    op.drop_table("atlas_macro_features_daily", schema=_SCHEMA)

    # 3. Intentionally do NOT drop atlas_regime_state — owned by 080.
