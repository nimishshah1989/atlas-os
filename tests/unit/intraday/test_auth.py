"""Tests for atlas.intraday.auth (pure unit tests, no DB required)."""

from __future__ import annotations

import pytest

from atlas.intraday.auth import _strip_dialect


class TestStripDialect:
    def test_strip_psycopg2_dialect_prefix(self) -> None:
        result = _strip_dialect("postgresql+psycopg2://user:pass@localhost/testdb")
        assert result == "postgresql://user:pass@localhost/testdb"

    def test_plain_postgresql_scheme_unchanged(self) -> None:
        result = _strip_dialect("postgresql://user:pass@localhost/testdb")
        assert result == "postgresql://user:pass@localhost/testdb"

    def test_other_schemes_unchanged(self) -> None:
        result = _strip_dialect("sqlite:///test.db")
        assert result == "sqlite:///test.db"

    def test_only_strips_once(self) -> None:
        """Should not double-strip if called twice."""
        dsn = "postgresql+psycopg2://user:pass@localhost/testdb"
        result = _strip_dialect(_strip_dialect(dsn))
        assert result == "postgresql://user:pass@localhost/testdb"


class TestExchangeRequestTokenValidation:
    def test_missing_api_key_raises_value_error(self) -> None:
        import os

        os.environ.pop("KITE_API_KEY", None)
        os.environ.pop("KITE_API_SECRET", None)

        from atlas.intraday.auth import exchange_request_token

        with pytest.raises(ValueError, match="KITE_API_KEY"):
            exchange_request_token("fake_request_token")

    def test_missing_api_secret_raises_value_error(self) -> None:
        import os

        os.environ["KITE_API_KEY"] = "fake_api_key"
        os.environ.pop("KITE_API_SECRET", None)

        from atlas.intraday.auth import exchange_request_token

        with pytest.raises(ValueError, match="KITE_API_SECRET"):
            exchange_request_token("fake_request_token")

        # Cleanup
        os.environ.pop("KITE_API_KEY", None)
