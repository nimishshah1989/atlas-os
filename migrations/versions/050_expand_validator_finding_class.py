"""Add frontend_diff and frontend_extract_error to finding_class CHECK constraint.

Phase C Route Crawler produces two new finding classes:
  frontend_diff        — frontend value differs from SQL source beyond tolerance
  frontend_extract_error — DOM value could not be parsed to Decimal

The migration is idempotent: it drops the old constraint if present and
recreates it with the expanded allowlist. Safe to re-run.

Revision ID: 050
Revises: 049
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old constraint (IF EXISTS — idempotent on re-run)
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_validator_findings
        DROP CONSTRAINT IF EXISTS chk_finding_class
    """))

    # Re-add with expanded allowlist
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_validator_findings
        ADD CONSTRAINT chk_finding_class
        CHECK (finding_class IN (
            'data_gap',
            'inconsistency',
            'calc_error',
            'accuracy_error',
            'insensible_value',
            'incomplete_data',
            'frontend_diff',
            'frontend_extract_error'
        ))
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_validator_findings
        DROP CONSTRAINT IF EXISTS chk_finding_class
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_validator_findings
        ADD CONSTRAINT chk_finding_class
        CHECK (finding_class IN (
            'data_gap',
            'inconsistency',
            'calc_error',
            'accuracy_error',
            'insensible_value',
            'incomplete_data'
        ))
    """))
