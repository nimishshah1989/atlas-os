"""Tests for atlas/trading/v6/governance.py.

Test strategy:
- Unit tests (no DB): test logic with mocked session returns
- Integration tests (DB): use tmp_db_session fixture (skipped if ATLAS_TEST_DB_URL unset)

Unit tests use a thin mock that replaces session.execute().fetchone()
and .fetchall() with controlled return values.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.trading.v6.governance import (
    apply_exclusions,
    is_excluded,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(fetchone_map: dict | None = None, fetchall_map: dict | None = None):
    """Build a mock SQLAlchemy session.

    fetchone_map: maps SQL snippet → row object (matched by substring).
    fetchall_map: maps SQL snippet → list of row objects.
    """
    session = MagicMock()
    execute_mock = MagicMock()
    session.execute.return_value = execute_mock

    def _fetchone():
        # Default: return None (fail-open)
        return None

    def _fetchall():
        return []

    execute_mock.fetchone.side_effect = _fetchone
    execute_mock.fetchall.side_effect = _fetchall
    return session


class _Row:
    """Simple row-like object for mocking DB results."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# is_excluded — pledge filter
# ---------------------------------------------------------------------------


def test_is_excluded_pledge_above_threshold_excludes():
    """pledge_ratio_pct > 30 → excluded with reason 'pledge'."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 1, 15)

    # First call = pledge query → pledge_ratio_pct = 35
    # Second call = fno_ban query (not reached if pledge fires first)
    pledge_result = MagicMock()
    pledge_result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("35.00"))

    insert_result = MagicMock()
    insert_result.fetchone.return_value = None

    call_count = [0]

    def execute_side_effect(sql, params=None):
        call_count[0] += 1
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str and ">" not in sql_str:
            # The SELECT for pledge (single instrument)
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("35.00"))
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is True
    assert reason == "pledge"


def test_is_excluded_pledge_below_threshold_not_excluded():
    """pledge_ratio_pct = 25 (below 30) → not excluded by pledge filter."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 1, 15)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str and "SELECT" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("25.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=False)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        elif "last_qualified_audit_date" in sql_str:
            result.fetchone.return_value = _Row(last_qualified_audit_date=date(2025, 6, 1))
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is False
    assert reason is None


def test_is_excluded_pledge_null_fails_open():
    """pledge_ratio_pct IS NULL → fail-open, not excluded."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 1, 15)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=None)
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=None)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        elif "last_qualified_audit_date" in sql_str:
            result.fetchone.return_value = _Row(last_qualified_audit_date=None)
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is False
    assert reason is None


def test_is_excluded_no_governance_row_fails_open():
    """No row in governance_daily → fail-open, not excluded."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 1, 15)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "atlas_governance_daily" in sql_str:
            result.fetchone.return_value = None  # No row at all
        elif "atlas_governance_master" in sql_str:
            result.fetchone.return_value = None
        elif "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is False
    assert reason is None


# ---------------------------------------------------------------------------
# is_excluded — fno_ban filter
# ---------------------------------------------------------------------------


def test_is_excluded_fno_ban_true_excludes():
    """in_fno_ban_list = true → excluded with reason 'fno_ban'."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 3, 10)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("10.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=True)
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is True
    assert reason == "fno_ban"


def test_is_excluded_fno_ban_false_not_excluded():
    """in_fno_ban_list = false → not excluded by fno_ban filter."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 3, 10)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("5.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=False)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        elif "last_qualified_audit_date" in sql_str:
            result.fetchone.return_value = _Row(last_qualified_audit_date=None)
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is False
    assert reason is None


# ---------------------------------------------------------------------------
# is_excluded — SME filter
# ---------------------------------------------------------------------------


def test_is_excluded_sme_tier_excludes():
    """tier = 'SME' → excluded with reason 'sme'."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 1, 15)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("5.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=False)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="SME")
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is True
    assert reason == "sme"


def test_is_excluded_sme_case_insensitive():
    """tier = 'sme' (lowercase) → still excluded (case insensitive check)."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 1, 15)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("5.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=False)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="sme")
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is True
    assert reason == "sme"


# ---------------------------------------------------------------------------
# is_excluded — audit_qualification filter
# ---------------------------------------------------------------------------


def test_is_excluded_audit_qualification_old_date_excludes():
    """last_qualified_audit_date > 365 days ago → excluded."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 5, 1)
    old_date = ref_date - timedelta(days=400)  # older than 365d

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("5.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=False)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        elif "last_qualified_audit_date" in sql_str:
            result.fetchone.return_value = _Row(last_qualified_audit_date=old_date)
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is True
    assert reason == "audit_qualification"


def test_is_excluded_audit_qualification_recent_date_not_excluded():
    """last_qualified_audit_date within 365 days → not excluded."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 5, 1)
    recent_date = ref_date - timedelta(days=200)  # within 365d

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=Decimal("5.00"))
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=True)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=False)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        elif "last_qualified_audit_date" in sql_str:
            result.fetchone.return_value = _Row(last_qualified_audit_date=recent_date)
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is False
    assert reason is None


