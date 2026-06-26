"""Flat→nested thresholds adapter.

`atlas.db.load_thresholds()` returns FLAT scalar keys straight from
`atlas_thresholds` (e.g. ``lens_weight_technical=0.20``,
``lens_conviction_high_score=58``). But ``compute_composite`` reads NESTED shapes
(``th['lens_weights']``, ``th['conviction_tiers']``, ``th['convergence']``). The
two never matched, so the composite silently fell back to its hard-coded
``_DEFAULT_*`` and **the DB / IC-learned weights were ignored** (Loop C blocker
0a; DECISIONS D8).

`nest_thresholds` builds those nested shapes from the flat keys and returns a
NEW dict that is the flat dict PLUS the nested keys — so the per-lens scorers,
which read flat keys (``ema_aligned_all``, ``rs_top10``…), keep working unchanged
while the composite finally consumes the DB weights. Pure, no I/O.
"""

from __future__ import annotations

from typing import Any

_LENSES = ("technical", "fundamental", "valuation", "catalyst", "flow", "policy")


def _g(flat: dict[str, Any], key: str, default: float) -> float:
    v = flat.get(key)
    return float(v) if v is not None else float(default)


def nest_thresholds(flat: dict[str, Any]) -> dict[str, Any]:
    """Return ``flat`` augmented with the nested shapes compute_composite expects.

    Idempotent: if a nested key already exists it is left untouched (so callers
    may pass an already-nested dict). Missing flat keys fall back to the same
    defaults the composite hard-codes, so behaviour never silently degrades.
    """
    out: dict[str, Any] = dict(flat)

    if "lens_weights" not in out:
        defaults = {
            "technical": 0.20,
            "fundamental": 0.20,
            "valuation": 0.00,
            "catalyst": 0.25,
            "flow": 0.25,
            "policy": 0.10,
        }
        out["lens_weights"] = {
            lens: _g(flat, f"lens_weight_{lens}", defaults[lens]) for lens in _LENSES
        }

    if "convergence" not in out:
        out["convergence"] = {
            "threshold": _g(flat, "lens_convergence_threshold", 40),
            "4plus": _g(flat, "lens_convergence_4plus", 1.15),
            "3": _g(flat, "lens_convergence_3", 1.10),
            "2": _g(flat, "lens_convergence_2", 1.06),
        }

    if "conviction_tiers" not in out:
        out["conviction_tiers"] = {
            "HIGHEST": {
                "min_score": _g(flat, "lens_conviction_highest_score", 70),
                "min_lenses": _g(flat, "lens_conviction_highest_min_layers", 3),
            },
            "HIGH": {
                "min_score": _g(flat, "lens_conviction_high_score", 58),
                "min_lenses": _g(flat, "lens_conviction_high_min_layers", 2),
            },
            "MEDIUM": {"min_score": _g(flat, "lens_conviction_medium_score", 45), "min_lenses": 0},
            "WATCH": {"min_score": _g(flat, "lens_conviction_watch_score", 30), "min_lenses": 0},
            "BELOW_THRESHOLD": {"min_score": 0, "min_lenses": 0},
        }

    return out
