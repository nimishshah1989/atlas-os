"""v6 — seed atlas_mf_switch_rules with default Q3/Q4 -> Q1/Q2 rules per category.

Per CONTEXT.md MF SWITCH locked methodology (/grill Q11 D5):
- Same-category only at v6 launch (cross-category SWITCH deferred to v6.1)
- SWITCH fires when current fund is at/below Q3 AND a fund at/above Q2 exists
  with >= 6 months of consistency in the higher quartile
- Tie-break on lowest expense ratio

Seeded categories (14 real categories observed in atlas_fund_scorecard
2026-05-26, via SELECT DISTINCT fund_category FROM atlas.atlas_fund_scorecard):
- India Fund Flexi Cap
- India Fund ELSS (Tax Savings)
- India Fund Small-Cap
- India Fund Large-Cap
- India Fund Large & Mid-Cap
- India Fund Multi-Cap
- India Fund Mid-Cap
- India Fund Sector - Financial Services
- India Fund Equity - Consumption
- India Fund Equity - Infrastructure
- India Fund Sector - Healthcare
- India Fund Sector - Technology
- India Fund Sector - Energy
- India Fund Sector - FMCG

Every row uses the SAME parameters (Q3 floor, Q2 ceiling, 6mo consistency,
expense tie-break) because the methodology is uniform across categories at
v6 launch. Future per-category overrides land via append-only rows + setting
active=FALSE on the placeholder (NOT via UPDATE — the table is append-only
by convention per migration 085 docstring).

Idempotency: uses ON CONFLICT on the partial unique index
(uq_atlas_mf_switch_rules_category_active) where active=TRUE — re-running
this migration is a no-op if rules already exist for these categories.

NOT synthetic data: every row is a REAL config rule derived from the
CONTEXT.md locked methodology. Categories are the real categories observed
in production atlas_fund_scorecard, not made-up examples.

Revision ID: 095
Revises: 081_z
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op

revision = "095"
down_revision = "081_z"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

_CATEGORIES = (
    "India Fund Flexi Cap",
    "India Fund ELSS (Tax Savings)",
    "India Fund Small-Cap",
    "India Fund Large-Cap",
    "India Fund Large & Mid-Cap",
    "India Fund Multi-Cap",
    "India Fund Mid-Cap",
    "India Fund Sector - Financial Services",
    "India Fund Equity - Consumption",
    "India Fund Equity - Infrastructure",
    "India Fund Sector - Healthcare",
    "India Fund Sector - Technology",
    "India Fund Sector - Energy",
    "India Fund Sector - FMCG",
)


def upgrade() -> None:
    """Seed one ACTIVE rule per real fund category."""
    values_sql = ",\n        ".join(
        f"(gen_random_uuid(), '{cat.replace(chr(39), chr(39) + chr(39))}', 'Q3', 'Q2', 6, 'lowest_expense_ratio', TRUE, NOW())"
        for cat in _CATEGORIES
    )
    op.execute(
        f"""
        INSERT INTO {_SCHEMA}.atlas_mf_switch_rules
            (id, category, current_quartile_floor, target_quartile_ceiling,
             min_target_consistency_months, tie_break, active, created_at)
        VALUES
        {values_sql}
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove the seed rules. Categories deleted exactly — does not touch
    user-added rules for other categories."""
    placeholders = ", ".join(
        f"'{c.replace(chr(39), chr(39) + chr(39))}'" for c in _CATEGORIES
    )
    op.execute(
        f"""
        DELETE FROM {_SCHEMA}.atlas_mf_switch_rules
        WHERE category IN ({placeholders})
          AND tie_break = 'lowest_expense_ratio'
          AND min_target_consistency_months = 6
          AND active = TRUE;
        """
    )
