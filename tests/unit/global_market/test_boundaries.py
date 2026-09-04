"""The bounded-context rule for atlas.global_market, run in CI.

scripts/hooks/check_module_boundaries.py only ever ran from pre-commit, so nothing enforced
it on a merge. ADR-0006 lets the global tree reuse India's PURE code (the subtree edges:
lenses.compute scorers, compute.signal_eval, compute._session, portfolio.engine) and
nothing else — atlas.lenses.data / atlas.lenses.pipeline read atlas_foundation, and the
global tree must never see that schema, even transitively. Asserted here against the
hook's own pure rule and against every real file under atlas/global_market/.

Pure filesystem — no DB, no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[3]
_HOOK = _REPO / "scripts" / "hooks" / "check_module_boundaries.py"
_GLOBAL = "atlas.global_market"

# India I/O — reads atlas_foundation; forbidden to the global tree.
_INDIA_IO = ["atlas.lenses.data.adapters", "atlas.lenses.pipeline"]
# The pure edges ADR-0006 declares in ALLOWED_SUBTREE_EDGES.
_PURE_EDGES = [
    "atlas.lenses.compute.technical",
    "atlas.compute.signal_eval",
    "atlas.compute._session",
    "atlas.portfolio.engine",
]

pytestmark = pytest.mark.unit


def _hook() -> ModuleType:
    """Load the hook by path (scripts/hooks is not an importable package)."""
    spec = importlib.util.spec_from_file_location("check_module_boundaries", _HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_real_module(dotted: str) -> bool:
    return (_REPO / (dotted.replace(".", "/") + ".py")).is_file()


@pytest.mark.parametrize("module", _INDIA_IO)
def test_india_io_is_forbidden_to_the_global_tree(module: str) -> None:
    assert _is_real_module(module), f"{module} is not a real module — the case proves nothing"
    assert _hook().forbidden_imports(_GLOBAL, [module]) == [("atlas.lenses", module)]


@pytest.mark.parametrize("module", _PURE_EDGES)
def test_declared_pure_edges_are_allowed(module: str) -> None:
    assert _is_real_module(module), f"{module} is not a real module — the case proves nothing"
    assert _hook().forbidden_imports(_GLOBAL, [module]) == []


def test_every_global_market_file_respects_the_boundary() -> None:
    """The real tree, through the real scanner — the check pre-commit would have run."""
    h = _hook()
    files = sorted((_REPO / "atlas" / "global_market").rglob("*.py"))
    assert files, "atlas/global_market has no Python files — the walk would pass vacuously"
    violations: list[str] = []
    for f in files:
        rel = f.relative_to(_REPO)
        ctx = h.context_of_path(rel)
        assert ctx == _GLOBAL, rel
        for other_ctx, imp in h.forbidden_imports(ctx, h.imports_in(f)):
            violations.append(f"{rel}: {ctx} → {other_ctx} — `{imp}`")
    assert not violations, "forbidden cross-context imports:\n  " + "\n  ".join(violations)
