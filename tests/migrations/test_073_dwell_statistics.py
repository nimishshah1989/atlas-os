"""Regression test for migration 073 — atlas_state_dwell_statistics.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verifies the table and all required columns are present in the live DB.
Skipped by default; run on EC2 after migration is applied.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy import text

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


@_SKIP_INTEGRATION
def test_dwell_statistics_table_exists(db_engine: sa.Engine) -> None:
    """Migration 073 creates atlas_state_dwell_statistics with all required columns."""
    with db_engine.connect() as c:
        cols = c.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='atlas' AND table_name='atlas_state_dwell_statistics'"
            )
        ).fetchall()
    required = {
        "cohort_key",
        "state",
        "mean_dwell_days",
        "median_dwell_days",
        "p25_dwell_days",
        "p75_dwell_days",
        "p95_dwell_days",
        "n_observations",
        "as_of_date",
        "refreshed_at",
    }
    found = {r[0] for r in cols}
    assert required <= found, f"missing: {required - found}"
