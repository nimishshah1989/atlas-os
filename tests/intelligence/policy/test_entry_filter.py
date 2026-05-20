"""Tests for atlas.intelligence.policy.entry_filter — apply_entry_filter pure function.

All tests are pure (no DB). The function filters a list of candidate instruments
against a Policy's entry rules:
    engine_state ∈ buy_states
    AND within_state_rank >= min_within_state_rank
    AND rs_rank_12m >= min_rs_rank

DoD #4: two policies (strict / loose) over the same candidates must
produce DIFFERENT, correctly-sized result sets.
"""

from __future__ import annotations

from decimal import Decimal

from atlas.intelligence.policy.entry_filter import (
    CandidateInstrument,
    apply_entry_filter,
)
from atlas.intelligence.policy.policy import Policy

# ---------------------------------------------------------------------------
# Shared policy fixture helper (mirrors test_policy.py HOUSE_DEFAULTS)
# ---------------------------------------------------------------------------

HOUSE_BASE: dict[str, object] = {
    "cash_floor_pct": Decimal("5"),
    "respect_regime_cap": True,
    "max_per_stock_pct": Decimal("5"),
    "max_per_sector_pct": Decimal("15"),
    "max_small_cap_pct": Decimal("30"),
    "min_holdings": 15,
    "max_positions": 40,
    "hard_stop_pct": Decimal("8"),
    "state_exit_trim": "stage_3",
    "state_exit_full": "stage_4",
    "trailing_stop_pct": None,
    "instrument_universe": "direct_equity",
    "benchmark": "Nifty 500",
    "rebalance_cadence": "weekly",
}


def _make_policy(**kw: object) -> Policy:
    base = dict(HOUSE_BASE)
    base.update(kw)
    return Policy(**base)  # type: ignore[arg-type]


STRICT_POLICY = _make_policy(
    buy_states=["stage_2b"],
    min_within_state_rank=Decimal("0.80"),
    min_rs_rank=Decimal("0.70"),
)

LOOSE_POLICY = _make_policy(
    buy_states=["stage_2a", "stage_2b"],
    min_within_state_rank=Decimal("0.50"),
    min_rs_rank=Decimal("0.40"),
)

# ---------------------------------------------------------------------------
# Hand-crafted candidate list used in DoD #4 and individual tests
# ---------------------------------------------------------------------------
# 5 candidates with varying attributes:
#   A: stage_2b, rank=0.90, rs=0.80  → passes both strict and loose
#   B: stage_2a, rank=0.60, rs=0.50  → passes loose, fails strict
#   C: stage_2b, rank=0.75, rs=0.65  → fails strict (rank < 0.80, rs < 0.70), passes loose
#   D: stage_1,  rank=0.90, rs=0.85  → fails both (wrong state)
#   E: stage_2b, rank=0.85, rs=0.72  → passes strict (rank>=0.80, rs>=0.70), passes loose


def _c(id_: str, state: str | None, rank: float | None, rs: float | None) -> CandidateInstrument:
    return CandidateInstrument(
        instrument_id=id_,
        symbol=id_,
        engine_state=state,
        within_state_rank=rank,
        rs_rank_12m=rs,
    )


CANDIDATES: list[CandidateInstrument] = [
    _c("A", "stage_2b", 0.90, 0.80),
    _c("B", "stage_2a", 0.60, 0.50),
    _c("C", "stage_2b", 0.75, 0.65),
    _c("D", "stage_1", 0.90, 0.85),
    _c("E", "stage_2b", 0.85, 0.72),
]


# ---------------------------------------------------------------------------
# CandidateInstrument construction
# ---------------------------------------------------------------------------


class TestCandidateInstrument:
    def test_fields_stored(self) -> None:
        c = CandidateInstrument(
            instrument_id="X",
            symbol="RELIANCE",
            engine_state="stage_2b",
            within_state_rank=0.75,
            rs_rank_12m=0.80,
        )
        assert c.instrument_id == "X"
        assert c.symbol == "RELIANCE"
        assert c.engine_state == "stage_2b"
        assert c.within_state_rank == 0.75
        assert c.rs_rank_12m == 0.80

    def test_null_fields_allowed(self) -> None:
        """NULL state/ranks are valid inputs — filter handles them."""
        c = CandidateInstrument(
            instrument_id="Y",
            symbol="XYZ",
            engine_state=None,
            within_state_rank=None,
            rs_rank_12m=None,
        )
        assert c.engine_state is None
        assert c.within_state_rank is None
        assert c.rs_rank_12m is None


