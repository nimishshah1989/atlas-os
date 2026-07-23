"""EMA fast/slow crossover — parametrized strategy behind the rule-based
portfolios (50/200 golden cross, 21/50, 13/34, 10/21).

Pure event detection over a preloaded technicals panel; no I/O.

Two modes:
  * daily-close (default): entry when the fast EMA crosses above the slow between
    consecutive stored closes, exit when it crosses back. Transition machinery
    lives in StateStrategy.
  * intraday (``intraday=True``): the cross is detected the day the *intraday*
    price breaches the provisional-cross level (proxied by the day's adjusted
    high/low), so a breakout that reverses by the close still fires that day. The
    fill then happens at that same day's close (``same_day_fill``), removing the
    +1-session lag. Used by the stock crossover portfolios that run on the live
    15-min feed. Needs high/low columns (``needs_ohlc``) alongside the EMAs.
"""

from __future__ import annotations

from typing import cast

import pandas as pd

from atlas.primitives import ema_cross_price

from .base import StateStrategy


class EmaCross(StateStrategy):
    key = "ema_cross"

    def __init__(
        self,
        fast: int,
        slow: int,
        intraday: bool = False,
        same_day_fill: bool | None = None,
    ):
        if int(fast) >= int(slow):
            raise ValueError(f"fast EMA ({fast}) must be shorter than slow ({slow})")
        self.fast, self.slow = int(fast), int(slow)
        self.intraday = bool(intraday)
        # Intraday detection implies same-day fill; but same-day fill can also be
        # used with plain daily-close confirmation (removes the +1-session lag
        # without the intraday fakeouts).
        self._same_day_fill = bool(intraday if same_day_fill is None else same_day_fill)

    @property
    def same_day_fill(self) -> bool:
        """Execute an event at its OWN session's close, not the next (no lag)."""
        return self._same_day_fill

    @property
    def needs_ohlc(self) -> bool:
        """Intraday detection needs the day's adjusted high/low, not just EMAs."""
        return self.intraday

    def required_columns(self) -> tuple[str, ...]:
        return (f"ema_{self.fast}", f"ema_{self.slow}")

    def _state(self, tech: pd.DataFrame) -> pd.Series:
        """fast>slow per row; NaN where either EMA is missing."""
        f = tech[f"ema_{self.fast}"].astype(float)
        s = tech[f"ema_{self.slow}"].astype(float)
        return (f > s).where(f.notna() & s.notna())

    def events(self, tech: pd.DataFrame) -> pd.DataFrame:
        if not self.intraday:
            return super().events(tech)
        return self._intraday_events(tech)

    def _intraday_events(self, tech: pd.DataFrame) -> pd.DataFrame:
        """Entry the day the intraday high breaches the provisional up-cross level
        (from the PRIOR close's confirmed EMAs); exit the day the intraday low
        breaches the down-cross level. One entry/exit per episode — a flat→long
        state walk suppresses re-firing while a breakout is still unconfirmed.

        ponytail: an entry whose intraday cross never confirms above (spike that
        closes below and stays there) has no death-cross to exit on. The engine's
        existing %/EMA risk stops cover that — enable one on the portfolio if the
        backtest shows stuck longs.
        """
        ef, es = f"ema_{self.fast}", f"ema_{self.slow}"
        frames: list[pd.DataFrame] = []
        for k, g in tech.groupby("instrument_key", sort=False):
            g = g.sort_values("date")
            pf = cast("pd.Series", g[ef].astype(float).shift())
            ps = cast("pd.Series", g[es].astype(float).shift())
            below = pf < ps
            level = ema_cross_price(pf, ps, fast=self.fast, slow=self.slow)
            hi = g["high"].astype(float)
            lo = g["low"].astype(float)
            up = (below & (hi >= level)).fillna(False)
            down = (~below & (lo <= level)).fillna(False)

            state = "flat"
            out: list[tuple[object, str]] = []
            for idx in g.index[up | down]:
                if state == "flat" and up.at[idx]:
                    out.append((g.at[idx, "date"], "entry"))
                    state = "long"
                elif state == "long" and down.at[idx]:
                    out.append((g.at[idx, "date"], "exit"))
                    state = "flat"
            if out:
                fr = pd.DataFrame(out, columns=pd.Index(["date", "event"]))
                fr["instrument_key"] = k
                frames.append(fr)

        if not frames:
            return pd.DataFrame(columns=pd.Index(["instrument_key", "date", "event"]))
        out_df = pd.DataFrame(pd.concat(frames, ignore_index=True))
        out_df = pd.DataFrame(out_df[["instrument_key", "date", "event"]]).sort_values(by="date")
        return out_df.reset_index(drop=True)
