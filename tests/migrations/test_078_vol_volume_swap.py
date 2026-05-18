"""Regression test for migration 078 — IC-validated vol/volume swap.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verifies that migration 078 correctly:
1. Deactivates theta_low_vol (stage_1) and theta_vol_mult (stage_2a).
2. Inserts theta_contraction (stage_1, 0.95) as active.
3. Inserts theta_obv_slope_neg (stage_3, 0.0) as active.
4. Does not create duplicate active rows for any key.

Skipped by default; run after migration 078 is applied.
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
def test_theta_low_vol_deactivated(db_engine: sa.Engine) -> None:
    """theta_low_vol (stage_1) should have no active row after migration 078."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM atlas.atlas_state_thresholds
                WHERE threshold_name = 'theta_low_vol'
                  AND state_or_gate = 'stage_1'
                  AND active = TRUE
            """)
        ).fetchone()
    assert rows.cnt == 0, "theta_low_vol (stage_1) should be inactive after migration 078"


@_SKIP_INTEGRATION
def test_theta_vol_mult_deactivated(db_engine: sa.Engine) -> None:
    """theta_vol_mult (stage_2a) should have no active row after migration 078."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM atlas.atlas_state_thresholds
                WHERE threshold_name = 'theta_vol_mult'
                  AND state_or_gate = 'stage_2a'
                  AND active = TRUE
            """)
        ).fetchone()
    assert rows.cnt == 0, "theta_vol_mult (stage_2a) should be inactive after migration 078"


@_SKIP_INTEGRATION
def test_theta_contraction_inserted(db_engine: sa.Engine) -> None:
    """theta_contraction (stage_1) should be active with value 0.95 after migration 078."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT threshold_value
                FROM atlas.atlas_state_thresholds
                WHERE threshold_name = 'theta_contraction'
                  AND state_or_gate = 'stage_1'
                  AND active = TRUE
            """)
        ).fetchall()
    assert len(rows) == 1, "expected exactly 1 active theta_contraction row"
    assert (
        abs(float(rows[0].threshold_value) - 0.95) < 1e-6
    ), f"theta_contraction value should be 0.95, got {rows[0].threshold_value}"


@_SKIP_INTEGRATION
def test_theta_obv_slope_neg_inserted(db_engine: sa.Engine) -> None:
    """theta_obv_slope_neg (stage_3) should be active with value 0.0 after migration 078."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT threshold_value
                FROM atlas.atlas_state_thresholds
                WHERE threshold_name = 'theta_obv_slope_neg'
                  AND state_or_gate = 'stage_3'
                  AND active = TRUE
            """)
        ).fetchall()
    assert len(rows) == 1, "expected exactly 1 active theta_obv_slope_neg row"
    assert (
        abs(float(rows[0].threshold_value) - 0.0) < 1e-6
    ), f"theta_obv_slope_neg value should be 0.0, got {rows[0].threshold_value}"


@_SKIP_INTEGRATION
def test_no_duplicate_active_rows(db_engine: sa.Engine) -> None:
    """No (threshold_name, state_or_gate) pair should have more than one active row."""
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
    assert len(dups) == 0, f"duplicate active rows found after migration 078: {dups}"
