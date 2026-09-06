"""seed_benchmarks — the roles against the DDL's CHECK constraint, and resolution.

Pure filesystem: the roles are cross-checked against ``scripts/global_market/ddl/00_core.sql``;
the one resolved row in the resolution test is SPY as the real 2026-09-04 directories describe
it (``scaffold_identity``).
"""

from __future__ import annotations

import re

import pytest

from tests.unit.global_market.scaffold_identity import scaffold_rows
from tests.unit.global_market.script_loader import SCRIPTS_DIR, load_global_script

sb = load_global_script("seed_benchmarks")

DDL = SCRIPTS_DIR / "ddl" / "00_core.sql"
CODES = [c for c, _ in sb.BENCHMARKS]

pytestmark = pytest.mark.unit


def test_roles_are_exactly_the_ddl_check_set() -> None:
    m = re.search(r"role IN \(([^)]+)\)", DDL.read_text())
    assert m, "benchmark_master role CHECK not found in 00_core.sql"
    allowed = set(re.findall(r"'([a-z]+)'", m.group(1)))
    assert allowed == {r for _, r in sb.BENCHMARKS} and len(sb.BENCHMARKS) == 7


def test_resolve_names_every_code_without_an_active_row() -> None:
    rows, missing = sb.resolve({})
    assert rows == [] and missing == CODES
    spy = next(r for r in scaffold_rows(("SPY",)) if r.symbol == "SPY")
    rows, missing = sb.resolve({"SPY": (spy.instrument_id, spy.name)})
    assert rows == [("SPY", spy.instrument_id, "market", "State Street SPDR S&P 500 ETF Trust")]
    assert missing == CODES[1:]
