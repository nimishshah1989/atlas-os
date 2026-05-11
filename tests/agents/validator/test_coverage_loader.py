"""Tests for atlas.agents.validator.coverage_loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atlas.agents.validator.coverage_loader import (
    TableCoverage,
    load_coverage_map,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "coverage_map.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_coverage_map_parses_default_yaml() -> None:
    """Default coverage_map.yaml loads without error and contains expected tables."""
    result = load_coverage_map()
    assert isinstance(result, list)
    assert len(result) > 0

    table_names = {tc.table_name for tc in result}
    assert "atlas_stock_states_daily" in table_names
    assert "atlas_market_regime_daily" in table_names
    assert "atlas_sector_states_daily" in table_names


@pytest.mark.unit
def test_load_coverage_map_validates_schema(tmp_path: Path) -> None:
    """Loaded TableCoverage objects have correct field types and values."""
    yaml_content = """\
        tables:
          my_table:
            description: Test table
            expected_dates: business_days
            expected_instruments_min: 100
            null_forbidden_columns:
              - col_a
              - col_b
            null_allowed_columns:
              - col_c
            coverage_tolerance_pct: 99.0
    """
    path = _write_yaml(tmp_path, yaml_content)
    result = load_coverage_map(path)

    assert len(result) == 1
    tc = result[0]
    assert isinstance(tc, TableCoverage)
    assert tc.table_name == "my_table"
    assert tc.expected_dates == "business_days"
    assert tc.expected_instruments_min == 100
    assert tc.null_forbidden_columns == ("col_a", "col_b")
    assert tc.null_allowed_columns == ("col_c",)
    assert tc.coverage_tolerance_pct == 99.0


@pytest.mark.unit
def test_load_coverage_map_raises_on_missing_required_field(tmp_path: Path) -> None:
    """Missing required field raises ValueError with the table name in the message."""
    yaml_content = """\
        tables:
          bad_table:
            description: Missing expected_dates and coverage_tolerance_pct
    """
    path = _write_yaml(tmp_path, yaml_content)
    with pytest.raises(ValueError, match="bad_table"):
        load_coverage_map(path)


@pytest.mark.unit
def test_load_coverage_map_raises_on_invalid_expected_dates(tmp_path: Path) -> None:
    """Invalid expected_dates value raises ValueError."""
    yaml_content = """\
        tables:
          bad_table:
            expected_dates: weekly
            coverage_tolerance_pct: 90.0
    """
    path = _write_yaml(tmp_path, yaml_content)
    with pytest.raises(ValueError, match="expected_dates"):
        load_coverage_map(path)


@pytest.mark.unit
def test_load_coverage_map_tolerance_zero_allowed(tmp_path: Path) -> None:
    """coverage_tolerance_pct of 0 is valid (presence not enforced)."""
    yaml_content = """\
        tables:
          sparse_table:
            expected_dates: any
            coverage_tolerance_pct: 0
    """
    path = _write_yaml(tmp_path, yaml_content)
    result = load_coverage_map(path)
    assert len(result) == 1
    assert result[0].coverage_tolerance_pct == 0.0
