"""Telegram alerts for the EMA-cross portfolios — the BOOKED stage (spec §E).

This is the third and authoritative message of the three the FM gets per crossover:

    provisional   crossover_monitor.py, the moment the 5-min feed breaches
    confirmed     crossover_monitor.py, at the close (buys) or the 15:15 lock (sells)
    booked        HERE, from the nightly mark, once the trade actually exists

Opt-in per portfolio via a ``notify: true`` params flag. Sends nothing if
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset (notify.py no-ops), so this is safe to
ship before the bot is configured.

Since 2026-07-30 this is the ONLY Telegram sender in the repo besides the monitor: the
desk breach alerts, the desk memo, the daily and weekly pipeline failures and the Sunday
QA report were all removed so the channel carries the crossover books and nothing else.
Those signals still exist — they are pull (logs, /health, the health snapshot) rather
than push.
"""

from __future__ import annotations

from atlas.intraday.notify import send_message_sync
from atlas.portfolio import alerts

M = "atlas_foundation"


def book_label(portfolio: dict) -> str:
    """The name that leads every message. The twin 13/34 books alert on the same symbol
    on the same day with opposite verdicts, so this is what keeps that legible rather
    than looking like the system contradicting itself."""
    params = portfolio.get("params") or {}
    return str(portfolio.get("name") or f"EMA {params.get('fast')}/{params.get('slow')}")


def notify_new_trades(portfolio: dict, trades) -> int:
    """Send one alert per newly-booked trade, for notify-enabled ema_cross portfolios.
    Returns the number of alerts sent. Safe no-op otherwise.

    The rationale written by the engine rides along in the message, so the WHY arrives
    with the WHAT instead of living only on a page nobody opens at 20:00.
    """
    if portfolio.get("strategy_key") != "ema_cross" or trades is None or trades.empty:
        return 0
    if not (portfolio.get("params") or {}).get("notify"):
        return 0
    label = book_label(portfolio)
    sent = 0
    for t in trades.to_dict("records"):
        send_message_sync(alerts.booked(book=label, trade=t))
        sent += 1
    return sent
