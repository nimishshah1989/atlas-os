"""Alembic environment.

Reads the DB URL from the same source application code uses
(``atlas.config.Config.DB_URL``) so dev/staging/prod can never disagree about
which database migrations target.

Migrations live in ``migrations/versions/`` and are numbered ``001_*`` through
``010_*`` per ``ATLAS_M1_SCHEMA_AND_REFERENCE.md``. Use linear (not branching)
revision history.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from atlas.config import Config as AtlasConfig

# Alembic Config object
config = context.config

# Override the URL from atlas config (single source of truth).
# configparser uses '%' for variable interpolation, so URL-encoded chars
# like '%40' break it — escape '%' to '%%' before storing. configparser
# returns the unescaped value via .get(), so SQLAlchemy + psycopg2 see
# the original URL.
_db_url = AtlasConfig.assert_db_url().replace("%", "%%")
config.set_main_option("sqlalchemy.url", _db_url)

# Logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We don't use Alembic autogenerate (schema is hand-written per
# 02_DATABASE_SCHEMA.md). Set ``target_metadata = None``.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="atlas_alembic_version",
        version_table_schema=AtlasConfig.SCHEMA_NAME,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Ensure the atlas schema exists before alembic tries to write its
        # version table to atlas.atlas_alembic_version. Migration 001 also
        # creates this schema, but alembic needs it to record version state.
        from sqlalchemy import text

        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {AtlasConfig.SCHEMA_NAME}"))
        connection.commit()

        context.configure(
            connection=connection,
            version_table="atlas_alembic_version",
            version_table_schema=AtlasConfig.SCHEMA_NAME,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