# ---------------------------------------------------------------------------
# apply_entry_filter basic cases
# ---------------------------------------------------------------------------


class TestApplyEntryFilter:
    def test_all_pass(self) -> None:
        """All candidates with matching state + high ranks pass a loose policy."""
        cands = [
            CandidateInstrument("1", "A", "stage_2a", 0.70, 0.60),
            CandidateInstrument("2", "B", "stage_2b", 0.80, 0.70),
        ]
        policy = LOOSE_POLICY
        result = apply_entry_filter(cands, policy)
        assert len(result) == 2

    def test_wrong_state_excluded(self) -> None:
        """stage_1 is not in buy_states=['stage_2b'] — excluded."""
        cands = [
            CandidateInstrument("1", "A", "stage_1", 0.90, 0.90),
        ]
        policy = STRICT_POLICY
        result = apply_entry_filter(cands, policy)
        assert len(result) == 0

    def test_below_within_state_rank_excluded(self) -> None:
        """Correct state but within_state_rank < min_within_state_rank → excluded."""
        cands = [
            CandidateInstrument("1", "A", "stage_2b", 0.50, 0.90),  # rank 0.50 < strict 0.80
        ]
        result = apply_entry_filter(cands, STRICT_POLICY)
        assert len(result) == 0

    def test_exactly_at_threshold_passes(self) -> None:
        """within_state_rank == min_within_state_rank is inclusive (>=)."""
        cands = [
            CandidateInstrument("1", "A", "stage_2b", 0.80, 0.70),  # exactly at strict thresholds
        ]
        result = apply_entry_filter(cands, STRICT_POLICY)
        assert len(result) == 1

    def test_below_rs_rank_excluded(self) -> None:
        """Correct state + rank but rs_rank_12m < min_rs_rank → excluded."""
        cands = [
            CandidateInstrument("1", "A", "stage_2b", 0.90, 0.60),  # rs 0.60 < strict 0.70
        ]
        result = apply_entry_filter(cands, STRICT_POLICY)
        assert len(result) == 0

    def test_null_engine_state_excluded(self) -> None:
        """NULL engine_state cannot match any buy_states list → excluded."""
        cands = [
            CandidateInstrument("1", "A", None, 0.90, 0.90),
        ]
        result = apply_entry_filter(cands, STRICT_POLICY)
        assert len(result) == 0

    def test_null_within_state_rank_excluded_when_threshold_positive(self) -> None:
        """NULL within_state_rank is treated as 0 → excluded when min_within_state_rank > 0."""
        cands = [
            CandidateInstrument("1", "A", "stage_2b", None, 0.90),
        ]
        result = apply_entry_filter(cands, STRICT_POLICY)
        assert len(result) == 0

    def test_null_rs_rank_excluded_when_threshold_positive(self) -> None:
        """NULL rs_rank_12m is treated as 0 → excluded when min_rs_rank > 0."""
        cands = [
            CandidateInstrument("1", "A", "stage_2b", 0.90, None),
        ]
        result = apply_entry_filter(cands, STRICT_POLICY)
        assert len(result) == 0

    def test_null_ranks_pass_when_threshold_zero(self) -> None:
        """NULL ranks are honest 0 → pass when thresholds are 0."""
        policy = _make_policy(
            buy_states=["stage_2a", "stage_2b"],
            min_within_state_rank=Decimal("0"),
            min_rs_rank=Decimal("0"),
        )
        cands = [
            CandidateInstrument("1", "A", "stage_2b", None, None),
        ]
        result = apply_entry_filter(cands, policy)
        assert len(result) == 1

    def test_empty_buy_states_excludes_all(self) -> None:
        """A policy with empty buy_states is valid and excludes all candidates."""
        policy = _make_policy(
            buy_states=[],
            min_within_state_rank=Decimal("0"),
            min_rs_rank=Decimal("0"),
        )
        cands = [
            CandidateInstrument("1", "A", "stage_2b", 0.90, 0.90),
        ]
        result = apply_entry_filter(cands, policy)
        assert len(result) == 0

    def test_empty_candidates_returns_empty(self) -> None:
        """Empty input always returns empty list."""
        result = apply_entry_filter([], STRICT_POLICY)
        assert result == []

    def test_order_preserved(self) -> None:
        """Returned list preserves input order."""
        cands = [
            CandidateInstrument("3", "C", "stage_2b", 0.90, 0.80),
            CandidateInstrument("1", "A", "stage_2b", 0.85, 0.75),
        ]
        result = apply_entry_filter(cands, LOOSE_POLICY)
        assert [c.instrument_id for c in result] == ["3", "1"]


