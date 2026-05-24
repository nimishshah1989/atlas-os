"""Sector family — v6 wrapper over ``atlas.compute``.

Re-exports sector relative-strength / velocity feature-compute callables.
See :mod:`atlas.features` for the wrapper-pattern rationale.
"""

from __future__ import annotations

from atlas.compute.sectors import compute_rs_velocity

__all__ = [
    "compute_rs_velocity",
]
