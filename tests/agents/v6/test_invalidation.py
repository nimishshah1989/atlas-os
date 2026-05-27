"""Tests for ``atlas.agents.v6.brief_generator.invalidate_briefs_on_corp_action``.

Coverage:
* Allowlisted corp-action types trigger an UPDATE.
* Non-allowlisted types short-circuit and write nothing.
* Missing instrument_id raises ValueError.
* The UPDATE row count is propagated as the return value.
* The corp_action_id (when present) appears in the bind params.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from atlas.agents.v6.brief_generator import (
    _INVALIDATING_CORP_ACTION_TYPES,
    invalidate_briefs_on_corp_action,
)

INSTRUMENT_ID = UUID("00000000-0000-4000-8000-000000000456")
CORP_ACTION_ID = UUID("00000000-0000-4000-8000-000000000aaa")


def _engine_with_rowcount(n: int) -> MagicMock:
    """Build a MagicMock engine whose `.begin() → connection.execute()` returns rowcount=n."""
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    result = MagicMock()
    result.rowcount = n
    conn.execute.return_value = result
    return engine


# ---------------------------------------------------------------------------
# Allowlist coverage
# ---------------------------------------------------------------------------


def test_invalidating_allowlist_size_matches_spec() -> None:
    """The 10 corp-action types per CONTEXT.md."""
    assert len(_INVALIDATING_CORP_ACTION_TYPES) == 10


@pytest.mark.parametrize("event_type", sorted(_INVALIDATING_CORP_ACTION_TYPES))
def test_allowlisted_corp_action_runs_update(event_type: str) -> None:
    """Every allowlisted type triggers the UPDATE."""
    engine = _engine_with_rowcount(3)
    n = invalidate_briefs_on_corp_action(
        engine,
        {
            "id": CORP_ACTION_ID,
            "instrument_id": INSTRUMENT_ID,
            "event_type": event_type,
        },
    )
    assert n == 3
    engine.begin.assert_called_once()


@pytest.mark.parametrize(
    "event_type",
    ["stock_split", "bonus_issue", "regular_dividend", "face_value_change", ""],
)
def test_non_allowlisted_corp_action_no_op(event_type: str) -> None:
    """Non-allowlisted corp actions short-circuit and write nothing."""
    engine = MagicMock()
    n = invalidate_briefs_on_corp_action(
        engine,
        {
            "id": CORP_ACTION_ID,
            "instrument_id": INSTRUMENT_ID,
            "event_type": event_type,
        },
    )
    assert n == 0
    engine.begin.assert_not_called()


def test_missing_instrument_id_raises() -> None:
    """A corp_action without instrument_id is a programming bug."""
    engine = MagicMock()
    with pytest.raises(ValueError, match="instrument_id is required"):
        invalidate_briefs_on_corp_action(
            engine,
            {
                "id": CORP_ACTION_ID,
                "instrument_id": None,
                "event_type": "merger",
            },
        )


def test_missing_event_type_is_treated_as_non_allowlisted() -> None:
    """No event_type → no invalidation (graceful)."""
    engine = MagicMock()
    n = invalidate_briefs_on_corp_action(
        engine,
        {
            "id": CORP_ACTION_ID,
            "instrument_id": INSTRUMENT_ID,
            "event_type": None,
        },
    )
    assert n == 0


def test_returns_zero_when_no_rows_match() -> None:
    """No active signal_calls match → rowcount 0."""
    engine = _engine_with_rowcount(0)
    n = invalidate_briefs_on_corp_action(
        engine,
        {
            "id": CORP_ACTION_ID,
            "instrument_id": INSTRUMENT_ID,
            "event_type": "merger",
        },
    )
    assert n == 0


# ---------------------------------------------------------------------------
# Bind-params content
# ---------------------------------------------------------------------------


def test_update_binds_instrument_id_and_corp_action_id() -> None:
    engine = _engine_with_rowcount(1)
    fixed_now = datetime(2026, 5, 24, 9, 0, 0, tzinfo=UTC)
    invalidate_briefs_on_corp_action(
        engine,
        {
            "id": CORP_ACTION_ID,
            "instrument_id": INSTRUMENT_ID,
            "event_type": "merger",
        },
        now=fixed_now,
    )
    conn = engine.begin.return_value.__enter__.return_value
    args, _kwargs = conn.execute.call_args
    bind_params = args[1]
    assert bind_params["instrument_id"] == INSTRUMENT_ID
    assert bind_params["corp_action_id"] == CORP_ACTION_ID
    assert bind_params["invalidated_at"] == fixed_now


def test_corp_action_without_id_still_invalidates_with_null_fk() -> None:
    """The id field is optional; we still update with NULL FK."""
    engine = _engine_with_rowcount(2)
    n = invalidate_briefs_on_corp_action(
        engine,
        {
            "instrument_id": INSTRUMENT_ID,
            "event_type": "spin_off",
        },
    )
    assert n == 2
    conn = engine.begin.return_value.__enter__.return_value
    args, _ = conn.execute.call_args
    assert args[1]["corp_action_id"] is None
