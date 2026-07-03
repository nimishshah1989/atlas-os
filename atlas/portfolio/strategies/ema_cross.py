"""EMA fast/slow crossover — the parametrized strategy behind all three launch
portfolios (50/200 golden cross, 21/50, 10/21).

Pure event detection over a preloaded technicals panel; no I/O. Entry when the
fast EMA crosses above the slow between consecutive stored rows, exit when it
crosses back below. Rows where either EMA is NULL (insufficient lookback) carry
no state, so the first valid row never emits an event.
"""

from __future__ import annotations

import pandas as pd


class EmaCross:
    key = "ema_cross"

    def __init__(self, fast: int, slow: int):
        if int(fast) >= int(slow):
            raise ValueError(f"fast EMA ({fast}) must be shorter than slow ({slow})")
        self.fast, self.slow = int(fast), int(slow)

    def required_columns(self) -> tuple[str, ...]:
        return (f"ema_{self.fast}", f"ema_{self.slow}")

    def _state(self, tech: pd.DataFrame) -> pd.Series:
        """fast>slow per row; NaN where either EMA is missing."""
        f = tech[f"ema_{self.fast}"].astype(float)
        s = tech[f"ema_{self.slow}"].astype(float)
        return (f > s).where(f.notna() & s.notna())

    def events(self, tech: pd.DataFrame) -> pd.DataFrame:
        """Crossover events from a panel (instrument_key, date, ema_*).

        Returns (instrument_key, date, event) with event in {'entry','exit'} —
        one row per state flip between an instrument's consecutive rows.
        """
        frames = []
        for k, g in tech.groupby("instrument_key", sort=False):
            g = g.sort_values("date")
            st = self._state(g)
            prev = st.shift()
            flips = g.loc[st.notna() & prev.notna() & (st != prev), ["date"]].copy()
            if flips.empty:
                continue
            flips["instrument_key"] = k
            flips["event"] = st.loc[flips.index].map({True: "entry", False: "exit"})
            frames.append(flips)
        if not frames:
            return pd.DataFrame(columns=pd.Index(["instrument_key", "date", "event"]))
        out = pd.DataFrame(pd.concat(frames, ignore_index=True))
        out = pd.DataFrame(out[["instrument_key", "date", "event"]]).sort_values(by="date")
        return out.reset_index(drop=True)

    def state(self, tech: pd.DataFrame) -> pd.Series:
        """Point-in-time state (fast>slow, bool) at each instrument's LAST row —
        used to seed a new portfolio at inception."""
        last = tech.sort_values("date").groupby("instrument_key", sort=False).tail(1)
        st = self._state(last).eq(True)  # NaN (missing EMA) → False, no dtype downcast
        return pd.Series(st.to_numpy(dtype=bool), index=last["instrument_key"].to_numpy())
