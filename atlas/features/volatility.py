"""Volatility family — v6 wrapper over ``atlas.compute``.

Re-exports pure volatility-family feature-compute callables. See
:mod:`atlas.features` for the wrapper-pattern rationale.
"""

from __future__ import annotations

from atlas.compute.primitives import add_atr, add_realized_vol

__all__ = [
    "add_atr",
    "add_realized_vol",
]