# ---------------------------------------------------------------------------
# DoD #4: strict vs loose over the SAME candidate list → different result sets
# ---------------------------------------------------------------------------


class TestDodFourDifferentPoliciesDifferentResults:
    """Definition-of-Done #4.

    Two portfolios with DIFFERENT policies must yield DIFFERENT candidate lists
    from the same engine output.

    Strict policy:  buy_states=['stage_2b'],         min_within_state_rank=0.80, min_rs_rank=0.70
    Loose  policy:  buy_states=['stage_2a','stage_2b'], min_within_state_rank=0.50, min_rs_rank=0.40

    Shared candidates:
      A: stage_2b, rank=0.90, rs=0.80  → both pass
      B: stage_2a, rank=0.60, rs=0.50  → loose passes, strict FAILS (wrong state)
      C: stage_2b, rank=0.75, rs=0.65  → loose passes, strict FAILS (rank<0.80, rs<0.70)
      D: stage_1,  rank=0.90, rs=0.85  → both FAIL (wrong state)
      E: stage_2b, rank=0.85, rs=0.72  → both pass
    """

    def test_strict_result_ids(self) -> None:
        """Strict policy: only A and E pass."""
        result = apply_entry_filter(CANDIDATES, STRICT_POLICY)
        ids = {c.instrument_id for c in result}
        assert ids == {"A", "E"}

    def test_loose_result_ids(self) -> None:
        """Loose policy: A, B, C, E pass (D fails — wrong state)."""
        result = apply_entry_filter(CANDIDATES, LOOSE_POLICY)
        ids = {c.instrument_id for c in result}
        assert ids == {"A", "B", "C", "E"}

    def test_result_sets_differ(self) -> None:
        """Strict and loose results are different sets."""
        strict = {c.instrument_id for c in apply_entry_filter(CANDIDATES, STRICT_POLICY)}
        loose = {c.instrument_id for c in apply_entry_filter(CANDIDATES, LOOSE_POLICY)}
        assert strict != loose

    def test_strict_subset_of_loose(self) -> None:
        """Every stock passing strict policy also passes loose policy (strict ⊆ loose)."""
        strict = {c.instrument_id for c in apply_entry_filter(CANDIDATES, STRICT_POLICY)}
        loose = {c.instrument_id for c in apply_entry_filter(CANDIDATES, LOOSE_POLICY)}
        assert strict.issubset(loose)

    def test_loose_has_more_candidates_than_strict(self) -> None:
        """Loose policy produces a larger candidate set."""
        strict_count = len(apply_entry_filter(CANDIDATES, STRICT_POLICY))
        loose_count = len(apply_entry_filter(CANDIDATES, LOOSE_POLICY))
        assert loose_count > strict_count

    def test_exact_strict_count(self) -> None:
        """Strict: 2 of 5 candidates pass."""
        result = apply_entry_filter(CANDIDATES, STRICT_POLICY)
        assert len(result) == 2

    def test_exact_loose_count(self) -> None:
        """Loose: 4 of 5 candidates pass."""
        result = apply_entry_filter(CANDIDATES, LOOSE_POLICY)
        assert len(result) == 4
