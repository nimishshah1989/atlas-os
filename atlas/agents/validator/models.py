"""Shared data models for the validator agent (Phases A–C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class Finding:
    """A single validator finding — database integrity or frontend accuracy issue."""

    finding_class: str  # 'insensible_value' | 'data_gap' | 'frontend_diff' | etc.
    severity: str  # 'P0' | 'P1' | 'P2' | 'P3'
    surface: str  # table.column  OR  component.field
    identifier: str  # PK-based string or data-validator-id
    expected_value: str
    actual_value: str
    evidence: dict[str, Any] = field(default_factory=dict)
    remediation: str = ""
    delta_abs: Decimal | None = None
    delta_pct: Decimal | None = None
