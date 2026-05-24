"""Volume family — v6 wrapper over ``atlas.compute``.

Re-exports per-instrument volume primitives and breadth aggregators. See
:mod:`atlas.features` for the wrapper-pattern rationale.
"""

from __future__ import annotations

from atlas.compute.breadth import compute_advances_declines
from atlas.compute.primitives import add_volume_primitives

__all__ = [
    "add_volume_primitives",
    "compute_advances_declines",
]
