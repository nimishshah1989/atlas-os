"""Add component_kind to atlas_component_validation.

Extends the component-validation table to distinguish IC-validated state-engine
tier rows from one-shot legacy-candidate rows produced by the ic_harness module.

Revision ID: 090_legacy_validation_kind
Revises: 089_aggregate_views_real
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "090_legacy_validation_kind"
down_revision = "089_aggregate_views_real"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "atlas_component_validation",
        sa.Column(
            "component_kind",
            sa.String(32),
            nullable=False,
            server_default="state_engine_tier",
        ),
        schema="atlas",
    )
    op.create_check_constraint(
        "ck_component_kind",
        "atlas_component_validation",
        "component_kind IN ('state_engine_tier','legacy_candidate')",
        schema="atlas",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_component_kind",
        "atlas_component_validation",
        type_="check",
        schema="atlas",
    )
    op.drop_column("atlas_component_validation", "component_kind", schema="atlas")
