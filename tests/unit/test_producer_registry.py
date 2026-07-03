"""The build-time half of the freshness contract (see scripts/ops/freshness_guard.py).

The 2026-07 incident: the consolidation deleted the sector/macro/holdings builders
while the board still read their tables, and nothing tied a guarded table to a
producer — so the orphaning shipped and went unnoticed for a week. These tests make
that class of change impossible to merge: every table the freshness guard watches
MUST have a producer wired into an orchestrator. Delete a builder (or drop its cron
step) and this goes red in CI before it can land.

Pure filesystem — no DB, no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _guard():
    """Load freshness_guard by path (it lives in scripts/ops, not an importable pkg)."""
    spec = importlib.util.spec_from_file_location(
        "freshness_guard", _REPO / "scripts" / "ops" / "freshness_guard.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_every_guarded_table_has_a_registered_producer():
    g = _guard()
    guarded = {t for t, _c, _l in g.KEY_TABLES + g.BOARD_TABLES}
    missing = guarded - set(g.PRODUCERS)
    assert not missing, (
        f"guarded table(s) with no producer in PRODUCERS: {sorted(missing)} — "
        "register the builder that writes each, or remove it from the guard."
    )


@pytest.mark.unit
def test_every_producer_is_wired_into_an_orchestrator():
    """The exact invariant the incident violated — a producer that no cron runs."""
    g = _guard()
    problems = g.check_producers()
    assert not problems, "orphaned guarded table(s):\n  " + "\n  ".join(problems)


@pytest.mark.unit
def test_registered_producers_are_only_for_guarded_tables():
    """Keep the registry honest — no stale producer entries for tables no longer guarded."""
    g = _guard()
    guarded = {t for t, _c, _l in g.KEY_TABLES + g.BOARD_TABLES}
    orphan_entries = set(g.PRODUCERS) - guarded
    assert not orphan_entries, (
        f"PRODUCERS lists table(s) that aren't guarded: {sorted(orphan_entries)}"
    )
