"""Regression test for migration 076 — seed initial state thresholds.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verifies that migration 076 seeds >= 18 active threshold rows and spot-checks
five specific (threshold_name, state_or_gate) -> value mappings that are
load-bearing for the Phase-1 state classifier.
Skipped by default; run after migration 076 is applied.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy import text

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


@_SKIP_INTEGRATION
def test_initial_thresholds_seeded(db_engine: sa.Engine) -> None:
    """Migration 076 seeds at least 18 active threshold rows; spot-check known values."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT threshold_name, state_or_gate, threshold_value
                FROM atlas.atlas_state_thresholds
                WHERE active = TRUE
                ORDER BY state_or_gate, threshold_name
            """)
        ).fetchall()
    assert len(rows) >= 18, f"expected >= 18 active rows, got {len(rows)}"
    expected = {
        ("theta_rs", "stage_2a"): 70.0,
        ("theta_vol_mult", "stage_2a"): 1.5,
        ("theta_fresh_days", "stage_2a"): 21,
        ("theta_confirmed_days", "stage_2b"): 126,
        ("theta_distribution", "stage_3"): 5,
    }
    actual = {(r.threshold_name, r.state_or_gate): float(r.threshold_value) for r in rows}
    for key, val in expected.items():
        assert key in actual, f"missing threshold: {key}"
        assert abs(actual[key] - val) < 1e-6, f"{key}: expected {val}, got {actual[key]}"


@_SKIP_INTEGRATION
def test_thresholds_all_distinct_name_state(db_engine: sa.Engine) -> None:
    """Each (threshold_name, state_or_gate) pair appears exactly once with active=TRUE.

    The partial unique index uq_state_thresholds_active enforces this at the DB
    level; this test confirms the seed didn't violate it.
    """
    with db_engine.connect() as c:
        dups = c.execute(
            text("""
                SELECT threshold_name, state_or_gate, COUNT(*) AS cnt
                FROM atlas.atlas_state_thresholds
                WHERE active = TRUE
                GROUP BY threshold_name, state_or_gate
                HAVING COUNT(*) > 1
            """)
        ).fetchall()
    assert len(dups) == 0, f"duplicate active rows found: {dups}"


@_SKIP_INTEGRATION
def test_thresholds_cover_all_states(db_engine: sa.Engine) -> None:
    """Active thresholds cover all seven stage states + uninvestable + risk_gate."""
    with db_engine.connect() as c:
        states = {
            row[0]
            for row in c.execute(
                text("""
                    SELECT DISTINCT state_or_gate
                    FROM atlas.atlas_state_thresholds
                    WHERE active = TRUE
                """)
            ).fetchall()
        }
    required_states = {
        "uninvestable",
        "stage_1",
        "stage_2a",
        "stage_2b",
        "stage_2c",
        "stage_3",
        "stage_4",
        "risk_gate",
    }
    missing = required_states - states
    assert not missing, f"states with no active threshold rows: {missing}"
