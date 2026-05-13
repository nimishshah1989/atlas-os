"""Unit tests for atlas.signals.screenshot.

All Playwright interactions are mocked — no real browser is launched.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlas.signals.screenshot import (
    _build_chart_url,
    capture_chart_screenshots,
)

# ---------------------------------------------------------------------------
# _build_chart_url
# ---------------------------------------------------------------------------


def test_build_chart_url_daily() -> None:
    """Daily chart URL uses interval 'D' and correct symbol format."""
    url = _build_chart_url(
        layout_id="abc123",
        ticker="RELIANCE",
        exchange="NSE",
        timeframe="D",
    )
    assert url == "https://www.tradingview.com/chart/abc123/?symbol=NSE:RELIANCE&interval=D"


def test_build_chart_url_weekly() -> None:
    """Weekly chart URL uses interval 'W'."""
    url = _build_chart_url(
        layout_id="xyz789",
        ticker="INFY",
        exchange="NSE",
        timeframe="W",
    )
    assert "interval=W" in url
    assert "xyz789" in url
    assert "NSE:INFY" in url


# ---------------------------------------------------------------------------
# capture_chart_screenshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_returns_none_path_on_failure() -> None:
    """When _screenshot_one returns False, the corresponding path key is None."""
    with patch(
        "atlas.signals.screenshot._screenshot_one",
        new=AsyncMock(return_value=False),
    ):
        result = await capture_chart_screenshots(
            ticker="RELIANCE",
            exchange="NSE",
            layout_id_nifty="nifty_layout",
            layout_id_sector="sector_layout",
        )

    assert result["daily_path"] is None
    assert result["weekly_path"] is None
    assert result["sector_path"] is None


@pytest.mark.asyncio
async def test_capture_returns_all_keys() -> None:
    """Returned dict always contains all 6 expected keys."""
    with patch(
        "atlas.signals.screenshot._screenshot_one",
        new=AsyncMock(return_value=True),
    ):
        result = await capture_chart_screenshots(
            ticker="TCS",
            exchange="NSE",
            layout_id_nifty="n1",
            layout_id_sector="s1",
        )

    assert set(result.keys()) == {
        "daily_path",
        "weekly_path",
        "sector_path",
        "daily_url",
        "weekly_url",
        "sector_url",
    }


@pytest.mark.asyncio
async def test_capture_urls_always_set_even_on_failure() -> None:
    """URL keys are populated regardless of screenshot success/failure."""
    with patch(
        "atlas.signals.screenshot._screenshot_one",
        new=AsyncMock(return_value=False),
    ):
        result = await capture_chart_screenshots(
            ticker="HDFC",
            exchange="NSE",
            layout_id_nifty="nifty_l",
            layout_id_sector="sector_l",
        )

    assert result["daily_url"] is not None
    assert result["weekly_url"] is not None
    assert result["sector_url"] is not None
    assert "HDFC" in result["daily_url"]
    assert "HDFC" in result["weekly_url"]


@pytest.mark.asyncio
async def test_capture_partial_failure() -> None:
    """If only some screenshots fail, paths are None only for failures."""
    # daily succeeds, weekly fails, sector succeeds
    side_effects = [True, False, True]
    mock = AsyncMock(side_effect=side_effects)

    with patch("atlas.signals.screenshot._screenshot_one", new=mock):
        result = await capture_chart_screenshots(
            ticker="WIPRO",
            exchange="NSE",
            layout_id_nifty="n2",
            layout_id_sector="s2",
        )

    assert result["daily_path"] is not None
    assert result["weekly_path"] is None
    assert result["sector_path"] is not None


@pytest.mark.asyncio
async def test_screenshot_dir_created(tmp_path: Path) -> None:
    """_screenshot_one calls Path.mkdir with parents=True, exist_ok=True."""
    from atlas.signals.screenshot import _screenshot_one

    screenshot_path = str(tmp_path / "signals" / "TEST" / "TEST_daily_20260101_120000.png")

    mock_page = AsyncMock()
    mock_browser = AsyncMock()
    mock_context_obj = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context_obj)
    mock_context_obj.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.screenshot = AsyncMock()
    mock_browser.close = AsyncMock()
    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium = mock_chromium

    mock_pw_cm = MagicMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

    mock_mkdir = MagicMock()
    with (
        patch("atlas.signals.screenshot.async_playwright", return_value=mock_pw_cm),
        patch.object(Path, "mkdir", mock_mkdir),
    ):
        result = await _screenshot_one(
            url="https://www.tradingview.com/chart/test/?symbol=NSE:TEST&interval=D",
            path=screenshot_path,
        )

    assert result is True
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
