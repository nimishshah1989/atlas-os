"""The build-time half of the freshness contract — for BOTH markets.

scripts/ops/freshness_guard.py (India, atlas_foundation) and
scripts/global_market/freshness_guard.py (US, atlas_global) each carry a producer
registry; every invariant below runs against each of them.

The 2026-07 incident: the consolidation deleted the sector/macro/holdings builders
while the board still read their tables, and nothing tied a guarded table to a
producer — so the orphaning shipped and went unnoticed for a week. These tests make
that class of change impossible to merge: every table a freshness guard watches
MUST have a producer wired into an orchestrator. Delete a builder (or drop its cron
step) and this goes red in CI before it can land. The US registry is EMPTY but valid
in Phase 0, so the first producer that lands there without its cron step trips it too.

Pure filesystem — no DB, no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GUARDS = {
    "india": _REPO / "scripts" / "ops" / "freshness_guard.py",
    "global": _REPO / "scripts" / "global_market" / "freshness_guard.py",
}

pytestmark = pytest.mark.unit


@pytest.fixture(params=list(_GUARDS), ids=list(_GUARDS))
def guard(request: pytest.FixtureRequest) -> ModuleType:
    """Load one market's freshness_guard by path (scripts/ is not an importable package).

    Executing the module imports the market's DB helper (``_db`` / ``_gdb``) — sys.path
    work only, no connection is opened.
    """
    market: str = request.param
    spec = importlib.util.spec_from_file_location(f"{market}_freshness_guard", _GUARDS[market])
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_guarded_table_has_a_registered_producer(guard: ModuleType) -> None:
    guarded = {t for t, _c, _l in guard.KEY_TABLES + guard.BOARD_TABLES}
    missing = guarded - set(guard.PRODUCERS)
    assert not missing, (
        f"guarded table(s) with no producer in PRODUCERS: {sorted(missing)} — "
        "register the builder that writes each, or remove it from the guard."
    )


def test_every_producer_is_wired_into_an_orchestrator(guard: ModuleType) -> None:
    """The exact invariant the incident violated — a producer that no cron runs."""
    problems = guard.check_producers()
    assert not problems, "orphaned guarded table(s):\n  " + "\n  ".join(problems)


def test_registered_producers_are_only_for_guarded_tables(guard: ModuleType) -> None:
    """Keep the registry honest — no stale producer entries for tables no longer guarded."""
    guarded = {t for t, _c, _l in guard.KEY_TABLES + guard.BOARD_TABLES}
    orphan_entries = set(guard.PRODUCERS) - guarded
    assert not orphan_entries, (
        f"PRODUCERS lists table(s) that aren't guarded: {sorted(orphan_entries)}"
    )
