"""Telegram alerts for the EMA-cross portfolios: one message per live buy/sell the
nightly mark books, so the FM sees each crossover trade as it happens.

Opt-in per portfolio via a ``notify: true`` params flag (start with 13/34). Sends
nothing if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset (notify.py no-ops), so
this is safe to ship before the bot is configured.
"""

from __future__ import annotations

from typing import Any

import _db

from atlas.intraday.notify import send_message_sync

M = "atlas_foundation"


def format_cross_alert(
    *,
    fast: int,
    slow: int,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    reason: str,
    trade_date: Any,
    ema_fast: float | None = None,
    ema_slow: float | None = None,
) -> str:
    """One Telegram message (HTML) for a booked EMA-cross trade."""
    buy = side == "buy"
    icon = "🟢" if buy else "🔴"
    act = "BUY" if buy else "SELL"
    if reason == "stop":
        move = "risk stop hit"
    elif buy:
        move = f"golden cross — EMA{fast} crossed above EMA{slow}"
    else:
        move = f"death cross — EMA{fast} crossed below EMA{slow}"
    q = int(qty) if float(qty).is_integer() else qty
    lines = [
        f"{icon} <b>EMA {fast}/{slow} — {act}</b>",
        f"{symbol} · {move}",
        f"{q} @ ₹{float(price):,.2f} · {trade_date}",
    ]
    if ema_fast is not None and ema_slow is not None:
        lines.append(f"EMA{fast} {float(ema_fast):.2f} / EMA{slow} {float(ema_slow):.2f}")
    return "\n".join(lines)


def _emas_at(instrument_key: str, fast: int, slow: int, on_or_before: Any):
    """Confirmed EMAs as of the signal (the last close on/before the fill)."""
    row = _db.read_df(
        f"""select ema_{fast} as ef, ema_{slow} as es from {M}.technical_daily
            where instrument_id::text = :k and date <= :d
            order by date desc limit 1""",
        {"k": instrument_key, "d": on_or_before},
    )
    if row.empty or row.iloc[0]["ef"] is None or row.iloc[0]["es"] is None:
        return None, None
    return float(row.iloc[0]["ef"]), float(row.iloc[0]["es"])


def notify_new_trades(portfolio: dict, trades) -> int:
    """Send one alert per newly-booked trade, for notify-enabled ema_cross
    portfolios. Returns the number of alerts sent. Safe no-op otherwise."""
    if portfolio.get("strategy_key") != "ema_cross" or trades is None or trades.empty:
        return 0
    params = portfolio.get("params") or {}
    if not params.get("notify"):
        return 0
    fast, slow = int(params["fast"]), int(params["slow"])
    sent = 0
    for t in trades.to_dict("records"):
        ef, es = _emas_at(str(t["instrument_key"]), fast, slow, t["trade_date"])
        send_message_sync(
            format_cross_alert(
                fast=fast,
                slow=slow,
                symbol=t["symbol"],
                side=t["side"],
                qty=t["qty"],
                price=t["price"],
                reason=t.get("reason", "signal"),
                trade_date=t["trade_date"],
                ema_fast=ef,
                ema_slow=es,
            )
        )
        sent += 1
    return sent
