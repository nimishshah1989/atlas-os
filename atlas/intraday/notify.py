"""Telegram notification helper for SP08 intraday engine."""

from __future__ import annotations

import asyncio
import os

import structlog

log = structlog.get_logger()


async def send_message(text: str) -> None:
    """Send a Telegram message via the Bot API.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment.
    If either is missing: logs a warning and returns (graceful no-op).
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.warning(
            "telegram_not_configured",
            reason="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping notification",
        )
        return

    try:
        from telegram import Bot  # type: ignore[import-untyped]

        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        log.debug("telegram_message_sent")
    except Exception as exc:
        log.warning("telegram_send_failed", error=str(exc))


def send_message_sync(text: str) -> None:
    """Synchronous wrapper around :func:`send_message`.

    Runs the coroutine via :func:`asyncio.run`. Safe to call from any
    synchronous context (ingester shutdown, EOD sentinel, etc.).
    """
    asyncio.run(send_message(text))
