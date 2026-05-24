"""Tests for atlas.trading.universe module."""

from datetime import date
from uuid import uuid4

from atlas.trading.universe import (
    build_membership_set,
    filter_to_universe,
    load_universe_membership,
)


def _mock_rows(pairs: list[tuple]) -> list[dict]:
    """Helper to create mock DB rows from (instrument_id, date) tuples."""
    return [{"instrument_id": iid, "date": d} for iid, d in pairs]


class TestBuildMembershipSet:
    """Test building membership index from DB rows."""

    def test_membership_set_basic(self):
        """Basic membership set construction from rows."""
        rows = _mock_rows([(1, date(2024, 1, 1)), (1, date(2024, 1, 2)), (2, date(2024, 1, 1))])
        membership = build_membership_set(rows)

        assert date(2024, 1, 1) in membership[1]
        assert date(2024, 1, 2) in membership[1]
        assert date(2024, 1, 2) not in membership[2]
        assert date(2024, 1, 1) in membership[2]

    def test_membership_set_empty(self):
        """Empty rows produce empty membership dict."""
        assert build_membership_set([]) == {}

    def test_membership_set_single_instrument(self):
        """Single instrument with multiple dates."""
        rows = _mock_rows([(1, date(2024, 1, 1)), (1, date(2024, 1, 2)), (1, date(2024, 1, 3))])
        membership = build_membership_set(rows)

        assert len(membership[1]) == 3
        expected_dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        assert all(d in membership[1] for d in expected_dates)

    def test_membership_set_deduplicates(self):
        """Duplicate rows are deduplicated via set."""
        rows = _mock_rows([(1, date(2024, 1, 1)), (1, date(2024, 1, 1))])
        membership = build_membership_set(rows)

        assert len(membership[1]) == 1


class TestFilterToUniverse:
    """Test filtering instrument IDs by point-in-time membership."""

    def test_filter_respects_date(self):
        """Only include instruments that were members on the given date."""
        membership = {1: {date(2024, 1, 1)}, 2: {date(2024, 1, 1), date(2024, 1, 2)}}
        result = filter_to_universe([1, 2], date(2024, 1, 2), membership)

        assert 1 not in result
        assert 2 in result

    def test_filter_empty_membership(self):
        """Empty membership dict returns empty list."""
        result = filter_to_universe([1, 2, 3], date(2024, 1, 1), {})
        assert result == []

    def test_filter_empty_input_list(self):
        """Empty instrument list returns empty list."""
        membership = {1: {date(2024, 1, 1)}, 2: {date(2024, 1, 1)}}
        result = filter_to_universe([], date(2024, 1, 1), membership)
        assert result == []

    def test_filter_all_included(self):
        """All instruments included when all are members on date."""
        membership = {1: {date(2024, 1, 1)}, 2: {date(2024, 1, 1)}, 3: {date(2024, 1, 1)}}
        result = filter_to_universe([1, 2, 3], date(2024, 1, 1), membership)

        assert result == [1, 2, 3]

    def test_filter_none_included(self):
        """No instruments included when none are members on date."""
        membership = {1: {date(2024, 1, 1)}, 2: {date(2024, 1, 1)}}
        result = filter_to_universe([1, 2], date(2024, 1, 2), membership)

        assert result == []

    def test_filter_partial_inclusion(self):
        """Partial inclusion based on membership dates."""
        membership = {
            1: {date(2024, 1, 1), date(2024, 1, 2)},
            2: {date(2024, 1, 1)},
            3: {date(2024, 1, 2)},
        }
        result = filter_to_universe([1, 2, 3], date(2024, 1, 2), membership)

        assert 1 in result
        assert 2 not in result
        assert 3 in result

    def test_filter_preserves_order(self):
        """Filter preserves input order."""
        membership = {5: {date(2024, 1, 1)}, 3: {date(2024, 1, 1)}, 1: {date(2024, 1, 1)}}
        result = filter_to_universe([5, 3, 1], date(2024, 1, 1), membership)

        assert result == [5, 3, 1]

    def test_filter_with_uuid_ids(self):
        """Filter works with UUID instrument IDs."""
        id1, id2, id3 = uuid4(), uuid4(), uuid4()
        membership = {id1: {date(2024, 1, 1)}, id2: {date(2024, 1, 1), date(2024, 1, 2)}}
        result = filter_to_universe([id1, id2, id3], date(2024, 1, 2), membership)

        assert id1 not in result
        assert id2 in result
        assert id3 not in result


class TestLoadUniverseMembership:
    """Test loading membership from DB (integration test)."""

    def test_load_universe_membership_mocked(self):
        """Load membership with mocked DB connection."""
        from unittest.mock import MagicMock

        # Mock connection and result
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_mappings = MagicMock()

        # Create mock rows
        mock_rows = [
            {"instrument_id": 1, "date": date(2024, 1, 1)},
            {"instrument_id": 2, "date": date(2024, 1, 1)},
            {"instrument_id": 2, "date": date(2024, 1, 2)},
        ]
        mock_mappings.all.return_value = mock_rows
        mock_result.mappings.return_value = mock_mappings
        mock_conn.execute.return_value = mock_result

        # Call the function
        result = load_universe_membership(mock_conn, "nifty500", date(2024, 1, 1), date(2024, 1, 2))

        # Verify result
        assert 1 in result
        assert 2 in result
        assert date(2024, 1, 1) in result[1]
        assert date(2024, 1, 1) in result[2]
        assert date(2024, 1, 2) in result[2]
