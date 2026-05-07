"""grant role permissions (Supabase-adapted)

Revision ID: 010
Revises: 009
Create Date: 2026-05-06 00:00:09.000000

Role + permission setup per ``docs/01_BACKEND_ARCHITECTURE.md`` Section 2.3
and ``prds/00_INFRA_DECISIONS.md`` Section 1.3.

**Supabase note:** Supabase already provisions a set of roles (``postgres``,
``authenticator``, ``anon``, ``authenticated``, ``service_role``,
``supabase_admin``, etc.). Atlas adds three application-level roles that
compute pipelines connect as directly. They are independent of Supabase Auth
and bypass RLS — appropriate for server-side compute, not browser users.

Passwords are NOT set in this migration. Use Supabase's SQL editor or the
``ALTER ROLE ... PASSWORD`` command to set them after the migration runs.
Storing the connection strings in ``ATLAS_DB_URL`` (per architecture 2.4)
removes the password from migration history.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def _create_role_if_missing(role: str) -> None:
    """Create a Postgres role idempotently. NOLOGIN by default — caller
    sets a password + LOGIN attribute via ``ALTER ROLE`` after migration."""
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'CREATE ROLE {role} NOLOGIN';
            END IF;
        END $$;
    """))


def upgrade() -> None:
    # ---- Create roles ----
    _create_role_if_missing("atlas_writer")
    _create_role_if_missing("atlas_reader")
    _create_role_if_missing("atlas_admin")

    # ---- atlas_writer: compute pipelines ----
    op.execute(sa.text("GRANT USAGE ON SCHEMA atlas TO atlas_writer"))
    op.execute(sa.text(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA atlas TO atlas_writer"
    ))
    op.execute(sa.text(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA atlas TO atlas_writer"
    ))
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA atlas "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO atlas_writer"
    ))
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA atlas "
        "GRANT USAGE, SELECT ON SEQUENCES TO atlas_writer"
    ))
    # Read-only access to JIP Data Core
    op.execute(sa.text("GRANT USAGE ON SCHEMA public TO atlas_writer"))
    op.execute(sa.text(
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_writer"
    ))
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT ON TABLES TO atlas_writer"
    ))

    # ---- atlas_reader: UI / FastAPI / ad-hoc ----
    op.execute(sa.text("GRANT USAGE ON SCHEMA atlas TO atlas_reader"))
    op.execute(sa.text(
        "GRANT SELECT ON ALL TABLES IN SCHEMA atlas TO atlas_reader"
    ))
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA atlas "
        "GRANT SELECT ON TABLES TO atlas_reader"
    ))
    # No SELECT on public.de_* — UI never queries Layer 1 directly per
    # architecture Section 2.3.

    # ---- atlas_admin: migrations, schema changes ----
    op.execute(sa.text("GRANT ALL ON SCHEMA atlas TO atlas_admin"))
    op.execute(sa.text("GRANT ALL ON ALL TABLES IN SCHEMA atlas TO atlas_admin"))
    op.execute(sa.text(
        "GRANT ALL ON ALL SEQUENCES IN SCHEMA atlas TO atlas_admin"
    ))
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA atlas "
        "GRANT ALL ON TABLES TO atlas_admin"
    ))
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA atlas "
        "GRANT ALL ON SEQUENCES TO atlas_admin"
    ))
    op.execute(sa.text("GRANT USAGE ON SCHEMA public TO atlas_admin"))
    op.execute(sa.text(
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_admin"
    ))


def downgrade() -> None:
    # Drop privileges first, then the roles. NOWAIT not needed for compute
    # accounts; if active connections exist, the migration fails clearly.
    for role in ("atlas_writer", "atlas_reader", "atlas_admin"):
        # Revoke is idempotent — Postgres ignores missing grants.
        op.execute(sa.text(
            f"REVOKE ALL ON ALL TABLES IN SCHEMA atlas FROM {role}"
        ))
        op.execute(sa.text(
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA atlas FROM {role}"
        ))
        op.execute(sa.text(f"REVOKE ALL ON SCHEMA atlas FROM {role}"))
        op.execute(sa.text(
            f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}"
        ))
        op.execute(sa.text(f"REVOKE ALL ON SCHEMA public FROM {role}"))
        op.execute(sa.text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA atlas REVOKE ALL ON TABLES FROM {role}"
        ))
        op.execute(sa.text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA atlas REVOKE ALL ON SEQUENCES FROM {role}"
        ))
        op.execute(sa.text(
            f"DO $$ BEGIN "
            f"  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"    EXECUTE 'DROP ROLE {role}'; "
            f"  END IF; "
            f"END $$;"
        ))
