"""TV Alert Provisioner.

Syncs TradingView alerts with the current investable universe from Atlas DB.
Diffs the current universe against the registered alert set, adds new tickers,
deactivates removed tickers, and invokes the alleyway tool via subprocess.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Provisioned conditions: (tier, condition_code, chart_type)
# ---------------------------------------------------------------------------
_PROVISIONED_CONDITIONS: list[tuple[int, str, str]] = [
    (1, "breakout_52w_volume", "vs_nifty"),
    (1, "rs_breakout_52w", "vs_nifty"),
    (1, "rs_sector_breakout_52w", "vs_sector"),
    (1, "breakout_52w_volume", "vs_sector"),
    (1, "rs_breakout_52w", "vs_sector"),
    (1, "rs_sector_breakout_52w", "vs_nifty"),
]

# Map chart_type to layout_id from Config
_CHART_LAYOUT_MAP: dict[str, str] = {
    "vs_nifty": "TV_LAYOUT_ID_VS_NIFTY",
    "vs_sector": "TV_LAYOUT_ID_VS_SECTOR",
}


def _diff_universe(
    current: set[str],
    registered: set[str],
) -> tuple[set[str], set[str]]:
    """Return (new_tickers, removed_tickers).

    new_tickers  = tickers in current but not in registered (need alerts added)
    removed_tickers = tickers in registered but not in current (need deactivation)
    """
    new_tickers = current - registered
    removed_tickers = registered - current
    return new_tickers, removed_tickers


def _build_alert_csv_row(
    ticker: str,
    exchange: str,
    condition_code: str,
    chart_type: str,
    layout_id: str,
    webhook_url: str,
    secret: str,
) -> str:
    """Build one CSV row for the alleyway tool config file.

    TradingView template variables ({{close}}, {{volume}}, {{timenow}}) are
    embedded with double-braces which Python f-string escaping converts to
    single-brace output, e.g. {{{{close}}}} → {{close}}.
    """
    symbol = f"{exchange}:{ticker}"
    message = (
        f'{{"tier":0,"code":"{condition_code}","chart":"{chart_type}",'
        f'"ticker":"{ticker}","exchange":"{exchange}",'
        f'"close":"{{{{close}}}}","volume":"{{{{volume}}}}","time":"{{{{timenow}}}}",'
        f'"secret":"{secret}"}}'
    )
    return f"{symbol},{condition_code},{layout_id},{webhook_url},{message}"


def _fetch_current_universe(conn: Any) -> set[str]:
    """Return the set of investable ticker symbols from Atlas DB (top 200)."""
    rows = conn.execute(
        text(
            "SELECT u.symbol FROM atlas.atlas_universe_stocks u "
            "JOIN atlas.atlas_stock_decisions_daily d ON d.instrument_id = u.instrument_id "
            "WHERE d.is_investable = TRUE AND u.effective_to IS NULL "
            "AND d.date = (SELECT MAX(date) FROM atlas.atlas_stock_decisions_daily) "
            "ORDER BY u.tier, u.symbol LIMIT 200"
        )
    ).fetchall()
    result: set[str] = {row[0] for row in rows}
    log.info("universe_fetched", count=len(result))
    return result


def _fetch_registered_tickers(conn: Any) -> set[str]:
    """Return the set of tickers currently registered in tv_alert_registry."""
    rows = conn.execute(
        text("SELECT DISTINCT ticker FROM tv_alert_registry WHERE is_active = TRUE")
    ).fetchall()
    result: set[str] = {row[0] for row in rows}
    log.info("registered_tickers_fetched", count=len(result))
    return result


def _resolve_exchange(ticker: str, conn: Any) -> str:
    """Resolve the exchange for a ticker from atlas_universe_stocks."""
    row = conn.execute(
        text(
            "SELECT exchange FROM atlas.atlas_universe_stocks "
            "WHERE symbol = :symbol AND effective_to IS NULL LIMIT 1"
        ),
        {"symbol": ticker},
    ).fetchone()
    # Default to NSE if not found — all India equities are NSE or BSE
    return str(row[0]) if row and row[0] else "NSE"


def provision_tv_alerts(alleyway_tool_path: str | None = None) -> dict:
    """Sync TradingView alerts with the current investable universe.

    Steps:
    1. Fetch current universe + registered tickers from DB.
    2. Diff: compute new tickers (to add) and removed tickers (to deactivate).
    3. Build CSV config rows for new tickers x all _PROVISIONED_CONDITIONS.
    4. Write CSV to tempfile and invoke the alleyway tool subprocess.
    5. On success: insert rows into tv_alert_registry for new ticker x condition.
    6. On removed tickers: set is_active = FALSE in tv_alert_registry.
    7. Return summary dict.

    Args:
        alleyway_tool_path: Path to the alleyway tool directory. Defaults to
            ``Config.SIGNAL_SCREENSHOT_DIR`` parent / 'alleyway'.

    Returns:
        {"added": int, "removed": int, "failed": list[str], "total_active": int}
    """
    tool_path = alleyway_tool_path or str(Path(Config.SIGNAL_SCREENSHOT_DIR).parent / "alleyway")

    _base = Config.SIGNAL_REPORT_BASE_URL
    if _base.endswith("/signals"):
        _base = _base[: -len("/signals")]
    webhook_url = f"{_base}/api/v1/tv/signal"
    secret = Config.TV_WEBHOOK_SECRET

    engine = get_engine()
    failed: list[str] = []

    with engine.connect() as conn:
        current_universe = _fetch_current_universe(conn)
        registered_tickers = _fetch_registered_tickers(conn)

        new_tickers, removed_tickers = _diff_universe(current_universe, registered_tickers)

        log.info(
            "provisioner_diff",
            new_count=len(new_tickers),
            removed_count=len(removed_tickers),
        )

        if not new_tickers and not removed_tickers:
            log.info("provisioner_no_changes")
            total_active = conn.execute(
                text(
                    "SELECT COUNT(DISTINCT ticker) FROM tv_alert_registry " "WHERE is_active = TRUE"
                )
            ).scalar()
            return {
                "added": 0,
                "removed": 0,
                "failed": [],
                "total_active": int(total_active or 0),
            }

        # Resolve exchanges for new tickers
        ticker_exchange: dict[str, str] = {}
        for ticker in new_tickers:
            ticker_exchange[ticker] = _resolve_exchange(ticker, conn)

    # Build CSV rows for new tickers
    csv_rows: list[str] = []
    for ticker in sorted(new_tickers):
        exchange = ticker_exchange.get(ticker, "NSE")
        for _tier, condition_code, chart_type in _PROVISIONED_CONDITIONS:
            layout_id_attr = _CHART_LAYOUT_MAP.get(chart_type, "TV_LAYOUT_ID_VS_NIFTY")
            layout_id = getattr(Config, layout_id_attr, "")
            row = _build_alert_csv_row(
                ticker=ticker,
                exchange=exchange,
                condition_code=condition_code,
                chart_type=chart_type,
                layout_id=layout_id,
                webhook_url=webhook_url,
                secret=secret,
            )
            csv_rows.append(row)

    added_count = 0

    if csv_rows:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, prefix="tv_alerts_"
        ) as tmp:
            tmp.write("\n".join(csv_rows))
            csv_path = tmp.name

        log.info("provisioner_invoking_tool", csv_path=csv_path, rows=len(csv_rows))

        try:
            result = subprocess.run(  # noqa: S603
                [tool_path, "add-alerts-tool/index.js", "--config", csv_path],
                timeout=300,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                log.info("alleyway_tool_success", rows=len(csv_rows))
                # Insert into tv_alert_registry for each new ticker x condition
                with engine.begin() as wconn:
                    for ticker in sorted(new_tickers):
                        exchange = ticker_exchange.get(ticker, "NSE")
                        for _tier, condition_code, chart_type in _PROVISIONED_CONDITIONS:
                            wconn.execute(
                                text(
                                    "INSERT INTO tv_alert_registry "
                                    "(ticker, exchange, condition_code, chart_type, "
                                    "webhook_url, is_active) "
                                    "VALUES (:ticker, :exchange, :condition_code, "
                                    ":chart_type, :webhook_url, TRUE) "
                                    "ON CONFLICT (ticker, condition_code, chart_type) "
                                    "DO UPDATE SET is_active = TRUE, "
                                    "updated_at = NOW()"
                                ),
                                {
                                    "ticker": ticker,
                                    "exchange": exchange,
                                    "condition_code": condition_code,
                                    "chart_type": chart_type,
                                    "webhook_url": webhook_url,
                                },
                            )
                    added_count = len(new_tickers)
            else:
                log.error(
                    "alleyway_tool_failed",
                    returncode=result.returncode,
                    stderr=result.stderr[:500],
                )
                failed.extend(sorted(new_tickers))
        except Exception:
            log.exception("alleyway_tool_error", csv_path=csv_path)
            failed.extend(sorted(new_tickers))

    # Deactivate removed tickers
    removed_count = 0
    if removed_tickers:
        with engine.begin() as wconn:
            for ticker in sorted(removed_tickers):
                wconn.execute(
                    text(
                        "UPDATE tv_alert_registry SET is_active = FALSE, "
                        "updated_at = NOW() "
                        "WHERE ticker = :ticker"
                    ),
                    {"ticker": ticker},
                )
            removed_count = len(removed_tickers)
        log.info("provisioner_deactivated", count=removed_count)

    # Count total active after changes
    with engine.connect() as conn:
        total_active = conn.execute(
            text("SELECT COUNT(DISTINCT ticker) FROM tv_alert_registry " "WHERE is_active = TRUE")
        ).scalar()

    log.info(
        "provisioner_complete",
        added=added_count,
        removed=removed_count,
        failed=len(failed),
        total_active=int(total_active or 0),
    )

    return {
        "added": added_count,
        "removed": removed_count,
        "failed": failed,
        "total_active": int(total_active or 0),
    }
