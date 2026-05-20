"""Tests for atlas.intelligence.policy.compliance — policy-compliance check.

All tests are pure (no DB). Every expected value is hand-computed independently
of the implementation.

Rules under test (C7):
    max_per_stock   — single holding weight > policy.max_per_stock_pct
    max_per_sector  — sector total > policy.max_per_sector_pct
    max_small_cap   — small-cap total > policy.max_small_cap_pct
    min_holdings    — count of holdings < policy.min_holdings
    max_positions   — count of holdings > policy.max_positions
    cash_floor      — (100 − invested) < policy.cash_floor_pct

Test inventory:
    TestMaxPerStock       — 7% holding vs 5% cap → 1 breach naming the instrument
    TestMinHoldings       — 12 holdings vs min_holdings=15 → 1 breach
    TestMaxPerSector      — sector sum=18% vs 15% cap → 1 sector breach
    TestMaxSmallCap       — small-cap total=35% vs 30% cap → 1 breach
    TestCashFloor         — weights sum to 98%, cash_floor=5% → cash=2% < 5%
    TestFullyCompliant    — well-formed book → empty list
    TestMultiBreach       — multiple simultaneous breaches → all present, none missing
    TestTypeInvariants    — ComplianceBreach fields are correct types
    TestImmutability      — ComplianceBreach is frozen
    TestEdgeCases         — boundary conditions (empty book, exact-at-limit)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.intelligence.policy.compliance import (
    ComplianceBreach,
    Holding,
    check_compliance,
)
from atlas.intelligence.policy.policy import Policy

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BASE_POLICY = Policy(
    cash_floor_pct=Decimal("5"),
    respect_regime_cap=True,
    max_per_stock_pct=Decimal("5"),
    max_per_sector_pct=Decimal("15"),
    max_small_cap_pct=Decimal("30"),
    min_holdings=10,
    max_positions=30,
    buy_states=["stage_2a", "stage_2b"],
    min_within_state_rank=Decimal("0.5"),
    min_rs_rank=Decimal("0.5"),
    hard_stop_pct=Decimal("7"),
    state_exit_trim="stage_3",
    state_exit_full="stage_4",
    trailing_stop_pct=None,
    instrument_universe="direct_equity",
    benchmark="NIFTY_500",
    rebalance_cadence="weekly",
)


def _make_holding(
    instrument_id: str,
    weight_pct: str,
    sector: str = "Technology",
    is_small_cap: bool = False,
) -> Holding:
    """Convenience constructor — weight_pct as string to avoid float."""
    return Holding(
        instrument_id=instrument_id,
        weight_pct=Decimal(weight_pct),
        sector=sector,
        is_small_cap=is_small_cap,
    )


# ---------------------------------------------------------------------------
# TestMaxPerStock — 7% holding vs 5% cap → exactly 1 breach
#
# Hand-computation:
#   holding "INFY" weight_pct = 7, policy.max_per_stock_pct = 5
#   7 > 5 → breach: actual=7, limit=5
#   Other holdings all at 3% < 5% → no breach
# ---------------------------------------------------------------------------


class TestMaxPerStock:
    """Single holding at 7% vs 5% cap produces exactly one max_per_stock breach."""

    def _make_book(self) -> list[Holding]:
        return [
            _make_holding("INFY", "7", sector="Technology"),
            _make_holding("TCS", "3", sector="Technology"),
            _make_holding("HDFCBANK", "3", sector="Financials"),
            _make_holding("ICICIBANK", "3", sector="Financials"),
            _make_holding("RELIANCE", "3", sector="Energy"),
            _make_holding("ONGC", "3", sector="Energy"),
            _make_holding("SUNPHARMA", "3", sector="Healthcare"),
            _make_holding("DRREDDY", "3", sector="Healthcare"),
            _make_holding("WIPRO", "3", sector="Technology"),
            _make_holding("TATASTEEL", "3", sector="Materials"),
        ]

    def test_exactly_one_breach(self) -> None:
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        stock_breaches = [b for b in breaches if b.rule == "max_per_stock"]
        assert (
            len(stock_breaches) == 1
        ), f"Expected 1 max_per_stock breach, got {len(stock_breaches)}: {stock_breaches}"

    def test_breach_names_the_instrument(self) -> None:
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        stock_breach = next(b for b in breaches if b.rule == "max_per_stock")
        assert (
            "INFY" in stock_breach.message
        ), f"Expected 'INFY' in breach message, got: {stock_breach.message!r}"

    def test_actual_equals_seven(self) -> None:
        """Hand-computed: INFY weight_pct=7 → actual must be Decimal('7')."""
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        stock_breach = next(b for b in breaches if b.rule == "max_per_stock")
        assert stock_breach.actual == Decimal(
            "7"
        ), f"Expected actual=Decimal('7'), got {stock_breach.actual!r}"

    def test_limit_equals_five(self) -> None:
        """Hand-computed: policy.max_per_stock_pct=5 → limit must be Decimal('5')."""
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        stock_breach = next(b for b in breaches if b.rule == "max_per_stock")
        assert stock_breach.limit == Decimal(
            "5"
        ), f"Expected limit=Decimal('5'), got {stock_breach.limit!r}"

    def test_no_spurious_stock_breach(self) -> None:
        """Holdings at exactly the cap (5%) should NOT produce a breach."""
        policy = Policy(
            **{
                **_BASE_POLICY.__dict__,
                "max_per_stock_pct": Decimal("5"),
            }
        )
        book = [_make_holding(f"STOCK{i}", "5", sector=f"SEC{i}") for i in range(10)]
        breaches = check_compliance(book, policy)
        stock_breaches = [b for b in breaches if b.rule == "max_per_stock"]
        assert (
            stock_breaches == []
        ), f"At exactly the cap (5%=5%) there should be no breach; got {stock_breaches}"


# ---------------------------------------------------------------------------
# TestMinHoldings — 12 holdings vs min_holdings=15 → 1 breach
#
# Hand-computation:
#   len(holdings) = 12, policy.min_holdings = 15
#   12 < 15 → breach: actual=12, limit=15
# ---------------------------------------------------------------------------


class TestMinHoldings:
    """12-holding book vs min_holdings=15 produces exactly one min_holdings breach."""

    def _make_policy(self) -> Policy:
        return Policy(
            **{
                **_BASE_POLICY.__dict__,
                "min_holdings": 15,
                "max_per_stock_pct": Decimal("10"),  # avoid per-stock collisions
                "max_per_sector_pct": Decimal("50"),  # avoid per-sector collisions
                "cash_floor_pct": Decimal("0"),  # avoid cash collision
            }
        )

    def _make_book(self) -> list[Holding]:
        return [_make_holding(f"STOCK{i}", "3", sector=f"SEC{i}") for i in range(12)]

    def test_exactly_one_breach(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        min_breaches = [b for b in breaches if b.rule == "min_holdings"]
        assert (
            len(min_breaches) == 1
        ), f"Expected 1 min_holdings breach, got {len(min_breaches)}: {min_breaches}"

    def test_actual_equals_twelve(self) -> None:
        """Hand-computed: 12 holdings → actual must be Decimal('12')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "min_holdings")
        assert breach.actual == Decimal(
            "12"
        ), f"Expected actual=Decimal('12'), got {breach.actual!r}"

    def test_limit_equals_fifteen(self) -> None:
        """Hand-computed: min_holdings=15 → limit must be Decimal('15')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "min_holdings")
        assert breach.limit == Decimal("15"), f"Expected limit=Decimal('15'), got {breach.limit!r}"

    def test_no_breach_at_minimum(self) -> None:
        """Exactly 15 holdings (= min_holdings) must NOT produce a breach."""
        book = [_make_holding(f"STOCK{i}", "3", sector=f"SEC{i}") for i in range(15)]
        breaches = check_compliance(book, self._make_policy())
        min_breaches = [b for b in breaches if b.rule == "min_holdings"]
        assert (
            min_breaches == []
        ), f"At exactly min_holdings (15) there should be no breach; got {min_breaches}"


# ---------------------------------------------------------------------------
# TestMaxPerSector — Technology sector sum=18% vs 15% cap → 1 sector breach
#
# Hand-computation:
#   Technology: INFY(8%) + WIPRO(10%) = 18%
#   policy.max_per_sector_pct = 15
#   18 > 15 → breach for "Technology": actual=18, limit=15
#   Other sectors each sum to <=10% (well under 15%) → no sector breach
# ---------------------------------------------------------------------------


class TestMaxPerSector:
    """Technology sector at 18% vs 15% cap produces exactly one max_per_sector breach."""

    def _make_policy(self) -> Policy:
        return Policy(
            **{
                **_BASE_POLICY.__dict__,
                "max_per_stock_pct": Decimal("10"),  # avoid per-stock collision
                "max_per_sector_pct": Decimal("15"),
                "cash_floor_pct": Decimal("0"),
            }
        )

    def _make_book(self) -> list[Holding]:
        return [
            # Technology: 8 + 10 = 18% → over the 15% cap
            _make_holding("INFY", "8", sector="Technology"),
            _make_holding("WIPRO", "10", sector="Technology"),
            # Financials: 5 + 5 = 10% → ok
            _make_holding("HDFCBANK", "5", sector="Financials"),
            _make_holding("ICICIBANK", "5", sector="Financials"),
            # Energy: 4 + 4 = 8% → ok
            _make_holding("RELIANCE", "4", sector="Energy"),
            _make_holding("ONGC", "4", sector="Energy"),
            # Healthcare: 3 + 3 = 6% → ok
            _make_holding("SUNPHARMA", "3", sector="Healthcare"),
            _make_holding("DRREDDY", "3", sector="Healthcare"),
            # Materials: 4% → ok
            _make_holding("TATASTEEL", "4", sector="Materials"),
            # Consumer: 4% → ok
            _make_holding("HINDUNILVR", "4", sector="Consumer"),
        ]

    def test_exactly_one_sector_breach(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        sector_breaches = [b for b in breaches if b.rule == "max_per_sector"]
        assert (
            len(sector_breaches) == 1
        ), f"Expected 1 max_per_sector breach, got {len(sector_breaches)}: {sector_breaches}"

    def test_breach_names_technology_sector(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_per_sector")
        assert (
            "Technology" in breach.message
        ), f"Expected 'Technology' in message, got: {breach.message!r}"

    def test_actual_equals_eighteen(self) -> None:
        """Hand-computed: INFY(8%) + WIPRO(10%) = 18% → actual=Decimal('18')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_per_sector")
        assert breach.actual == Decimal(
            "18"
        ), f"Expected actual=Decimal('18'), got {breach.actual!r}"

    def test_limit_equals_fifteen(self) -> None:
        """Hand-computed: max_per_sector_pct=15 → limit=Decimal('15')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_per_sector")
        assert breach.limit == Decimal("15"), f"Expected limit=Decimal('15'), got {breach.limit!r}"

    def test_no_breach_at_cap(self) -> None:
        """Sector summing to exactly 15% (= cap) must NOT breach."""
        book = [
            _make_holding("INFY", "8", sector="Technology"),
            _make_holding("WIPRO", "7", sector="Technology"),  # 8+7=15=cap
        ]
        breaches = check_compliance(book, self._make_policy())
        sector_breaches = [b for b in breaches if b.rule == "max_per_sector"]
        assert (
            sector_breaches == []
        ), f"At exactly sector cap (15%) there should be no breach; got {sector_breaches}"


# ---------------------------------------------------------------------------
# TestMaxSmallCap — small-cap total=35% vs 30% cap → 1 breach
#
# Hand-computation:
#   Small-cap holdings: SC1(10%) + SC2(12%) + SC3(13%) = 35%
#   policy.max_small_cap_pct = 30
#   35 > 30 → breach: actual=35, limit=30
# ---------------------------------------------------------------------------


class TestMaxSmallCap:
    """Small-cap total at 35% vs 30% cap produces exactly one max_small_cap breach."""

    def _make_policy(self) -> Policy:
        return Policy(
            **{
                **_BASE_POLICY.__dict__,
                "max_per_stock_pct": Decimal("15"),  # avoid per-stock collision
                "max_per_sector_pct": Decimal("50"),  # avoid sector collision
                "max_small_cap_pct": Decimal("30"),
                "cash_floor_pct": Decimal("0"),
                "min_holdings": 5,
            }
        )

    def _make_book(self) -> list[Holding]:
        return [
            # Small-cap: 10+12+13 = 35% → over 30% cap
            _make_holding("SC1", "10", sector="Materials", is_small_cap=True),
            _make_holding("SC2", "12", sector="Materials", is_small_cap=True),
            _make_holding("SC3", "13", sector="Materials", is_small_cap=True),
            # Large-cap (not small): 5+5 = 10%
            _make_holding("LC1", "5", sector="Financials", is_small_cap=False),
            _make_holding("LC2", "5", sector="Energy", is_small_cap=False),
        ]

    def test_exactly_one_breach(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        sc_breaches = [b for b in breaches if b.rule == "max_small_cap"]
        assert (
            len(sc_breaches) == 1
        ), f"Expected 1 max_small_cap breach, got {len(sc_breaches)}: {sc_breaches}"

    def test_actual_equals_thirty_five(self) -> None:
        """Hand-computed: 10+12+13=35 → actual=Decimal('35')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_small_cap")
        assert breach.actual == Decimal(
            "35"
        ), f"Expected actual=Decimal('35'), got {breach.actual!r}"

    def test_limit_equals_thirty(self) -> None:
        """Hand-computed: max_small_cap_pct=30 → limit=Decimal('30')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_small_cap")
        assert breach.limit == Decimal("30"), f"Expected limit=Decimal('30'), got {breach.limit!r}"

    def test_no_breach_at_exact_cap(self) -> None:
        """Small-cap total exactly at cap (30%) must NOT breach."""
        book = [
            _make_holding("SC1", "15", sector="Materials", is_small_cap=True),
            _make_holding("SC2", "15", sector="Materials", is_small_cap=True),
            _make_holding("LC1", "5", sector="Financials", is_small_cap=False),
        ]
        breaches = check_compliance(book, self._make_policy())
        sc_breaches = [b for b in breaches if b.rule == "max_small_cap"]
        assert (
            sc_breaches == []
        ), f"At exactly small-cap cap (30%) there should be no breach; got {sc_breaches}"


# ---------------------------------------------------------------------------
# TestCashFloor — weights sum to 98%, cash_floor=5% → cash=2% < 5%
#
# Hand-computation:
#   10 holdings each at 9.8% → invested = 98%
#   cash = 100 - 98 = 2%
#   policy.cash_floor_pct = 5
#   2 < 5 → breach: actual=2, limit=5
# ---------------------------------------------------------------------------


class TestCashFloor:
    """Book with 98% invested and 5% cash floor produces one cash_floor breach."""

    def _make_policy(self) -> Policy:
        return Policy(
            **{
                **_BASE_POLICY.__dict__,
                "cash_floor_pct": Decimal("5"),
                "max_per_stock_pct": Decimal("15"),  # avoid per-stock collision
                "max_per_sector_pct": Decimal("50"),  # avoid sector collision
            }
        )

    def _make_book(self) -> list[Holding]:
        # 10 holdings × 9.8% = 98% invested; cash = 2%
        return [_make_holding(f"STOCK{i}", "9.8", sector=f"SEC{i}") for i in range(10)]

    def test_exactly_one_breach(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        cash_breaches = [b for b in breaches if b.rule == "cash_floor"]
        assert (
            len(cash_breaches) == 1
        ), f"Expected 1 cash_floor breach, got {len(cash_breaches)}: {cash_breaches}"

    def test_actual_equals_two(self) -> None:
        """Hand-computed: 100 - 98 = 2 → actual cash = Decimal('2')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "cash_floor")
        assert breach.actual == Decimal("2"), f"Expected actual=Decimal('2'), got {breach.actual!r}"

    def test_limit_equals_five(self) -> None:
        """Hand-computed: cash_floor_pct=5 → limit=Decimal('5')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "cash_floor")
        assert breach.limit == Decimal("5"), f"Expected limit=Decimal('5'), got {breach.limit!r}"

    def test_no_breach_at_exact_floor(self) -> None:
        """Invested=95% → cash=5% = floor → NOT a breach (boundary is exclusive)."""
        # 10 holdings × 9.5% = 95%; cash = 5% = cash_floor_pct
        book = [_make_holding(f"STOCK{i}", "9.5", sector=f"SEC{i}") for i in range(10)]
        breaches = check_compliance(book, self._make_policy())
        cash_breaches = [b for b in breaches if b.rule == "cash_floor"]
        assert (
            cash_breaches == []
        ), f"At exactly cash_floor_pct (5%) there should be no breach; got {cash_breaches}"


# ---------------------------------------------------------------------------
# TestFullyCompliant — well-formed book returns empty list
#
# Hand-computation:
#   10 holdings × 4% = 40% invested; cash = 60% ≥ 5%
#   Each holding: 4% ≤ max_per_stock_pct=5%
#   Each sector has 1 holding: 4% ≤ max_per_sector_pct=15%
#   No small-cap holdings: small_cap_total=0% ≤ 30%
#   count=10 ≥ min_holdings=10 and ≤ max_positions=30
#   → NO breaches
# ---------------------------------------------------------------------------


class TestFullyCompliant:
    """A well-formed book produces an empty breach list."""

    def _make_book(self) -> list[Holding]:
        return [
            _make_holding(f"STOCK{i}", "4", sector=f"SEC{i}", is_small_cap=False) for i in range(10)
        ]

    def test_returns_empty_list(self) -> None:
        result = check_compliance(self._make_book(), _BASE_POLICY)
        assert result == [], f"Expected empty list for compliant book, got {result}"

    def test_return_type_is_list(self) -> None:
        result = check_compliance(self._make_book(), _BASE_POLICY)
        assert isinstance(result, list), f"Expected list, got {type(result)}"


# ---------------------------------------------------------------------------
# TestMultiBreach — multiple simultaneous breaches
#
# Policy: max_per_stock=5, max_per_sector=15, max_small_cap=20, min_holdings=10,
#         max_positions=30, cash_floor=5
#
# Book (7 holdings — under min_holdings=10):
#   BIGSTOCK  Tech     8%  large_cap  → violates max_per_stock (8>5)
#   TCS       Tech     5%  large_cap  → at per-stock cap; no per-stock breach
#   INFY      Tech     4%  large_cap  → Tech total = 8+5+4 = 17% > 15% → sector breach
#   SC1       Pharma   4%  small_cap  → small_cap
#   SC2       Energy   4%  small_cap  → small_cap total = 4+4 = 8% < 20% → no small_cap breach
#   LC1       Banks    4%  large_cap
#   LC2       Metals   4%  large_cap
#   invested  = 8+5+4+4+4+4+4 = 33%
#   cash      = 100-33 = 67% ≥ 5% → no cash breach
#   count     = 7 < min_holdings=10 → min_holdings breach
#
# Breaches expected (exactly 3):
#   1. max_per_stock for BIGSTOCK (actual=8, limit=5)
#   2. max_per_sector for Technology (actual=17, limit=15)
#   3. min_holdings (actual=7, limit=10)
#
# Verified non-breaches:
#   small_cap total = 4+4 = 8% < 20% → no max_small_cap breach
#   max_positions=30, count=7 < 30 → no max_positions breach
#   cash = 100-33 = 67 ≥ 5 → no cash breach
# ---------------------------------------------------------------------------


class TestMultiBreach:
    """Multiple rules breached simultaneously — all expected, none missing, none spurious."""

    def _make_policy(self) -> Policy:
        return Policy(
            **{
                **_BASE_POLICY.__dict__,
                "max_per_stock_pct": Decimal("5"),
                "max_per_sector_pct": Decimal("15"),
                "max_small_cap_pct": Decimal("20"),
                "min_holdings": 10,
                "max_positions": 30,
                "cash_floor_pct": Decimal("5"),
            }
        )

    def _make_book(self) -> list[Holding]:
        return [
            # Technology sector: 8+5+4 = 17% → sector breach (>15%)
            # BIGSTOCK also: 8% → per-stock breach (>5%)
            # TCS at exactly 5% cap → no per-stock breach
            _make_holding("BIGSTOCK", "8", sector="Technology", is_small_cap=False),
            _make_holding("TCS", "5", sector="Technology", is_small_cap=False),
            _make_holding("INFY", "4", sector="Technology", is_small_cap=False),
            # Small-cap: 4+4 = 8% < 20% → no small_cap breach
            _make_holding("SC1", "4", sector="Pharma", is_small_cap=True),
            _make_holding("SC2", "4", sector="Energy", is_small_cap=True),
            # Large-cap, distinct sectors
            _make_holding("LC1", "4", sector="Banks", is_small_cap=False),
            _make_holding("LC2", "4", sector="Metals", is_small_cap=False),
            # count=7 < min_holdings=10 → min_holdings breach
        ]

    def test_max_per_stock_breach_present(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        rules = {b.rule for b in breaches}
        assert "max_per_stock" in rules, f"Expected max_per_stock breach in {rules}"

    def test_max_per_sector_breach_present(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        rules = {b.rule for b in breaches}
        assert "max_per_sector" in rules, f"Expected max_per_sector breach in {rules}"

    def test_min_holdings_breach_present(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        rules = {b.rule for b in breaches}
        assert "min_holdings" in rules, f"Expected min_holdings breach in {rules}"

    def test_no_max_small_cap_breach(self) -> None:
        """small_cap total=17% < 20% → no max_small_cap breach."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        sc_breaches = [b for b in breaches if b.rule == "max_small_cap"]
        assert sc_breaches == [], f"Expected no max_small_cap breach (17%<20%), got {sc_breaches}"

    def test_no_max_positions_breach(self) -> None:
        """count=7 < max_positions=30 → no max_positions breach."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        mp_breaches = [b for b in breaches if b.rule == "max_positions"]
        assert mp_breaches == [], f"Expected no max_positions breach (7<30), got {mp_breaches}"

    def test_no_cash_floor_breach(self) -> None:
        """invested=46%, cash=54% ≥ 5% floor → no cash_floor breach."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        cf_breaches = [b for b in breaches if b.rule == "cash_floor"]
        assert cf_breaches == [], f"Expected no cash_floor breach (54%≥5%), got {cf_breaches}"

    def test_exactly_three_breaches(self) -> None:
        """Exactly 3 breaches total: max_per_stock + max_per_sector + min_holdings."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        assert (
            len(breaches) == 3
        ), f"Expected exactly 3 breaches, got {len(breaches)}: {[b.rule for b in breaches]}"


# ---------------------------------------------------------------------------
# TestMaxPositions — count of holdings above max_positions → 1 breach
#
# Hand-computation:
#   5 holdings, policy.max_positions=3
#   5 > 3 → breach: actual=5, limit=3
# ---------------------------------------------------------------------------


class TestMaxPositions:
    """More holdings than max_positions produces one max_positions breach."""

    def _make_policy(self) -> Policy:
        return Policy(
            **{
                **_BASE_POLICY.__dict__,
                "max_positions": 3,
                "min_holdings": 1,
                "max_per_stock_pct": Decimal("30"),  # avoid per-stock collision
                "max_per_sector_pct": Decimal("50"),  # avoid sector collision
                "cash_floor_pct": Decimal("0"),
            }
        )

    def _make_book(self) -> list[Holding]:
        return [_make_holding(f"STOCK{i}", "3", sector=f"SEC{i}") for i in range(5)]

    def test_exactly_one_breach(self) -> None:
        breaches = check_compliance(self._make_book(), self._make_policy())
        mp_breaches = [b for b in breaches if b.rule == "max_positions"]
        assert (
            len(mp_breaches) == 1
        ), f"Expected 1 max_positions breach, got {len(mp_breaches)}: {mp_breaches}"

    def test_actual_equals_five(self) -> None:
        """Hand-computed: 5 holdings → actual=Decimal('5')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_positions")
        assert breach.actual == Decimal("5"), f"Expected actual=Decimal('5'), got {breach.actual!r}"

    def test_limit_equals_three(self) -> None:
        """Hand-computed: max_positions=3 → limit=Decimal('3')."""
        breaches = check_compliance(self._make_book(), self._make_policy())
        breach = next(b for b in breaches if b.rule == "max_positions")
        assert breach.limit == Decimal("3"), f"Expected limit=Decimal('3'), got {breach.limit!r}"


