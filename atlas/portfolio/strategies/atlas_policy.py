"""AtlasPolicy — the system-generated portfolio's policy template.

A glass-box rulebook over Atlas's own signals, parametrized by a small set of
interpretable knobs (all stored in portfolio_master.params, tuned by the
walk-forward champion/challenger in scripts/foundation/portfolio_evolve.py):

    fast/slow        — EMA trend state (as EmaCross)
    confirm_200      — additionally require the SLOW EMA above the 200 EMA
                       (no-op when slow == 200; uses only EMA columns so it
                       works for stocks, ETFs and NAV-based fund EMAs alike)
    rs_min           — minimum 3-month relative strength vs NIFTY 500 (stocks/ETFs)
    min_composite    — minimum Atlas composite score (stocks; needs_composite)
    regime_gate      — force OUT of the market in Risk-Off / dislocation
                       (state False ⇒ exits fire; re-enters when regime clears)

State semantics: a row carries a signal only when EVERY knob's input is present
(NaN otherwise), so entries/exits fire only on real transitions — same contract
as EmaCross via StateStrategy.
"""

from __future__ import annotations

import pandas as pd

from .base import StateStrategy

_RISK_OFF = ("Risk-Off", "DISLOCATION_SUSPENDED")


class AtlasPolicy(StateStrategy):
    key = "atlas_policy"

    def __init__(
        self,
        fast: int,
        slow: int,
        confirm_200: bool = False,
        rs_min: float | None = None,
        min_composite: float | None = None,
        regime_gate: bool = False,
    ):
        if int(fast) >= int(slow):
            raise ValueError(f"fast EMA ({fast}) must be shorter than slow ({slow})")
        self.fast, self.slow = int(fast), int(slow)
        self.confirm_200 = bool(confirm_200) and self.slow != 200
        self.rs_min = None if rs_min is None else float(rs_min)
        self.min_composite = None if min_composite is None else float(min_composite)
        self.regime_gate = bool(regime_gate)

    @property
    def needs_composite(self) -> bool:
        return self.min_composite is not None

    @property
    def needs_regime(self) -> bool:
        return self.regime_gate

    def required_columns(self) -> tuple[str, ...]:
        cols = [f"ema_{self.fast}", f"ema_{self.slow}"]
        if self.confirm_200:
            cols.append("ema_200")
        if self.rs_min is not None:
            cols.append("rs_3m_n500")
        return tuple(dict.fromkeys(cols))

    def _state(self, tech: pd.DataFrame) -> pd.Series:
        f = tech[f"ema_{self.fast}"].astype(float)
        s = tech[f"ema_{self.slow}"].astype(float)
        valid = f.notna() & s.notna()
        state = f > s
        if self.confirm_200:
            e200 = tech["ema_200"].astype(float)
            valid &= e200.notna()
            state &= s > e200
        if self.rs_min is not None:
            rs = tech["rs_3m_n500"].astype(float)
            valid &= rs.notna()
            state &= rs >= self.rs_min
        if self.min_composite is not None:
            comp = tech["composite"].astype(float)
            valid &= comp.notna()
            state &= comp >= self.min_composite
        if self.regime_gate:
            regime = tech["regime_state"]
            valid &= regime.notna()
            state &= ~regime.isin(_RISK_OFF)
        return state.where(valid)
