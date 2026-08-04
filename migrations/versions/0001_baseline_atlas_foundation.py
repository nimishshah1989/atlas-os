"""baseline — the consolidated atlas_foundation schema (single-schema squash).

Replaces the 125-revision pre-consolidation chain, which had drifted from prod
(non-IMMUTABLE functional indexes, retired-subsystem migrations, schemas since
dropped) and no longer applied to a fresh DB. This baseline is a verbatim
``pg_dump --schema-only`` of the live prod schema, so ``alembic upgrade head`` on
an empty postgres reproduces exactly what runs in production.

Re-squashed 2026-08-04. The first dump (2026-07-29) carried 48 tables; prod had
since grown to 75 — the whole ``maal_*``, ``desk_*`` and ``portfolio_*`` subsystems
were created directly against prod and never captured here. Migration 0002
(crossover v2) then added a column to ``portfolio_trades``, a table the baseline
did not create, so "Migrations apply on a fresh DB" had been failing in CI. 0002 is
folded into this dump — prod already carries both of its objects — which is what a
squash baseline is for.

Prod is NOT alembic-tracked (there is no ``atlas_foundation.alembic_version``); the
schema is managed directly and this file exists so a FRESH database can reproduce
it. That is why re-dumping and dropping the intervening revision is safe: the only
consumers of this chain are CI and new local databases.

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
