"""Regression test for migration 075 — atlas_state_action_log.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verifies the table, all required columns, and the CHECK constraint on
``action`` are present in the live DB after migration 075 is applied.
Skipped by default; run on EC2 after migration is applied.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


@_SKIP_INTEGRATION
def test_action_log_table_exists(db_engine: sa.Engine) -> None:
    """Migration 075 creates atlas_state_action_log with all required columns."""
    with db_engine.connect() as c:
        cols = c.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='atlas' AND table_name='atlas_state_action_log'
            """)
        ).fetchall()
    required = {
        "instrument_id",
        "date",
        "transition",
        "action",
        "suppressed_by",
        "position_size",
        "within_state_rank",
        "urgency_score",
        "created_at",
    }
    missing = required - {r[0] for r in cols}
    assert not missing, f"missing columns: {missing}"


@_SKIP_INTEGRATION
def test_action_log_rejects_invalid_action(db_engine: sa.Engine) -> None:
    """ck_action_value rejects values outside BUY/HOLD/TRIM/EXIT/WATCH/FORCE_EXIT."""
    iid = uuid.uuid4()
    with pytest.raises(IntegrityError, match="ck_action_value"):
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_state_action_log
                        (instrument_id, date, transition, action)
                    VALUES (:iid, :d, 'stage_1->stage_2a', 'bogus_action')
                """),
                {"iid": iid, "d": date(2026, 1, 1)},
            )
    # Cleanup in case the row somehow landed before the constraint fired
    with db_engine.begin() as c:
        c.execute(
            text("DELETE FROM atlas.atlas_state_action_log WHERE instrument_id = :iid"),
            {"iid": iid},
        )


@_SKIP_INTEGRATION
def test_action_log_accepts_valid_actions(db_engine: sa.Engine) -> None:
    """All six valid action values insert and clean up successfully."""
    valid_actions = ["BUY", "HOLD", "TRIM", "EXIT", "WATCH", "FORCE_EXIT"]
    inserted_ids = []
    with db_engine.begin() as c:
        for action in valid_actions:
            iid = uuid.uuid4()
            inserted_ids.append(iid)
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_state_action_log
                        (instrument_id, date, transition, action)
                    VALUES (:iid, :d, :tr, :action)
                """),
                {
                    "iid": iid,
                    "d": date(2026, 1, 1),
                    "tr": f"test->{action.lower()}",
                    "action": action,
                },
            )
    # Cleanup
    with db_engine.begin() as c:
        for iid in inserted_ids:
            c.execute(
                text("DELETE FROM atlas.atlas_state_action_log WHERE instrument_id = :iid"),
                {"iid": iid},
            )
