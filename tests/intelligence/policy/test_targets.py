"""Tests for atlas.intelligence.policy.targets — sector-target derivation.

All tests are pure (no DB). Hand-computed golden values per
chunk-decision-engine-T2.4-targets-approach.md.

Invariants under test (C6/C7):
- sum(targets) <= regime_cap
- every target <= max_per_sector_pct
- gap = target - current; negative gap surfaced honestly (not clamped)
- degenerate case (all pct_stage_2=0) -> all targets 0, no exception
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.intelligence.policy.policy import Policy
from atlas.intelligence.policy.targets import (
    SectorSignal,
    SectorTarget,
    derive_sector_targets,
)

# ---------------------------------------------------------------------------
# Shared Policy fixture — mirrors house defaults; max_per_sector_pct=15
# ---------------------------------------------------------------------------

HOUSE_DEFAULTS_KWARGS: dict[str, object] = {
    "cash_floor_pct": Decimal("5"),
    "respect_regime_cap": True,
    "max_per_stock_pct": Decimal("5"),
    "max_per_sector_pct": Decimal("15"),
    "max_small_cap_pct": Decimal("30"),
    "min_holdings": 15,
    "max_positions": 40,
    "buy_states": ["stage_2a", "stage_2b"],
    "min_within_state_rank": Decimal("0.60"),
    "min_rs_rank": Decimal("0.70"),
    "hard_stop_pct": Decimal("8"),
    "state_exit_trim": "stage_3",
    "state_exit_full": "stage_4",
    "trailing_stop_pct": None,
    "instrument_universe": "direct_equity",
    "benchmark": "Nifty 500",
    "rebalance_cadence": "weekly",
}


def _make_policy(**overrides: object) -> Policy:
    kwargs = dict(HOUSE_DEFAULTS_KWARGS)
    kwargs.update(overrides)
    return Policy(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Golden test: 4 sectors, full formula walk-through
#
# Inputs:
#   A: pct_stage_2=0.8, mean_within_state_rank=0.9, current=12
#   B: pct_stage_2=0.6, mean_within_state_rank=0.7, current=10
#   C: pct_stage_2=0.3, mean_within_state_rank=0.5, current=5
#   D: pct_stage_2=0.1, mean_within_state_rank=0.4, current=3
#
# Hand-computed:
#   raw:        A=0.72,  B=0.42,  C=0.15,  D=0.04   total=1.33
#   pre_cap:    A=21.65, B=12.63, C=4.51,  D=1.20
#   capped:     A=15.00, B=12.63, C=4.51,  D=1.20   (max_per_sector_pct=15)
#   rounded:    A=15.00, B=12.63, C=4.51,  D=1.20
#   sum=33.34 <= 40 (regime_cap)
#   gaps:       A=+3.00, B=+2.63, C=-0.49, D=-1.80
# ---------------------------------------------------------------------------


class TestGoldenFourSectors:
    """Full formula walk with hand-computed expected values (C6)."""

    @pytest.fixture
    def signals(self) -> list[SectorSignal]:
        return [
            SectorSignal(
                sector="A",
                pct_stage_2=Decimal("0.8"),
                mean_within_state_rank=Decimal("0.9"),
            ),
            SectorSignal(
                sector="B",
                pct_stage_2=Decimal("0.6"),
                mean_within_state_rank=Decimal("0.7"),
            ),
            SectorSignal(
                sector="C",
                pct_stage_2=Decimal("0.3"),
                mean_within_state_rank=Decimal("0.5"),
            ),
            SectorSignal(
                sector="D",
                pct_stage_2=Decimal("0.1"),
                mean_within_state_rank=Decimal("0.4"),
            ),
        ]

    @pytest.fixture
    def current_weights(self) -> dict[str, Decimal]:
        return {
            "A": Decimal("12"),
            "B": Decimal("10"),
            "C": Decimal("5"),
            "D": Decimal("3"),
        }

    @pytest.fixture
    def results(
        self,
        signals: list[SectorSignal],
        current_weights: dict[str, Decimal],
    ) -> list[SectorTarget]:
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        return derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=current_weights,
            regime_cap=Decimal("40"),
        )

    @pytest.fixture
    def by_sector(self, results: list[SectorTarget]) -> dict[str, SectorTarget]:
        return {r.sector: r for r in results}

    def test_returns_four_targets(self, results: list[SectorTarget]) -> None:
        assert len(results) == 4

    def test_sector_a_target(self, by_sector: dict[str, SectorTarget]) -> None:
        # A pre-cap=21.65 -> capped at 15.00 (max_per_sector_pct=15)
        assert by_sector["A"].target == Decimal("15.00")

    def test_sector_b_target(self, by_sector: dict[str, SectorTarget]) -> None:
        # B pre-cap=12.63 -> not capped -> 12.63
        assert by_sector["B"].target == Decimal("12.63")

    def test_sector_c_target(self, by_sector: dict[str, SectorTarget]) -> None:
        # C pre-cap=4.51 -> not capped -> 4.51
        assert by_sector["C"].target == Decimal("4.51")

    def test_sector_d_target(self, by_sector: dict[str, SectorTarget]) -> None:
        # D pre-cap=1.20 -> not capped -> 1.20
        assert by_sector["D"].target == Decimal("1.20")

    def test_sector_a_current(self, by_sector: dict[str, SectorTarget]) -> None:
        assert by_sector["A"].current == Decimal("12")

    def test_sector_a_gap_positive(self, by_sector: dict[str, SectorTarget]) -> None:
        # gap = 15.00 - 12 = +3.00
        assert by_sector["A"].gap == Decimal("3.00")

    def test_sector_b_gap_positive(self, by_sector: dict[str, SectorTarget]) -> None:
        # gap = 12.63 - 10 = +2.63
        assert by_sector["B"].gap == Decimal("2.63")

    def test_sector_c_gap_negative(self, by_sector: dict[str, SectorTarget]) -> None:
        # gap = 4.51 - 5 = -0.49 (trim signal)
        assert by_sector["C"].gap == Decimal("-0.49")

    def test_sector_d_gap_negative(self, by_sector: dict[str, SectorTarget]) -> None:
        # gap = 1.20 - 3 = -1.80 (trim signal)
        assert by_sector["D"].gap == Decimal("-1.80")

    def test_sum_targets_does_not_exceed_regime_cap(self, results: list[SectorTarget]) -> None:
        # sum = 33.34 <= 40
        total = sum(r.target for r in results)
        assert total == Decimal("33.34")
        assert total <= Decimal("40")


# ---------------------------------------------------------------------------
# Cap test: one sector over cap, others NOT re-inflated
#
# Inputs:
#   X: pct_stage_2=0.9, mean_within_state_rank=0.9, current=10
#   Y: pct_stage_2=0.4, mean_within_state_rank=0.5, current=8
#   Z: pct_stage_2=0.1, mean_within_state_rank=0.3, current=2
#
# max_per_sector_pct=20, regime_cap=50
#
# Hand-computed:
#   raw: X=0.81, Y=0.20, Z=0.03   total=1.04
#   pre_cap: X=38.94, Y=9.62,  Z=1.44
#   capped:  X=20.00, Y=9.62,  Z=1.44   (X capped; Y and Z NOT re-inflated)
#   sum=31.06 <= 50
#   gaps:    X=+10.00, Y=+1.62, Z=-0.56
# ---------------------------------------------------------------------------


class TestCapOneExceedsOthersNotReinflated:
    """Sector X pre-cap=38.94 exceeds max=20. Y and Z keep their natural shares (C6)."""

    @pytest.fixture
    def results(self) -> list[SectorTarget]:
        signals = [
            SectorSignal(
                sector="X",
                pct_stage_2=Decimal("0.9"),
                mean_within_state_rank=Decimal("0.9"),
            ),
            SectorSignal(
                sector="Y",
                pct_stage_2=Decimal("0.4"),
                mean_within_state_rank=Decimal("0.5"),
            ),
            SectorSignal(
                sector="Z",
                pct_stage_2=Decimal("0.1"),
                mean_within_state_rank=Decimal("0.3"),
            ),
        ]
        current_weights = {
            "X": Decimal("10"),
            "Y": Decimal("8"),
            "Z": Decimal("2"),
        }
        policy = _make_policy(
            max_per_sector_pct=Decimal("20"),
            max_per_stock_pct=Decimal("5"),
        )
        return derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=current_weights,
            regime_cap=Decimal("50"),
        )

    @pytest.fixture
    def by_sector(self, results: list[SectorTarget]) -> dict[str, SectorTarget]:
        return {r.sector: r for r in results}

    def test_x_capped_at_max_per_sector_pct(self, by_sector: dict[str, SectorTarget]) -> None:
        # X pre-cap=38.94, capped at 20
        assert by_sector["X"].target == Decimal("20.00")

    def test_y_not_reinflated(self, by_sector: dict[str, SectorTarget]) -> None:
        # Y natural share = 9.62; must NOT be bumped up to fill X's excess
        assert by_sector["Y"].target == Decimal("9.62")

    def test_z_not_reinflated(self, by_sector: dict[str, SectorTarget]) -> None:
        # Z natural share = 1.44
        assert by_sector["Z"].target == Decimal("1.44")

    def test_sum_targets_below_regime_cap(self, results: list[SectorTarget]) -> None:
        # sum=31.06 <= 50
        total = sum(r.target for r in results)
        assert total == Decimal("31.06")
        assert total <= Decimal("50")

    def test_every_target_at_or_below_max_per_sector_pct(self, results: list[SectorTarget]) -> None:
        for r in results:
            assert r.target <= Decimal("20"), f"{r.sector}.target {r.target} > 20"


# ---------------------------------------------------------------------------
# Invariant tests: sum<=regime_cap and target<=max_per_sector_pct
# ---------------------------------------------------------------------------


class TestInvariants:
    """Structural invariants hold for any legal input combination (C7)."""

    def _run(
        self,
        signals: list[SectorSignal],
        max_per_sector: Decimal,
        regime_cap: Decimal,
        currents: dict[str, Decimal],
    ) -> list[SectorTarget]:
        policy = _make_policy(
            max_per_sector_pct=max_per_sector,
            max_per_stock_pct=Decimal("5"),
        )
        return derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=currents,
            regime_cap=regime_cap,
        )

    def test_sum_lte_regime_cap_golden(self) -> None:
        signals = [
            SectorSignal("A", Decimal("0.8"), Decimal("0.9")),
            SectorSignal("B", Decimal("0.6"), Decimal("0.7")),
            SectorSignal("C", Decimal("0.3"), Decimal("0.5")),
            SectorSignal("D", Decimal("0.1"), Decimal("0.4")),
        ]
        results = self._run(
            signals,
            max_per_sector=Decimal("15"),
            regime_cap=Decimal("40"),
            currents={"A": Decimal("0"), "B": Decimal("0"), "C": Decimal("0"), "D": Decimal("0")},
        )
        total = sum(r.target for r in results)
        assert total <= Decimal("40"), f"sum {total} > regime_cap 40"

    def test_every_target_lte_max_per_sector_pct(self) -> None:
        signals = [
            SectorSignal("A", Decimal("0.9"), Decimal("1.0")),
            SectorSignal("B", Decimal("0.8"), Decimal("0.9")),
            SectorSignal("C", Decimal("0.7"), Decimal("0.8")),
        ]
        results = self._run(
            signals,
            max_per_sector=Decimal("10"),
            regime_cap=Decimal("60"),
            currents={"A": Decimal("0"), "B": Decimal("0"), "C": Decimal("0")},
        )
        for r in results:
            assert r.target <= Decimal(
                "10"
            ), f"{r.sector}.target {r.target} exceeds max_per_sector_pct=10"

    def test_sum_lte_regime_cap_when_all_capped(self) -> None:
        # Tight cap: max=5, three equal sectors, regime_cap=30
        # All three would get 10 pre-cap (30/3), capped at 5 each -> sum=15 <= 30
        signals = [
            SectorSignal("X", Decimal("0.5"), Decimal("0.5")),
            SectorSignal("Y", Decimal("0.5"), Decimal("0.5")),
            SectorSignal("Z", Decimal("0.5"), Decimal("0.5")),
        ]
        results = self._run(
            signals,
            max_per_sector=Decimal("5"),
            regime_cap=Decimal("30"),
            currents={"X": Decimal("0"), "Y": Decimal("0"), "Z": Decimal("0")},
        )
        total = sum(r.target for r in results)
        assert total <= Decimal("30")
        for r in results:
            assert r.target <= Decimal("5")


# ---------------------------------------------------------------------------
# Degenerate test: all pct_stage_2 = 0 -> all targets = 0
# ---------------------------------------------------------------------------


class TestDegenerate:
    """All pct_stage_2=0 produces all-zero targets without raising (C6)."""

    def test_all_zero_pct_stage_2_returns_zero_targets(self) -> None:
        signals = [
            SectorSignal("A", pct_stage_2=Decimal("0"), mean_within_state_rank=Decimal("0.8")),
            SectorSignal("B", pct_stage_2=Decimal("0"), mean_within_state_rank=Decimal("0.5")),
            SectorSignal("C", pct_stage_2=Decimal("0"), mean_within_state_rank=Decimal("0.3")),
        ]
        current_weights = {"A": Decimal("10"), "B": Decimal("5"), "C": Decimal("3")}
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=current_weights,
            regime_cap=Decimal("40"),
        )
        for r in results:
            assert r.target == Decimal("0"), f"{r.sector}.target should be 0, got {r.target}"

    def test_all_zero_wsr_returns_zero_targets(self) -> None:
        """mean_within_state_rank=0 also produces all-zero raw scores."""
        signals = [
            SectorSignal("P", pct_stage_2=Decimal("0.8"), mean_within_state_rank=Decimal("0")),
            SectorSignal("Q", pct_stage_2=Decimal("0.5"), mean_within_state_rank=Decimal("0")),
        ]
        current_weights = {"P": Decimal("20"), "Q": Decimal("15")}
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=current_weights,
            regime_cap=Decimal("40"),
        )
        for r in results:
            assert r.target == Decimal("0")

    def test_degenerate_gaps_are_negative(self) -> None:
        """When all targets=0 but current>0, gap must be negative (honest trim signal)."""
        signals = [
            SectorSignal(sector="A", pct_stage_2=Decimal("0"), mean_within_state_rank=Decimal("0")),
        ]
        current_weights = {"A": Decimal("10")}
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=current_weights,
            regime_cap=Decimal("40"),
        )
        assert results[0].gap == Decimal("-10")


# ---------------------------------------------------------------------------
# Negative gap (trim signal) test
#
# Inputs:
#   P: pct_stage_2=0.5, mean_within_state_rank=0.6, current=20 (over-allocated)
#   Q: pct_stage_2=0.8, mean_within_state_rank=0.8, current=5
#
# max_per_sector_pct=15, regime_cap=40
#
# Hand-computed:
#   raw: P=0.30, Q=0.64   total=0.94
#   pre_cap: P=12.77, Q=27.23
#   capped:  P=12.77, Q=15.00
#   gaps:    P=-7.23, Q=+10.00
# ---------------------------------------------------------------------------


class TestNegativeGap:
    """A sector currently over target surfaces a negative gap (trim signal) (C6)."""

    @pytest.fixture
    def results(self) -> list[SectorTarget]:
        signals = [
            SectorSignal(
                sector="P",
                pct_stage_2=Decimal("0.5"),
                mean_within_state_rank=Decimal("0.6"),
            ),
            SectorSignal(
                sector="Q",
                pct_stage_2=Decimal("0.8"),
                mean_within_state_rank=Decimal("0.8"),
            ),
        ]
        current_weights = {"P": Decimal("20"), "Q": Decimal("5")}
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        return derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights=current_weights,
            regime_cap=Decimal("40"),
        )

    @pytest.fixture
    def by_sector(self, results: list[SectorTarget]) -> dict[str, SectorTarget]:
        return {r.sector: r for r in results}

    def test_p_target(self, by_sector: dict[str, SectorTarget]) -> None:
        # P pre-cap=12.77, not capped
        assert by_sector["P"].target == Decimal("12.77")

    def test_q_target_capped(self, by_sector: dict[str, SectorTarget]) -> None:
        # Q pre-cap=27.23, capped at 15
        assert by_sector["Q"].target == Decimal("15.00")

    def test_p_gap_is_negative(self, by_sector: dict[str, SectorTarget]) -> None:
        # P gap = 12.77 - 20 = -7.23 (trim signal — NOT clamped to 0)
        assert by_sector["P"].gap == Decimal("-7.23")

    def test_q_gap_is_positive(self, by_sector: dict[str, SectorTarget]) -> None:
        # Q gap = 15.00 - 5 = +10.00
        assert by_sector["Q"].gap == Decimal("10.00")

    def test_gap_not_clamped(self, by_sector: dict[str, SectorTarget]) -> None:
        """Negative gaps must NOT be clamped to 0."""
        assert by_sector["P"].gap < Decimal("0"), "Expected negative gap, got non-negative"


# ---------------------------------------------------------------------------
# SectorTarget output field types
# ---------------------------------------------------------------------------


class TestOutputTypes:
    """All numeric fields in SectorTarget must be Decimal, never float."""

    def test_all_output_fields_are_decimal(self) -> None:
        signals = [
            SectorSignal("A", pct_stage_2=Decimal("0.5"), mean_within_state_rank=Decimal("0.5")),
        ]
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights={"A": Decimal("10")},
            regime_cap=Decimal("40"),
        )
        r = results[0]
        assert isinstance(r.current, Decimal), f"current is {type(r.current)}, not Decimal"
        assert isinstance(r.target, Decimal), f"target is {type(r.target)}, not Decimal"
        assert isinstance(r.gap, Decimal), f"gap is {type(r.gap)}, not Decimal"


# ---------------------------------------------------------------------------
# Missing current weight defaults to Decimal("0")
# ---------------------------------------------------------------------------


class TestMissingCurrentWeight:
    """A sector in signals but not in current_weights defaults to current=0."""

    def test_missing_current_treated_as_zero(self) -> None:
        signals = [
            SectorSignal(
                sector="NEW",
                pct_stage_2=Decimal("0.6"),
                mean_within_state_rank=Decimal("0.7"),
            ),
        ]
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        # No entry for "NEW" in current_weights
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights={},
            regime_cap=Decimal("40"),
        )
        assert results[0].current == Decimal("0")
        # target should be min(40, 15) = 15.00 (single sector gets full regime_cap, capped)
        assert results[0].target == Decimal("15.00")
        assert results[0].gap == Decimal("15.00")


# ---------------------------------------------------------------------------
# Regression: None sector-signal fields coerced to zero (empty-sector safety)
#
# The real sector aggregator (aggregate_sector_states) emits None for
# mean_within_state_rank and pct_stage_2 when a sector has no classified
# stocks.  Constructing a SectorSignal with None must NOT raise TypeError,
# and the resulting target must be Decimal("0") with zero raw contribution.
# ---------------------------------------------------------------------------


class TestNoneSectorSignalCoercion:
    """SectorSignal(None fields) does not crash; empty sector gets target=0 (C5/T2.4)."""

    def test_mean_within_state_rank_none_does_not_raise(self) -> None:
        """Constructing SectorSignal with mean_within_state_rank=None must not raise."""
        sig = SectorSignal(
            sector="Empty",
            pct_stage_2=Decimal("0.5"),
            mean_within_state_rank=None,  # type: ignore[arg-type]
        )
        # After __post_init__, field must be coerced to Decimal("0")
        assert sig.mean_within_state_rank == Decimal("0")

    def test_pct_stage_2_none_does_not_raise(self) -> None:
        """Constructing SectorSignal with pct_stage_2=None must not raise."""
        sig = SectorSignal(
            sector="Empty",
            pct_stage_2=None,  # type: ignore[arg-type]
            mean_within_state_rank=Decimal("0.7"),
        )
        # After __post_init__, field must be coerced to Decimal("0")
        assert sig.pct_stage_2 == Decimal("0")

    def test_none_mean_within_state_rank_produces_zero_target(self) -> None:
        """A sector with mean_within_state_rank=None yields target=0."""
        signals = [
            SectorSignal(
                sector="EmptyA",
                pct_stage_2=Decimal("0.5"),
                mean_within_state_rank=None,  # type: ignore[arg-type]
            ),
            SectorSignal(
                sector="Healthy",
                pct_stage_2=Decimal("0.8"),
                mean_within_state_rank=Decimal("0.9"),
            ),
        ]
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights={"EmptyA": Decimal("5"), "Healthy": Decimal("10")},
            regime_cap=Decimal("40"),
        )
        by_sector = {r.sector: r for r in results}
        # EmptyA: raw = 0.5 * 0 = 0 → target must be 0
        got = by_sector["EmptyA"].target
        assert got == Decimal(
            "0"
        ), f"Expected target=0 for None-mean_within_state_rank sector, got {got}"
        # Healthy: has valid signals, target must be > 0
        assert by_sector["Healthy"].target > Decimal("0")

    def test_none_pct_stage_2_produces_zero_target(self) -> None:
        """A sector with pct_stage_2=None yields target=0."""
        signals = [
            SectorSignal(
                sector="EmptyB",
                pct_stage_2=None,  # type: ignore[arg-type]
                mean_within_state_rank=Decimal("0.8"),
            ),
            SectorSignal(
                sector="Healthy",
                pct_stage_2=Decimal("0.7"),
                mean_within_state_rank=Decimal("0.8"),
            ),
        ]
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights={"EmptyB": Decimal("8"), "Healthy": Decimal("6")},
            regime_cap=Decimal("40"),
        )
        by_sector = {r.sector: r for r in results}
        # EmptyB: raw = 0 * 0.8 = 0 → target must be 0
        assert by_sector["EmptyB"].target == Decimal(
            "0"
        ), f"Expected target=0 for None-pct_stage_2 sector, got {by_sector['EmptyB'].target}"

    def test_all_none_sectors_degenerate_path(self) -> None:
        """All sectors have None fields → degenerate path, all targets=0, no exception."""
        signals = [
            SectorSignal(
                sector="S1",
                pct_stage_2=None,  # type: ignore[arg-type]
                mean_within_state_rank=None,  # type: ignore[arg-type]
            ),
            SectorSignal(
                sector="S2",
                pct_stage_2=None,  # type: ignore[arg-type]
                mean_within_state_rank=None,  # type: ignore[arg-type]
            ),
            SectorSignal(
                sector="S3",
                pct_stage_2=None,  # type: ignore[arg-type]
                mean_within_state_rank=None,  # type: ignore[arg-type]
            ),
        ]
        policy = _make_policy(max_per_sector_pct=Decimal("15"))
        results = derive_sector_targets(
            sector_signals=signals,
            policy=policy,
            current_weights={"S1": Decimal("10"), "S2": Decimal("5"), "S3": Decimal("3")},
            regime_cap=Decimal("40"),
        )
        for r in results:
            assert r.target == Decimal(
                "0"
            ), f"{r.sector}.target should be 0 in all-None degenerate case, got {r.target}"
        # Verify gaps are honest (negative, since current > 0)
        assert results[0].gap == Decimal("-10")
        assert results[1].gap == Decimal("-5")
        assert results[2].gap == Decimal("-3")
