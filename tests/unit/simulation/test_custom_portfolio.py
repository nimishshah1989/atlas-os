"""Unit tests for custom/portfolio.py — mocked DB and engine, no real vectorbt."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atlas.simulation.custom.builder import InstrumentWeight

_INSTRUMENTS = [
    InstrumentWeight("INS_A", "stock", 50.0),
    InstrumentWeight("INS_B", "stock", 50.0),
]


class TestCreateCustomPortfolio:
    def test_returns_portfolio_id_string(self):
        from atlas.simulation.custom.portfolio import create_custom_portfolio

        with (
            patch("atlas.simulation.custom.portfolio.validate_custom_portfolio"),
            patch(
                "atlas.simulation.custom.portfolio._save_portfolio_record",
                return_value="test-portfolio-uuid",
            ),
            patch("atlas.simulation.custom.portfolio._trigger_backtest_background"),
        ):
            portfolio_id = create_custom_portfolio(
                name="My Test Portfolio",
                instruments=_INSTRUMENTS,
                engine=MagicMock(),
            )

        assert portfolio_id == "test-portfolio-uuid"

    def test_validation_called_before_save(self):
        from atlas.simulation.custom.portfolio import create_custom_portfolio

        call_order = []

        def mock_validate(*args, **kwargs):
            call_order.append("validate")

        def mock_save(*args, **kwargs):
            call_order.append("save")
            return "uuid"

        with (
            patch(
                "atlas.simulation.custom.portfolio.validate_custom_portfolio",
                side_effect=mock_validate,
            ),
            patch(
                "atlas.simulation.custom.portfolio._save_portfolio_record",
                side_effect=mock_save,
            ),
            patch("atlas.simulation.custom.portfolio._trigger_backtest_background"),
        ):
            create_custom_portfolio("Test", _INSTRUMENTS, MagicMock())

        assert call_order == ["validate", "save"]

    def test_validation_error_does_not_save(self):
        from atlas.simulation.custom.portfolio import create_custom_portfolio

        with (
            patch(
                "atlas.simulation.custom.portfolio.validate_custom_portfolio",
                side_effect=ValueError("bad portfolio"),
            ),
            patch("atlas.simulation.custom.portfolio._save_portfolio_record") as mock_save,
        ):
            with pytest.raises(ValueError, match="bad portfolio"):
                create_custom_portfolio("Test", _INSTRUMENTS, MagicMock())

        mock_save.assert_not_called()
