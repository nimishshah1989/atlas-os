"""Tests for tier_assignment — 20-day ADV rank → 5 liquidity tiers."""

from __future__ import annotations

from datetime import date

import pytest
from atlas.intelligence.conviction.tier_assignment import (
    assign_tier_from_rank,
    compute_tier_membership,
)

from atlas.db import get_engine


class TestAssignTierFromRank:
    def test_rank_1_is_megacap(self) -> None:
        assert assign_tier_from_rank(1) == "tier_1_megacap"

    def test_rank_50_is_megacap(self) -> None:
        assert assign_tier_from_rank(50) == "tier_1_megacap"

    def test_rank_51_is_largecap(self) -> None:
        assert assign_tier_from_rank(51) == "tier_2_largecap"

    def test_rank_150_is_largecap(self) -> None:
        assert assign_tier_from_rank(150) == "tier_2_largecap"

    def test_rank_300_is_uppermid(self) -> None:
        assert assign_tier_from_rank(300) == "tier_3_uppermid"

    def test_rank_999_is_smallcap(self) -> None:
        assert assign_tier_from_rank(999) == "tier_5_smallcap"

    def test_rank_1001_is_untiered(self) -> None:
        assert assign_tier_from_rank(1001) == "untiered"


@pytest.mark.integration
class TestComputeTierMembership:
    def test_returns_dataframe_with_required_columns(self) -> None:
        engine = get_engine()
        df = compute_tier_membership(engine, as_of=date(2026, 4, 1))
        assert {
            "instrument_id",
            "date",
            "tier",
            "adv_rank",
            "adv_20d",
        } <= set(df.columns)

    def test_top_50_are_tier_1(self) -> None:
        engine = get_engine()
        df = compute_tier_membership(engine, as_of=date(2026, 4, 1))
        if df.empty:
            pytest.skip("no OHLCV data for this date in this env")
        top_50 = df.nsmallest(50, "adv_rank")
        assert (top_50["tier"] == "tier_1_megacap").all()

    def test_returns_at_most_1000_rows(self) -> None:
        engine = get_engine()
        df = compute_tier_membership(engine, as_of=date(2026, 4, 1))
        assert len(df) <= 1000

    def test_no_untiered_in_result(self) -> None:
        engine = get_engine()
        df = compute_tier_membership(engine, as_of=date(2026, 4, 1))
        if df.empty:
            pytest.skip("no OHLCV data for this date in this env")
        assert (df["tier"] != "untiered").all()
