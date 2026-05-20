"""Wave 4A Task 5 — seed band + floor thresholds for hybrid sector/fund classifiers.

These thresholds are read by:
  atlas.intelligence.aggregations.sector._sector_rank_config()
  atlas.intelligence.aggregations.fund._fund_rank_config()

Both functions fall back to inline Decimal defaults when the key is absent
(keeping unit tests DB-free). This migration makes the values live in
atlas_thresholds so they are runtime-tunable via the /admin/thresholds UI
without a redeploy.

All proportion values are stored as 0-1 fractions (not whole-number %).
sector_overweight_floor = 0.10 means "pct_stage_2 >= 10% to hold Overweight".
fund_recommended_floor  = 0.20 means "strong_aum_pct >= 20% to hold Recommended".

Idempotent — ON CONFLICT (threshold_key) DO NOTHING.

Revision ID: 095_seed_hybrid_classifier_thresholds
Revises: 094_sector_state_from_computed
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "095_seed_hybrid_classifier_thresholds"
down_revision = "094_sector_state_from_computed"
branch_labels = None
depends_on = None

# (key, value, category, description, min_allowed, max_allowed, default_value)
SEEDS: tuple[tuple[str, float, str, str, float, float, float], ...] = (
    # --- Sector cross-sectional hybrid-rank band cut-points ---
    (
        "sector_band_p20",
        0.20,
        "sector_rank",
        "Bottom percentile cut-point for sector hybrid-rank label Avoid",
        0.05, 0.40, 0.20,
    ),
    (
        "sector_band_p50",
        0.50,
        "sector_rank",
        "Mid percentile cut-point separating Underweight from Neutral sectors",
        0.30, 0.70, 0.50,
    ),
    (
        "sector_band_p80",
        0.80,
        "sector_rank",
        "Top percentile cut-point for sector hybrid-rank label Overweight",
        0.60, 0.95, 0.80,
    ),
    (
        "sector_overweight_floor",
        0.10,
        "sector_rank",
        "Min pct_stage_2 (0-1 proportion) a sector must hold to keep Overweight label",
        0.05, 0.50, 0.10,
    ),
    # --- Fund cross-sectional hybrid-rank band cut-points ---
    (
        "fund_band_p20",
        0.20,
        "fund_rank",
        "Bottom percentile cut-point for fund hybrid-rank label Exit",
        0.05, 0.40, 0.20,
    ),
    (
        "fund_band_p50",
        0.50,
        "fund_rank",
        "Mid percentile cut-point separating Reduce from Hold funds",
        0.30, 0.70, 0.50,
    ),
    (
        "fund_band_p80",
        0.80,
        "fund_rank",
        "Top percentile cut-point for fund hybrid-rank label Recommended",
        0.60, 0.95, 0.80,
    ),
    (
        "fund_recommended_floor",
        0.20,
        "fund_rank",
        "Min strong_aum_pct (0-1 proportion) a fund must hold to keep Recommended label",
        0.05, 0.50, 0.20,
    ),
)


def upgrade() -> None:
    for key, value, category, description, lo, hi, default in SEEDS:
        op.execute(f"""
            INSERT INTO atlas.atlas_thresholds (
                threshold_key, threshold_value, category, description,
                min_allowed, max_allowed, default_value,
                last_modified_by, is_active
            )
            VALUES (
                '{key}', {value}, '{category}', '{description}',
                {lo}, {hi}, {default},
                'migration_095', TRUE
            )
            ON CONFLICT (threshold_key) DO NOTHING
        """)  # noqa: S608 -- key/category/description are string literals from SEEDS above, not user input


def downgrade() -> None:
    keys = ", ".join(f"'{row[0]}'" for row in SEEDS)
    op.execute(
        f"DELETE FROM atlas.atlas_thresholds WHERE threshold_key IN ({keys})"  # noqa: S608 -- keys are string literals from SEEDS, not user input
    )
