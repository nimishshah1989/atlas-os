"""baseline — the consolidated atlas_foundation schema (single-schema squash).

Replaces the 125-revision pre-consolidation chain, which had drifted from prod
(non-IMMUTABLE functional indexes, retired-subsystem migrations, schemas since
dropped) and no longer applied to a fresh DB. This baseline is a verbatim
``pg_dump --schema-only`` of the live prod schema, so ``alembic upgrade head`` on
an empty postgres reproduces exactly what runs in production.

Regenerate the SQL after a real schema change:
    pg_dump "$ATLAS_DB_URL" --schema=atlas_foundation --schema-only \
        --no-owner --no-privileges --no-tablespaces > migrations/baseline/atlas_foundation_schema.sql
(strip the psql preamble above the CREATE SCHEMA line; make it IF NOT EXISTS).
"""

from pathlib import Path

from alembic import op

revision = "0001_baseline_atlas_foundation"
down_revision = None
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[1] / "baseline" / "atlas_foundation_schema.sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_SQL.read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP SCHEMA IF EXISTS atlas_foundation CASCADE")