def test_is_excluded_audit_qualification_null_fails_open():
    """last_qualified_audit_date IS NULL → fail-open, not excluded."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 5, 1)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchone.return_value = _Row(pledge_ratio_pct=None)
        elif "auditor_is_top_10" in sql_str:
            result.fetchone.return_value = _Row(auditor_is_top_10=None)
        elif "in_fno_ban_list" in sql_str:
            result.fetchone.return_value = _Row(in_fno_ban_list=None)
        elif "tier" in sql_str and "atlas_universe_stocks" in sql_str:
            result.fetchone.return_value = _Row(tier="LARGE")
        elif "last_qualified_audit_date" in sql_str:
            result.fetchone.return_value = _Row(last_qualified_audit_date=None)
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute.side_effect = execute_side_effect

    excluded, reason = is_excluded(session, iid, ref_date)
    assert excluded is False
    assert reason is None


# ---------------------------------------------------------------------------
# apply_exclusions — batch mode
# ---------------------------------------------------------------------------


def test_apply_exclusions_empty_universe_returns_empty():
    """Empty universe input → empty exclusion set."""
    session = MagicMock()
    excluded, logs = apply_exclusions(session, [], date(2026, 1, 15))
    assert excluded == set()
    assert logs == []
    # Should not call execute at all
    session.execute.assert_not_called()


def test_apply_exclusions_batch_pledge_excludes():
    """Batch mode: pledge query returns one hit → that instrument excluded."""
    session = MagicMock()
    iid1 = uuid.uuid4()
    iid2 = uuid.uuid4()
    ref_date = date(2026, 2, 1)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchall.return_value = [_Row(instrument_id=str(iid1))]
        elif "in_fno_ban_list" in sql_str:
            result.fetchall.return_value = []
        elif "UPPER(tier)" in sql_str:
            result.fetchall.return_value = []
        elif "last_qualified_audit_date" in sql_str:
            result.fetchall.return_value = []
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    session.execute.side_effect = execute_side_effect

    excluded, logs = apply_exclusions(session, [iid1, iid2], ref_date)
    assert iid1 in excluded
    assert iid2 not in excluded
    assert len(logs) == 1
    assert logs[0].reason == "pledge"
    assert logs[0].instrument_id == iid1


def test_apply_exclusions_batch_fno_ban_excludes():
    """Batch mode: fno_ban query returns one hit → that instrument excluded."""
    session = MagicMock()
    iid1 = uuid.uuid4()
    iid2 = uuid.uuid4()
    ref_date = date(2026, 3, 1)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchall.return_value = []
        elif "in_fno_ban_list" in sql_str:
            result.fetchall.return_value = [_Row(instrument_id=str(iid2))]
        elif "UPPER(tier)" in sql_str:
            result.fetchall.return_value = []
        elif "last_qualified_audit_date" in sql_str:
            result.fetchall.return_value = []
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    session.execute.side_effect = execute_side_effect

    excluded, logs = apply_exclusions(session, [iid1, iid2], ref_date)
    assert iid2 in excluded
    assert iid1 not in excluded
    assert len(logs) == 1
    assert logs[0].reason == "fno_ban"


def test_apply_exclusions_no_double_count():
    """If an instrument hits pledge AND fno_ban, it appears once in excluded."""
    session = MagicMock()
    iid = uuid.uuid4()
    ref_date = date(2026, 4, 1)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "pledge_ratio_pct" in sql_str:
            result.fetchall.return_value = [_Row(instrument_id=str(iid))]
        elif "in_fno_ban_list" in sql_str:
            result.fetchall.return_value = [_Row(instrument_id=str(iid))]
        elif "UPPER(tier)" in sql_str:
            result.fetchall.return_value = []
        elif "last_qualified_audit_date" in sql_str:
            result.fetchall.return_value = []
        elif "atlas_v6_exclusions_log" in sql_str:
            result.fetchone.return_value = None
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    session.execute.side_effect = execute_side_effect

    excluded, logs = apply_exclusions(session, [iid], ref_date)
    assert iid in excluded
    # Excluded set deduplicates; logs show pledge (first hit) only
    assert len(excluded) == 1
    # Only pledge should be in logs (fno_ban skipped because already excluded)
    reasons = {entry.reason for entry in logs}
    assert "pledge" in reasons


def test_apply_exclusions_all_clean_returns_empty():
    """Batch mode: no hits from any filter → empty exclusion set."""
    session = MagicMock()
    iids = [uuid.uuid4() for _ in range(5)]
    ref_date = date(2026, 1, 15)

    def execute_side_effect(sql, params=None):
        result = MagicMock()
        result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    session.execute.side_effect = execute_side_effect

    excluded, logs = apply_exclusions(session, iids, ref_date)
    assert excluded == set()
    assert logs == []
