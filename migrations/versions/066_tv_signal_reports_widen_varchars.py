"""tv_signal_reports: widen conviction_trend, macd_signal, severity varchar columns

conviction_trend VARCHAR(10) overflows 'industry_grade' (14 chars).
macd_signal VARCHAR(10) is right at limit — widen for safety.
severity VARCHAR(10) is fine but widen consistently.

Revision ID: 066
Revises: 065
Create Date: 2026-05-14
"""

from alembic import op

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tv_signal_reports ALTER COLUMN conviction_trend TYPE VARCHAR(50)")
    op.execute("ALTER TABLE tv_signal_reports ALTER COLUMN macd_signal TYPE VARCHAR(30)")
    op.execute("ALTER TABLE atlas_signal_alerts ALTER COLUMN severity TYPE VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE tv_signal_reports ALTER COLUMN conviction_trend TYPE VARCHAR(10)")
    op.execute("ALTER TABLE tv_signal_reports ALTER COLUMN macd_signal TYPE VARCHAR(10)")
    op.execute("ALTER TABLE atlas_signal_alerts ALTER COLUMN severity TYPE VARCHAR(10)")
