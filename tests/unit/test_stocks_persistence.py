"""Persistence-contract tests for ``atlas.compute.stocks`` (M3).

These lock the set of columns written to ``atlas_stock_metrics_daily`` so the
migration, backfill, and frontend stay aligned with the 7-window RS lock.
"""

from __future__ import annotations

import pytest

from atlas.compute.primitives import RS_WINDOWS
from atlas.compute.stocks import METRICS_COLUMNS


@pytest.mark.unit
def test_metrics_persists_all_seven_tier_rs_windows() -> None:
    for w in RS_WINDOWS:
        assert f"rs_{w}_tier" in METRICS_COLUMNS, f"rs_{w}_tier not persisted"


@pytest.mark.unit
def test_metrics_persists_all_seven_gold_rs_windows() -> None:
    for w in RS_WINDOWS:
        assert f"rs_{w}_tier_gold" in METRICS_COLUMNS, f"rs_{w}_tier_gold not persisted"


@pytest.mark.unit
def test_metrics_persists_ret_24m_for_sector_aggregation() -> None:
    # Sector bottom-up RS at 24m is the weighted mean of stock ret_24m / gold;
    # the sector pipeline reads ret_24m back from atlas_stock_metrics_daily.
    assert "ret_24m" in METRICS_COLUMNS