# ---------------------------------------------------------------------------
# TestTypeInvariants — ComplianceBreach fields have correct types
# ---------------------------------------------------------------------------


class TestTypeInvariants:
    """ComplianceBreach fields must be str (rule, message) and Decimal (actual, limit)."""

    def _make_book(self) -> list[Holding]:
        return [_make_holding("OVERWEIGHT", "7", sector="Technology")]

    def test_rule_is_str(self) -> None:
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        for breach in breaches:
            assert isinstance(breach.rule, str), f"breach.rule must be str, got {type(breach.rule)}"

    def test_message_is_str(self) -> None:
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        for breach in breaches:
            assert isinstance(
                breach.message, str
            ), f"breach.message must be str, got {type(breach.message)}"

    def test_actual_is_decimal(self) -> None:
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        for breach in breaches:
            assert isinstance(
                breach.actual, Decimal
            ), f"breach.actual must be Decimal, got {type(breach.actual)}"

    def test_limit_is_decimal(self) -> None:
        breaches = check_compliance(self._make_book(), _BASE_POLICY)
        for breach in breaches:
            assert isinstance(
                breach.limit, Decimal
            ), f"breach.limit must be Decimal, got {type(breach.limit)}"


# ---------------------------------------------------------------------------
# TestImmutability — ComplianceBreach must be frozen
# ---------------------------------------------------------------------------


