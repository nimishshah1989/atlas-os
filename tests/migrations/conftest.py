"""Conftest for tests/migrations/.

Provides a `db_engine` fixture backed by ATLAS_DB_URL.
Individual test modules declare their own ``_SKIP_INTEGRATION`` marker to gate
live-DB tests; set ``ATLAS_INTEGRATION_TESTS=1`` to enable them (EC2 only).
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


@pytest.fixture(scope="session")
def db_engine() -> sa.Engine:
    url = os.environ["ATLAS_DB_URL"]
    return sa.create_engine(url, pool_pre_ping=True)
