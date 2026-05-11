"""SP01: create atlas_signal_ic for storing rolling IC measurements.

One row per (signal_name, timeframe, forward_period_days, rolling_window,
as_of_date). Rolling-window-end-date is the natural key — every window has
its own row, so the time series of IC over time is reconstructible.

Revision ID: 033
Revises: 032
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_signal_ic (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            signal_name             VARCHAR(64) NOT NULL,
            timeframe               VARCHAR(16) NOT NULL,
            forward_period_days     INTEGER     NOT NULL,
            rolling_window          VARCHAR(8)  NOT NULL,
            as_of_date              DATE        NOT NULL,

            n_observations          INTEGER     NOT NULL,
            mean_ic                 NUMERIC(10, 6),
            ic_std                  NUMERIC(10, 6),
            ic_t_stat               NUMERIC(10, 4),
            ic_ir                   NUMERIC(10, 4),
            quantile_spread_ann     NUMERIC(10, 4),
            turnover_monthly        NUMERIC(10, 4),

            computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_signal_ic_run UNIQUE (
                signal_name, timeframe, forward_period_days,
                rolling_window, as_of_date
            ),
            CONSTRAINT chk_signal_ic_period CHECK (forward_period_days > 0),
            CONSTRAINT chk_signal_ic_n_obs CHECK (n_observations >= 0)
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_signal_ic_signal_date
        ON atlas.atlas_signal_ic (signal_name, as_of_date DESC)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_signal_ic_signal_date"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_signal_ic"))
