"""EmaCross exit-rule selection (crossover v2, spec §A).

The 13/34 rulebook runs as twin books that differ ONLY in how a position closes:

  * ``exit="death_cross"`` (default) — the fast EMA crossing back below the slow.
    Every book that existed before crossover v2 uses this, so it MUST stay the
    default and MUST NOT change behaviour.
  * ``exit="fast_ema"`` — price losing the fast EMA itself. A much tighter exit
    (26.8% higher trigger than the death cross on real MRPL at 2026-07-29), so it
    is opt-in per portfolio.

These are config assertions only; the behavioural equivalence and divergence are
asserted on real records in tests/integration/portfolio/test_ema_cross_exit_variants.py.
"""

from __future__ import annotations

import pytest

from atlas.portfolio.strategies import EmaCross

pytestmark = pytest.mark.unit


def test_default_exit_is_the_death_cross() -> None:
    # Every pre-v2 book relies on this default. Changing it silently re-writes
    # the exit rule of 9 live portfolios.
    assert EmaCross(13, 34).exit == "death_cross"


def test_fast_ema_exit_is_selectable() -> None:
    assert EmaCross(13, 34, exit="fast_ema").exit == "fast_ema"


def test_unknown_exit_rule_is_rejected() -> None:
    # A typo in a portfolio's params JSONB must fail loudly at construction, not
    # silently fall back to an exit rule the FM did not choose.
    with pytest.raises(ValueError, match="exit"):
        EmaCross(13, 34, exit="ema13")


def test_exit_rule_does_not_change_required_columns() -> None:
    # The fast-EMA exit compares price to ema_fast, which the crossover already
    # requires — so neither variant needs an extra column loaded.
    assert (
        EmaCross(13, 34, exit="fast_ema").required_columns() == EmaCross(13, 34).required_columns()
    )
