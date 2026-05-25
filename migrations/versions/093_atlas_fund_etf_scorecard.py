"""v6 — atlas_etf_scorecard + atlas_fund_scorecard + ranking thresholds.

Layers Fund + ETF ranking on top of the 24-cell conviction tape:

1. ``atlas_etf_scorecard`` — date × instrument_id with 6 component scores
   (matrix_conviction, sector_strength, tracking_quality, aum_bracket,
   liquidity, expense_ratio) and a weighted composite. Top 25% per
   ``etf_category`` flagged ``is_atlas_leader``.

2. ``atlas_fund_scorecard`` — date × scheme_code with 4 layer scores
   (risk_adjusted_return, holdings_conviction, style_sector,
   cost_manager) plus survivorship + staleness caveat columns. Top 25%
   per category → ``is_atlas_leader``; bottom 25% → ``is_avoid``.

Plus threshold rows for every weight tunable so the methodology can be
re-tuned without a redeploy.

Revision ID: 093
Revises: 092
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


# (key, value, category, description, methodology_section, units,
#  min_allowed, max_allowed, default)
_THRESHOLD_SEEDS: tuple[tuple[str, float, str, str, str, str, float, float, float], ...] = (
    # ---- ETF layer weights (sum to 1.0) -------------------------------------
    (
        "etf_weight_matrix",
        0.30,
        "etf_rank",
        "ETF composite — matrix conviction weight",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.30,
    ),
    (
        "etf_weight_sector",
        0.25,
        "etf_rank",
        "ETF composite — sector strength weight",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.25,
    ),
    (
        "etf_weight_tracking",
        0.15,
        "etf_rank",
        "ETF composite — tracking quality weight",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.15,
    ),
    (
        "etf_weight_aum",
        0.10,
        "etf_rank",
        "ETF composite — AUM bracket weight",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.10,
    ),
    (
        "etf_weight_liquidity",
        0.10,
        "etf_rank",
        "ETF composite — liquidity weight",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.10,
    ),
    (
        "etf_weight_expense",
        0.10,
        "etf_rank",
        "ETF composite — expense ratio weight (inverse)",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.10,
    ),
    # ---- Mutual fund layer weights (sum to 1.0) -----------------------------
    (
        "mf_weight_risk_adj",
        0.50,
        "mf_rank",
        "MF composite — risk-adjusted return layer (Sharpe/Sortino/Alpha/MaxDD/Calmar)",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.50,
    ),
    (
        "mf_weight_holdings",
        0.25,
        "mf_rank",
        "MF composite — holdings conviction layer (24-cell weighted avg)",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.25,
    ),
    (
        "mf_weight_style_sector",
        0.15,
        "mf_rank",
        "MF composite — style + sector tilt layer",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.15,
    ),
    (
        "mf_weight_cost_manager",
        0.10,
        "mf_rank",
        "MF composite — cost + manager layer (TER/tenure/AUM/age)",
        "fund-etf-ranking",
        "ratio",
        0.0,
        1.0,
        0.10,
    ),
    # ---- MF tunables --------------------------------------------------------
    (
        "mf_holdings_top_n",
        20.0,
        "mf_rank",
        "Top-N holdings used for the holdings conviction aggregation",
        "fund-etf-ranking",
        "count",
        5.0,
        50.0,
        20.0,
    ),
    (
        "mf_aum_sweet_spot_min_cr",
        500.0,
        "mf_rank",
        "Minimum AUM (Cr) for full cost+manager AUM score",
        "fund-etf-ranking",
        "INR_cr",
        50.0,
        5000.0,
        500.0,
    ),
    (
        "mf_aum_sweet_spot_max_cr",
        5000.0,
        "mf_rank",
        "Maximum AUM (Cr) for full cost+manager AUM score (above = liquidity drag)",
        "fund-etf-ranking",
        "INR_cr",
        500.0,
        50000.0,
        5000.0,
    ),
    (
        "mf_min_history_years_for_full_confidence",
        3.0,
        "mf_rank",
        "Years of NAV history required before confidence_low=FALSE",
        "fund-etf-ranking",
        "years",
        1.0,
        10.0,
        3.0,
    ),
    (
        "mf_atlas_leader_pct",
        25.0,
        "mf_rank",
        "Top-percentile cutoff (per category) for is_atlas_leader=TRUE",
        "fund-etf-ranking",
        "pct",
        5.0,
        50.0,
        25.0,
    ),
    (
        "mf_avoid_pct",
        25.0,
        "mf_rank",
        "Bottom-percentile cutoff (per category) for is_avoid=TRUE",
        "fund-etf-ranking",
        "pct",
        5.0,
        50.0,
        25.0,
    ),
    (
        "etf_atlas_leader_pct",
        25.0,
        "etf_rank",
        "Top-percentile cutoff (per category) for ETF is_atlas_leader=TRUE",
        "fund-etf-ranking",
        "pct",
        5.0,
        50.0,
        25.0,
    ),
    # ---- ETF tunables -------------------------------------------------------
    (
        "etf_aum_sweet_spot_min_cr",
        100.0,
        "etf_rank",
        "Minimum AUM (Cr) for full ETF AUM score",
        "fund-etf-ranking",
        "INR_cr",
        10.0,
        1000.0,
        100.0,
    ),
    (
        "etf_aum_sweet_spot_max_cr",
        50000.0,
        "etf_rank",
        "Maximum AUM (Cr) for full ETF AUM score",
        "fund-etf-ranking",
        "INR_cr",
        1000.0,
        500000.0,
        50000.0,
    ),
)


def upgrade() -> None:
    # -----------------------------------------------------------------
    # atlas_etf_scorecard
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_etf_scorecard",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("isin", sa.String(length=16), nullable=True),
        sa.Column("ticker", sa.String(length=32), nullable=True),
        sa.Column("etf_name", sa.String(length=256), nullable=True),
        sa.Column("etf_category", sa.String(length=32), nullable=False),
        sa.Column("underlying_sector", sa.String(length=64), nullable=True),
        # 6 component scores (0-100)
        sa.Column("matrix_conviction_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("sector_strength_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("tracking_quality_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("aum_bracket_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("liquidity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("expense_ratio_score", sa.Numeric(6, 2), nullable=True),
        # Composite + ranking
        sa.Column("composite_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("rank_in_category", sa.Integer(), nullable=True),
        sa.Column("category_size", sa.Integer(), nullable=True),
        sa.Column(
            "is_atlas_leader",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("eli5", sa.Text(), nullable=True),
        sa.Column("raw_metrics", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_date",
            "instrument_id",
            name="uq_atlas_etf_scorecard_natural_key",
        ),
        sa.CheckConstraint(
            "etf_category IN ('broad_index','sector','thematic','commodity',"
            "'international','debt','smart_beta')",
            name="ck_atlas_etf_scorecard_category",
        ),
        sa.CheckConstraint(
            "composite_score BETWEEN 0 AND 100",
            name="ck_atlas_etf_scorecard_composite_range",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_etf_scorecard_date_score",
        "atlas_etf_scorecard",
        ["snapshot_date", sa.text("composite_score DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_etf_scorecard_category_date",
        "atlas_etf_scorecard",
        ["etf_category", "snapshot_date"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_fund_scorecard
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_fund_scorecard",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        # We key by scheme_code (= mstar_id in our world). Stored as VARCHAR
        # to stay loose from the de_mf_master PK type.
        sa.Column("scheme_code", sa.String(length=32), nullable=False),
        sa.Column("isin", sa.String(length=16), nullable=True),
        sa.Column("fund_name", sa.String(length=256), nullable=True),
        sa.Column("fund_category", sa.String(length=64), nullable=False),
        sa.Column("fund_style", sa.String(length=32), nullable=True),
        sa.Column("amc", sa.String(length=128), nullable=True),
        # Layer scores (0-100)
        sa.Column("risk_adjusted_return_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("holdings_conviction_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("style_sector_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("cost_manager_score", sa.Numeric(6, 2), nullable=True),
        # Composite + ranking flags
        sa.Column("composite_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("rank_in_category", sa.Integer(), nullable=True),
        sa.Column("category_size", sa.Integer(), nullable=True),
        sa.Column(
            "is_atlas_leader",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "is_avoid",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        # Caveats
        sa.Column(
            "confidence_low",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "holdings_unjoinable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("survivorship_exposure_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("nav_as_of", sa.Date(), nullable=True),
        sa.Column("holdings_as_of", sa.Date(), nullable=True),
        sa.Column("eli5", sa.Text(), nullable=True),
        sa.Column("sub_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("top_holdings", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_date",
            "scheme_code",
            name="uq_atlas_fund_scorecard_natural_key",
        ),
        sa.CheckConstraint(
            "composite_score BETWEEN 0 AND 100",
            name="ck_atlas_fund_scorecard_composite_range",
        ),
        sa.CheckConstraint(
            "survivorship_exposure_pct IS NULL OR survivorship_exposure_pct BETWEEN 0 AND 100",
            name="ck_atlas_fund_scorecard_survivorship_range",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_fund_scorecard_date_score",
        "atlas_fund_scorecard",
        ["snapshot_date", sa.text("composite_score DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "idx_fund_scorecard_category_date",
        "atlas_fund_scorecard",
        ["fund_category", "snapshot_date"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # Seed threshold rows (idempotent)
    # -----------------------------------------------------------------
    for key, value, category, desc, section, units, lo, hi, default in _THRESHOLD_SEEDS:
        op.execute(
            sa.text(
                """
                INSERT INTO atlas.atlas_thresholds (
                    threshold_key, threshold_value, category, description,
                    methodology_section, units, min_allowed, max_allowed,
                    default_value, last_modified_by, is_active
                ) VALUES (
                    :key, :value, :category, :desc, :section, :units,
                    :lo, :hi, :default, 'migration_093', TRUE
                )
                ON CONFLICT (threshold_key) DO NOTHING
                """
            ).bindparams(
                key=key,
                value=value,
                category=category,
                desc=desc,
                section=section,
                units=units,
                lo=lo,
                hi=hi,
                default=default,
            )
        )


def downgrade() -> None:
    # Threshold keys come from the module-level constant tuple — no
    # untrusted input flows here. Hence noqa: S608 (Bandit SQL-injection
    # heuristic flags any f-string in SQL, but this site is safe.)
    keys = ", ".join(f"'{s[0]}'" for s in _THRESHOLD_SEEDS)
    op.execute(
        sa.text(
            f"DELETE FROM atlas.atlas_thresholds WHERE threshold_key IN ({keys})"  # noqa: S608
        )
    )

    op.drop_index(
        "idx_fund_scorecard_category_date",
        table_name="atlas_fund_scorecard",
        schema=_SCHEMA,
    )
    op.drop_index(
        "idx_fund_scorecard_date_score",
        table_name="atlas_fund_scorecard",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_fund_scorecard", schema=_SCHEMA)

    op.drop_index(
        "idx_etf_scorecard_category_date",
        table_name="atlas_etf_scorecard",
        schema=_SCHEMA,
    )
    op.drop_index(
        "idx_etf_scorecard_date_score",
        table_name="atlas_etf_scorecard",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_etf_scorecard", schema=_SCHEMA)
