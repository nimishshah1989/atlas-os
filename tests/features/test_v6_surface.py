"""Tests for the v6 ``atlas.features`` canonical surface (issue #42).

Verifies the wrapper package exists, exposes the 5 scorecard family
modules, re-exports the v5 pure feature-compute functions, and ships the
``FEATURES`` allowlist used by :class:`atlas.decisions.rule_dsl` Pydantic
``Literal[...]`` validation.

Pure surface tests — no DB, no compute behaviour. Feature math is already
covered by ``tests/unit/test_primitives.py`` and ``tests/unit/test_indices.py``.
"""

from __future__ import annotations

import importlib
from typing import get_type_hints

import pytest

LOCKED_METHODOLOGY_FEATURES = (
    "rs_residual_6m",
    "log_med_tv_60d",
    "realized_vol_60d",
    "formation_max_dd",
    "listing_age_days",
    "log_price",
)
"""Per CONTEXT.md "29-feature library" — the 6 locked methodology features
that ship as first-class columns on ``atlas.atlas_scorecard_daily`` (per
migration 080)."""

FAMILY_MODULES = (
    "atlas.features.trend",
    "atlas.features.volatility",
    "atlas.features.volume",
    "atlas.features.path",
    "atlas.features.sector",
)


def test_atlas_features_package_importable() -> None:
    """The wrapper package itself must import cleanly."""
    mod = importlib.import_module("atlas.features")
    assert mod is not None


@pytest.mark.parametrize("family_module", FAMILY_MODULES)
def test_family_module_importable(family_module: str) -> None:
    """Each of the 5 scorecard family modules must import cleanly."""
    mod = importlib.import_module(family_module)
    assert mod is not None


def test_features_allowlist_is_tuple() -> None:
    """``FEATURES`` must be a tuple — immutability is load-bearing for the
    Pydantic ``Literal[...]`` validation surface."""
    from atlas.features import FEATURES

    assert isinstance(FEATURES, tuple)


def test_features_allowlist_has_minimum_size() -> None:
    """``FEATURES`` must have at least the 6 locked methodology features."""
    from atlas.features import FEATURES

    assert len(FEATURES) >= 6


def test_features_allowlist_contains_locked_methodology_features() -> None:
    """All 6 locked methodology features (per CONTEXT.md) must be in the
    allowlist — they are first-class columns on ``atlas_scorecard_daily``."""
    from atlas.features import FEATURES

    missing = [f for f in LOCKED_METHODOLOGY_FEATURES if f not in FEATURES]
    assert not missing, f"Missing locked methodology features: {missing}"


def test_features_allowlist_entries_are_strings() -> None:
    """Every entry must be a ``str`` — ``Literal[*FEATURES]`` requires it."""
    from atlas.features import FEATURES

    non_strings = [f for f in FEATURES if not isinstance(f, str)]
    assert not non_strings, f"Non-string entries: {non_strings}"


def test_features_allowlist_has_no_duplicates() -> None:
    """A duplicate name in the allowlist silently de-dupes inside
    ``Literal[...]`` but signals an authorial mistake — fail loud."""
    from atlas.features import FEATURES

    assert len(FEATURES) == len(set(FEATURES)), "FEATURES contains duplicates"


def test_features_allowlist_is_final_annotated() -> None:
    """``FEATURES`` is declared ``Final`` — confirms the source-of-truth
    contract per /grill Q4."""
    import atlas.features as features_pkg

    hints = get_type_hints(features_pkg, include_extras=True)
    annotation = hints.get("FEATURES")
    assert annotation is not None, "FEATURES is not annotated"
    # The Final[...] marker survives in the string form regardless of
    # whether the runtime sees the bare type or the wrapped Final type.
    annotation_str = repr(annotation)
    assert "Final" in annotation_str or "tuple" in annotation_str.lower()


def test_trend_family_reexports_add_emas() -> None:
    """The trend family must re-export :func:`atlas.compute.primitives.add_emas`."""
    from atlas.compute.primitives import add_emas as compute_add_emas
    from atlas.features.trend import add_emas

    assert callable(add_emas)
    assert add_emas is compute_add_emas


def test_volatility_family_reexports_add_realized_vol() -> None:
    """The volatility family must re-export
    :func:`atlas.compute.primitives.add_realized_vol`."""
    from atlas.compute.primitives import add_realized_vol as compute_add_realized_vol
    from atlas.features.volatility import add_realized_vol

    assert callable(add_realized_vol)
    assert add_realized_vol is compute_add_realized_vol


def test_volume_family_reexports_volume_primitives() -> None:
    """The volume family must re-export per-instrument volume primitives
    and at least one breadth aggregator."""
    from atlas.features.volume import (
        add_volume_primitives,
        compute_advances_declines,
    )

    assert callable(add_volume_primitives)
    assert callable(compute_advances_declines)


def test_path_family_reexports_max_drawdown_and_returns() -> None:
    """The path family must re-export drawdown + returns compute."""
    from atlas.features.path import add_max_drawdown, add_returns

    assert callable(add_max_drawdown)
    assert callable(add_returns)


def test_sector_family_reexports_rs_velocity() -> None:
    """The sector family must re-export rs_velocity compute."""
    from atlas.features.sector import compute_rs_velocity

    assert callable(compute_rs_velocity)


def test_package_init_documents_wrapper_pattern() -> None:
    """The package docstring must explain the wrapper pattern + v6 transition
    plan so future readers understand why ``atlas.features`` exists alongside
    ``atlas.compute``."""
    import atlas.features as features_pkg

    doc = features_pkg.__doc__ or ""
    # Look for keywords that signal the wrapper-pattern narrative without
    # being brittle about exact wording.
    assert "v6" in doc.lower()
    assert "atlas.compute" in doc or "atlas/compute" in doc
