"""Trend / momentum family — v6 wrapper over ``atlas.compute``.

Re-exports pure trend-family feature-compute callables. See
:mod:`atlas.features` for the wrapper-pattern rationale.
"""

from __future__ import annotations

from atlas.compute.primitives import add_emas, add_rs_momentum

__all__ = [
    "add_emas",
    "add_rs_momentum",
]
