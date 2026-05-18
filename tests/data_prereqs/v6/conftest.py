"""Shared fixtures for v6 data prereq tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def tmp_db_session():
    """Transactional SAVEPOINT — rolled back after each test.

    Skips when ATLAS_TEST_DB_URL is unset.
    """
    db_url = os.environ.get("ATLAS_TEST_DB_URL")
    if not db_url:
        pytest.skip("ATLAS_TEST_DB_URL not set — DB integration tests skipped")
    eng = create_engine(db_url)
    session_factory = sessionmaker(bind=eng)
    conn = eng.connect()
    trans = conn.begin()
    session = session_factory(bind=conn)
    yield session
    session.close()
    trans.rollback()
    conn.close()