class TestImmutability:
    """ComplianceBreach must be a frozen dataclass."""

    def test_frozen(self) -> None:
        breach = ComplianceBreach(
            rule="max_per_stock",
            message="test",
            actual=Decimal("7"),
            limit=Decimal("5"),
        )
        with pytest.raises((AttributeError, TypeError)):
            breach.rule = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestHoldingDataclass — Holding fields and immutability
# ---------------------------------------------------------------------------


class TestHoldingDataclass:
    """Holding must be a frozen dataclass with the documented fields."""

    def test_construction(self) -> None:
        h = Holding(
            instrument_id="TEST",
            weight_pct=Decimal("5"),
            sector="Technology",
            is_small_cap=False,
        )
        assert h.instrument_id == "TEST"
        assert h.weight_pct == Decimal("5")
        assert h.sector == "Technology"
        assert h.is_small_cap is False

    def test_frozen(self) -> None:
        h = Holding(
            instrument_id="TEST",
            weight_pct=Decimal("5"),
            sector="Technology",
            is_small_cap=False,
        )
        with pytest.raises((AttributeError, TypeError)):
            h.weight_pct = Decimal("99")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestEdgeCases — boundary conditions
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge conditions: empty book, exact-at-limit boundaries."""

    def test_empty_book_triggers_min_holdings(self) -> None:
        """Empty holdings list → min_holdings breach (0 < min_holdings)."""
        breaches = check_compliance([], _BASE_POLICY)
        rules = {b.rule for b in breaches}
        assert (
            "min_holdings" in rules
        ), f"Empty book should produce min_holdings breach; rules={rules}"

    def test_empty_book_no_cash_floor_breach(self) -> None:
        """Empty book → invested=0, cash=100 ≥ cash_floor_pct=5 → no cash breach."""
        breaches = check_compliance([], _BASE_POLICY)
        cf_breaches = [b for b in breaches if b.rule == "cash_floor"]
        assert (
            cf_breaches == []
        ), f"Empty book should not produce cash_floor breach; got {cf_breaches}"

    def test_exactly_at_max_per_stock_is_not_breach(self) -> None:
        """weight_pct == max_per_stock_pct is NOT a breach (strict >)."""
        book = [_make_holding(f"STOCK{i}", "5", sector=f"SEC{i}") for i in range(10)]
        breaches = check_compliance(book, _BASE_POLICY)
        stock_breaches = [b for b in breaches if b.rule == "max_per_stock"]
        assert (
            stock_breaches == []
        ), f"At exactly cap (5%=5%) there should be no per-stock breach; got {stock_breaches}"

    def test_single_holding_fully_invested_cash_breach(self) -> None:
        """Single 100% holding → cash=0 < cash_floor_pct=5 → cash breach."""
        book = [_make_holding("BIGSTOCK", "100", sector="Technology")]
        policy = Policy(
            **{
                **_BASE_POLICY.__dict__,
                "max_per_stock_pct": Decimal("100"),  # avoid per-stock collision
                "max_per_sector_pct": Decimal("100"),  # avoid sector collision
                "min_holdings": 1,
                "cash_floor_pct": Decimal("5"),
            }
        )
        breaches = check_compliance(book, policy)
        cf_breaches = [b for b in breaches if b.rule == "cash_floor"]
        assert len(cf_breaches) == 1, f"Expected 1 cash_floor breach (cash=0%), got {cf_breaches}"
