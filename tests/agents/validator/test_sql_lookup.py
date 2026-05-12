"""Unit tests for route_crawler.sql_lookup — whitelist and format validation.

Tests that don't require DB (validation logic) are plain unit tests.
Integration tests that hit DB are marked @pytest.mark.integration.
"""

from __future__ import annotations

import pytest

from atlas.agents.validator.route_crawler.sql_lookup import LOOKUPS, _esc, lookup


class TestEsc:
    def test_safe_alphanum(self) -> None:
        assert _esc("RELIANCE") == "RELIANCE"

    def test_safe_with_space(self) -> None:
        assert _esc("Information Technology") == "Information Technology"

    def test_safe_with_dash(self) -> None:
        assert _esc("2026-05-12") == "2026-05-12"

    def test_single_quote_rejected(self) -> None:
        # Single quotes are not in the safe set — instrument IDs never contain them
        with pytest.raises(ValueError, match="Unsafe pk_value"):
            _esc("O'REILLY")

    def test_unsafe_semicolon(self) -> None:
        with pytest.raises(ValueError, match="Unsafe pk_value"):
            _esc("RELIANCE; DROP TABLE atlas.atlas_stock_metrics_daily --")

    def test_unsafe_injection(self) -> None:
        with pytest.raises(ValueError, match="Unsafe pk_value"):
            _esc("1=1 OR 1")


class TestWhitelist:
    def test_key_count(self) -> None:
        # Should have at least 25 entries
        assert len(LOOKUPS) >= 25

    def test_stock_conviction_present(self) -> None:
        assert "stock.conviction_score" in LOOKUPS

    def test_sector_state_present(self) -> None:
        assert "sector.sector_state" in LOOKUPS

    def test_etf_rs_pctile_present(self) -> None:
        assert "etf.rs_pctile_3m" in LOOKUPS

    def test_regime_state_present(self) -> None:
        assert "regime.regime_state" in LOOKUPS


class TestLookupValidation:
    def test_missing_colon_raises(self, fake_conn: object) -> None:
        with pytest.raises(ValueError, match="Invalid data-validator-id format"):
            lookup("stock.conviction_score_no_colon", fake_conn)  # type: ignore[arg-type]

    def test_unknown_field_key_raises(self, fake_conn: object) -> None:
        with pytest.raises(ValueError, match="No SQL lookup registered"):
            lookup("unknown.field_not_in_whitelist:RELIANCE", fake_conn)  # type: ignore[arg-type]

    def test_valid_key_does_not_raise_on_validation(self) -> None:
        # Calling lookup with None conn will fail but not on validation
        with pytest.raises(Exception) as exc_info:
            lookup("stock.conviction_score:RELIANCE", None)  # type: ignore[arg-type]
        # Should fail with AttributeError (NoneType has no .execute), not ValueError
        assert "ValueError" not in type(exc_info.value).__name__


@pytest.fixture()
def fake_conn() -> object:
    """Fixture that returns a non-Connection object for validation-only tests."""
    return object()
