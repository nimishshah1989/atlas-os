"""Binary-state strategy base: a subclass defines `_state(tech)` — True/False per
row where all its signals are present, NaN where any is missing — and inherits
event detection (state flips between an instrument's consecutive rows) and the
point-in-time `state()` used to seed FM baskets. Rows with NaN state carry no
signal, so the first valid row never emits an event.
"""

from __future__ import annotations

import pandas as pd


class StateStrategy:
    def _state(self, tech: pd.DataFrame) -> pd.Series:  # pragma: no cover - interface
        raise NotImplementedError

    def events(self, tech: pd.DataFrame) -> pd.DataFrame:
        """(instrument_key, date, event∈{'entry','exit'}) — one row per state flip."""
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
        """Point-in-time state (bool) at each instrument's LAST row."""
        last = tech.sort_values("date").groupby("instrument_key", sort=False).tail(1)
        st = self._state(last).eq(True)  # NaN (missing signal) → False
        return pd.Series(st.to_numpy(dtype=bool), index=last["instrument_key"].to_numpy())
