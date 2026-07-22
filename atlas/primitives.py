"""Shared pure primitives usable across bounded contexts (rule 3).

Only stateless, dependency-free helpers belong here — the one module every
``atlas/`` context may import from alongside ``atlas.db`` / ``atlas.config``.
"""

from __future__ import annotations


def ema_cross_price(ema_fast: float, ema_slow: float, *, fast: int, slow: int) -> float:
    """Price at which a provisional EMA (yesterday's confirmed EMA + today's live
    price as the forming bar) makes fast == slow.

    Provisional EMA_n(today) = ema_prev_n + α_n·(price − ema_prev_n), α_n = 2/(n+1).
    Setting fast == slow and solving for price gives a single crossing level P*.
    Because α_fast > α_slow, price ABOVE P* ⇒ fast>slow (golden), BELOW ⇒ death.
    Callers compare P* against the day's high (entry) / low (exit) in backtest, or
    the live 15-min price intraday.
    """
    a_f = 2 / (fast + 1)
    a_s = 2 / (slow + 1)
    return (ema_slow * (1 - a_s) - ema_fast * (1 - a_f)) / (a_f - a_s)
