"""v6 — atlas_lens_scores_daily + policy_registry + lens threshold seeds.

Creates the primary output table for the six-lens scoring engine
(Technical, Fundamental, Valuation, Catalyst, Flow, Policy) plus a
policy registry (config-as-data) seeded with 15 government policies,
and threshold rows for lens weights, convergence bonuses, conviction
tiers, and valuation zone multipliers.

Revision ID: 124
Revises: 123
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "124"
down_revision = "123"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


# ---------------------------------------------------------------------------
# Threshold seeds
# (key, value, category, description, methodology_section, units,
#  min_allowed, max_allowed, default)
# ---------------------------------------------------------------------------
_THRESHOLD_SEEDS: tuple[tuple[str, float, str, str, str, str, float, float, float], ...] = (
    # ---- Lens weights (sum to 1.0 for non-valuation lenses) ----------------
    (
        "lens_weight_technical",
        0.20,
        "lens_weight",
        "Weight of the Technical lens in composite scoring",
        "lens",
        "ratio",
        0.05, 0.40, 0.20,
    ),
    (
        "lens_weight_fundamental",
        0.20,
        "lens_weight",
        "Weight of the Fundamental lens in composite scoring",
        "lens",
        "ratio",
        0.05, 0.40, 0.20,
    ),
    (
        "lens_weight_valuation",
        0.00,
        "lens_weight",
        "Weight of the Valuation lens — neutral descriptor, acts as multiplier not additive weight",
        "lens",
        "ratio",
        0.00, 0.20, 0.00,
    ),
    (
        "lens_weight_catalyst",
        0.25,
        "lens_weight",
        "Weight of the Catalyst lens in composite scoring",
        "lens",
        "ratio",
        0.05, 0.40, 0.25,
    ),
    (
        "lens_weight_flow",
        0.25,
        "lens_weight",
        "Weight of the Flow lens in composite scoring",
        "lens",
        "ratio",
        0.05, 0.40, 0.25,
    ),
    (
        "lens_weight_policy",
        0.10,
        "lens_weight",
        "Weight of the Policy lens in composite scoring",
        "lens",
        "ratio",
        0.00, 0.25, 0.10,
    ),
    # ---- Convergence bonus -------------------------------------------------
    (
        "lens_convergence_4plus",
        1.15,
        "lens_convergence",
        "Convergence multiplier when 4 or more lenses are firing",
        "lens",
        "multiplier",
        1.0, 1.3, 1.15,
    ),
    (
        "lens_convergence_3",
        1.10,
        "lens_convergence",
        "Convergence multiplier when exactly 3 lenses are firing",
        "lens",
        "multiplier",
        1.0, 1.2, 1.10,
    ),
    (
        "lens_convergence_2",
        1.06,
        "lens_convergence",
        "Convergence multiplier when exactly 2 lenses are firing",
        "lens",
        "multiplier",
        1.0, 1.15, 1.06,
    ),
    (
        "lens_convergence_threshold",
        40.0,
        "lens_convergence",
        "Minimum rescaled lens score to count as firing for convergence bonus",
        "lens",
        "score",
        20.0, 60.0, 40.0,
    ),
    # ---- Conviction tiers --------------------------------------------------
    (
        "lens_conviction_highest_score",
        70.0,
        "lens_conviction",
        "Minimum composite score for Highest conviction tier",
        "lens",
        "score",
        50.0, 90.0, 70.0,
    ),
    (
        "lens_conviction_highest_min_layers",
        3.0,
        "lens_conviction",
        "Minimum number of firing lenses required for Highest conviction tier",
        "lens",
        "count",
        2.0, 5.0, 3.0,
    ),
    (
        "lens_conviction_high_score",
        58.0,
        "lens_conviction",
        "Minimum composite score for High conviction tier",
        "lens",
        "score",
        40.0, 75.0, 58.0,
    ),
    (
        "lens_conviction_high_min_layers",
        2.0,
        "lens_conviction",
        "Minimum number of firing lenses required for High conviction tier",
        "lens",
        "count",
        1.0, 4.0, 2.0,
    ),
    (
        "lens_conviction_medium_score",
        45.0,
        "lens_conviction",
        "Minimum composite score for Medium conviction tier",
        "lens",
        "score",
        30.0, 60.0, 45.0,
    ),
    (
        "lens_conviction_watch_score",
        30.0,
        "lens_conviction",
        "Minimum composite score for Watch conviction tier",
        "lens",
        "score",
        15.0, 45.0, 30.0,
    ),
    # ---- Valuation zones ---------------------------------------------------
    (
        "lens_val_deep_value_threshold",
        75.0,
        "lens_valuation",
        "Valuation score threshold above which zone is Deep Value",
        "lens",
        "score",
        60.0, 90.0, 75.0,
    ),
    (
        "lens_val_deep_value_mult",
        1.15,
        "lens_valuation",
        "Composite multiplier applied in Deep Value zone",
        "lens",
        "multiplier",
        1.0, 1.3, 1.15,
    ),
    (
        "lens_val_cheap_threshold",
        55.0,
        "lens_valuation",
        "Valuation score threshold above which zone is Cheap",
        "lens",
        "score",
        40.0, 70.0, 55.0,
    ),
    (
        "lens_val_cheap_mult",
        1.08,
        "lens_valuation",
        "Composite multiplier applied in Cheap zone",
        "lens",
        "multiplier",
        1.0, 1.2, 1.08,
    ),
    (
        "lens_val_fair_threshold",
        35.0,
        "lens_valuation",
        "Valuation score threshold above which zone is Fair",
        "lens",
        "score",
        20.0, 50.0, 35.0,
    ),
    (
        "lens_val_fair_mult",
        1.00,
        "lens_valuation",
        "Composite multiplier applied in Fair zone (neutral)",
        "lens",
        "multiplier",
        0.8, 1.1, 1.00,
    ),
    (
        "lens_val_expensive_threshold",
        20.0,
        "lens_valuation",
        "Valuation score threshold above which zone is Expensive (below = Overvalued)",
        "lens",
        "score",
        10.0, 35.0, 20.0,
    ),
    (
        "lens_val_expensive_mult",
        0.90,
        "lens_valuation",
        "Composite multiplier applied in Expensive zone",
        "lens",
        "multiplier",
        0.7, 1.0, 0.90,
    ),
    (
        "lens_val_overvalued_mult",
        0.75,
        "lens_valuation",
        "Composite multiplier applied in Overvalued zone (below Expensive threshold)",
        "lens",
        "multiplier",
        0.5, 0.95, 0.75,
    ),
)


# ---------------------------------------------------------------------------
# Policy registry seeds (15 policies)
# (policy_id, policy_name, description, impact, sectors_json, keywords_json)
# ---------------------------------------------------------------------------
_POLICY_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "pli_electronics",
        "PLI Scheme — IT Hardware & Electronics",
        "Production-linked incentive scheme for IT hardware, electronics, and semiconductor manufacturing in India",
        "HIGH",
        '["Consumer Electronics", "Electronic Equipment", "Semiconductors", "Electronic Components"]',
        '["electronics", "semiconductor", "pcb", "circuit", "led", "display", "hardware"]',
    ),
    (
        "pli_pharma",
        "PLI Scheme — Pharmaceuticals & API",
        "Production-linked incentive scheme for pharmaceuticals, APIs, and medical devices",
        "HIGH",
        '["Pharmaceuticals", "Drug Manufacturers", "Healthcare", "Biotechnology"]',
        '["pharma", "drug", "api", "medical device", "biotech", "healthcare"]',
    ),
    (
        "pli_auto",
        "PLI Scheme — Auto & Auto Components",
        "Production-linked incentive scheme for automobile and auto component manufacturing",
        "HIGH",
        '["Auto Components", "Auto Manufacturers", "Auto - Cars & Light Trucks"]',
        '["auto", "automobile", "vehicle", "car", "ev", "battery", "motor"]',
    ),
    (
        "pli_textiles",
        "PLI Scheme — Textiles (MMF & Technical)",
        "Production-linked incentive scheme for man-made fibre and technical textiles",
        "MEDIUM",
        '["Textiles", "Textile Manufacturing", "Apparel Manufacturing"]',
        '["textile", "fabric", "yarn", "fibre", "garment", "apparel", "weaving"]',
    ),
    (
        "pli_food",
        "PLI Scheme — Food Processing",
        "Production-linked incentive scheme for food processing and agri-products",
        "MEDIUM",
        '["Packaged Foods", "Farm Products", "Food Distribution"]',
        '["food", "edible", "dairy", "agri", "sugar", "milling", "processing"]',
    ),
    (
        "pli_steel",
        "PLI Scheme — Specialty Steel",
        "Production-linked incentive scheme for specialty steel manufacturing",
        "MEDIUM",
        '["Steel", "Metal Fabrication", "Iron & Steel Products"]',
        '["steel", "alloy", "stainless", "metal", "iron"]',
    ),
    (
        "defense_indigenization",
        "Defense Indigenization & Positive List",
        "Defense indigenization initiative with positive lists for domestic manufacturing of defense equipment",
        "HIGH",
        '["Aerospace & Defense", "Defense", "Industrials"]',
        '["defense", "defence", "military", "aerospace", "ammunition", "naval", "missile", "radar"]',
    ),
    (
        "semiconductor_fab",
        "India Semiconductor Mission",
        "National mission for semiconductor fabrication, OSAT, and design ecosystem in India",
        "HIGH",
        '["Semiconductors", "Electronic Components", "Electronic Equipment"]',
        '["semiconductor", "chip", "wafer", "osat", "foundry", "silicon"]',
    ),
    (
        "green_hydrogen",
        "National Green Hydrogen Mission",
        "National mission for green hydrogen production, electrolyser manufacturing, and renewable energy",
        "MEDIUM",
        '["Renewable Energy", "Industrial Gases", "Utilities - Renewable"]',
        '["hydrogen", "electrolyser", "green energy", "renewable", "solar", "wind"]',
    ),
    (
        "pm_gati_shakti",
        "PM Gati Shakti — Infrastructure Push",
        "Multi-modal connectivity and infrastructure master plan for logistics and construction",
        "HIGH",
        '["Infrastructure", "Construction", "Engineering & Construction", "Building Materials", "Cement"]',
        '["infrastructure", "construction", "road", "highway", "bridge", "railway", "cement", "building"]',
    ),
    (
        "digital_india",
        "Digital India & IT Modernization",
        "Digital India initiative for IT modernization, e-governance, and digital infrastructure",
        "MEDIUM",
        '["Information Technology Services", "Software - Application", "Software - Infrastructure"]',
        '["digital", "software", "cloud", "cybersecurity", "fintech", "saas"]',
    ),
    (
        "fame_ev",
        "FAME III / EV Ecosystem Support",
        "Faster adoption and manufacturing of electric vehicles scheme and EV ecosystem support",
        "HIGH",
        '["Auto Components", "Auto Manufacturers", "Electrical Equipment"]',
        '["electric vehicle", "ev", "battery", "charging", "lithium", "motor"]',
    ),
    (
        "pm_awas_yojana",
        "PM Awas Yojana (Urban & Rural Housing)",
        "Affordable housing scheme for urban and rural areas driving demand for building materials",
        "MEDIUM",
        '["Building Materials", "Cement", "Building Products"]',
        '["housing", "cement", "pipe", "tile", "sanitaryware", "paint", "fitting"]',
    ),
    (
        "china_plus_one",
        "China+1 Manufacturing Shift",
        "Supply-chain diversification away from China benefiting Indian chemical and component manufacturers",
        "MEDIUM",
        '["Chemicals", "Specialty Chemicals", "Electronic Components", "Auto Components", "Textiles"]',
        '["chemical", "specialty chemical", "dye", "pigment", "agrochemical", "intermediates", "manufacturing"]',
    ),
    (
        "pli_solar",
        "PLI Scheme — Solar PV Manufacturing",
        "Production-linked incentive scheme for solar photovoltaic module and cell manufacturing",
        "HIGH",
        '["Solar", "Renewable Energy", "Utilities - Renewable"]',
        '["solar", "photovoltaic", "pv", "module", "cell", "renewable"]',
    ),
)


def upgrade() -> None:
    # -----------------------------------------------------------------
    # atlas_lens_scores_daily
    # -----------------------------------------------------------------
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_lens_scores_daily (
            instrument_id   UUID NOT NULL,
            date            DATE NOT NULL,
            asset_class     TEXT NOT NULL DEFAULT 'stock',
            -- 6 lens scores (0-100)
            technical       NUMERIC(6,2),
            fundamental     NUMERIC(6,2),
            valuation       NUMERIC(6,2),
            catalyst        NUMERIC(6,2),
            flow            NUMERIC(6,2),
            policy          NUMERIC(6,2),
            -- Technical subcomponents
            tech_trend          NUMERIC(6,2),
            tech_rs             NUMERIC(6,2),
            tech_vol_contraction NUMERIC(6,2),
            tech_volume         NUMERIC(6,2),
            -- Fundamental subcomponents
            fund_profitability  NUMERIC(6,2),
            fund_margin         NUMERIC(6,2),
            fund_growth         NUMERIC(6,2),
            fund_balance_sheet  NUMERIC(6,2),
            fund_op_leverage    NUMERIC(6,2),
            -- Valuation subcomponents
            val_pe_vs_sector    NUMERIC(6,2),
            val_absolute_pe     NUMERIC(6,2),
            val_pb              NUMERIC(6,2),
            val_ev_ebitda       NUMERIC(6,2),
            val_52w_position    NUMERIC(6,2),
            -- Catalyst subcomponents
            cat_earnings_strategy NUMERIC(6,2),
            cat_capital_action    NUMERIC(6,2),
            cat_governance        NUMERIC(6,2),
            -- Flow subcomponents
            flow_promoter       NUMERIC(6,2),
            flow_institutional  NUMERIC(6,2),
            flow_smart_money    NUMERIC(6,2),
            -- Policy subcomponent
            policy_tailwind     NUMERIC(6,2),
            -- Composite + conviction
            composite           NUMERIC(6,2),
            conviction_tier     TEXT,
            valuation_zone      TEXT,
            valuation_multiplier NUMERIC(6,4),
            -- Modifiers
            smart_money_score   NUMERIC(6,2),
            degradation_score   NUMERIC(6,2),
            -- Risk flags
            risk_flags          JSONB DEFAULT '[]'::jsonb,
            -- Evidence refs
            evidence            JSONB DEFAULT '{}'::jsonb,
            -- Metadata
            lenses_active       INTEGER DEFAULT 0,
            coverage_factor     NUMERIC(6,4),
            compute_run_id      UUID,
            computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_lens_scores_daily_date "
        "ON atlas.atlas_lens_scores_daily (date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_lens_scores_daily_tier "
        "ON atlas.atlas_lens_scores_daily (conviction_tier, date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_lens_scores_daily_class "
        "ON atlas.atlas_lens_scores_daily (asset_class, date)"
    ))

    # -----------------------------------------------------------------
    # policy_registry (config-as-data)
    # -----------------------------------------------------------------
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.policy_registry (
            policy_id       TEXT NOT NULL PRIMARY KEY,
            policy_name     TEXT NOT NULL,
            description     TEXT,
            impact          TEXT NOT NULL CHECK (impact IN ('HIGH', 'MEDIUM', 'LOW')),
            beneficiary_sectors JSONB NOT NULL DEFAULT '[]'::jsonb,
            beneficiary_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # -----------------------------------------------------------------
    # Seed policy_registry (idempotent via ON CONFLICT)
    # -----------------------------------------------------------------
    for pid, pname, desc, impact, sectors, keywords in _POLICY_SEEDS:
        op.execute(
            sa.text(
                """
                INSERT INTO atlas.policy_registry (
                    policy_id, policy_name, description, impact,
                    beneficiary_sectors, beneficiary_keywords
                ) VALUES (
                    :pid, :pname, :desc, :impact,
                    CAST(:sectors AS jsonb), CAST(:keywords AS jsonb)
                )
                ON CONFLICT (policy_id) DO UPDATE SET
                    policy_name = EXCLUDED.policy_name,
                    description = EXCLUDED.description,
                    impact = EXCLUDED.impact,
                    beneficiary_sectors = EXCLUDED.beneficiary_sectors,
                    beneficiary_keywords = EXCLUDED.beneficiary_keywords,
                    updated_at = NOW()
                """
            ).bindparams(
                pid=pid,
                pname=pname,
                desc=desc,
                impact=impact,
                sectors=sectors,
                keywords=keywords,
            )
        )

    # -----------------------------------------------------------------
    # Seed threshold rows (idempotent via ON CONFLICT DO NOTHING)
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
                    :lo, :hi, :default, 'migration_124', TRUE
                )
                ON CONFLICT (threshold_key) DO UPDATE SET
                    threshold_value = EXCLUDED.threshold_value,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    methodology_section = EXCLUDED.methodology_section,
                    units = EXCLUDED.units,
                    min_allowed = EXCLUDED.min_allowed,
                    max_allowed = EXCLUDED.max_allowed,
                    default_value = EXCLUDED.default_value,
                    last_modified_by = EXCLUDED.last_modified_by
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
    # Remove threshold seeds
    keys = ", ".join(f"'{s[0]}'" for s in _THRESHOLD_SEEDS)
    op.execute(
        sa.text(
            f"DELETE FROM atlas.atlas_thresholds WHERE threshold_key IN ({keys})"  # noqa: S608
        )
    )

    # Remove policy seeds
    pids = ", ".join(f"'{s[0]}'" for s in _POLICY_SEEDS)
    op.execute(
        sa.text(
            f"DELETE FROM atlas.policy_registry WHERE policy_id IN ({pids})"  # noqa: S608
        )
    )

    # Drop tables
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.policy_registry"))
    op.execute(sa.text(
        "DROP INDEX IF EXISTS atlas.ix_lens_scores_daily_class"
    ))
    op.execute(sa.text(
        "DROP INDEX IF EXISTS atlas.ix_lens_scores_daily_tier"
    ))
    op.execute(sa.text(
        "DROP INDEX IF EXISTS atlas.ix_lens_scores_daily_date"
    ))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_lens_scores_daily"))
