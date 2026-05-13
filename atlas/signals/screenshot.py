"""TradingView chart screenshot capture via Playwright.

Provides cookie-authenticated browser sessions that navigate to TV chart
URLs and save PNG screenshots to disk. Used by the signal pipeline to
attach chart images to signal reports.

No DB interaction — pure async I/O. Exceptions in individual screenshots
are swallowed (logged) so a single chart failure does not abort the pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from atlas.config import Config

log = structlog.get_logger()

try:
    from playwright.async_api import async_playwright  # pyright: ignore[reportMissingImports]
except ImportError:
    async_playwright = None  # type: ignore[assignment]

_TV_CHART_BASE = "https://www.tradingview.com/chart"
_TV_COOKIE_DOMAIN = ".tradingview.com"
_NETWORK_IDLE_WAIT_MS = 3_000  # extra ms after networkidle for chart render


def _build_chart_url(
    layout_id: str,
    ticker: str,
    exchange: str,
    timeframe: str,
) -> str:
    """Return a TradingView chart URL for the given parameters.

    Args:
        layout_id: TradingView layout/chart ID (from TV_LAYOUT_ID_* env vars).
        ticker: Instrument symbol, e.g. ``"RELIANCE"``.
        exchange: Exchange prefix, e.g. ``"NSE"``.
        timeframe: Interval string — ``"D"`` for daily, ``"W"`` for weekly.

    Returns:
        Fully-qualified TradingView chart URL string.
    """
    return f"{_TV_CHART_BASE}/{layout_id}/?symbol={exchange}:{ticker}&interval={timeframe}"


async def _screenshot_one(url: str, path: str) -> bool:
    """Navigate to a TradingView chart URL and save a PNG screenshot.

    Injects TV session cookies before navigation so the page loads as a
    logged-in user. Waits for ``networkidle`` then an additional 3 seconds
    for chart rendering before capturing.

    Args:
        url: Fully-qualified TradingView chart URL.
        path: Absolute filesystem path for the PNG output.

    Returns:
        ``True`` on success, ``False`` if any exception occurs (exception
        is logged via structlog).
    """
    if async_playwright is None:
        log.warning("playwright_not_installed", url=url)
        return False

    Path(path).parent.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": Config.TV_SESSION_ID,
                        "domain": _TV_COOKIE_DOMAIN,
                        "path": "/",
                    },
                    {
                        "name": "sessionid_sign",
                        "value": Config.TV_SESSION_SIGN,
                        "domain": _TV_COOKIE_DOMAIN,
                        "path": "/",
                    },
                ]
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(_NETWORK_IDLE_WAIT_MS)
            await page.screenshot(path=path)
            await browser.close()
        log.info("screenshot_saved", path=path, url=url)
        return True
    except Exception as exc:
        log.warning("screenshot_failed", url=url, path=path, error=str(exc))
        return False


async def capture_chart_screenshots(
    ticker: str,
    exchange: str,
    layout_id_nifty: str,
    layout_id_sector: str,
) -> dict[str, str | None]:
    """Capture daily, weekly, and sector chart screenshots for a ticker.

    Attempts all three captures even if one fails. Failed captures return
    ``None`` for the path key while the URL key is always populated.

    Args:
        ticker: Instrument symbol, e.g. ``"RELIANCE"``.
        exchange: Exchange prefix, e.g. ``"NSE"``.
        layout_id_nifty: TradingView layout ID for the Nifty comparison chart.
        layout_id_sector: TradingView layout ID for the sector comparison chart.

    Returns:
        Dict with six keys:

        - ``daily_path``: Filesystem path of daily PNG, or ``None`` on failure.
        - ``weekly_path``: Filesystem path of weekly PNG, or ``None`` on failure.
        - ``sector_path``: Filesystem path of sector PNG, or ``None`` on failure.
        - ``daily_url``: TradingView URL for daily chart (always set).
        - ``weekly_url``: TradingView URL for weekly chart (always set).
        - ``sector_url``: TradingView URL for sector chart (always set).
    """
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    base_dir = Config.SIGNAL_SCREENSHOT_DIR

    daily_url = _build_chart_url(layout_id_nifty, ticker, exchange, "D")
    weekly_url = _build_chart_url(layout_id_nifty, ticker, exchange, "W")
    sector_url = _build_chart_url(layout_id_sector, ticker, exchange, "D")

    daily_path_target = f"{base_dir}/{ticker}/{ticker}_daily_{ts}.png"
    weekly_path_target = f"{base_dir}/{ticker}/{ticker}_weekly_{ts}.png"
    sector_path_target = f"{base_dir}/{ticker}/{ticker}_sector_{ts}.png"

    log.info(
        "capture_chart_screenshots_start",
        ticker=ticker,
        exchange=exchange,
        daily_url=daily_url,
        weekly_url=weekly_url,
        sector_url=sector_url,
    )

    daily_ok = await _screenshot_one(daily_url, daily_path_target)
    weekly_ok = await _screenshot_one(weekly_url, weekly_path_target)
    sector_ok = await _screenshot_one(sector_url, sector_path_target)

    result: dict[str, str | None] = {
        "daily_path": daily_path_target if daily_ok else None,
        "weekly_path": weekly_path_target if weekly_ok else None,
        "sector_path": sector_path_target if sector_ok else None,
        "daily_url": daily_url,
        "weekly_url": weekly_url,
        "sector_url": sector_url,
    }

    log.info(
        "capture_chart_screenshots_done",
        ticker=ticker,
        daily_ok=daily_ok,
        weekly_ok=weekly_ok,
        sector_ok=sector_ok,
    )
    return result
