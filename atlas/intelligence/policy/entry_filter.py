"""Entry-rule filter for atlas.intelligence.policy.

Given a list of candidate instruments and a Policy, returns only those
candidates that pass the Policy's ENTRY rules:

    engine_state ∈ policy.buy_states
    AND within_state_rank >= policy.min_within_state_rank
    AND rs_rank_12m >= policy.min_rs_rank

NULL handling (C5 — no fabricated data):
    - engine_state = None → excluded (cannot match any buy_state)
    - within_state_rank = None → treated as 0 (excluded when threshold > 0)
    - rs_rank_12m = None → treated as 0 (excluded when threshold > 0)

This is a pure function — no DB access, no I/O.  Unit-tested in
tests/intelligence/policy/test_entry_filter.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.intelligence.policy.policy import Policy


@dataclass(frozen=True)
class CandidateInstrument:
    """A candidate instrument with the fields needed for entry-rule evaluation.

    Fields:
        instrument_id:     UUID string from atlas_universe_stocks.
        symbol:            Ticker symbol for human-readable display.
        engine_state:      Weinstein state from atlas_stock_signal_unified
                           (e.g. 'stage_2a', 'stage_2b').  None = unclassified.
        within_state_rank: Quantile rank within the engine_state cohort, [0, 1].
                           None = not computed (treated as 0 for filter purposes).
        rs_rank_12m:       12-month RS rank, quantile [0, 1].
                           None = not computed (treated as 0 for filter purposes).
    """

    instrument_id: str
    symbol: str
    engine_state: str | None
    within_state_rank: float | None
    rs_rank_12m: float | None


def apply_entry_filter(
    candidates: list[CandidateInstrument],
    policy: Policy,
) -> list[CandidateInstrument]:
    """Filter candidates against the Policy's entry rules.

    Returns a new list (input order preserved) containing only those
    candidates that satisfy ALL three entry gates:

        1. engine_state is in policy.buy_states
        2. within_state_rank (None → 0) >= policy.min_within_state_rank
        3. rs_rank_12m      (None → 0) >= policy.min_rs_rank

    An empty policy.buy_states is valid and results in an empty output list.

    Args:
        candidates: Instruments to filter.  May be empty.
        policy:     Effective Policy for the portfolio.

    Returns:
        Filtered list, preserving input order.
    """
    buy_states_set = set(policy.buy_states)
    min_rank = policy.min_within_state_rank
    min_rs = policy.min_rs_rank

    result: list[CandidateInstrument] = []
    for c in candidates:
        # Gate 1: state membership
        if c.engine_state is None or c.engine_state not in buy_states_set:
            continue

        # Gate 2: within_state_rank (None → 0)
        rank = c.within_state_rank if c.within_state_rank is not None else 0.0
        if rank < float(min_rank):
            continue

        # Gate 3: rs_rank_12m (None → 0)
        rs = c.rs_rank_12m if c.rs_rank_12m is not None else 0.0
        if rs < float(min_rs):
            continue

        result.append(c)

    return result
