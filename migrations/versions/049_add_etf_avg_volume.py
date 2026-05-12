"""Add avg_volume_20 to atlas_etf_metrics_daily."""
from alembic import op
import sqlalchemy as sa

revision = '049'
down_revision = '048'


def upgrade() -> None:
    op.add_column(
        'atlas_etf_metrics_daily',
        sa.Column('avg_volume_20', sa.Numeric(precision=20, scale=2), nullable=True),
        schema='atlas',
    )


def downgrade() -> None:
    op.drop_column('atlas_etf_metrics_daily', 'avg_volume_20', schema='atlas')
