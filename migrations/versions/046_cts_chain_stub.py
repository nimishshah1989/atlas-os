"""Stub for CTS chain revision 046.

This revision was applied to the database as part of the CTS milestone branch
but the migration file was not retained in git. The stub exists solely to allow
alembic to build a complete revision map (044 → 045 → 046 → 047 → 048).
No schema change is performed by upgrade() or downgrade().

Revision ID: 046
Revises: 045
Create Date: 2026-05-12
"""

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
