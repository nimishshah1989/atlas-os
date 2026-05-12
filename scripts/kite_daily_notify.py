#!/usr/bin/env python3
"""Send daily Kite OAuth reminder via Telegram at 08:55 IST.

Invoked by systemd atlas-intraday-notify.timer (03:25 UTC = 08:55 IST Mon-Fri).

Checks whether a valid Kite access token already exists:
- If yes: sends a short "already authenticated" confirmation.
- If no:  sends the full auth URL with a 20-minute window reminder.

Required env vars (read from .env):
  TELEGRAM_BOT_TOKEN  — Telegram bot token
  TELEGRAM_CHAT_ID    — Target chat/channel ID
  DATABASE_URL        — Postgres DSN (for token validity check)

Exits 0 on success, 1 on unhandled error.
"""

from __future__ import annotations

import os
import sys
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

# ---------------------------------------------------------------------------
# Telegram message templates
# ---------------------------------------------------------------------------
_MSG_AUTH_REQUIRED = (
    "🔑 <b>Kite Auth Required</b>\n\n"
    "Market opens at 09:15 IST. You have 20 minutes.\n\n"
    '👉 <a href="https://atlas.jslwealth.in/api/kite/login">Click to authenticate</a>\n\n'
    "Token valid until midnight IST."
)

_MSG_ALREADY_AUTH = "✅ <b>Kite Already Authenticated</b> — Token valid until midnight IST."


def _check_token_valid() -> bool:
    """Return True if a valid Kite access token exists in the DB.

    Returns False if DATABASE_URL is missing, or if no valid token is found.
    Logs at warning level for missing config; does not raise.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.warning(
            "kite_notify_no_db_url",
            reason="DATABASE_URL not set — skipping token validity check",
        )
        return False

    try:
        from atlas.intraday.auth import get_valid_access_token

        get_valid_access_token(conn_str=database_url)
        return True
    except RuntimeError:
        # No active/non-expired session row
        return False
    except Exception as exc:
        log.warning("kite_notify_token_check_failed", error=str(exc))
        return False


def main() -> None:
    """Send Telegram notification and exit."""
    from atlas.intraday.notify import send_message_sync

    try:
        already_authed = _check_token_valid()

        if already_authed:
            message = _MSG_ALREADY_AUTH
            log.info("kite_notify_sending_already_auth")
        else:
            message = _MSG_AUTH_REQUIRED
            log.info("kite_notify_sending_auth_required")

        send_message_sync(message)
        log.info("kite_notify_done")
        sys.exit(0)

    except Exception as exc:
        log.error("kite_notify_failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
