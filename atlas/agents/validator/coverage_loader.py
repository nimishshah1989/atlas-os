"""Coverage map loader for Phase B schema/coverage validation.

Parses ``coverage_map.yaml`` and returns a list of ``TableCoverage``
dataclasses. Validates required fields and raises ``ValueError`` on
malformed entries so callers fail fast rather than silently skipping tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

COVERAGE_MAP_PATH = Path(__file__).parent / "coverage_map.yaml"

_VALID_EXPECTED_DATES = frozenset(["business_days", "any"])


@dataclass(frozen=True)
class TableCoverage:
    """Parsed expected-coverage spec for one table."""

    table_name: str
    description: str
    expected_dates: str  # "business_days" | "any"
    coverage_tolerance_pct: float
    expected_instruments_min: int | None = None
    expected_sectors_min: int | None = None
    null_forbidden_columns: tuple[str, ...] = field(default_factory=tuple)
    null_allowed_columns: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_coverage_map(path: Path | None = None) -> list[TableCoverage]:
    """Parse the coverage YAML and return validated ``TableCoverage`` objects.

    Args:
        path: Override the default YAML path. Used in tests.

    Returns:
        List of ``TableCoverage``, one per table entry.

    Raises:
        ValueError: If a table entry is missing required fields or has an
                    invalid ``expected_dates`` value.
        FileNotFoundError: If the YAML file does not exist.
    """
    resolved = path or COVERAGE_MAP_PATH
    with resolved.open() as fh:
        raw: dict = yaml.safe_load(fh)

    tables_raw: dict = raw.get("tables", {})
    if not isinstance(tables_raw, dict) or not tables_raw:
        raise ValueError("coverage_map.yaml must have a non-empty 'tables' key")

    results: list[TableCoverage] = []
    for table_name, spec in tables_raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Entry '{table_name}' must be a mapping, got {type(spec)}")

        # Required fields
        for required in ("expected_dates", "coverage_tolerance_pct"):
            if required not in spec:
                raise ValueError(f"Table '{table_name}' is missing required field '{required}'")

        expected_dates = spec["expected_dates"]
        if expected_dates not in _VALID_EXPECTED_DATES:
            raise ValueError(
                f"Table '{table_name}': expected_dates must be one of "
                f"{sorted(_VALID_EXPECTED_DATES)}, got '{expected_dates}'"
            )

        tolerance = float(spec["coverage_tolerance_pct"])
        if not (0.0 <= tolerance <= 100.0):
            raise ValueError(
                f"Table '{table_name}': coverage_tolerance_pct must be 0–100, got {tolerance}"
            )

        null_forbidden = tuple(spec.get("null_forbidden_columns") or [])
        null_allowed = tuple(spec.get("null_allowed_columns") or [])

        results.append(
            TableCoverage(
                table_name=table_name,
                description=str(spec.get("description", "")),
                expected_dates=expected_dates,
                coverage_tolerance_pct=tolerance,
                expected_instruments_min=spec.get("expected_instruments_min"),
                expected_sectors_min=spec.get("expected_sectors_min"),
                null_forbidden_columns=null_forbidden,
                null_allowed_columns=null_allowed,
            )
        )

    return results


__all__ = ["COVERAGE_MAP_PATH", "TableCoverage", "load_coverage_map"]
