#!/usr/bin/env python3
"""SP08 intraday ingester entry point.

Invoked by systemd atlas-intraday.service at 09:10 IST on trading days.
The trading calendar guard (ExecStartPre in the unit file) already blocks
startup on holidays; this script adds a belt-and-suspenders check in Python
to handle manual runs outside systemd.

Required env vars (read from .env):
  ATLAS_DB_URL       — Postgres DSN
  KITE_API_KEY       — KiteConnect API key
  KITE_API_SECRET    — KiteConnect API secret
  KITE_TOKEN_ENCRYPTION_KEY — pgp_sym_encrypt key for token storage

Exits:
  0 — not a trading day, or clean shutdown via SIGTERM/SIGINT
  1 — missing ATLAS_DB_URL or fatal startup error
"""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import structlog  # noqa: E402

log = structlog.get_logger()


def main() -> None:
    """Start the intraday ingester after pre-flight checks."""
    # ------------------------------------------------------------------
    # 1. Trading day guard (belt-and-suspenders; systemd ExecStartPre is
    #    the primary gate but this handles manual/test invocations)
    # ------------------------------------------------------------------
    from scripts.trading_calendar import is_trading_day

    if not is_trading_day():
        log.info("intraday_skipped", reason="Not a trading day, exiting.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 2. Require ATLAS_DB_URL (via Config — fails loudly if missing)
    # ------------------------------------------------------------------
    from atlas.config import Config

    try:
        database_url = Config.assert_db_url()
    except RuntimeError as exc:
        log.error("intraday_startup_failed", reason=str(exc))
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Instantiate ingester
    # ------------------------------------------------------------------
    from atlas.intraday.ingester import IntradayIngester

    ingester = IntradayIngester(conn_str=database_url)

    # ------------------------------------------------------------------
    # 4. Signal handlers — graceful shutdown on SIGTERM / SIGINT
    # ------------------------------------------------------------------
    def _shutdown(signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        log.info("intraday_shutdown_signal", signal=sig_name)
        ingester.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # ------------------------------------------------------------------
    # 5. Start the ingester
    # ------------------------------------------------------------------
    log.info("intraday_starting")
    ingester.start()
    log.info("intraday_running")

    # ------------------------------------------------------------------
    # 6. Block until stop event is set (or signal received)
    # ------------------------------------------------------------------
    while not ingester._stop_event.is_set():
        time.sleep(10)

    log.info("intraday_stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
