"""Shared pure primitives usable across bounded contexts (rule 3).

Only stateless, dependency-free helpers belong here — the one module every
``atlas/`` context may import from alongside ``atlas.db`` / ``atlas.config``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

if TYPE_CHECKING:
    import pandas as pd


@overload
def ema_cross_price(ema_fast: float, ema_slow: float, *, fast: int, slow: int) -> float: ...
@overload
def ema_cross_price(
    ema_fast: pd.Series, ema_slow: pd.Series, *, fast: int, slow: int
) -> pd.Series: ...
def ema_cross_price(ema_fast, ema_slow, *, fast, slow):
    """Price at which a provisional EMA (yesterday's confirmed EMA + today's live
    price as the forming bar) makes fast == slow.

    Provisional EMA_n(today) = ema_prev_n + α_n·(price − ema_prev_n), α_n = 2/(n+1).
    Setting fast == slow and solving for price gives a single crossing level P*.
    Because α_fast > α_slow, price ABOVE P* ⇒ fast>slow (golden), BELOW ⇒ death.
    Callers compare P* against the day's high (entry) / low (exit) in backtest, or
    the live 15-min price intraday. Works elementwise on pandas Series too (the
    backtest vectorizes over a whole price column).
    """
    a_f = 2 / (fast + 1)
    a_s = 2 / (slow + 1)
    return (ema_slow * (1 - a_s) - ema_fast * (1 - a_f)) / (a_f - a_s)
