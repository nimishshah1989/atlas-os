#!/usr/bin/env python3
"""Pre-commit hook: enforce bounded-context import boundaries.

Each top-level package under atlas/ is a bounded context. They MUST NOT
reach into each other's internals. Allowed exchange happens through:
  - The package's __init__.py public exports
  - The shared kernel (atlas/primitives/, atlas/db.py)
  - An explicit edge: a whole context (ALLOWED_EDGES) or, narrower, one module
    subtree of a context (ALLOWED_SUBTREE_EDGES — e.g. the pure scorers under
    atlas.lenses.compute, but not the I/O in atlas.lenses.data)

This stops the modulith from quietly turning into a tangle of cross-cutting
imports. The day you outgrow it and need to extract a context into its own
service, the boundaries are already crisp.

Reads staged Python files, parses imports, fails on forbidden combinations.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

# Bounded contexts under atlas/. Each may import:
#   - itself
#   - the shared kernel (primitives, db, config)
# Adjust as new contexts appear.
CONTEXTS: tuple[str, ...] = (
    "atlas.compute",
    "atlas.intraday",
    "atlas.lenses",
    "atlas.portfolio",  # pure strategy/engine math; I/O lives in scripts/foundation
    "atlas.desk",  # pure agent prompts/validators; I/O lives in scripts/foundation
    # US market (ADR-0006): its own schema (atlas_global), its own pipelines. Reuses
    # India's PURE code only, through the subtree edges below — never India's I/O.
    "atlas.global_market",
)

SHARED_KERNEL: tuple[str, ...] = (
    "atlas.primitives",
    "atlas.db",
    "atlas.config",
    "atlas.preflight",  # one-off; fine to import from
)

# Direction rules: which contexts may depend on which.
# Default: NO context may import another context's internals.
ALLOWED_EDGES: set[tuple[str, str]] = {
    # simulation → compute: simulation uses open_compute_session / bulk_upsert from
    # compute._session. Both contexts share the same Postgres schema and connection
    # pool. Extracting the session manager into the shared kernel (atlas.db) is the
    # long-term fix; for now this explicit edge makes the dependency visible.
    ("atlas.simulation", "atlas.compute"),
    # api → simulation: the API surface for custom portfolios (M7 Phase 3) is a
    # thin HTTP wrapper over atlas.simulation.custom orchestrators (validate,
    # save, trigger background backtest). The simulation context owns the
    # business logic; api owns the request/response shape.
    ("atlas.api", "atlas.simulation"),
    # api → compute: api endpoints read from atlas tables via the same
    # open_compute_session helper used everywhere else (statement_timeout=0
    # reset on the pooled connection). Same long-term fix as above — promote
    # session manager into atlas.db.
    ("atlas.api", "atlas.compute"),
    # health → compute: atlas.health.runs uses open_compute_session to write
    # pipeline run rows with statement_timeout=0 (avoids Supabase pooler
    # timeout on run-log inserts). Pre-existing edge; documented here so
    # staged edits to runs.py don't trip the boundary check.
    ("atlas.health", "atlas.compute"),
    # validation → compute: tier2_metrics.py and tier3_states.py call
    # open_compute_session to read from atlas tables for hand-validation
    # spot-checks. Pre-existing edge (present before 2026-05 health audit).
    # Long-term fix: extract session factory into atlas.db shared kernel.
    ("atlas.validation", "atlas.compute"),
    # SP07: api → agents. POST /api/agents/invoke is a thin HTTP wrapper
    # over the specialist invoker. The agents context owns the LLM loop
    # and tool registry; api owns request/response shape and auth. The
    # API imports the specialist registry + invoke_routed through the
    # public __init__.py of atlas.agents.specialists (the package's
    # public surface) — same pattern as api → simulation above.
    ("atlas.api", "atlas.agents"),
    # SP04 Stage 4a: api → intelligence. POST /api/admin/proposals/{id}/*
    # is a thin HTTP wrapper over atlas.intelligence.conviction.optimization
    # persistence (apply/reject/snooze). Business logic stays in
    # intelligence; api owns request/response shape + admin role gate.
    ("atlas.api", "atlas.intelligence"),
}

# Subtree edges: (importing context, allowed module PREFIX in another context).
# Narrower than ALLOWED_EDGES — an import `imp` from `my_ctx` passes only if
# `imp == prefix` or `imp.startswith(prefix + ".")`, so the rest of the target
# context stays forbidden. Widening one is a visible diff, which is the point.
ALLOWED_SUBTREE_EDGES: set[tuple[str, str]] = {
    # global_market → lenses.compute: the PURE scorers (score_technical,
    # score_fundamental, score_valuation — dict in, dict out) are reused verbatim
    # on US inputs (ADR-0006 Decision 2). atlas.lenses.data and
    # atlas.lenses.pipeline read atlas_foundation and stay forbidden: the global
    # tree must never see the India schema, even transitively.
    ("atlas.global_market", "atlas.lenses.compute"),
    # global_market → compute.signal_eval: rank-IC / decile-spread math behind
    # /methodology/signal — pure functions over DataFrames the caller loads.
    ("atlas.global_market", "atlas.compute.signal_eval"),
    # global_market → compute._session: open_compute_session (statement_timeout=0
    # reset on the pooled connection). Same long-term fix as the ALLOWED_EDGES
    # users above — promote the session manager into atlas.db.
    ("atlas.global_market", "atlas.compute._session"),
    # global_market → portfolio.engine: buy-and-hold replay with a fractional
    # quantum is the book of record for basket NAV (plan M2); one accounting
    # truth, not a second engine.
    ("atlas.global_market", "atlas.portfolio.engine"),
}


def staged_python_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        text=True,
    )
    paths = [Path(line.strip()) for line in out.splitlines() if line.strip()]
    return [p for p in paths if p.suffix == ".py" and str(p).startswith("atlas/")]


def context_of(module: str) -> str | None:
    for ctx in CONTEXTS:
        if module == ctx or module.startswith(ctx + "."):
            return ctx
    return None


def is_kernel(module: str) -> bool:
    return any(module == k or module.startswith(k + ".") for k in SHARED_KERNEL)


def subtree_allowed(my_ctx: str, module: str) -> bool:
    """True if ``module`` falls under a prefix ``my_ctx`` is explicitly allowed to import."""
    return any(
        ctx == my_ctx and (module == prefix or module.startswith(prefix + "."))
        for ctx, prefix in ALLOWED_SUBTREE_EDGES
    )


def imports_in(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
    return out


def context_of_path(path: Path) -> str | None:
    parts = path.parts
    if len(parts) < 2 or parts[0] != "atlas":
        return None
    return f"atlas.{parts[1]}"


def forbidden_imports(my_ctx: str, imports: list[str]) -> list[tuple[str, str]]:
    """Return ``(target_context, module)`` for each import that crosses a boundary illegally.

    Pure: the rule in one place, so it can be exercised without staging files.
    """
    out: list[tuple[str, str]] = []
    for imp in imports:
        if not imp.startswith("atlas."):
            continue
        if is_kernel(imp):
            continue
        other_ctx = context_of(imp)
        if other_ctx is None or other_ctx == my_ctx:
            continue
        if (my_ctx, other_ctx) in ALLOWED_EDGES:
            continue
        if subtree_allowed(my_ctx, imp):
            continue
        out.append((other_ctx, imp))
    return out


def main() -> int:
    failures: list[str] = []
    for f in staged_python_files():
        my_ctx = context_of_path(f)
        if my_ctx not in CONTEXTS:
            continue
        for other_ctx, imp in forbidden_imports(my_ctx, imports_in(f)):
            failures.append(f"{f}: {my_ctx} → {other_ctx} (forbidden) — `{imp}`")

    if failures:
        print("✗ Forbidden cross-context imports:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nRule: each top-level package under atlas/ is a bounded context.\n"
            "Cross-context imports go through the shared kernel\n"
            "(atlas/primitives, atlas/db, atlas/config) or through the public\n"
            "__init__.py of the target context. If you need a new edge, add it\n"
            "to ALLOWED_EDGES (whole context) or, preferably, ALLOWED_SUBTREE_EDGES\n"
            "(one module prefix, e.g. atlas.lenses.compute for the pure scorers)\n"
            "in scripts/hooks/check_module_boundaries.py and document why in a\n"
            "commit message.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
