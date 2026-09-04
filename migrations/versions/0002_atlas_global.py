"""atlas_global — the US-market schema (the second schema; ADR-0006).

The DDL files in ``scripts/global_market/ddl/`` are the source of truth — NOT this revision.
Prod DDL is managed directly (``scripts/global_market/apply_ddl.py``; prod carries no
alembic_version), exactly as India's ``0001_baseline_*`` documents for its own schema. This
revision exists so that CI's fresh-PG17 job ("Migrations apply on a fresh DB") proves the DDL
files apply on an empty database, in order, on the same major version prod runs — and so a
new local database reproduces both schemas with one ``alembic upgrade head``.

Every DDL file is idempotent (``CREATE … IF NOT EXISTS`` throughout, no ``DROP``), so running
it here and again through ``apply_ddl.py`` is safe. To add or change a table: edit the DDL
file (never this revision), re-apply it to prod with ``apply_ddl.py``, and CI re-proves the
edited file on the next push. Adding a further revision that touches atlas_global would
split the source of truth in two — don't.
"""

from pathlib import Path

from alembic import op

revision = "0002_atlas_global"
down_revision = "0001_baseline_atlas_foundation"
branch_labels = None
depends_on = None

# Same directory and glob that apply_ddl.py uses, so the two can never disagree on the set.
_DDL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "global_market" / "ddl"
_DDL_GLOB = "[0-9][0-9]_*.sql"


def upgrade() -> None:
    files = sorted(_DDL_DIR.glob(_DDL_GLOB))
    if not files:
        raise RuntimeError(f"no {_DDL_GLOB} files under {_DDL_DIR}")
    bind = op.get_bind()
    for path in files:
        sql = path.read_text()
        if "%" in sql:
            # exec_driver_sql hands psycopg2 an (empty) parameter mapping, so a bare '%'
            # anywhere in the text — even a comment — is parsed as a placeholder and fails
            # with an opaque TypeError. apply_ddl.py carries the same rule.
            raise RuntimeError(f"{path.name}: '%' is not allowed in DDL files; write 'percent'")
        bind.exec_driver_sql(sql)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP SCHEMA IF EXISTS atlas_global CASCADE")
