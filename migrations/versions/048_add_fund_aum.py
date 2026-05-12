"""Add aum_cr to atlas_universe_funds for AMFI monthly AUM data."""
from alembic import op
import sqlalchemy as sa

revision = '048'
down_revision = '047'


def upgrade() -> None:
    op.add_column(
        'atlas_universe_funds',
        sa.Column('aum_cr', sa.Numeric(precision=12, scale=2), nullable=True),
        schema='atlas',
    )
    op.add_column(
        'atlas_universe_funds',
        sa.Column('aum_as_of', sa.Date(), nullable=True),
        schema='atlas',
    )
    op.execute(
        "COMMENT ON COLUMN atlas.atlas_universe_funds.aum_cr IS "
        "'Monthly average AUM in Indian Rupees crore, sourced from AMFI'"
    )


def downgrade() -> None:
    op.drop_column('atlas_universe_funds', 'aum_as_of', schema='atlas')
    op.drop_column('atlas_universe_funds', 'aum_cr', schema='atlas')
