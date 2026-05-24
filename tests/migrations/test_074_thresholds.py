"""Regression test for migration 074 — atlas_state_thresholds.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verifies the table, all required columns, and the partial unique index
on active=TRUE are present in the live DB.
Skipped by default; run on EC2 after migration is applied.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


@_SKIP_INTEGRATION
def test_thresholds_table_exists(db_engine: sa.Engine) -> None:
    """Migration 074 creates atlas_state_thresholds with all required columns."""
    with db_engine.connect() as c:
        cols = c.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='atlas' AND table_name='atlas_state_thresholds'"
            )
        ).fetchall()
    required = {
        "threshold_name",
        "state_or_gate",
        "threshold_value",
        "ic_at_threshold",
        "ic_ir_at_threshold",
        "q5_q1_spread",
        "as_of_date",
        "active",
        "tuned_at",
    }
    found = {r[0] for r in cols}
    missing = required - found
    assert not missing, f"missing columns: {missing}"


@_SKIP_INTEGRATION
def test_thresholds_active_unique_per_name_state(db_engine: sa.Engine) -> None:
    """Two rows with active=TRUE for the same (threshold_name, state_or_gate) must fail."""
    with pytest.raises(IntegrityError):
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_state_thresholds
                        (threshold_name, state_or_gate, threshold_value, as_of_date, active)
                    VALUES ('test_th', 'test_state', 1.0, :d1, TRUE),
                           ('test_th', 'test_state', 2.0, :d2, TRUE)
                """),
                {"d1": date(2026, 1, 1), "d2": date(2026, 2, 1)},
            )
    # Clean up any rows that landed before the constraint fired
    with db_engine.begin() as c:
        c.execute(text("DELETE FROM atlas.atlas_state_thresholds WHERE threshold_name='test_th'"))
