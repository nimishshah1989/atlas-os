"""create cross-table foreign-key constraints

Revision ID: 009
Revises: 008
Create Date: 2026-05-06 00:00:08.000000

Foreign keys per ``docs/02_DATABASE_SCHEMA.md`` Section 8.1. Atlas uses FKs
conservatively — only on reference tables, never on Layer 3 metric/state/
decision tables (those would block daily writes during quarterly universe
refreshes).

Most CHECK constraints are baked into the table-creation migrations 002–007;
only the cross-table FKs and any constraints not enforceable at table-create
time live here.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _add_fk_if_missing(table: str, fk_name: str, ddl: str) -> None:
    """Idempotent FK add. Skips if a constraint with this name already exists."""
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema = 'atlas'
                  AND table_name = '{table}'
                  AND constraint_name = '{fk_name}'
            ) THEN
                EXECUTE $sql$ {ddl} $sql$;
            END IF;
        END $$;
    """))


def upgrade() -> None:
    # universe_funds.benchmark_code -> benchmark_master.benchmark_code
    _add_fk_if_missing(
        "atlas_universe_funds",
        "fk_universe_funds_benchmark",
        "ALTER TABLE atlas.atlas_universe_funds "
        "ADD CONSTRAINT fk_universe_funds_benchmark "
        "FOREIGN KEY (benchmark_code) "
        "REFERENCES atlas.atlas_benchmark_master(benchmark_code) "
        "DEFERRABLE INITIALLY DEFERRED",
    )

    # universe_etfs.linked_sector -> sector_master.sector_name
    _add_fk_if_missing(
        "atlas_universe_etfs",
        "fk_universe_etfs_linked_sector",
        "ALTER TABLE atlas.atlas_universe_etfs "
        "ADD CONSTRAINT fk_universe_etfs_linked_sector "
        "FOREIGN KEY (linked_sector) "
        "REFERENCES atlas.atlas_sector_master(sector_name) "
        "DEFERRABLE INITIALLY DEFERRED",
    )

    # universe_indices.linked_sector -> sector_master.sector_name
    _add_fk_if_missing(
        "atlas_universe_indices",
        "fk_universe_indices_linked_sector",
        "ALTER TABLE atlas.atlas_universe_indices "
        "ADD CONSTRAINT fk_universe_indices_linked_sector "
        "FOREIGN KEY (linked_sector) "
        "REFERENCES atlas.atlas_sector_master(sector_name) "
        "DEFERRABLE INITIALLY DEFERRED",
    )

    # validation_results.compute_run_id is already FK-enforced via the inline
    # REFERENCES in 007. fund_category_benchmark_map.benchmark_code is FK-
    # enforced via the inline REFERENCES in 003.


def downgrade() -> None:
    for table, name in (
        ("atlas_universe_funds", "fk_universe_funds_benchmark"),
        ("atlas_universe_etfs", "fk_universe_etfs_linked_sector"),
        ("atlas_universe_indices", "fk_universe_indices_linked_sector"),
    ):
        op.execute(sa.text(
            f"ALTER TABLE atlas.{table} DROP CONSTRAINT IF EXISTS {name}"
        ))
