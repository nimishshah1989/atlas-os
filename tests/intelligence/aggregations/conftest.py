"""Conftest for tests/intelligence/aggregations/.

Provides a ``test_engine`` fixture backed by ATLAS_DB_URL.
Integration tests are skipped unless ``ATLAS_INTEGRATION_TESTS=1`` is set,
consistent with the tests/migrations/ convention.

The ``test_engine`` fixture yields the shared engine. Persistence tests
that write rows must DELETE them in teardown (via pytest fixture teardown or
within the test body). The persistence functions use engine.begin() which
auto-commits, so SAVEPOINT-based rollback cannot intercept them without
rewriting the production functions.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv

    load_dotenv(_ENV_FILE, override=False)


@pytest.fixture(scope="session")
def db_engine() -> sa.Engine:
    url = os.environ["ATLAS_DB_URL"]
    return sa.create_engine(url, pool_pre_ping=True)


@pytest.fixture()
def test_engine(db_engine: sa.Engine) -> sa.Engine:  # type: ignore[misc]
    """Engine for persistence integration tests.

    Yields the shared engine. Tests are responsible for cleaning up any rows
    they insert — the fixture does not wrap in a transaction because the
    persistence functions call engine.begin() directly (auto-commit).
    """
    yield db_engine
