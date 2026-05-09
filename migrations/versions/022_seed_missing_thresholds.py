"""seed missing methodology thresholds

Revision ID: 022
Revises: 021
Create Date: 2026-05-09 04:45:00.000000

Pull hardcoded constants out of compute modules and into atlas_thresholds.
This keeps the 'thresholds live in DB' invariant complete and unlocks
runtime tuning without a redeploy.

Idempotent — uses INSERT ... ON CONFLICT DO NOTHING so re-applying is safe.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


# (key, value, category, description, methodology_section, units, min, max, default)
SEEDS: tuple[tuple[str, float, str, str, str, str, float, float, float], ...] = (
    (
        "sector_rs_quintile_top_pct",
        80.0,
        "sector",
        "Top cross-sector RS percentile cutoff for sector_state = Overweight",
        "10.5",
        "pct",
        50.0, 95.0, 80.0,
    ),
    (
        "sector_rs_quintile_bottom_pct",
        20.0,
        "sector",
        "Bottom cross-sector RS percentile cutoff for sector_state = Avoid",
        "10.5",
        "pct",
        5.0, 50.0, 20.0,
    ),
    (
        "etf_rs_strong_pct",
        5.0,
        "etf",
        "ETF rs_3m_benchmark cutoff (in pct) above which etf rs_state becomes Strong",
        "13.5",
        "pct",
        1.0, 20.0, 5.0,
    ),
)


def upgrade() -> None:
    for key, value, category, desc, section, units, lo, hi, default in SEEDS:
        op.execute(sa.text(f"""
            INSERT INTO atlas.atlas_thresholds (
                threshold_key, threshold_value, category, description,
                methodology_section, units, min_allowed, max_allowed,
                default_value, last_modified_by, is_active
            )
            VALUES (
                '{key}', {value}, '{category}', '{desc.replace("'", "''")}',
                '{section}', '{units}', {lo}, {hi}, {default},
                'migration_022', TRUE
            )
            ON CONFLICT (threshold_key) DO NOTHING
        """))


def downgrade() -> None:
    keys = ", ".join(f"'{s[0]}'" for s in SEEDS)
    op.execute(sa.text(
        f"DELETE FROM atlas.atlas_thresholds WHERE threshold_key IN ({keys})"
    ))
