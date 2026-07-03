"""The Admin "Data status" tab must show EXACTLY the tables the freshness guard watches.

Same anti-drift idea as test_producer_registry, one layer up: the data-health tab reads two
hand-maintained lists in health.ts (FOUNDATION_TABLES = derived, SOURCE_TABLES = raw feeds).
If a new producer is added to the guard but not surfaced here (or a dropped table lingers),
the operator dashboard silently lies about coverage. This asserts the tab's union equals the
guard's KEY_TABLES + BOARD_TABLES, so that drift is a red CI check, not a stale dashboard.

Pure filesystem — parses health.ts, no DB, no network.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_HEALTH_TS = _REPO / "frontend" / "src" / "lib" / "queries" / "health.ts"


def _guard_tables() -> set[str]:
    spec = importlib.util.spec_from_file_location(
        "freshness_guard", _REPO / "scripts" / "ops" / "freshness_guard.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {t for t, _c, _l in mod.KEY_TABLES + mod.BOARD_TABLES}


def _ts_array_body(const: str) -> str:
    """The [...] literal body of `const <NAME> ... = [ ... ]` in health.ts."""
    m = re.search(rf"const {const}\b.*?=\s*\[(.*?)\n\]", _HEALTH_TS.read_text(), re.S)
    assert m, f"{const} not found in health.ts"
    return m.group(1)


def _data_status_surface() -> set[str]:
    foundation = set(re.findall(r"table:\s*'([a-z0-9_]+)'", _ts_array_body("FOUNDATION_TABLES")))
    source = set(re.findall(r"name:\s*'([a-z0-9_]+)'", _ts_array_body("SOURCE_TABLES")))
    return foundation | source


@pytest.mark.unit
def test_data_status_tab_shows_exactly_the_guarded_tables():
    guard, surface = _guard_tables(), _data_status_surface()
    missing = guard - surface  # guarded but not shown on the tab (the silent-lie case)
    extra = surface - guard  # shown but not guarded (dropped/renamed table lingering)
    assert not missing, f"data-status tab is missing guarded table(s): {sorted(missing)}"
    assert not extra, f"data-status tab lists non-guarded table(s): {sorted(extra)}"
