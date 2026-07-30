"""Decision-trail composition (crossover v2 spec §I).

Every engine-written trade must say WHY on the row itself. Two halves:

  * the STRATEGY says which rule fired and at what level (carried on the events
    frame as a note) — the engine cannot know that;
  * the ENGINE says why this instrument won the slot and why the size is what it is
    — nothing else knows the ranked candidate list at fill time.

The "passed over" clause is the part that answers the FM's actual question. "Why
ECLERX" only means something against the names that lost.

Composites below are REAL scores from atlas_lens_scores_daily at 2026-07-10, the
signal date behind the 13/34 book's 2026-07-13 fills (rule #0):

    JUBLINGREA 69.00   GLENMARK 59.00   SWIGGY 16.25   ECLERX 15.45
    MRPL        6.75   CLEAN     6.45   DEVYANI  4.50
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.portfolio.rationale import Slot, inception_clause, slot_clause, stop_clause

pytestmark = pytest.mark.unit


def test_slot_clause_names_the_conviction_rank_and_the_losers() -> None:
    c = slot_clause(
        Slot(
            composite=59.0,
            rank=1,
            n_candidates=4,
            open_slots=3,
            passed_over=[("MRPL", 6.75)],
            cap_limited=True,
            alloc=Decimal("79901.50"),
            cap_pct=Decimal("0.08"),
        )
    )
    assert "Conviction 59.0" in c
    assert "ranked #1 of 4" in c
    assert "3 slots open" in c
    assert "MRPL (6.8)" in c  # the counterfactual: why this name and not that one
    assert "8% cap" in c


def test_slot_clause_says_cash_limited_when_the_size_was_not_the_cap() -> None:
    # A small position must never read as a mistake — it says WHY it is small.
    c = slot_clause(
        Slot(
            composite=15.45,
            rank=4,
            n_candidates=4,
            open_slots=4,
            passed_over=[],
            cap_limited=False,
            alloc=Decimal("73673.55"),
            cap_pct=Decimal("0.08"),
        )
    )
    assert "cash-limited" in c
    assert "8% cap" not in c or "not the 8% cap" in c


def test_slot_clause_omits_the_passed_over_sentence_when_nobody_lost() -> None:
    c = slot_clause(
        Slot(
            composite=69.0,
            rank=1,
            n_candidates=1,
            open_slots=12,
            passed_over=[],
            cap_limited=True,
            alloc=Decimal("80000.00"),
            cap_pct=Decimal("0.08"),
        )
    )
    assert "Passed over" not in c


def test_slot_clause_reports_a_missing_composite_honestly() -> None:
    # -inf is the engine's "no score" sentinel. Printing it, or silently calling it
    # zero, would both be lies about a name that simply was not scored that day.
    c = slot_clause(
        Slot(
            composite=float("-inf"),
            rank=2,
            n_candidates=2,
            open_slots=2,
            passed_over=[],
            cap_limited=True,
            alloc=Decimal("80000.00"),
            cap_pct=Decimal("0.08"),
        )
    )
    assert "unscored" in c
    assert "-inf" not in c


def test_passed_over_names_are_ordered_by_conviction_desc() -> None:
    c = slot_clause(
        Slot(
            composite=59.0,
            rank=1,
            n_candidates=4,
            open_slots=1,
            passed_over=[("DEVYANI", 4.50), ("SWIGGY", 16.25), ("MRPL", 6.75)],
            cap_limited=True,
            alloc=Decimal("80000.00"),
            cap_pct=Decimal("0.08"),
        )
    )
    assert c.index("SWIGGY") < c.index("MRPL") < c.index("DEVYANI")


def test_stop_clause_states_the_level_and_what_breached_it() -> None:
    c = stop_clause(
        kind="pct",
        prior_close=Decimal("412.30"),
        level=Decimal("412.29"),
        pct=Decimal("0.10"),
    )
    assert "10%" in c
    assert "412.30" in c


def test_inception_clause_names_the_target_weight_for_a_weighted_basket() -> None:
    assert "25%" in inception_clause(weight=Decimal("0.25"))


def test_inception_clause_for_an_equal_weight_basket_says_so() -> None:
    c = inception_clause(weight=None)
    assert "inception" in c.lower()
    assert "%" not in c
