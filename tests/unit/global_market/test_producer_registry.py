"""Global-only checks on scripts/global_market/freshness_guard.py.

The registry invariants shared by both markets — every guarded table has a producer, every
producer is wired into an orchestrator, no stale producer entries — run against this guard
too, parametrised over both markets in tests/unit/test_producer_registry.py. What is left
here is specific to the US guard: the Phase 0 orchestrators carry the whole Phase 1 step
list COMMENTED OUT, and the orchestrator paths the guard reads must be the real files.

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
