"""Conftest for tests/migrations/.

Provides a `db_engine` fixture backed by ATLAS_DB_URL.
All tests in this directory are skipped when ATLAS_INTEGRATION_TESTS is unset
so that CI on Mac (where psycopg2 may lack SSL) does not fail.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

# Load .env from repo root so ATLAS_DB_URL is available when running locally.
_REPO_ROOT = Path(__file__).parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv

    load_dotenv(_ENV_FILE, override=False)

_SKIP = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


@pytest.fixture(scope="session")
def db_engine() -> sa.Engine:
    url = os.environ["ATLAS_DB_URL"]
    return sa.create_engine(url, pool_pre_ping=True)
