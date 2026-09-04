"""The build-time half of the US platform's freshness contract
(scripts/global_market/freshness_guard.py) — a copy of tests/unit/test_producer_registry.py.

India's 2026-07 incident: the consolidation deleted builders while the board still read
their tables, and nothing tied a guarded table to a producer. Here the registry exists
from day one, EMPTY but valid in Phase 0, so the first producer that lands without its
cron step (or whose step is later dropped) goes red in CI before it can merge.

Pure filesystem — no DB, no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_GUARD = _REPO / "scripts" / "global_market" / "freshness_guard.py"

pytestmark = pytest.mark.unit


def _guard():
    """Load freshness_guard by path (it lives in scripts/global_market, not an importable pkg)."""
    spec = importlib.util.spec_from_file_location("global_freshness_guard", _GUARD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_guarded_table_has_a_registered_producer():
    g = _guard()
    guarded = {t for t, _c, _l in g.KEY_TABLES + g.BOARD_TABLES}
    missing = guarded - set(g.PRODUCERS)
    assert not missing, (
        f"guarded table(s) with no producer in PRODUCERS: {sorted(missing)} — "
        "register the builder that writes each, or remove it from the guard."
    )


def test_every_producer_is_wired_into_an_orchestrator():
    """The exact invariant the incident violated — a producer that no cron runs."""
    g = _guard()
    problems = g.check_producers()
    assert not problems, "orphaned guarded table(s):\n  " + "\n  ".join(problems)


def test_registered_producers_are_only_for_guarded_tables():
    """Keep the registry honest — no stale producer entries for tables no longer guarded."""
    g = _guard()
    guarded = {t for t, _c, _l in g.KEY_TABLES + g.BOARD_TABLES}
    orphan_entries = set(g.PRODUCERS) - guarded
    assert not orphan_entries, (
        f"PRODUCERS lists table(s) that aren't guarded: {sorted(orphan_entries)}"
    )


def test_a_commented_out_step_does_not_satisfy_the_registry():
    """The Phase 0 orchestrators list every Phase 1 step commented out. A producer token
    that appears only inside a comment must still count as orphaned."""
    g = _guard()
    live = g._live_lines(
        "# step ingest_prices.py   (commented)\n  # also commented\nstep score_etfs.py"
    )
    assert "ingest_prices.py" not in live
    assert "score_etfs.py" in live


def test_both_orchestrators_exist_and_are_the_ones_the_guard_reads():
    """An orchestrator path typo would make check_producers read nothing and pass vacuously."""
    g = _guard()
    assert g.ORCHESTRATORS == [
        "scripts/ops/atlas_global_daily.sh",
        "scripts/ops/atlas_global_weekly.sh",
    ]
    for o in g.ORCHESTRATORS:
        assert (_REPO / o).exists(), f"{o} missing — the registry would pass vacuously"
