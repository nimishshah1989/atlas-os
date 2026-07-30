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

Exit rule (``exit``) is independent of both modes — entries are always the golden
cross; only the close differs:
  * ``death_cross`` (default): the fast EMA crosses back below the slow. Every
    book predating crossover v2 uses this, so the default must never move.
  * ``fast_ema``: price loses the fast EMA itself. Far tighter — on real MRPL at
    2026-07-29 the EMA13 trigger sat 26.8% above the death-cross level, so the two
    disagree on the same name on the same day. Run as a twin book, never a silent
    substitution.
"""

from __future__ import annotations

from typing import cast

import pandas as pd

from atlas.primitives import ema_cross_price

from .base import StateStrategy

EXIT_RULES = ("death_cross", "fast_ema")
ENTRY_CONFIRMS = ("intraday", "close")


class EmaCross(StateStrategy):
    key = "ema_cross"

    def __init__(
        self,
        fast: int,
        slow: int,
        intraday: bool = False,
        same_day_fill: bool | None = None,
        exit: str = "death_cross",
        entry_confirm: str = "intraday",
    ):
        if int(fast) >= int(slow):
            raise ValueError(f"fast EMA ({fast}) must be shorter than slow ({slow})")
        if exit not in EXIT_RULES:
            raise ValueError(f"unknown exit rule {exit!r}; known: {list(EXIT_RULES)}")
        if entry_confirm not in ENTRY_CONFIRMS:
            raise ValueError(
                f"unknown entry_confirm {entry_confirm!r}; known: {list(ENTRY_CONFIRMS)}"
            )
        self.fast, self.slow = int(fast), int(slow)
        self.exit = exit
        self.entry_confirm = entry_confirm
        self.intraday = bool(intraday)
        # Intraday detection implies same-day fill; but same-day fill can also be
        # used with plain daily-close confirmation (removes the +1-session lag
        # without the intraday fakeouts).
        #
        # entry_confirm="close" is the exception: there the CONFIRMING CLOSE is the
        # signal, so filling at that same close would be lookahead. Such an entry
        # belongs to the next session (at its open, per the runner). An explicit
        # same_day_fill still wins — sweeps need to force the combination.
        auto_same_day = intraday and entry_confirm != "close"
        self._same_day_fill = bool(auto_same_day if same_day_fill is None else same_day_fill)

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
        breaches the exit level AND the close still sustains the break. One
        entry/exit per episode — a flat→long state walk suppresses re-firing while a
        breakout is still unconfirmed.

        The exit's second condition is the FM's 15:15 lock: a breach that recovers
        before the close is an alert, not a trade. Daily bars hold no 15:15 price, so
        the backtest proxies the lock with the close (spec: divergence #2). Real MRPL
        2026-07-27 is the case that makes this load-bearing — low 161.50 broke EMA13
        166.74, then closed back up at 169.75. A one-condition rule sells there and is
        wrong; the sustained break came the next session.

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
            close = g["close"].astype(float)
            if self.entry_confirm == "close":
                # The breach only ALERTS; the position opens on the first close that
                # actually confirms fast > slow. Real MRPL 2026-07-16 is the case this
                # filters: it breached P* 163.88 on the high of 178.40 but closed at
                # 157.47, leaving ema13 154.89 still under ema34 155.44 — so the entry
                # belongs to the 17th, not the 16th.
                up = (below & (g[ef].astype(float) > g[es].astype(float))).fillna(False)
            else:
                up = (below & (hi >= level)).fillna(False)
            # fast_ema books close on price losing the fast EMA itself; death_cross
            # books on the level where fast would cross below slow. Both need the
            # break to still hold at the close (the 15:15 lock).
            exit_level = pf if self.exit == "fast_ema" else level
            sustained = close <= exit_level
            down = (lo <= exit_level) & sustained
            if self.exit == "death_cross":
                down = down & ~below  # unchanged: only from a confirmed-long state
            down = down.fillna(False)

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
