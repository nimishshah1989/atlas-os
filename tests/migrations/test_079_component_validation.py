"""Regression test for migration 079 — atlas_component_validation table.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verifies that migration 079:
1. Creates atlas.atlas_component_validation with the correct columns.
2. Enforces the status CHECK constraint (rejects invalid values).
3. Enforces the composite PK (component_name, badge, horizon_days, as_of_date).

Skipped by default; run after migration 079 is applied.
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

_TABLE = "atlas.atlas_component_validation"
_VALID_ROW = {
    "component_name": "rs_rank_12m",
    "badge": "Leader",
    "threshold_range": "rs_rank_12m >= 0.90",
    "implied_action": "favours_long",
    "horizon_days": 63,
    "as_of_date": "2024-01-01",
    "mean_ic": 0.05,
    "ic_std": 0.12,
    "ic_t_stat": 2.10,
    "ic_ir": 0.42,
    "q5_q1_spread": 0.003,
    "n_observations": 120,
    "status": "validated",
}


@_SKIP_INTEGRATION
def test_table_exists(db_engine: sa.Engine) -> None:
    """atlas_component_validation table exists in atlas schema after migration 079."""
    with db_engine.connect() as c:
        result = c.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM information_schema.tables
                WHERE table_schema = 'atlas'
                  AND table_name = 'atlas_component_validation'
            """)
        ).fetchone()
    assert result is not None
    assert result.cnt == 1, "atlas_component_validation table not found in atlas schema"


@_SKIP_INTEGRATION
def test_can_insert_valid_row(db_engine: sa.Engine) -> None:
    """A row with a valid status value inserts and can be read back."""
    with db_engine.begin() as c:
        c.execute(
            text("""
                INSERT INTO atlas.atlas_component_validation
                    (component_name, badge, threshold_range, implied_action,
                     horizon_days, as_of_date, mean_ic, ic_std, ic_t_stat,
                     ic_ir, q5_q1_spread, n_observations, status)
                VALUES
                    (:component_name, :badge, :threshold_range, :implied_action,
                     :horizon_days, :as_of_date, :mean_ic, :ic_std, :ic_t_stat,
                     :ic_ir, :q5_q1_spread, :n_observations, :status)
                ON CONFLICT (component_name, badge, horizon_days, as_of_date)
                DO UPDATE SET status = EXCLUDED.status
            """),
            _VALID_ROW,
        )
    with db_engine.connect() as c:
        row = c.execute(
            text("""
                SELECT status, ic_ir FROM atlas.atlas_component_validation
                WHERE component_name = 'rs_rank_12m'
                  AND badge = 'Leader'
                  AND horizon_days = 63
                  AND as_of_date = '2024-01-01'
            """)
        ).fetchone()
    assert row is not None
    assert row.status == "validated"
    assert abs(float(row.ic_ir) - 0.42) < 1e-4


@_SKIP_INTEGRATION
def test_status_check_rejects_invalid(db_engine: sa.Engine) -> None:
    """status CHECK constraint rejects values outside the allowed set."""
    with pytest.raises(Exception) as exc_info:
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_component_validation
                        (component_name, badge, threshold_range, implied_action,
                         horizon_days, as_of_date, status)
                    VALUES
                        ('rs_rank_12m', 'BadBadge', 'x', 'favours_long',
                         63, '2024-01-02', 'INVALID_STATUS')
                """)
            )
    # PostgreSQL raises IntegrityError or similar for CHECK violations.
    assert (
        "ck_component_validation_status" in str(exc_info.value)
        or "check" in str(exc_info.value).lower()
    )


@_SKIP_INTEGRATION
def test_primary_key_upsert(db_engine: sa.Engine) -> None:
    """Upserting on the same PK updates the status rather than inserting a duplicate."""
    with db_engine.begin() as c:
        c.execute(
            text("""
                INSERT INTO atlas.atlas_component_validation
                    (component_name, badge, threshold_range, implied_action,
                     horizon_days, as_of_date, status)
                VALUES
                    ('rs_rank_12m', 'Laggard', 'rs_rank_12m < 0.10',
                     'warns_long', 63, '2024-01-03', 'decorative')
                ON CONFLICT (component_name, badge, horizon_days, as_of_date)
                DO UPDATE SET status = EXCLUDED.status
            """)
        )
    with db_engine.begin() as c:
        c.execute(
            text("""
                INSERT INTO atlas.atlas_component_validation
                    (component_name, badge, threshold_range, implied_action,
                     horizon_days, as_of_date, status)
                VALUES
                    ('rs_rank_12m', 'Laggard', 'rs_rank_12m < 0.10',
                     'warns_long', 63, '2024-01-03', 'weak')
                ON CONFLICT (component_name, badge, horizon_days, as_of_date)
                DO UPDATE SET status = EXCLUDED.status
            """)
        )
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT COUNT(*) AS cnt, MAX(status) AS latest_status
                FROM atlas.atlas_component_validation
                WHERE component_name = 'rs_rank_12m'
                  AND badge = 'Laggard'
                  AND horizon_days = 63
                  AND as_of_date = '2024-01-03'
            """)
        ).fetchone()
    assert rows is not None
    assert rows.cnt == 1, "upsert created duplicate PK rows"
    assert rows.latest_status == "weak"
