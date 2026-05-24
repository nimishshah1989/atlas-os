"""Path family — v6 wrapper over ``atlas.compute``.

Re-exports drawdown / returns / formation-path feature-compute callables.
See :mod:`atlas.features` for the wrapper-pattern rationale.
"""

from __future__ import annotations

from atlas.compute.primitives import add_max_drawdown, add_returns

__all__ = [
    "add_max_drawdown",
    "add_returns",
]
