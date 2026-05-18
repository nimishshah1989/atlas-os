"""Migration 080 — v6 prerequisite tables.

These are integration tests that require a Postgres database whose URL
is supplied via ATLAS_TEST_DB_URL. When the env var is absent, tests skip
with a clear reason; the migration file itself is still authored and
applied to real databases via operator runbooks.
"""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.skipif(
    not os.environ.get("ATLAS_TEST_DB_URL"),
    reason="ATLAS_TEST_DB_URL not set — migration integration tests skipped",
)


@pytest.fixture
def alembic_config():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["ATLAS_TEST_DB_URL"])
    return cfg


def test_migration_080_creates_all_eight_tables(alembic_config):
    """All eight v6 prereq tables exist after upgrade to 080."""
    command.upgrade(alembic_config, "080")
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    insp = inspect(eng)
    tables = set(insp.get_table_names(schema="atlas"))
    expected = {
        "atlas_index_membership",
        "atlas_factor_returns_daily",
        "atlas_macro_daily",
        "atlas_governance_master",
        "atlas_governance_daily",
        "atlas_v6_strategy_runs",
        "atlas_v6_exclusions_log",
        "atlas_v6_recommendations_daily",
    }
    assert expected.issubset(tables), f"Missing: {expected - tables}"


def test_migration_080_downgrade_drops_all(alembic_config):
    """Downgrade to 079 drops every table 080 created."""
    command.upgrade(alembic_config, "080")
    command.downgrade(alembic_config, "079")
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    insp = inspect(eng)
    tables = set(insp.get_table_names(schema="atlas"))
    must_not_exist = {
        "atlas_index_membership",
        "atlas_factor_returns_daily",
        "atlas_macro_daily",
        "atlas_governance_master",
        "atlas_governance_daily",
        "atlas_v6_strategy_runs",
        "atlas_v6_exclusions_log",
        "atlas_v6_recommendations_daily",
    }
    assert must_not_exist.isdisjoint(tables), f"Still present: {must_not_exist & tables}"


def test_migration_080_indexes_present(alembic_config):
    """Critical PIT lookup indexes exist."""
    command.upgrade(alembic_config, "080")
    eng = create_engine(os.environ["ATLAS_TEST_DB_URL"])
    with eng.connect() as c:
        rows = c.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname='atlas' AND tablename='atlas_index_membership'"
            )
        ).fetchall()
    names = {r.indexname for r in rows}
    assert "ix_atlas_index_membership_lookup" in names
