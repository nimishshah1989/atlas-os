"""create strategy_optimization_runs + optuna schema

Revision ID: 019
Revises: 018
Create Date: 2026-05-08 00:00:00.000000

Creates the optuna schema (for Optuna RDB backend) and
strategy_optimization_runs for FM threshold promotion workflow.
approved_by stores Supabase auth.uid() — enforced in API layer.
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS optuna"))
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_optimization_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regime TEXT NOT NULL,
            archetype TEXT NOT NULL,
            study_name TEXT NOT NULL,
            best_params JSONB NOT NULL,
            param_importances JSONB,
            oos_sharpe NUMERIC(10,4) NOT NULL,
            oos_alpha_vs_nifty500 NUMERIC(10,4),
            walk_forward_windows INT NOT NULL,
            trial_count INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT,
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_optim_status
            ON atlas.strategy_optimization_runs(status, created_at DESC);
        CREATE INDEX idx_optim_regime_archetype
            ON atlas.strategy_optimization_runs(regime, archetype, created_at DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_optimization_runs"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS optuna CASCADE"))
